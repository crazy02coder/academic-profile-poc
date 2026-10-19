// İnce kabuk: arayüz http://127.0.0.1:8000/agent'ten yüklenir; bu dosya yalnızca tarayıcı yeteneklerini
// (sekme içeriği, gezinme, vurgulama, öğrenme modunda ağ kaydı) postMessage köprüsüyle sağlar.
const SERVER = "http://127.0.0.1:8000";
const frame = document.getElementById("app");
const down = document.getElementById("down");

async function serverUp() {
  try { const r = await fetch(`${SERVER}/api/health`, { cache: "no-store" }); return r.ok; } catch { return false; }
}
async function boot() {
  const up = await serverUp();
  frame.style.display = up ? "block" : "none";
  down.style.display = up ? "none" : "block";
  if (up) frame.src = `${SERVER}/agent?t=${Date.now()}`;
}
document.getElementById("retry").onclick = boot;
boot();

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}

function post(msg) { frame.contentWindow?.postMessage(msg, SERVER); }

// ------------------------------------------------------------- öğrenme modu (CDP ağ kaydı)
const learn = { tabId: null, requests: new Map(), order: [], clicks: [] };

async function learnStart() {
  const tab = await activeTab();
  learn.tabId = tab.id; learn.requests.clear(); learn.order = []; learn.clicks = [];
  await chrome.debugger.attach({ tabId: tab.id }, "1.3");
  await chrome.debugger.sendCommand({ tabId: tab.id }, "Network.enable", { maxPostDataSize: 65536 });
  // tıklanan öğelerin öznitelikleri (detay butonu tarifleri için)
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
    window.__aizClicks = [];
    document.addEventListener("click", (e) => {
      const el = e.target.closest("a, button, [data-id], [onclick], [role=button]") || e.target;
      const attrs = {}; for (const a of el.attributes || []) attrs[a.name] = a.value;
      window.__aizClicks.push({ tag: el.tagName.toLowerCase(), text: (el.innerText || "").slice(0, 80), attrs });
    }, true);
  } });
  return { tabId: tab.id };
}

chrome.debugger.onEvent.addListener(async (src, method, params) => {
  if (src.tabId !== learn.tabId) return;
  if (method === "Network.requestWillBeSent") {
    learn.requests.set(params.requestId, { req: params.request, type: params.type, started: params.wallTime });
    learn.order.push(params.requestId);
  } else if (method === "Network.responseReceived") {
    const r = learn.requests.get(params.requestId); if (r) r.resp = params.response;
  } else if (method === "Network.loadingFinished") {
    const r = learn.requests.get(params.requestId);
    if (r && ["XHR", "Fetch", "Document"].includes(r.type)) {
      try {
        const body = await chrome.debugger.sendCommand({ tabId: learn.tabId }, "Network.getResponseBody", { requestId: params.requestId });
        r.body = body.base64Encoded ? "" : (body.body || "").slice(0, 300000);
      } catch { /* gövde alınamadı */ }
    }
  }
});

async function learnStop() {
  const tabId = learn.tabId;
  let clicks = [];
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: () => window.__aizClicks || [] });
    clicks = res.result || [];
  } catch { /* sayfa değişmiş olabilir */ }
  try { await chrome.debugger.detach({ tabId }); } catch { /* zaten ayrılmış */ }
  const entries = [];
  for (const id of learn.order) {
    const r = learn.requests.get(id);
    if (!r || !r.resp || !["XHR", "Fetch", "Document"].includes(r.type)) continue;
    entries.push({
      startedDateTime: new Date((r.started || Date.now() / 1000) * 1000).toISOString(), time: 0,
      request: { method: r.req.method, url: r.req.url, httpVersion: "HTTP/1.1",
        headers: Object.entries(r.req.headers || {}).map(([name, value]) => ({ name, value: String(value) })),
        queryString: [], cookies: [], headersSize: -1, bodySize: (r.req.postData || "").length,
        ...(r.req.postData ? { postData: { mimeType: r.req.headers?.["Content-Type"] || "", text: r.req.postData } } : {}) },
      response: { status: r.resp.status, statusText: r.resp.statusText || "", httpVersion: "HTTP/1.1",
        headers: Object.entries(r.resp.headers || {}).map(([name, value]) => ({ name, value: String(value) })),
        cookies: [], content: { size: (r.body || "").length, mimeType: r.resp.mimeType || "", text: r.body || "" },
        redirectURL: "", headersSize: -1, bodySize: (r.body || "").length },
      cache: {}, timings: { send: 0, wait: 0, receive: 0 }, _resourceType: r.type.toLowerCase(),
    });
  }
  learn.tabId = null;
  return { har: { log: { version: "1.2", creator: { name: "akademik-iz-extension", version: "1.0" }, entries } }, clicks };
}

// ------------------------------------------------------------------- köprü komutları
const handlers = {
  async snapshot() {
    const tab = await activeTab();
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id },
      func: () => ({ url: location.href, title: document.title, html: document.documentElement.outerHTML }) });
    return res.result;
  },
  async navigate({ url }) {
    const tab = await activeTab();
    await chrome.tabs.update(tab.id, { url });
    await new Promise((resolve) => {
      const done = (id, info) => { if (id === tab.id && info.status === "complete") { chrome.tabs.onUpdated.removeListener(done); resolve(); } };
      chrome.tabs.onUpdated.addListener(done);
      setTimeout(resolve, 20000);
    });
    return { url };
  },
  async highlight({ text }) {
    const tab = await activeTab();
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, args: [text], func: (needle) => {
      const fold = (s) => s.toLocaleLowerCase("tr").normalize("NFKD").replace(/[̀-ͯ]/g, "");
      const n = fold(needle);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        if (fold(walker.currentNode.textContent).includes(n)) {
          const el = walker.currentNode.parentElement;
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          const old = el.style.outline; el.style.outline = "3px solid #7c9cff"; el.style.outlineOffset = "3px";
          setTimeout(() => { el.style.outline = old; }, 4000);
          return true;
        }
      }
      return false;
    } });
    return { found: res.result };
  },
  learnStart, learnStop,
};

window.addEventListener("message", async (e) => {
  if (e.origin !== SERVER || !e.data || !e.data.__aiz) return;
  const { id, type, payload } = e.data;
  try { post({ __aiz: true, id, ok: true, data: await handlers[type](payload || {}) }); }
  catch (err) { post({ __aiz: true, id, ok: false, error: String(err?.message || err) }); }
});

// Sekme değişince panel yeni sayfayı anlasın
chrome.tabs.onActivated.addListener(() => post({ __aiz: true, event: "tab_changed" }));
chrome.tabs.onUpdated.addListener((id, info, tab) => {
  if (info.status === "complete" && tab.active) post({ __aiz: true, event: "tab_changed", url: tab.url });
});
