/* Akademik İz — hareket katmanı. Sayfa kodundan bağımsızdır: içerik ekrana geldikçe (DOM'a eklendikçe) çalışır.
 *
 *   • Açılış perdesi   oturumda bir kez, tüm ekranı kaplar; logo ve ad belirir, sonra perde yukarı çekilir.
 *   • Sıralı düşme     liste, kart ve tablo satırları tek tek, kısa aralıkla yerine oturur ("pıt pıt").
 *   • Derinlikten geliş üniversite kartları ekrana arkadan (z ekseninde) gelir; üstüne gelince fareye doğru eğilir.
 *   • Sayaç            sayılar sıfırdan sayarak gelir.
 *   • Işık             tıklanabilir kartlarda fareyi izleyen ışık.
 *   • Ayarlar          uzun sayfa sekmelere bölünür.
 *
 * "Hareketi azalt" sistem ayarında yalnız açılış perdesi kısa bir solma olarak kalır.
 */
(function () {
  "use strict";
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SPRING = "linear(0, .25 6%, .62 14%, .9 22%, 1.04 31%, 1.07 38%, 1.05 46%, 1.01 58%, .995 72%, 1)";
  const seen = new WeakSet(), counted = new WeakSet();

  /* ---------------------------------------------------------------- açılış perdesi */
  function splash() {
    try { if (sessionStorage.getItem("fx-splash")) return; sessionStorage.setItem("fx-splash", "1"); } catch { return; }
    const el = document.createElement("div");
    el.className = "fx-splash";
    el.innerHTML = `<div class="fx-splash-glow"></div><div class="fx-splash-mark"><img src="/static/brand-mark.svg" alt=""></div>
      <div class="fx-splash-name">${[..."Akademik İz"].map((ch, i) => `<span style="--i:${i}">${ch === " " ? "&nbsp;" : ch}</span>`).join("")}</div>
      <p class="fx-splash-line">Akademisyenler, üniversiteler ve firmalar; kaynaklarıyla tek yerde.</p><div class="fx-splash-bar"><i></i></div>`;
    document.body.appendChild(el);
    const close = () => { if (el.dataset.out) return; el.dataset.out = "1"; el.classList.add("out"); setTimeout(() => el.remove(), 620); };
    el.onclick = close; document.addEventListener("keydown", close, { once: true });
    setTimeout(close, calm ? 500 : 1900);
  }

  /* ---------------------------------------------------------------- sıralı düşme */
  // Kap → öğelerinin nasıl geleceği. "deep": derinlikten; "drop": yukarıdan düşer; "rise": aşağıdan kalkar; "side": yandan.
  const GROUPS = [
    [".uni-grid", "deep"], [".timeline", "side"], [".co-list", "rise"], [".proj-list", "rise"], [".place-list", "rise"], [".campus-btns", "rise"],
    [".kpis", "rise"], [".t-score-grid, .sc-grid, .t-cards", "rise"], [".student-term-courses", "drop"], [".section-list", "drop"], [".pat-list", "rise"],
    [".collabs", "rise"], [".bubble-grid", "deep"], [".home-tiles, .tile-row", "deep"], [".settings-pane.on", "rise"], [".aday-list", "drop"], [".lp-grid", "rise"],
    ["#unitStaff, .staff-list, .people-list", "rise"], ["tbody", "drop"],
  ];
  const FROM = {
    deep: { opacity: 0, transform: "perspective(1100px) translateZ(-320px) rotateX(24deg) scale(.82)" },
    drop: { opacity: 0, transform: "translateY(-14px) scale(.985)" },
    rise: { opacity: 0, transform: "translateY(18px) scale(.975)" },
    side: { opacity: 0, transform: "translateX(-18px)" },
  };
  function land(children, mode) {
    let k = 0;
    children.forEach((el) => {
      if (seen.has(el) || !(el instanceof HTMLElement) || el.hidden) return;
      seen.add(el);
      if (calm || k > 28) return;  // çok uzun listede ilk ekrandan sonrası beklemesin
      el.animate([FROM[mode], { opacity: 1, transform: "none" }], { duration: mode === "deep" ? 760 : 560, delay: k * (mode === "deep" ? 55 : 42), easing: SPRING, fill: "backwards" });
      k += 1;
    });
  }
  function sweep(scope) {
    if (!(scope instanceof Element)) return;
    GROUPS.forEach(([sel, mode]) => {
      const hosts = [...scope.querySelectorAll(sel)];
      if (scope.matches(sel)) hosts.push(scope);
      const up = scope.closest(sel); if (up) hosts.push(up);
      hosts.forEach((host) => land([...host.children], mode));
    });
    count(scope); tabsFor(scope);
  }
  // Açılan bölüm (accordion): içindekiler özetin altından sırayla düşer.
  document.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.open || calm) return;
    [...d.children].filter((el) => el.tagName !== "SUMMARY").forEach((el, i) => {
      el.animate([{ opacity: 0, transform: "translateY(-10px)" }, { opacity: 1, transform: "none" }], { duration: 420, delay: i * 50, easing: SPRING, fill: "backwards" });
      const rows = el.querySelectorAll(":scope > *");
      if (rows.length > 1 && rows.length < 60) rows.forEach((row, k) => { if (k < 24) row.animate([FROM.drop, { opacity: 1, transform: "none" }], { duration: 480, delay: 90 + k * 38, easing: SPRING, fill: "backwards" }); });
    });
  }, true);

  /* ---------------------------------------------------------------- sayaç */
  const COUNT = ".kpi b, .co-side b, .tab .n, .fx-count, .t-score-total b, .sc-num, .metric b, .stat b, .globe-head b";
  function count(scope) {
    if (calm) return;
    scope.querySelectorAll(COUNT).forEach((el) => {
      if (counted.has(el) || el.children.length) return;
      const raw = el.textContent.trim(), m = raw.match(/^(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d+))?$/);
      counted.add(el);
      if (!m) return;
      const dec = m[2] ? m[2].length : 0, target = Number(m[1].replace(/\./g, "") + (dec ? "." + m[2] : ""));
      if (!target || target > 1e7) return;
      const fmt = (v) => v.toLocaleString("tr-TR", { minimumFractionDigits: dec, maximumFractionDigits: dec });
      const start = performance.now(), ms = Math.min(1100, 500 + Math.log10(target + 1) * 180);
      const step = (now) => {
        if (!el.isConnected) return;
        const t = Math.min(1, (now - start) / ms), e = 1 - Math.pow(1 - t, 4);
        el.textContent = t < 1 ? fmt(dec ? target * e : Math.round(target * e)) : raw;
        if (t < 1) requestAnimationFrame(step);
      };
      el.textContent = fmt(0); requestAnimationFrame(step);
    });
  }

  /* ---------------------------------------------------------------- ayarlar: sekmeler */
  function tabsFor(scope) {
    const stack = scope.matches?.(".settings-stack") ? scope : scope.querySelector?.(".settings-stack");
    if (!stack || stack.dataset.tabbed) return;
    const labels = [...stack.children].filter((el) => el.classList.contains("settings-label"));
    if (labels.length < 2) return;
    stack.dataset.tabbed = "1";
    const bar = document.createElement("div"); bar.className = "settings-tabs"; bar.setAttribute("role", "tablist");
    const panes = labels.map((label, i) => {
      const pane = document.createElement("div"); pane.className = "settings-pane"; pane.setAttribute("role", "tabpanel");
      let next = label.nextElementSibling;
      while (next && !next.classList.contains("settings-label")) { const move = next; next = next.nextElementSibling; pane.appendChild(move); }
      const tab = document.createElement("button"); tab.type = "button"; tab.setAttribute("role", "tab"); tab.textContent = label.textContent.trim(); tab.dataset.i = i;
      bar.appendChild(tab); label.remove();
      return pane;
    });
    const glider = document.createElement("i"); glider.className = "settings-glider"; bar.appendChild(glider);
    stack.prepend(bar); panes.forEach((p) => stack.appendChild(p));
    let current = -1;
    const show = (i) => {
      if (i === current) return;
      const dir = i > current ? 1 : -1; current = i;
      [...bar.querySelectorAll("button")].forEach((b, k) => { b.classList.toggle("on", k === i); b.setAttribute("aria-selected", k === i); });
      panes.forEach((p, k) => p.classList.toggle("on", k === i));
      const b = bar.children[i]; glider.style.width = b.offsetWidth + "px"; glider.style.transform = `translateX(${b.offsetLeft}px)`;
      if (!calm) panes[i].animate([{ opacity: 0, transform: `translateX(${dir * 26}px)` }, { opacity: 1, transform: "none" }], { duration: 420, easing: SPRING });
      try { sessionStorage.setItem("fx-settings-tab", String(i)); } catch { /* yok */ }
    };
    bar.onclick = (e) => { const b = e.target.closest("button"); if (b) show(+b.dataset.i); };
    let first = 0; try { first = Math.min(panes.length - 1, +sessionStorage.getItem("fx-settings-tab") || 0); } catch { /* yok */ }
    requestAnimationFrame(() => show(first));
  }

  /* ---------------------------------------------------------------- fareyi izleyen ışık ve eğilme */
  const LIT = ".uni-card, .co-row, .proj-row, .ai-idea, .campus-btn, .place-row, .person, .thesis, .kpi, .settings-pane .card, .t-score-card, .collab";
  if (!calm && matchMedia("(hover: hover) and (pointer: fine)").matches) {
    let tilted = null;
    document.addEventListener("pointermove", (e) => {
      const el = e.target.closest?.(LIT);
      if (el) { const r = el.getBoundingClientRect(); el.style.setProperty("--mx", `${e.clientX - r.left}px`); el.style.setProperty("--my", `${e.clientY - r.top}px`); }
      const card = e.target.closest?.(".uni-card, .bubble");
      if (tilted && tilted !== card) { tilted.style.transform = ""; tilted = null; }
      if (card) {
        const r = card.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        card.style.transform = `perspective(900px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 9).toFixed(2)}deg) translateZ(10px)`; tilted = card;
      }
    }, { passive: true });
    document.addEventListener("pointerleave", () => { if (tilted) { tilted.style.transform = ""; tilted = null; } }, true);
  }

  /* ---------------------------------------------------------------- başlat */
  const start = () => {
    splash();
    sweep(document.body);
    new MutationObserver((list) => {
      const fresh = new Set();
      list.forEach((m) => m.addedNodes.forEach((n) => { if (n instanceof Element && !n.closest(".fx-splash")) fresh.add(n); }));
      if (fresh.size) requestAnimationFrame(() => fresh.forEach((n) => { if (n.isConnected) sweep(n); }));
    }).observe(document.body, { childList: true, subtree: true });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
