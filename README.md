# Akademik İz

**Kurum sitesinden akademisyen araştırma profili çıkaran, kanıta dayalı bir asistan.**

Bir akademik kadro linki ve akademisyen adı verirsin. Sistem kişiyi sitede bulur, yayınlarını açık kaynaklardan toplar, birleştirir, doğrular ve Gemini ile kaynak gösteren bir araştırma profili çıkarır. Sonra o kişi hakkında soru sorabilirsin.

Tarama ve veri toplama senin bilgisayarında çalışır. Dil modeli olarak Gemini API'nin ücretsiz katmanı kullanılır; ücretli servis gerekmez.

```
Scrapling · REA · Gemini · OpenAlex · Crossref · ORCID · YÖK Akademik · Google Scholar
```

---

## Hızlı başlangıç

```bash
bash run.sh
```

Ardından **http://127.0.0.1:8000** adresini aç.

`run.sh` ilk çalıştırmada her şeyi kurar: Python ortamı, Scrapling tarayıcıları, REA (npm).

**Gemini anahtarı:** https://aistudio.google.com/apikey adresinden ücretsiz anahtar al, proje kökünde `.env` dosyasına yaz:

```
GEMINI_API_KEY=...
OPENALEX_API_KEY=...   # isteğe bağlı, ücretsiz: https://openalex.org (hesap → API key)
EPO_KEY=...            # isteğe bağlı, ücretsiz: https://developers.epo.org (My Apps → Consumer Key)
EPO_SECRET=...         # patent sekmeleri yalnızca bu ikisi tanımlıysa görünür
```

OpenAlex anahtarsız da çalışır ama IP başına günlük ortak bütçe (~1000 istek) çabuk dolar; kendi anahtarınla kişisel bütçe kullanılır.

`.env` git'e girmez. Anahtar yoksa analiz ve sohbet basit kural tabanlı yedeğe (mock) düşer.
![alt text](image.png)
**Gerekenler**

| Araç | Sürüm | Not |
|---|---|---|
| Python | 3.11+ | |
| Node.js | 22.19+ / 24.11+ | REA için. Yoksa sistem REA'sız çalışır (aşağıya bak). |

**Modeller**

| Görev | Varsayılan |
|---|---|
| Analiz, sohbet, sayfa okuma | `gemini-3.5-flash` |
| Kısa işler (link seçimi) | `gemini-3.5-flash-lite` |
| RAG gömme | `gemini-embedding-001` (768 boyut) |

Ücretsiz katmanda kota (429) ve yoğunluk (503) hataları olağandır. Hata alan istek sıradaki modelle (`GEMINI_FALLBACKS`) yeniden denenir; kotası dolan model 60 sn atlanır.

---

## Nasıl çalışır

```
 kadro linki + ad
        │
        ▼
 ┌──────────────┐   arama motoru (site:) ─┐
 │ Kişiyi bul   │   kayıtlı tarif / hafıza ├─► kişi kartı + profil sayfası
 │              │   LLM ajanı ∥ Spider ───┘
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ Yayın topla  │   YÖK · OpenAlex · Crossref · ORCID · Scholar   (paralel)
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ Birleştir    │   DOI · başlık · bulanık eşleşme · TR↔EN çeviri eşleşmesi
 │ & doğrula    │   kaynaklar arası tutarlılık (doğrulandı / tek kaynak / çelişki)
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ Analiz       │   Gemini; her cümle bir yayın kimliğine bağlı
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ Sohbet       │   soru tipine göre CAG, RAG veya Hibrit otomatik seçilir
 └──────────────┘
```

Her aşama arayüzde canlı akar. Ham teknik loglar **"Teknik ayrıntılar"** altında kapalı durur.

---

## Bileşenlerin rolleri

Sistem üç parçanın iş bölümüne dayanır:

| Bileşen | Görevi | Benzetme |
|---|---|---|
| **Scrapling** | Siteye **erişim**. Statik okuma (Chrome TLS taklidi), bot duvarında gizli tarayıcı ve Cloudflare çözücü, Spider ile tarama, kart ve liste tespiti. | Her gün mutfakta yemeği yapan |
| **REA** | Sayfanın **arkasındaki gizli isteği bulmak**. Bulduğu isteği bir **tarif** olarak kaydeder. | Aşçıyı bir kez izleyip tarifi deftere yazan |
| **Gemini** | **Anlamak**. Sayfa türü, doğru link, profil alanları, analiz, sohbet. | |

### REA ne işe yarıyor? Somut örnek: Ankara Bilim

Kadro sayfasında her hocanın bir kartı ve bir **"Detaylı Bilgi"** butonu var. Ama bu buton bir link değil:

```html
<button data-id="1234">Detaylı Bilgi</button>
```

Tıklayınca JavaScript arka planda sunucuya gizli bir istek atıyor ve detayı (bölüm, ilgi alanları, ORCID…) bir pencerede gösteriyor. Scrapling HTML'i okuyunca sadece butonu görür. Detay HTML'de yok, gidilecek bir adres de yok.

**İlk sefer (REA, bir kez):**

1. REA sayfayı gerçek bir tarayıcıda açar ve butona **tıklar**.
2. Tıklama anında giden trafiği izler ve isteği yakalar:
   ```
   POST https://ankarabilim.edu.tr/department-personnel-info
   personnelId=1234
   ```
3. `1234` değerinin butondaki `data-id` ile aynı olduğunu fark eder.
4. Bunu tarif olarak kaydeder: *"Detay için butonun `data-id`'sini `personnelId` olarak bu adrese gönder."*

**Sonraki seferler (REA yok, sadece Scrapling):**

Başka bir hoca arandığında Scrapling kartı bulur, `data-id`'yi alır (ör. `5678`) ve isteği doğrudan atar. Tarayıcı açılmaz, butona tıklanmaz. Yaklaşık 1 saniye sürer.

**Site değişirse:** tarif artık çalışmaz. Sistem bunu fark eder (`replay_failed`), REA'yı yeniden gönderir, tarif güncellenir. Kimse kod yazmaz.

> **REA öğrenir, Scrapling tekrarlar; bozulunca REA yeniden öğrenir.**

### YÖK Akademik: ikisi birlikte

YÖK düz istemcilere `418` döndürür. Arama da bir formun arkasındaki `POST` isteğidir.

- **Scrapling** gizli tarayıcıyla duvarı geçer.
- **REA** aynı tarayıcıya CDP üzerinden bağlanır, formu doldurur, Enter'a basar ve arkadaki `POST /AkademikArama/AkademisyenArama` isteğini gözler.
- Sonraki aramalarda tarif açık oturumun içinden doğrudan oynatılır.

### Öğrenilmiş tarifler

| Site | Tarif | Öğrenildi | Kullanım |
|---|---|---|---|
| `yok.gov.tr` | `yok_search` | 16.10.2026 | 13 tekrar, 0 hata |
| `ankarabilim.edu.tr` | `profile_detail` | 16.10.2026 | 3 tekrar, 0 hata |

Tarifler `data/recipes/<alan-adı>.json` altında, REA kanıt kimliğiyle (`evidence_id`) birlikte tutulur.

### REA olmasa ne olur?

| Durum | Sonuç |
|---|---|
| Tarif zaten kayıtlı | Fark yok; tekrarı zaten Scrapling yapıyor. |
| **Ankara Bilim**, tarif yok | Kişi bulunur ama yalnızca kartta yazanlar gelir (ad, unvan). Bölüm, ilgi alanları ve ORCID gelmez. |
| **YÖK**, tarif yok | YÖK tamamen atlanır. Örnek: Mesut Ünlü'nün 21 yayınının 17'si YÖK'ten geliyordu. REA'sız 4 yayın kalır. YÖK'ten gelen ORCID de kaybolur, OpenAlex'te yanlış kişiyle eşleşme riski artar. |
| Site güncellendi | Bozulan tarif kendiliğinden onarılamaz. |

**Dürüst sınır:** REA imkânsızı yapmıyor. Bir geliştirici tarayıcının ağ sekmesinden bu istekleri elle bulabilirdi. REA'nın katkısı bunu **otomatik** yapması: keşfetmek, kaydetmek ve bozulunca yeniden öğrenmek. Klasik HTML sitelerde katkısı sınırlıdır.

---

## İlkeler

- **Genel çözüm.** Belirli bir üniversiteye ya da siteye özel kod yok.
- **Uydurma yok.** Analizdeki her cümle bir yayın kimliğine bağlı ve doğrulanıyor. Bulunamayan bilgi için "bulunamadı" deniyor; sahte yayın üretilmiyor.
- **Anlamayı model yapar, doğrulamayı kurallar.** Gemini karar verir, çıktısı sayfa metninde kontrol edilir.
- **Kibar tarama.** `robots.txt`'ye uyulur, sayfa ve derinlik sınırları vardır, sonuçlar önbelleğe alınır.

---

## Yayınlar: toplama, birleştirme, doğrulama

**Kaynaklar** (paralel sorgulanır):

| Kaynak | Not |
|---|---|
| YÖK Akademik | REA tarifiyle. Türkçe yayınlarda en zengin kaynak. |
| OpenAlex | ORCID varsa onunla; yoksa ad + kurum (eğitim kurumu tercih edilir). |
| Crossref | ORCID filtresiyle. |
| ORCID | Kişi sayfasında ya da YÖK'te ORCID bulunursa. |
| Google Scholar | Best-effort; engellenirse akış bozulmaz, CAPTCHA çözülmez. |

**Tekilleştirme** (`app/dedup.py`):

- aynı DOI ya da aynı normalize başlık
- bulanık başlık eşleşmesi (`rapidfuzz`, ≥92, yıl farkı ≤1)
- **TR↔EN çeviri eşleşmesi:** farklı dilde, aynı yıl, ortak yazar ya da aynı dergi olan çiftlerde Gemini'ye "aynı çalışma mı?" diye sorulur
- farklı DOI'ler asla birleştirilmez; tüm dil varyantları korunur

**Doğrulama** (`app/consensus.py`): her alan kaynak ağırlıklarıyla karşılaştırılır ve **doğrulandı / tek kaynak / çelişki / değişti** olarak etiketlenir.

---

## Sohbet: CAG, RAG, Hibrit

Profil çıktıktan sonra kişi hakkında soru sorulabilir. Yöntemi soru tipi belirler:

| Yöntem | Ne zaman | Nasıl |
|---|---|---|
| **CAG** | Genel sorular ("ana araştırma alanı ne?") | Tüm profil modelin bağlamına konur; önek her soruda aynı olduğu için Gemini örtük önbelleği tekrarlarda kullanılır. |
| **RAG** | Ayrıntı soruları ("2019'da hangi dergide yayın yaptı?") | BM25 (Türkçe kök + TR↔EN genişletme) ve gömme araması, RRF ile birleştirilir. |
| **Hibrit** | İkisinin arası | Çekirdek profil + ilgili parçalar. |

Sohbetler `data/chats/` altında saklanır; listelenebilir, açılabilir ve silinebilir.

---

## Ayarlar

Hepsi isteğe bağlı ortam değişkenleri:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PORT` | `8000` | Sunucu portu |
| `GEMINI_API_KEY` | — | Gemini anahtarı (`.env`) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Ana model |
| `GEMINI_FAST_MODEL` | `gemini-3.5-flash-lite` | Kısa işler |
| `GEMINI_FALLBACKS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash` | Hata/kota durumunda sırayla denenir |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-001` | RAG gömme modeli |
| `LLM_MODE` | `auto` | `mock` modeli devre dışı bırakır |
| `CAG_BUDGET_TOKENS` | `30000` | Bu sınırı aşan bilgi tabanında CAG yerine Hibrit |
| `CRAWL_MAX_PAGES` / `_DEPTH` / `_CONCURRENCY` | `90` / `3` / `8` | Tarama sınırları |
| `BRAVE_API_KEY` | — | Varsa resmi Brave Search API kullanılır |
| `DDGS_BACKEND` | `brave,duckduckgo,google` | `ddgs` motor sırası |
| `GOOGLE_SEARCH_ENABLED` | `1` | Google sonuç sayfası araması |
| `GOOGLE_REA_ENABLED` | `1` | Google sayfasını REA ile yakalama |
| `REA_BIN` | `node_modules/.bin/rea` | REA CLI yolu |
| `WATCH_INTERVAL_MIN` | — | Periyodik değişiklik taraması |

---

## Proje yapısı

```
app/
  main.py          FastAPI uç noktaları, iş hattı, SSE akışı
  discover.py      sitede kişiyi bulma ve profil çıkarma
  navigator.py     LLM ajanı, sayfalama, site içi arama formu (REA)
  spider.py        Scrapling Spider; JS sayfalarda REA
  rea.py           REA CLI entegrasyonu, StealthBridge (Scrapling ↔ REA)
  recipes.py       tarifler: öğrenme, tekrar oynatma, değişiklik algılama
  sources.py       YÖK, OpenAlex, Crossref, ORCID, Scholar
  dedup.py         tekilleştirme (TR↔EN dahil)
  consensus.py     kaynaklar arası doğrulama
  analysis.py      kanıtlı araştırma analizi
  chat.py          CAG / RAG / Hibrit sohbet
  paper.py         yayın detayı ve özet
  websearch.py     site: araması (ddgs → Brave API → Google → Brave sayfası)
  google_search.py Google sonuç sayfası (Playwright + REA)
  net.py           erişim katmanı: TLS zincir onarımı, duvar ve yumuşak 404 tespiti
  llm.py           Gemini istemcisi (JSON şeması, akış, embedding, model zinciri)
  text.py          Türkçe metin işleme: kök, unvan, ad eşleşmesi, dil tespiti
  history.py       sohbet ve sonuç geçmişi
static/            web arayüzü
data/
  recipes/         REA tarifleri ve değişiklik olayları (site başına)
  chats/           sohbet geçmişi
  facts/           doğrulanmış bilgiler
runs/              profil sonuçları
```

---

## Bilinen sınırlar

- **Test seti yok.** Başarı oranı ve süre sistematik olarak ölçülmedi; denemeler tek tek sitelerde yapıldı (OSTİM, Bilkent, Boğaziçi, Koç, Ankara Bilim, KTÜ).
- **Arama motorları:** ücretsiz motorlar yoğun kullanımda engelliyor. Arama motorlarını ve Google'ı otomatik sorgulamak kullanım koşulları açısından gri alan; kalıcı çözüm resmi bir API (`BRAVE_API_KEY`).
- **Gemini ücretsiz katmanı:** dakika ve gün sınırları var; yoğun kullanımda istekler yedek modellere kayar. Sayfa metinleri ve sorular Google'a gönderilir (kamuya açık kurum verisi).
- Tek kullanıcılı, yerel PoC. İşler bellekte tutulur, kimlik doğrulama yoktur.

---

## Kaynaklar

- [Scrapling](https://github.com/D4Vinci/Scrapling) (BSD-3-Clause)
- [REA](https://github.com/morluto/rea) (MIT)
- [OpenAlex API](https://docs.openalex.org) · [Crossref REST API](https://github.com/CrossRef/rest-api-doc) · [Gemini API](https://ai.google.dev/gemini-api/docs)

Proje kodu MIT lisanslıdır. Dış veri ve araçlarda kendi lisansları geçerlidir.
