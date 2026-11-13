// Araçlar: doçentlik / akademik teşvik puan hesabı ve danışman bulucu. app.js'in yardımcılarını (api, setView, esc, icon…) kullanır.
const T_CHECK = '<svg class="t-tick" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
const T_CROSS = '<svg class="t-tick" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
const tNum = (n) => Number(n || 0).toLocaleString("tr-TR", { maximumFractionDigits: 1 });
const tBar = (have, need, cls = "") => `<div class="t-bar ${cls}"><i style="width:${Math.max(2, Math.min(100, need ? have / need * 100 : 100))}%"></i></div>`;
const tRing = (have, need, label) => {
  const k = Math.max(0, Math.min(1, need ? have / need : 1)), c = 2 * Math.PI * 52;
  return `<div class="t-ring ${have >= need ? "ok" : ""}"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" class="t-ring-bg"/><circle cx="60" cy="60" r="52" class="t-ring-fg" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - k)}"/></svg><div><b>${tNum(have)}</b><span>/ ${tNum(need)} ${esc(label)}</span></div></div>`;
};

// ------------------------------------------------------------------ puan hesaplayıcı (akademisyen sayfasındaki sekme)
function mountScore(host, jobId) {
  if (!host || !jobId || host.dataset.job === jobId) return;
  host.dataset.job = jobId;
  host.innerHTML = `<div class="t-score-head"><div><h3>Doçentlik ve akademik teşvik puanı</h3><p class="muted">Bu profildeki yayınlar, dergi çeyrekleri, yönetilen tezler ve derslerden hesaplanır.</p></div>
      <div class="t-seg" role="tablist"><button type="button" data-tab-score="doc" aria-selected="true">Doçentlik</button><button type="button" data-tab-score="tes" aria-selected="false">Akademik teşvik</button></div></div>
    <div class="t-body">${skeleton(4)}</div>`;
  const box = $(".t-body", host);
  let data, tab = "doc";
  const rowsHtml = (rows) => rows.length ? `<div class="t-rows">${rows.slice(0, 40).map((r) => `<div class="t-row"><span class="t-pts">${tNum(r.points)}</span><span class="t-row-main"><b>${esc(r.title)}</b><small>${esc([r.cat_label, r.year || "", `${r.authors} yazar · pay ${String(r.share).replace(".", ",")}`, r.after_phd === false ? "doktora öncesi" : ""].filter(Boolean).join(" · "))}</small></span></div>`).join("")}${rows.length > 40 ? `<p class="faint">+${rows.length - 40} kayıt daha</p>` : ""}</div>` : "";
  const itemCard = (it, i) => `<button type="button" class="card t-item ${it.ok === false ? "miss" : ""}" data-item="${i}" ${it.rows?.length ? "" : "data-empty tabindex=\"-1\""}>
      <div class="t-item-top"><span class="t-item-name">${esc(it.label)}</span>${it.min != null ? `<span class="t-state ${it.ok ? "ok" : "no"}">${it.ok ? T_CHECK : T_CROSS}en az ${tNum(it.min)}</span>` : ""}</div>
        <div class="t-item-num"><b>${tNum(it.points)}</b><span>puan</span>${it.cap != null ? `<small>tavan ${tNum(it.cap)}${it.capped_from ? ` · ham ${tNum(it.capped_from)}` : ""}</small>` : ""}</div>
        ${tBar(it.points, it.min ?? it.cap ?? Math.max(it.points, 1), it.ok === false ? "no" : "")}
        <small class="t-item-note">${esc(it.note || `${fmtNum(it.count)} kayıt`)}${it.rows?.length ? " · ayrıntı için tıkla" : ""}</small></button>`;
  const bindItems = (items) => $$("[data-item]", box).forEach((b) => b.onclick = () => {
    const it = items[+b.dataset.item]; if (!it?.rows?.length) return;
    openModal(`<div class="reading-modal"><header class="reading-head"><span class="reading-ic">${icon("award")}</span><div><h2>${esc(it.label)}</h2>
      <p class="muted">${tNum(it.points)} puan${it.capped_from ? ` (tavan uygulandı, ham ${tNum(it.capped_from)})` : ""} · ${fmtNum(it.count)} kayıt</p></div></header>${rowsHtml(it.rows)}</div>`);
  });
  const draw = () => {
    if (!box.isConnected || !data) return;
    $$("[data-tab-score]", host).forEach((b) => b.setAttribute("aria-selected", b.dataset.tabScore === tab));
    if (tab === "doc") {
      const d = data.docentlik, miss = d.missing.length;
      box.innerHTML = `<section class="card t-hero ${miss ? "" : "ok"}">
          <div class="t-rings">${tRing(d.total, d.need, "toplam")}${tRing(d.after_phd, d.need_after, "doktora sonrası")}</div>
          <div class="t-verdict"><span class="t-badge ${miss ? "no" : "ok"}">${miss ? T_CROSS : T_CHECK}${miss ? `${miss} şart eksik` : "Asgari şartlar sağlanıyor"}</span>
            <h2>${d.verified ? "" : "Tahmini: "}${miss ? "Henüz başvuru eşiğinde değil" : "Puan eşiği aşılmış görünüyor"}</h2>
            <p class="muted">${d.phd_year ? `Doktora yılı ${d.phd_year}; bu yıldan itibaren yayınlar “doktora sonrası” sayıldı.` : "Doktora yılı bulunamadı."}</p>
            <ul class="t-checks">${d.checks.map((c) => `<li class="${c.ok ? "ok" : "no"}">${c.ok ? T_CHECK : T_CROSS}<span>${esc(c.label)}</span><b>${tNum(c.have)}${c.ok ? "" : ` · ${tNum(c.need - c.have)} eksik`}</b></li>`).join("")}</ul></div></section>
        <div class="notice warn">${icon("info")}<div><b>Taslak ölçüt tablosu.</b> Puanlar ÜAK'ın genel tablo yapısına göre girildi ve resmî tabloyla doğrulanmadı; temel alanına göre puan ve asgari koşullar değişir. ${d.notes.map(esc).join(" ")}</div></div>
        <div class="t-grid">${d.items.map(itemCard).join("")}</div>`;
      bindItems(d.items);
    } else {
      const t = data.tesvik, now = new Date().getFullYear();
      box.innerHTML = `<section class="card t-hero ${t.ok ? "ok" : ""}"><div class="t-rings">${tRing(t.total, t.need, "asgari")}</div>
          <div class="t-verdict"><span class="t-badge ${t.ok ? "ok" : "no"}">${t.ok ? T_CHECK : T_CROSS}${t.ok ? `${tNum(t.need)} puan eşiği aşılıyor` : `${tNum(t.need - t.total)} puan eksik`}</span>
            <h2>${t.year} faaliyet yılı tahmini</h2><p class="muted">Yalnız o takvim yılının yayın ve tebliğleri. Üst sınır ${t.max} puan.</p>
            <div class="t-years">${[now - 1, now - 2, now].map((y) => `<button type="button" class="chip ${y === t.year ? "blue" : ""}" data-year="${y}">${y}</button>`).join("")}</div></div></section>
        <div class="notice warn">${icon("info")}<div><b>Taslak hesap.</b> ${t.notes.map(esc).join(" ")} Üniversitenin teşvik komisyonu kararı esastır.</div></div>
        <div class="t-grid">${t.items.map(itemCard).join("")}</div>`;
      bindItems(t.items);
      $$("[data-year]", box).forEach((b) => b.onclick = () => load(Number(b.dataset.year)));
    }
    hydrateIcons(box);
  };
  async function load(year) {
    try { data = await api(`/api/tools/score/${encodeURIComponent(jobId)}${year ? `?year=${year}` : ""}`); draw(); }
    catch (e) { if (box.isConnected) { host.dataset.job = ""; box.innerHTML = `<div class="card">${emptyState("info", "Puan hesaplanamadı", esc(e.message))}</div>`; hydrateIcons(box); } }
  }
  $$("[data-tab-score]", host).forEach((b) => b.onclick = () => { tab = b.dataset.tabScore; draw(); });
  load();
}
// Sekme ilk açıldığında hesaplanır; profil yenilenince kutu yeniden çizildiği için tekrar yüklenir.
document.addEventListener("click", (e) => {
  if (!e.target.closest('.tab[data-tab="score"]')) return;
  const host = document.getElementById("scoreBox");
  if (host) mountScore(host, host.dataset.jobId);
});

// ------------------------------------------------------------------ danışman bulucu
async function viewAdvisor(params) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Danışman bul" }]);
  let own = ""; try { own = localStorage.getItem("own-uni") || ""; } catch { /* tercih */ }
  const q = params.get("q") || "", mode = params.get("mode") === "2209" ? "2209" : "tez", uni = params.has("uni") ? params.get("uni") : (mode === "2209" ? own : "");
  setView(`<div class="section-head"><div><h1>Danışman bul</h1><p>Konunu ya da proje fikrini yaz; o alanda son 5 yılda yayın yapan, tez yönetmiş ve hâlâ aktif akademisyenleri sıralayalım.</p></div>
      <div class="t-seg" role="tablist"><button type="button" data-mode="tez" aria-selected="${mode === "tez"}">Tez danışmanı</button><button type="button" data-mode="2209" aria-selected="${mode === "2209"}">TÜBİTAK 2209-A</button></div></div>
    <form id="aForm" class="card t-form"><textarea id="aQ" rows="3" maxlength="400" placeholder="${mode === "2209" ? "Proje fikrini yaz: ör. tarım arazilerinde drone görüntüsünden hastalık tespiti" : "Tez konunu yaz: ör. deprem sonrası hasar tespiti için derin öğrenme"}">${esc(q)}</textarea>
      <div class="t-form-row"><div class="t-uni">${icon("building")}<select id="aUni" class="select" aria-label="Üniversite"><option value="">${mode === "2209" ? "Kendi üniversiteni seç" : "Tüm üniversiteler"}</option></select></div>
        <label class="t-own"><input type="checkbox" id="aOwn" ${uni && uni === own ? "checked" : ""}>Kendi üniversitem olarak hatırla</label><span class="spacer"></span>
        <button class="btn primary" type="submit">${icon("search")}Danışman ara</button></div>
      ${mode === "2209" ? `<p class="faint t-hint">2209-A'da danışman, öğrencinin kendi üniversitesinden bir öğretim üyesi ya da doktoralı öğretim elemanı olur; güncel çağrı metnini kontrol et.</p>` : ""}</form>
    <div id="aResults"></div>`);
  const go = (m = mode) => {
    const text = $("#aQ").value.trim(), u = $("#aUni").value;
    try { if ($("#aOwn").checked && u) localStorage.setItem("own-uni", u); } catch { /* tercih */ }
    if (m === "2209" && !u && text.length >= 3) { toast("2209-A için kendi üniversiteni seç."); $("#aUni").focus(); return; }
    const hash = `#/danisman?mode=${m}&uni=${encodeURIComponent(u)}${text ? `&q=${encodeURIComponent(text)}` : ""}`;
    if (location.hash === hash) viewAdvisor(new URLSearchParams(hash.split("?")[1])); else location.hash = hash;
  };
  $("#aForm").onsubmit = (e) => { e.preventDefault(); if ($("#aQ").value.trim().length >= 3) go(); };
  $("#aQ").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#aForm").requestSubmit(); } };
  $$(".t-seg [data-mode]").forEach((b) => b.onclick = () => go(b.dataset.mode));
  const hash = location.hash;
  api("/api/universities").then((r) => {
    const sel = $("#aUni"); if (!sel || location.hash !== hash) return;
    sel.insertAdjacentHTML("beforeend", (r.items || []).map((u) => `<option value="${esc(u.id)}">${esc(u.name)}</option>`).join("")); sel.value = uni || "";
  }).catch(() => {});
  const box = $("#aResults");
  if (q.length < 3) {
    box.innerHTML = `<div class="t-steps">${[["search", "Konunu yaz", "Türkçe yazabilirsin; İngilizce karşılığıyla birlikte aranır."], ["users", "Adaylar sıralanır", "Son 5 yıldaki konu yayınları, atıflar ve güncellik birlikte puanlanır."], ["cap", "YÖK bilgisi eklenir", "Daha önce bakılanlar hemen görünür; diğerleri için karttaki düğmeyle YÖK’ten istenir."]].map(([ic, t, d], i) => `<div class="card t-step"><span>${i + 1}</span>${icon(ic)}<b>${t}</b><small>${d}</small></div>`).join("")}</div>`;
    hydrateIcons(box); return;
  }
  box.innerHTML = `<div class="loading-line" role="status"><span class="spinner"></span>Konudaki yayınlar taranıyor…</div>${skeleton(4)}`;
  let r;
  try { r = await api(`/api/tools/advisors?q=${encodeURIComponent(q)}&uni=${encodeURIComponent(uni)}&mode=${mode}`); }
  catch (e) { if (location.hash === hash) { box.innerHTML = `<div class="notice err"><div>${esc(e.message)}</div></div>`; } return; }
  if (location.hash !== hash) return;
  const items = r.items || [];
  box.innerHTML = `<div class="src-status"><span class="chip teal">${fmtNum(r.works)} yayın tarandı</span>${r.english ? `<span class="chip blue">EN: ${esc(r.english)}</span>` : ""}${r.university ? `<span class="chip">${esc(r.university)}</span>` : ""}<span class="chip">son ${r.years || 5} yıl</span><span class="faint" data-yok-note></span></div>`
    + (items.length ? `<div class="t-advisors">${items.map((a, i) => `<article class="card t-adv" ${yokAttrs(a)}>
        <div class="t-adv-rank">${i + 1}</div>${avatar(a.name, a.job_id ? `/api/jobs/${encodeURIComponent(a.job_id)}/photo?v=2` : "")}
        <div class="t-adv-main"><div class="t-adv-head"><div>${yokTitle(a)}<h3>${esc(a.name)}</h3>
              <p class="t-adv-unit">${esc([a.institution, a.department].filter(Boolean).join(" · "))}</p></div>
            <div class="t-match"><b>%${a.match}</b><span>uyum</span>${tBar(a.match, 100)}</div></div>
          <div class="chips t-adv-chips">${a.active ? `<span class="chip teal">Aktif · son yayın ${a.last_year}</span>` : `<span class="chip gold">Son yayın ${a.last_year}</span>`}
            <span class="chip">${fmtNum(a.works)} konu yayını</span><span class="chip">${fmtNum(a.citations)} atıf</span>
            ${thesisChip(a)}
            ${mode === "2209" && a.eligible ? `<span class="chip teal">2209-A danışmanı olabilir</span>` : ""}</div>
          ${a.samples?.length ? `<ul class="t-adv-works">${a.samples.map((w) => `<li>${w.doi ? `<a href="https://doi.org/${esc(w.doi)}" target="_blank" rel="noopener">${esc(w.title)}</a>` : esc(w.title)}<small>${w.year}${w.citations ? ` · ${fmtNum(w.citations)} atıf` : ""}</small></li>`).join("")}</ul>` : ""}
          <p class="t-adv-thesis" ${a.thesis_titles?.length ? "" : "hidden"}>${a.thesis_titles?.length ? `<b>Yönettiği son tezler:</b> ${a.thesis_titles.map(esc).join(" · ")}` : ""}</p>
          <div class="t-adv-actions"><a class="btn sm primary" href="${a.chat_id ? `#/profil/${encodeURIComponent(a.chat_id)}` : `#/akademisyenler?q=${encodeURIComponent(a.name)}`}">${icon("user")}${a.chat_id ? "Profili aç" : "Profili incele"}</a>
            ${yokButtons(a)}
            ${a.orcid ? `<a class="btn sm ghost" href="https://orcid.org/${esc(a.orcid)}" target="_blank" rel="noopener">ORCID</a>` : ""}</div></div></article>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "Aday bulunamadı", esc(r.message || "Konuyu daha genel yaz ya da üniversite filtresini kaldır."))}</div>`);
  hydrateIcons(box);
  const list = $(".t-advisors", box);
  if (list) tPager(list, 10, () => enrichYok(box));
}

// ------------------------------------------------------------------ YÖK bilgisi: otomatik istek YOK
// Sayfa açılınca yalnız yerel önbellek okunur (cached=true, YÖK'e gitmez). Canlı istek yalnız karttaki
// "YÖK bilgisini getir" / "Tez geçmişi" düğmesine basılınca, o kart için gider.
const YOK_SEEN = new Map();
const yokAttrs = (a) => `data-yok-name="${esc(a.name)}" data-yok-inst="${esc(a.lookup_institution || a.institution || "")}"${a.yok_checked || a.title ? ` data-yok-done="1"` : ""}`;
const yokTitle = (a) => `<span class="t-adv-title">${esc(a.title || (a.yok_checked ? "Unvan YÖK'te eşleşmedi" : "Unvan bilinmiyor"))}</span>`;
const thesisChip = (a) => a.theses != null ? `<span class="chip blue" data-yok-thesis-chip>${fmtNum(a.theses)} tez yönetti${a.theses_recent ? ` · ${a.theses_recent} son 5 yılda` : ""}${a.theses_phd ? ` · ${a.theses_phd} doktora` : ""}</span>` : "";
const yokGetBtn = `<button class="btn sm ghost" type="button" data-yok-get>${icon("download")}YÖK bilgisini getir</button>`;
const yokThesesBtn = `<button class="btn sm ghost" type="button" data-yok-theses>${icon("cap")}Tez geçmişi</button>`;
const yokButtons = (a) => `${a.yok_url ? `<a class="btn sm" href="${esc(a.yok_url)}" target="_blank" rel="noopener" data-yok-link>${icon("external")}YÖK Akademik</a>` : ""}
  ${!(a.yok_checked || a.title) ? yokGetBtn : a.theses == null && a.yok_url ? yokThesesBtn : ""}`;

function tPager(list, size, onPage) {
  const cards = [...list.children];
  if (cards.length <= size) { onPage?.(); return; }
  const pages = Math.ceil(cards.length / size), bar = document.createElement("nav");
  bar.className = "t-pager"; bar.setAttribute("aria-label", "Sayfalar");
  const show = (p) => {
    cards.forEach((c, i) => { c.hidden = Math.floor(i / size) !== p; });
    bar.innerHTML = Array.from({ length: pages }, (_, i) => `<button type="button" class="btn sm${i === p ? " primary" : ""}" data-pg="${i}" ${i === p ? `aria-current="page"` : ""}>${i * size + 1}–${Math.min(cards.length, (i + 1) * size)}</button>`).join("");
    onPage?.();
  };
  bar.onclick = (e) => { const b = e.target.closest("[data-pg]"); if (!b) return; show(+b.dataset.pg); list.scrollIntoView({ block: "start", behavior: calmMotion() ? "auto" : "smooth" }); };
  list.after(bar); show(0);
}

function applyYok(card, d) {
  const title = $(".t-adv-title", card), unit = $(".t-adv-unit", card);
  if (title) title.textContent = d.title || (d.error ? "YÖK bilgisi alınamadı" : "Unvan YÖK'te eşleşmedi");
  if (unit && d.university) unit.textContent = [d.university, d.department].filter(Boolean).join(" · ");
  const actions = $(".t-adv-actions", card);
  if (actions && d.url && !$("[data-yok-link]", card)) $("a", actions)?.insertAdjacentHTML("afterend", `<a class="btn sm" href="${esc(d.url)}" target="_blank" rel="noopener" data-yok-link>${icon("external")}YÖK Akademik</a>`);
  if (!d.error) $("[data-yok-get]", card)?.remove();
  if (!d.error && d.yok_id && d.theses == null && actions && !$("[data-yok-theses]", card)) actions.insertAdjacentHTML("beforeend", yokThesesBtn);
  if (!d.error && !d.yok_id) $("[data-yok-theses]", card)?.remove();
  if (d.theses != null) {
    $("[data-yok-theses]", card)?.remove();
    $("[data-yok-thesis-chip]", card)?.remove();
    $(".t-adv-chips", card)?.insertAdjacentHTML("beforeend", thesisChip(d));
    const p = $(".t-adv-thesis", card);
    if (p && d.thesis_titles?.length) { p.hidden = false; p.innerHTML = `<b>Yönettiği son tezler:</b> ${d.thesis_titles.map(esc).join(" · ")}`; }
  }
  hydrateIcons(card);
}

// Sigorta: kalan süre geri sayımı; süre bitene kadar canlı düğmeler kapalı
let yokPauseUntil = 0, yokPauseTimer = 0;
function yokPaused(until) {
  if (until) yokPauseUntil = Math.max(yokPauseUntil, until * 1000);
  clearInterval(yokPauseTimer);
  const tick = () => {
    const left = Math.max(0, Math.round((yokPauseUntil - Date.now()) / 1000));
    const text = left ? `YÖK sigortası devrede: ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} sonra yeniden denenebilir.` : "";
    $$("[data-yok-note]").forEach((n) => { n.textContent = text; });
    $$("[data-yok-get],[data-yok-theses]").forEach((b) => { b.disabled = !!left; b.title = left ? text : ""; });
    if (!left) clearInterval(yokPauseTimer);
  };
  tick(); if (yokPauseUntil > Date.now()) yokPauseTimer = setInterval(tick, 1000);
}

async function yokFetch(card, { theses = false, cached = false } = {}) {
  const name = card.dataset.yokName, inst = card.dataset.yokInst || "", key = `${name}|${inst}|${theses ? 1 : 0}|${cached ? 1 : 0}`;
  if (YOK_SEEN.has(key)) return YOK_SEEN.get(key);
  let d;
  try { d = await api(`/api/tools/yok-person?name=${encodeURIComponent(name)}&institution=${encodeURIComponent(inst)}${theses ? "&theses=true" : ""}${cached ? "&cached=true" : ""}`, { quiet: true }); }
  catch { d = { error: true }; }
  if (!d.error && !d.paused && d.cached !== false) YOK_SEEN.set(key, d);
  if (d.paused_until) yokPaused(d.paused_until);
  return d;
}

let yokRun = 0;
async function enrichYok(host) {
  const run = ++yokRun;
  api("/api/tools/yok-status", { quiet: true }).then((s) => { if (s.paused) yokPaused(s.paused_until); }).catch(() => {});
  for (const card of $$("[data-yok-name]:not([data-yok-done])", host)) {
    if (run !== yokRun || !card.isConnected) return;
    if (card.hidden) continue;
    const d = await yokFetch(card, { cached: true });  // yalnız yerel önbellek
    if (d.cached === false || d.error) continue;      // önbellekte yok: düğme kalır, YÖK'e gidilmez
    card.dataset.yokDone = "1";
    applyYok(card, d);
  }
}

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-yok-get],[data-yok-theses]"); if (!btn || btn.disabled) return;
  const card = btn.closest("[data-yok-name]"); if (!card) return;
  const theses = btn.hasAttribute("data-yok-theses"), label = btn.innerHTML;
  btn.disabled = true; btn.textContent = theses ? "Tezler alınıyor…" : "YÖK'ten alınıyor…";
  const d = await yokFetch(card, { theses });
  if (d.paused || d.error) {
    btn.innerHTML = label; hydrateIcons(btn); btn.disabled = false;
    if (d.paused) yokPaused(d.paused_until); else toast("YÖK bilgisi alınamadı; biraz sonra yeniden dene.");
    return;
  }
  card.dataset.yokDone = "1";
  if (theses && d.theses == null) btn.remove();
  applyYok(card, d);
});

// ------------------------------------------------------------------ konu bul: Türkiye gündemi ve kategori gündemi
function renderAgenda(host) {
  if (!host) return;
  let cat = ""; try { cat = localStorage.getItem("agenda-cat") || ""; } catch { /* tercih */ }
  const papers = readRecentPapers().slice(0, 6), topics = readRecentVisits().filter((v) => v.kind === "topic").slice(0, 12);
  const store = { tr: [], cat: [] }, cache = new Map();
  host.innerHTML = `<div class="ag">
      <section class="card card-pad"><div class="card-title">${icon("flame")}Türkiye gündemi<span class="spacer"></span><span class="ag-note">Son 12 ayda en hızlı büyüyen konular</span></div>
        <div class="ag-grid" data-ag="tr">${skeleton(3)}</div></section>
      <section class="card card-pad"><div class="card-title">${icon("layers")}Kategori gündemi<span class="spacer"></span><button class="btn sm" type="button" data-ag-read hidden>${icon("book")}Alanın öne çıkan yayınları</button></div>
        <div class="ag-cats" role="tablist" data-ag-cats></div><div class="ag-grid" data-ag="cat">${skeleton(3)}</div></section>
      <div class="ag-two">
        <section class="card card-pad"><div class="card-title">${icon("search")}Son aradığın konular</div>
          ${topics.length ? `<div class="chips">${topics.map((t) => `<a class="chip ag-chip" href="#/ara?q=${encodeURIComponent(t.name)}">${esc(t.name)}</a>`).join("")}</div>` : `<p class="faint">Aradığın konular burada birikir.</p>`}</section>
        <section class="card card-pad"><div class="card-title">${icon("clock")}Son okudukların</div>
          ${papers.length ? `<div class="ag-papers">${papers.map((p, i) => `<button type="button" class="ag-paper" data-ag-paper="${i}"><b>${esc(p.title)}</b><small>${esc([p.year, p.venue, (p.authors || []).slice(0, 2).join(", ")].filter(Boolean).join(" · "))}</small></button>`).join("")}</div>` : `<p class="faint">Açtığın makaleler burada listelenir.</p>`}</section>
      </div></div>`;
  hydrateIcons(host);
  const grid = (key) => $(`[data-ag="${key}"]`, host);
  const fill = (key, items, emptyText) => {
    const el = grid(key); if (!el) return;
    store[key] = items;
    const max = Math.max(1, ...items.map((t) => Number(t.growth) || 0));
    el.innerHTML = items.length ? items.map((t, i) => `<button type="button" class="ag-topic" data-ag-topic="${key}:${i}">
        <span class="ag-rank">${i + 1}</span><b>${esc(t.name_tr || t.name)}</b>
        <span class="ag-meta"><span class="ag-growth">+%${fmtNum(t.growth)}</span><small>${fmtNum(t.count)} yayın · geçen yıl ${fmtNum(t.prev)}</small></span>
        <span class="t-bar"><i style="width:${Math.max(4, Math.round((Number(t.growth) || 0) / max * 100))}%"></i></span></button>`).join("")
      : `<p class="faint">${esc(emptyText)}</p>`;
    if (!calmMotion()) $$(".ag-topic", el).forEach((b, i) => b.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 300, delay: i * 30, easing: EASE, fill: "backwards" }));
  };
  api("/api/topics/trending", { quiet: true }).then((d) => fill("tr", d.items || [], "Gündem şu an hesaplanamadı.")).catch((e) => fill("tr", [], e.message));
  let cats = [];
  const pick = async (id) => {
    cat = id; try { localStorage.setItem("agenda-cat", id); } catch { /* tercih */ }
    $$("[data-ag-cat]", host).forEach((b) => b.setAttribute("aria-selected", b.dataset.agCat === id));
    const read = $("[data-ag-read]", host); if (read) read.hidden = false;
    if (!cache.has(id)) { const el = grid("cat"); if (el) el.innerHTML = skeleton(3); }
    try {
      if (!cache.has(id)) cache.set(id, (await api(`/api/topics/trending?cat=${encodeURIComponent(id)}`, { quiet: true })).items || []);
      if (cat === id) fill("cat", cache.get(id), "Bu alanda belirgin bir yükseliş hesaplanamadı.");
    } catch (e) { if (cat === id) fill("cat", [], e.message); }
  };
  api("/api/reading", { quiet: true }).then((d) => {
    cats = d.items || [];
    const bar = $("[data-ag-cats]", host); if (!bar) return;
    bar.innerHTML = cats.map((c) => `<button type="button" role="tab" data-ag-cat="${esc(c.id)}" aria-selected="false">${icon(c.icon)}${esc(c.label)}</button>`).join("");
    hydrateIcons(bar);
    $$("[data-ag-cat]", bar).forEach((b) => b.onclick = () => pick(b.dataset.agCat));
    if (cats.length) pick(cats.some((c) => c.id === cat) ? cat : cats[0].id);
  }).catch((e) => fill("cat", [], e.message));
  host.onclick = (e) => {
    const topic = e.target.closest("[data-ag-topic]");
    if (topic) { const [key, i] = topic.dataset.agTopic.split(":"), t = store[key][+i]; if (t) openTopicShelf({ id: t.id, name: t.name, label: t.name_tr || t.name, trend: t }); return; }
    const paper = e.target.closest("[data-ag-paper]");
    if (paper) { const p = papers[+paper.dataset.agPaper]; if (p) openPaper(reg(p, {})); return; }
    if (e.target.closest("[data-ag-read]")) { const c = cats.find((x) => x.id === cat); if (c) openReadingShelf(c.id, c.label); }
  };
}

// ------------------------------------------------------------------ jüri ve hakem önerici
const expertCard = (a, i, extra = "") => `<article class="card t-adv" ${yokAttrs(a)}><div class="t-adv-rank">${i + 1}</div>${avatar(a.name, a.job_id ? `/api/jobs/${encodeURIComponent(a.job_id)}/photo?v=2` : "")}
    <div class="t-adv-main"><div class="t-adv-head"><div>${yokTitle(a)}<h3>${esc(a.name)}</h3><p class="t-adv-unit">${esc([a.institution, a.department].filter(Boolean).join(" · "))}</p></div>
        <div class="t-match"><b>%${a.match}</b><span>uyum</span>${tBar(a.match, 100)}</div></div>
      <div class="chips t-adv-chips">${extra}<span class="chip">${fmtNum(a.works)} konu yayını</span>${a.active ? `<span class="chip teal">Aktif · ${a.last_year}</span>` : `<span class="chip">son yayın ${a.last_year}</span>`}${thesisChip(a)}</div>
      ${a.samples?.length ? `<ul class="t-adv-works">${a.samples.slice(0, 2).map((w) => `<li>${w.doi ? `<a href="https://doi.org/${esc(w.doi)}" target="_blank" rel="noopener">${esc(w.title)}</a>` : esc(w.title)}<small>${w.year}</small></li>`).join("")}</ul>` : ""}
      <p class="t-adv-thesis" hidden></p>
      <div class="t-adv-actions"><a class="btn sm primary" href="${a.chat_id ? `#/profil/${encodeURIComponent(a.chat_id)}` : `#/akademisyenler?q=${encodeURIComponent(a.name)}`}" data-close-modal>${icon("user")}${a.chat_id ? "Profili aç" : "Profili incele"}</a>
        ${yokButtons(a)}</div></div></article>`;

// Akademisyen profili → Tezler sekmesi: "Jüri öner"
function openJury() {
  const r = S.result; if (!r?.job_id) return;
  const y = r.profile?.yok || {}, rows = [...((y.sections || {}).theses || []), ...((y.tez_merkezi || {}).advised || [])];
  const titles = [...new Set(rows.map((t) => String(t["Tez Adı"] || t.title || "").trim()).filter((t) => t.length > 8))].slice(0, 60);
  openModal(`<div class="reading-modal"><header class="reading-head"><span class="reading-ic">${icon("users")}</span><div><h2>Jüri öner</h2><p class="muted">Tez konusunda yayın yapan öğretim üyeleri; ${esc(r.profile?.name || "danışman")} listeden çıkarılır.</p></div></header>
    <form id="juryForm" class="t-jury-form">${titles.length ? `<select class="select" id="juryPick" aria-label="Tez seç"><option value="">Yönettiği tezlerden seç…</option>${titles.map((t) => `<option>${esc(t)}</option>`).join("")}</select>` : ""}
      <div class="t-jury-row"><div class="input">${icon("search")}<input id="juryTopic" maxlength="400" placeholder="Tez başlığı ya da konusu"></div><button class="btn primary" type="submit">Jüri öner</button></div></form>
    <div id="juryOut"><p class="faint">Bir tez seç ya da konuyu yaz. Doktora jürilerinde kurum dışından üye gerektiği için öneriler kurum içi ve kurum dışı olarak ayrılır.</p></div></div>`);
  const pick = $("#juryPick"), topic = $("#juryTopic"), out = $("#juryOut");
  if (pick) pick.onchange = () => { if (pick.value) { topic.value = pick.value; $("#juryForm").requestSubmit(); } };
  $("#juryForm").onsubmit = async (e) => {
    e.preventDefault(); const q = topic.value.trim(); if (q.length < 5) return;
    out.innerHTML = `<div class="loading-line"><span class="spinner"></span>Konuda yayın yapanlar taranıyor…</div>${skeleton(3)}`;
    try {
      const d = await api(`/api/tools/jury?job_id=${encodeURIComponent(r.job_id)}&topic=${encodeURIComponent(q)}`);
      if (!out.isConnected) return;
      const flag = (a) => a.coauthor ? `<span class="chip gold">Danışmanla ortak yayını var</span>` : "";
      const group = (title, items, empty) => `<div class="m-h">${title} <span class="count">${items.length}</span></div>${items.length ? `<div class="t-advisors">${items.map((a, i) => expertCard(a, i, flag(a))).join("")}</div>` : `<p class="faint">${empty}</p>`}`;
      out.innerHTML = `<div class="src-status"><span class="chip teal">${fmtNum(d.works)} yayın tarandı</span>${d.english ? `<span class="chip blue">EN: ${esc(d.english)}</span>` : ""}<span class="faint" data-yok-note></span></div>
        ${group(`Kurum içi · ${esc(d.institution || "")}`, d.inside, "Bu konuda aynı üniversiteden aday bulunamadı.")}${group("Kurum dışı", d.outside, "Kurum dışından aday bulunamadı; konuyu daha genel yaz.")}
        <p class="faint">Öneriler yayın geçmişine dayanır; jüri koşulları (unvan, kurum dışı üye sayısı) için enstitü yönetmeliğine bak.</p>`;
      hydrateIcons(out);
      enrichYok(out);
    } catch (err) { if (out.isConnected) out.innerHTML = `<div class="notice err"><div>${esc(err.message)}</div></div>`; }
  };
}
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-jury]")) { e.preventDefault(); openJury(); return; }
  if (e.target.closest("[data-close-modal]") && typeof closeModal === "function") closeModal();
});

// Konu bul → "Hakem bul"
async function viewReviewer(params) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Konu bul", href: "#/ara" }, { label: "Hakem bul" }]);
  const q = params.get("q") || "", exclude = params.get("exclude") || "", inst = params.get("inst") || "";
  setView(`<div class="section-head"><div><h1>Hakem bul</h1><p>Makalenin başlığını ya da özetini yaz; konuda yayın yapan akademisyenleri sıralayalım. Yazarlar listeden çıkarılır.</p></div><a class="btn sm" href="#/ara">${icon("arrow")}Konu bul</a></div>
    <form id="rvForm" class="card t-form"><textarea id="rvQ" rows="3" maxlength="400" placeholder="Makale başlığı ya da özetin ilk cümleleri">${esc(q)}</textarea>
      <div class="t-form-row"><div class="input" style="flex:2;min-width:240px">${icon("users")}<input id="rvEx" maxlength="400" placeholder="Yazarlar (virgülle) — listeden çıkarılır" value="${esc(exclude)}"></div>
        <div class="input" style="flex:1;min-width:200px">${icon("building")}<input id="rvInst" maxlength="160" placeholder="Yazarın kurumu (isteğe bağlı)" value="${esc(inst)}"></div>
        <button class="btn primary" type="submit">${icon("search")}Hakem öner</button></div></form>
    <div id="rvOut"></div>`);
  $("#rvForm").onsubmit = (e) => {
    e.preventDefault(); const v = $("#rvQ").value.trim(); if (v.length < 10) { toast("En az 10 karakterlik bir başlık ya da özet yaz."); return; }
    const hash = `#/hakem?q=${encodeURIComponent(v)}&exclude=${encodeURIComponent($("#rvEx").value.trim())}&inst=${encodeURIComponent($("#rvInst").value.trim())}`;
    if (location.hash === hash) viewReviewer(new URLSearchParams(hash.split("?")[1])); else location.hash = hash;
  };
  const out = $("#rvOut"), hash = location.hash;
  if (q.length < 10) return;
  out.innerHTML = `<div class="loading-line" role="status"><span class="spinner"></span>Konuda yayın yapanlar taranıyor…</div>${skeleton(4)}`;
  let d;
  try { d = await api(`/api/tools/reviewers?q=${encodeURIComponent(q)}&exclude=${encodeURIComponent(exclude)}&institution=${encodeURIComponent(inst)}`); }
  catch (e) { if (location.hash === hash) out.innerHTML = `<div class="notice err"><div>${esc(e.message)}</div></div>`; return; }
  if (location.hash !== hash) return;
  out.innerHTML = `<div class="src-status"><span class="chip teal">${fmtNum(d.works)} yayın tarandı</span>${d.english ? `<span class="chip blue">EN: ${esc(d.english)}</span>` : ""}${d.excluded.map((n) => `<span class="chip">hariç: ${esc(n)}</span>`).join("")}<span class="faint" data-yok-note></span></div>`
    + (d.items.length ? `<div class="t-advisors">${d.items.map((a, i) => expertCard(a, i, `${a.coauthor ? `<span class="chip gold">Yazarlarla ortak yayını var</span>` : ""}${a.same_institution ? `<span class="chip gold">Yazarla aynı kurum</span>` : ""}`)).join("")}</div>
      <p class="faint" style="margin-top:12px">Yalnızca Türkiye adresli yayınlar taranır. ${d.coauthors_checked ? "Yazarların OpenAlex'teki ortak yazarları işaretlenip sona alındı; yine de adayın profilinden kontrol et." : "Yazarlar OpenAlex'te bulunamadı; ortak yazarlık denetlenemedi."}</p>`
      : `<div class="card">${emptyState("users", "Aday bulunamadı", "Başlığı daha genel yaz.")}</div>`);
  hydrateIcons(out);
  const list = $(".t-advisors", out);
  if (list) tPager(list, 10, () => enrichYok(out));
}
