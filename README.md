# Akademik İz — akademisyen araştırma profili PoC

FastAPI + SSE, **D4Vinci/Scrapling**, **morluto/rea CLI**, OpenAlex/Crossref ve yerel Ollama/Qwen2.5. Ücretli API veya bulut LLM kullanılmaz. Türkçe koyu temalı arayüz HTML/CSS/JavaScript kullanır; CDN bağımlılığı yoktur.

**Teslim durumu:** Kullanıcının isteği üzerine kod yazıldı; bağımlılık kurulumu, çalıştırma ve test yapılmadı. Çalıştığı doğrulanmış bir teslim olarak değerlendirilmemelidir.

## Tek komutla çalıştır

Python 3.11+ yüklü olmalı. Proje dizininde:

```bash
bash run.sh
```

İlk çalıştırmada paketleri kurmak için internet gerekir. http://127.0.0.1:8000 adresini açın. **Örnek demoyu keşfet**, dış servislerden bağımsız kurgu veri akışını başlatır; REA, Ollama veya tarayıcı gerektirmez. Beş kurgu kaydın dört yayına birleşmesi hedeflenir. Demo gerçek akademisyene atfedilmez; kendi kurgu adıyla gösterilir.

Gerçek arama girdileri:

- Üniversite linki: `[BURAYA AKADEMİK KADRO LİNKİ]`
- Akademisyen adı: `[BURAYA AD]`

Yer tutucuları gerçek adres ve adla değiştirin. Gerçek aramada sahte yayın üretilmez; kaynak bulunamazsa 0 yayın ile tamamlanır.

## REA ve dinamik sayfalar

Node.js 22.19+ (22.x), 24.11+ (24.x) veya 26+:

```bash
npm install
.venv/bin/python -m playwright install chromium
```

REA proje içindeki `node_modules/.bin/rea` üzerinden çağrılır; global `rea` veya `REA_BIN=/tam/yol/rea` da kullanılabilir. `rea-agents` morluto/rea paketidir; ücretli native analiz araçlarına ihtiyaç yoktur.

Scrapling Fetcher önce statik sayfayı okur. İçerik yetersizse ayrı bir Chromium başlatılır. REA `inspect-web-page <loopback-CDP> <target-id> --observation-ms 6000 --include-accessibility-text --include-json-body-shapes --json` çağrısıyla ağ yapısını inceler. Uygulama sayfayı yeniden yükler; REA pasif gözlem yapar. Aynı origin üzerindeki keşfedilmiş GET JSON isteklerinden adla eşleşen kayıtlar alınır. Tarayıcı sonunda kapatılır. Gözlem penceresi bütün istekleri yakalamayı garanti etmez.

REA yoksa/hata verirse Scrapling DynamicFetcher denenir; o da kullanılamazsa eldeki statik içerikle devam edilir. Fallback logda açıkça görünür. Demo modunda bu adımlar simüle edilir; gerçek servis çağrılmış gibi gösterilmez.

## Yerel Ollama/Qwen

Ollama kurulu değilse otomatik mock analiz kullanılır. Gerçek model için ayrı terminalde:

```bash
ollama serve
ollama pull qwen2.5:7b
```

Ollama zaten servis olarak çalışıyorsa `serve` gerekmez. `OLLAMA_URL` varsayılanı `http://127.0.0.1:11434`; `OLLAMA_MODEL` varsayılanı `qwen2.5:7b`. Daha küçük model: `ollama pull qwen2.5:3b`, ardından `OLLAMA_MODEL=qwen2.5:3b bash run.sh`.

Model erişilemezse, 120 saniyede cevap vermezse veya JSON/kanıt kontrolünü geçemezse **mock analiz** devreye girer. Zorlamak için `LLM_MODE=mock bash run.sh`. Mock, mevcut başlık/özetlerde sınırlı anahtar sözcük kurallarıyla alan, yöntem ve yıl dağılımı çıkarır; eşleşme yoksa iddia yazmaz. Demo daima mock kullanır.

Qwen en güncel 35 yayını analiz eder. Her iddianın tek cümle olması, geçerli yayın ID'sine dayanması ve zaman çizelgesi kanıtlarının yılı kontrol edilir. Anlamsal kanıt uygunluğu garanti edilmez. Her iddianın yanında yayının başlığı ve bağlantısı gösterilir. Kurgu yayın bağlantıları sayfa içindeki demo kaydına gider.

## Yayın toplama ve birleştirme

1. OpenAlex yazarları adla arar; ORCID varsa onu kullanır. Aksi halde tam ad + kurum eşleşmesi gerekir. Birden çok aday varsa rastgele seçim yapılmaz.
2. Crossref ikinci sırada ek kayıtlar için aranır. Kurum ve ad aynı yazar nesnesinde eşleşmelidir; ORCID varsa önceliklidir. Kurum metadatası eksik yayınlar kaçabilir.
3. İki kaynak da boşsa Scholar kısa zaman aşımıyla bir kez denenir. Bot engeli tüm akışı bozmaz; CAPTCHA çözümü yapılmaz. Scholar kayıtları kurum doğrulanamadı etiketiyle gösterilir. OpenAlex sonuç vermişse Scholar'a ihtiyaç duyulmaz; kullanılmayan kaynağa başarısız olmuş gibi log yazılmaz.
4. Kaynak başına en fazla 100 kayıt alınır; tam bibliyografya iddiası yoktur. OpenAlex anahtarsız ücretsiz istek denenir; erişim/kota hatasında Crossref'e geçilir. Servis koşulları değişebilir.
5. Aynı DOI birleştirilir. DOI yoksa yıl + ortak yazar + aynı başlık veya sınırlı TR/EN sözlüğüyle çok yüksek başlık örtüşmesi gerekir. Farklı DOI'ler birleştirilmez. Bu, genel çok dilli semantik tekilleştirme değildir. Orijinal varyantlar, kaynaklar ve diller korunur. `langdetect` kısa başlıklarda yanılabilir; düşük güven `Belirsiz` gösterilir.

## Yayın ayrıntısı ve YÖK

YÖK ayrıntıları eski `yayinDetay.jsp?id=…&no=…` adresi doğrudan açılarak okunmaz.
Akademisyen profili üzerinden güncel yayın listesi açılır; başlık/yıl eşleşmesinden
sonra ayrıntı isteği aynı tarayıcı oturumunda yapılır. Yeni kayıtlarda profil
bağlamı birleştirme sırasında korunur; eski raporlarda raporun YÖK profil bağlantısı
kullanılır. Kaynak düğmesi akademisyenin YÖK profiline gider.

Genel site açıklamaları ve oturum hataları makale özeti kabul edilmez. Gerçek
özet veya Semantic Scholar TL;DR metni yoksa Qwen çağrılmaz; yalnızca künye
gösterilir. Erişilemeyen sayfa için yayının hiç özeti olmadığı iddia edilmez.
Bu düzenleme test veya canlı YÖK sorgusu çalıştırılmadan yapılmıştır.

## Docker

```bash
docker compose up --build
```

Aynı adreste çalıştırılır. İmaj Scrapling ve Chromium içerir; REA içermez, DynamicFetcher fallback'i kullanır. Tam REA akışı için yerel Node kurulumunu kullanın. Ollama ana makinede `host.docker.internal` üzerinden aranır; erişilemezse mock analiz kullanılır. Açık kaynak Podman ve uyumlu compose sağlayıcısı alternatif olarak kullanılabilir. Docker kurulumu/build de doğrulanmadı.

## Dosyalar

- `app/main.py`: iş oluşturma, SSE ve süreç yönetimi
- `app/scraper.py`: Scrapling, REA CLI ve Scholar fallback
- `app/publications.py`: OpenAlex/Crossref ve yazar eşleştirme
- `app/data.py`: dil tespiti, birleştirme ve kurgu demo
- `app/analysis.py`: Ollama, kanıt doğrulama ve mock
- `static/`: tek sayfa arayüz
- `run.sh`, `Dockerfile`, `compose.yaml`: çalıştırma

PoC yerel ve tek kullanıcı içindir. Tek worker kullanın. İşler bellektedir; sunucu yeniden başlarsa kaybolur, tamamlanan işler bir saat sonra yeni iş açılırken temizlenir. Başlangıç URL ve statik yönlendirmelerde özel IP kontrolü vardır; dinamik tarayıcı tam ağ izolasyonu sağlamaz. Çok kullanıcılı internet dağıtımı için ağ izolasyonu, kimlik doğrulama ve kalıcı iş kuyruğu gerekir. E-posta profil alanı oluşturulmaz; analiz metnindeki e-posta desenleri çıkarılır. Unvan/bölüm bulma HTML yapısına bağlı sezgiseldir; bulunamayan alanlar belirtilir.

## Resmî kaynaklar

- https://github.com/D4Vinci/Scrapling (BSD-3-Clause)
- https://github.com/morluto/rea (MIT)
- https://github.com/morluto/rea/blob/main/docs/browser-observation.md
- https://help.openalex.org/api/authentication/
- https://github.com/CrossRef/rest-api-doc
- https://docs.ollama.com/api/generate

Proje kodu MIT lisanslıdır; dış veri ve araçların kendi lisansları geçerlidir.

## SSL ve eksik sonuç düzeltmesi

Scrapling sertifika zinciri hatasında hata ayrıntısı loga yazılır; sistem `curl` ile TLS doğrulaması açık tutularak HTTP okunur, HTML yine Scrapling ile ayrıştırılır. `curl` yoksa sistemin paket yöneticisiyle kurulmalıdır. Özel CA kullanılıyorsa `SCRAPLING_CA_BUNDLE=/tam/yol/ca.pem bash run.sh` ayarlanabilir. TLS doğrulaması kapatılmaz.

Kurum ismi özgeçmişte geçen mezun olunan üniversiteden alınmaz. OSTİM alan adı güncel kuruma eşlenir; Türkçe `Teknik` ve İngilizce `Technical` yayın eşleştirmesinde normalize edilir. Program başlıkları ve biyografideki ilgi alanları okunur. Üniversite sayfasındaki doğrudan Scholar profil bağlantısı son çare olarak kullanılır. Yayın bulunmazsa mock analiz tamamlandı yerine analiz yapılmadı/kısmi sonuç gösterilir.

Değişikliklerden sonra sunucuyu Ctrl+C ile durdurup `bash run.sh` ile yeniden başlatın; tarayıcıyı tam yenileyin. Bu düzeltmede test paketi veya uçtan uca uygulama testi çalıştırılmadı.
