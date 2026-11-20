"""Uygulama logosundan (static/brand-mark.svg) simgeleri üretir.

    python packaging/make_icon.py

  akademik-iz.ico, akademik-iz-128.png   uygulamanın kendi simgesi (logo)
  akademik-iz-setup.ico                  kurulum dosyasının simgesi: logo açık bir kurulum kutusunun içinden çıkar
  wizard-small.bmp, wizard-large.bmp     kurulum sihirbazının görselleri

SVG'ler Playwright'ın Chromium'uyla saydam arka planda çizilir (ayrı bir SVG kütüphanesi gerekmez); ICO, Pillow ile
Windows'un kullandığı boyutları içerecek biçimde yazılır.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SVG = (ROOT / "static" / "brand-mark.svg").read_text(encoding="utf-8")
OUT = Path(__file__).resolve().parent
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _logo_inner() -> str:
    """Logonun <svg> etiketinin içi (başka bir SVG'ye yerleştirmek için)."""
    return re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", SVG.strip(), flags=re.S)


# Açık bir karton kurulum kutusu; logo kutunun içinden yukarı doğru çıkar. 64 birimlik çizim alanı.
SETUP_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="front" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e2a95a"/><stop offset="1" stop-color="#b9772c"/></linearGradient>
    <linearGradient id="side" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c88a3e"/><stop offset="1" stop-color="#94591d"/></linearGradient>
    <linearGradient id="flap" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f0c27f"/><stop offset="1" stop-color="#d79a4d"/></linearGradient>
  </defs>
  <!-- kutunun içi (arka) -->
  <polygon points="6,33 16,25 58,25 48,33" fill="#6e4214"/>
  <!-- arka kapaklar -->
  <polygon points="16,25 58,25 54,15 20,15" fill="url(#flap)" opacity=".9"/>
  <!-- içinden çıkan logo -->
  <g transform="translate(13,2) scale(0.5)" fill="none">{_logo_inner()}</g>
  <!-- ön yüz ve sağ yan -->
  <polygon points="6,33 48,33 48,60 6,60" fill="url(#front)"/>
  <polygon points="48,33 58,25 58,52 48,60" fill="url(#side)"/>
  <!-- ön kapaklar (dışa açık) -->
  <polygon points="6,33 48,33 42,41 0,41" fill="url(#flap)"/>
  <polygon points="48,33 58,25 64,32 54,40" fill="#e0a75c"/>
  <!-- bant ve kenar çizgileri -->
  <rect x="22" y="41" width="10" height="19" fill="#f6dcae" opacity=".55"/>
  <polyline points="6,60 48,60 58,52" fill="none" stroke="#7a4612" stroke-width="1" opacity=".5"/>
</svg>"""


def _render(page, svg: str) -> Image.Image:
    sized = svg.replace("<svg ", '<svg width="512" height="512" ', 1)
    page.set_content(f"<html><body style='margin:0;background:transparent'><div style='width:512px;height:512px'>{sized}</div></body></html>")
    png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": 512, "height": 512})
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=1)
        image = _render(page, SVG)
        setup = _render(page, SETUP_SVG)
        browser.close()
    image.save(OUT / "akademik-iz.ico", sizes=SIZES)
    image.resize((128, 128), Image.LANCZOS).save(OUT / "akademik-iz-128.png")
    setup.save(OUT / "akademik-iz-setup.ico", sizes=SIZES)
    setup.resize((256, 256), Image.LANCZOS).save(OUT / "akademik-iz-setup-256.png")
    # Kurulum sihirbazının küçük görseli (sağ üst köşe): kutudaki logo, beyaz zemin.
    small = Image.new("RGB", (110, 116), "white")
    icon = setup.resize((100, 100), Image.LANCZOS)
    small.paste(icon, (5, 8), icon)
    small.save(OUT / "wizard-small.bmp")
    # Kurulum sihirbazının sol şeridi (164x314, iki kat çözünürlük): marka mavisi zemin, ortada kutudaki logo.
    big = Image.new("RGB", (328, 628), (29, 78, 216))
    box = setup.resize((240, 240), Image.LANCZOS)
    big.paste(box, (44, 170), box)
    big.save(OUT / "wizard-large.bmp")
    print("simgeler yazildi:", OUT)


if __name__ == "__main__":
    main()
