"""Yerel PDF bağışları, sınırlı OCR işleri ve sahiplik belirteci."""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import secrets
import shutil
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
import httpx
from fastapi import HTTPException
from .config import ROOT, OPENALEX_PARAMS
from .library_common import atomic_json, clean_title, category_for, CATEGORY_MAP
from .pdf_resolve import render_thumb

BASE = ROOT / "data/library"
FILES = BASE / "donations"
META = BASE / "donations.json"
LIMIT = 40 * 1024 * 1024
QUOTA = 5 * 1024**3
LOCK = asyncio.Lock()
WORKERS = asyncio.Semaphore(2)
JOBS: dict[str, dict] = {}
TASKS: dict[str, asyncio.Task] = {}
RATES = defaultdict(deque)
LICENSES = {"Kendi eserim", "CC BY", "CC BY-SA", "CC0", "Diğer açık lisans"}

def records():
    try:
        value = json.loads(META.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def ident(value):
    if not re.fullmatch(r"[a-f0-9]{32}", value or ""):
        raise HTTPException(404, "Kayıt bulunamadı")
    return value

def public(record):
    return {k: v for k, v in record.items() if k not in {"owner_hash", "original_name", "ip"}}

def list_items(cat="", q="", limit=120):
    values = [public(r) for r in records().values() if r.get("status") == "done" and (not cat or r.get("category") == cat)]
    words = q.casefold().split()
    if words:
        text_dir = BASE / "text"
        selected = []
        for value in values:
            text = " ".join([value.get("title", ""), " ".join(value.get("authors", [])), value.get("note", "")]).casefold()
            if not all(word in text for word in words):
                try:
                    text += (text_dir / f"{value['id']}.txt").read_text()[:2_000_000].casefold()
                except OSError:
                    pass
            if all(word in text for word in words):
                selected.append(value)
        values = selected
    return sorted(values, key=lambda r: r.get("created_at", ""), reverse=True)[:max(1, min(limit, 500))]

def get(value):
    result = records().get(ident(value))
    if not result:
        raise HTTPException(404, "Bağış bulunamadı")
    return public(result)

async def update(value, **fields):
    async with LOCK:
        all_records = records()
        if value not in all_records:
            return
        all_records[value].update(fields)
        await asyncio.to_thread(atomic_json, META, all_records)

def pdf_info(path):
    from pypdf import PdfReader
    reader = PdfReader(path, strict=False)
    if reader.is_encrypted:
        raise ValueError("Şifreli PDF kabul edilmiyor.")
    count = len(reader.pages)
    if not 1 <= count <= 300:
        raise ValueError("PDF 1–300 sayfa içermeli.")
    # İlk sayfayı çözümlemek bozuk içerik ağacını da yakalar.
    reader.pages[0].get_contents()
    return count

async def upload(file, fields, ip):
    if not str(file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Yalnız PDF kabul edilir.")
    value, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
    FILES.mkdir(parents=True, exist_ok=True)
    path = FILES / f"{value}.pdf"
    async with LOCK:
        now = time.time(); attempts = RATES[ip]
        while attempts and now - attempts[0] > 3600:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(429, "Saatlik 10 yükleme sınırına ulaşıldı.")
        attempts.append(now)
        used = sum(p.stat().st_size for p in BASE.rglob("*") if p.is_file())
        size = 0
        try:
            with path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    if not size and not chunk.startswith(b"%PDF-"):
                        raise HTTPException(400, "Geçerli PDF imzası bulunamadı.")
                    size += len(chunk)
                    if size > LIMIT:
                        raise HTTPException(413, "PDF en fazla 40 MB olabilir.")
                    if used + size + LIMIT > QUOTA:
                        raise HTTPException(507, "Kütüphane disk kotası dolu.")
                    target.write(chunk)
            if size == 0:
                raise HTTPException(400, "PDF boş.")
            try:
                pages = await asyncio.to_thread(pdf_info, path)
            except Exception:
                raise HTTPException(400, "PDF bozuk, şifreli veya 300 sayfadan uzun.") from None
            all_records = records()
            category = str(fields.get("category", ""))
            year = str(fields.get("year", ""))[:4]
            original = re.sub(r"[^\w\s.-]", "", str(file.filename))[:120]
            all_records[value] = {
                "id": value, "title": clean_title(fields.get("title") or Path(original).stem)[:500],
                "authors": [x.strip()[:120] for x in str(fields.get("authors", "")).split(",") if x.strip()][:20],
                "year": int(year) if year.isdigit() else None, "category": category if category in CATEGORY_MAP else "genel",
                "title_manual": bool(fields.get("title")) and clean_title(fields.get("title")) != clean_title(Path(original).stem.replace("_", " ").replace("-", " ")),
                "category_manual": category in CATEGORY_MAP, "license": fields.get("license") if fields.get("license") in LICENSES else "", "pages": pages,
                "note": re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[e-posta gizlendi]", str(fields.get("note", "")))[:1500],
                "ocr": "pending", "status": "queued", "created_at": datetime.now(timezone.utc).isoformat(),
                "owner_hash": hashlib.sha256(token.encode()).hexdigest(), "original_name": original,
                "thumb": f"/api/library/thumb?donation={value}", "pdf": f"/api/library/donations/{value}/pdf", "source": "Bağış",
            }
            await asyncio.to_thread(atomic_json, META, all_records)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
    JOBS[value] = {"id": value, "status": "queued", "step": "Dosya kontrol ediliyor", "progress": 10}
    TASKS[value] = asyncio.create_task(process(value))
    TASKS[value].add_done_callback(lambda _: TASKS.pop(value, None))
    return {"id": value, "job_id": value, "owner_token": token}

def extract(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    texts = [(p.extract_text() or "")[:100000] for p in reader.pages]
    return texts, any(len(t.strip()) < 30 for t in texts)

_OCR_LANG = None
def ocr_lang():
    """Kurulu Tesseract dilleri: Türkçe paketi yoksa yalnız İngilizce (yoksa OCR tamamen düşerdi)."""
    global _OCR_LANG
    if _OCR_LANG is None:
        import subprocess
        try:
            out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10).stdout.split()
        except (OSError, subprocess.SubprocessError):
            out = []
        _OCR_LANG = "+".join(x for x in ("tur", "eng") if x in out) or "eng"
    return _OCR_LANG

async def ocr(value, path, texts):
    output = FILES / f"{value}.ocr.pdf"
    if shutil.which("ocrmypdf"):
        JOBS[value].update(step=f"OCR · {len(texts)} sayfa yerelde işleniyor", progress=30)
        proc = await asyncio.create_subprocess_exec("ocrmypdf", "--language", ocr_lang(), "--skip-text", "--optimize", "1", str(path), str(output), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), 600)
            if proc.returncode == 0 and output.exists():
                output.replace(path)
                return (await asyncio.to_thread(extract, path))[0], "ocrmypdf"
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill(); await proc.wait()
            if asyncio.current_task().cancelling():
                raise
        finally:
            output.unlink(missing_ok=True)
    try:
        import pytesseract
        import pypdfium2 as pdfium
        if not shutil.which("tesseract"):
            return texts, "OCR yok, metinsiz sayfalar eklendi"
        # Tek sayfa render'ı, sınırlı çözünürlük, toplam 10 dakika bütçe.
        deadline = time.monotonic() + 600
        for i, text in enumerate(texts):
            if len(text.strip()) >= 30 or time.monotonic() > deadline:
                continue
            JOBS[value].update(step=f"OCR · sayfa {i + 1}/{len(texts)}", progress=25 + int(i / len(texts) * 40))
            def page_text():
                doc = pdfium.PdfDocument(str(path))
                try:
                    page = doc[i]
                    bitmap = page.render(scale=min(2, 2000 / max(page.get_size())))
                    try:
                        return pytesseract.image_to_string(bitmap.to_pil(), lang=ocr_lang(), timeout=min(45, max(1, deadline - time.monotonic())))
                    finally:
                        bitmap.close(); page.close()
                finally:
                    doc.close()
            try:
                texts[i] = await asyncio.to_thread(page_text)
            except Exception:
                continue
        return texts, "tesseract"
    except ImportError:
        return texts, "OCR yok, metinsiz sayfalar eklendi"

async def metadata(text, title):
    match = re.search(r"10\.\d{4,9}/[^\s\"<>]+", text)
    doi = match[0].rstrip(".,;)") if match else ""
    isbn = re.search(r"ISBN(?:-1[03])?[:\s]*([\dXx -]{10,20})", text, re.I)
    result = {"doi": doi, "isbn": isbn[1].strip() if isbn else ""}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get("https://api.openalex.org/works" + ("/https://doi.org/" + doi if doi else ""), params=OPENALEX_PARAMS | ({} if doi else {"search": title, "per_page": 3}))
            if response.status_code != 200:
                return result
            works = [response.json()] if doi else response.json().get("results", [])
            for work in works:
                name = clean_title(work.get("title", ""))
                if not doi and SequenceMatcher(None, title.casefold(), name.casefold()).ratio() < .85:
                    continue
                topic = work.get("primary_topic") or {}
                result.update(title=name, authors=[a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])[:20]], year=work.get("publication_year"), topic=topic.get("display_name", ""), category=category_for(" ".join((topic.get(k) or {}).get("display_name", "") for k in ("field", "domain"))))
                break
    except (httpx.HTTPError, ValueError):
        pass
    return result

async def process(value):
    async with WORKERS:
        try:
            await update(value, status="processing")
            JOBS[value].update(status="processing", step="Metin çıkarılıyor", progress=20)
            path = FILES / f"{value}.pdf"
            texts, scanned = await asyncio.to_thread(extract, path)
            ocr_status = "Metin katmanı var"
            if scanned:
                texts, ocr_status = await ocr(value, path, texts)
            all_text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[e-posta gizlendi]", "\n\n".join(texts))
            (BASE / "text").mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread((BASE / "text" / f"{value}.txt").write_text, all_text, encoding="utf-8")
            JOBS[value].update(step="Künye aranıyor", progress=70)
            original = records()[value]
            meta = await metadata("\n".join(texts[:3]), original["title"])
            JOBS[value].update(step="Kategori atanıyor", progress=85)
            category = original["category"] if original.get("category_manual") else meta.pop("category", "genel")
            if category == "genel":
                category = category_for(all_text[:30000])
            meta.pop("category", None)
            # Kullanıcının açıkça yazdığı künye korunur; boş alanlar tamamlanır.
            fields = {k: v for k, v in meta.items() if v and (k not in ("title", "authors", "year") or not original.get(k) or (k == "title" and not original.get("title_manual")))}
            try:
                await asyncio.to_thread(render_thumb, str(path), FILES / f"{value}.jpg")
            except Exception:
                pass
            await update(value, **fields, category=category, ocr=ocr_status, status="done")
            JOBS[value].update(status="done", step="Rafa yerleştirildi", progress=100, category=category, category_name=CATEGORY_MAP[category][0])
        except asyncio.CancelledError:
            raise
        except Exception:
            await update(value, status="error", error="PDF işlenemedi. Dosyayı kaldırıp yeniden yükleyebilirsin.")
            JOBS[value].update(status="error", step="PDF işlenemedi", progress=0)

async def remove(value, token):
    ident(value)
    async with LOCK:
        entries = records(); record = entries.get(value)
        if not record:
            raise HTTPException(404, "Bağış bulunamadı")
        if not secrets.compare_digest(record["owner_hash"], hashlib.sha256(token.encode()).hexdigest()):
            raise HTTPException(403, "Bu bağışı yalnız yükleyen tarayıcı silebilir.")
    task = TASKS.get(value)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    async with LOCK:
        entries = records(); entries.pop(value, None)
        await asyncio.to_thread(atomic_json, META, entries)
        for path in [FILES / f"{value}.pdf", FILES / f"{value}.jpg", BASE / "text" / f"{value}.txt"]:
            path.unlink(missing_ok=True)
        JOBS.pop(value, None)
    return {"deleted": True}
