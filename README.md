# Akademik İz

**Türkiye'deki akademisyenlerin kanıta dayalı araştırma profilini çıkaran asistan.**

Akademisyenin adını yazarsın, YÖK'te bulunanlardan doğru kişiyi seçersin; ya da üniversite → fakülte → bölüm ağacından gidersin. Sistem yayınlarını akademik kaynaklardan toplar, birleştirir ve doğrular; tezlerini, projelerini, patentlerini ve sanayi iş birliklerini ekler. Sonra o kişi hakkında soru sorabilirsin.

Ters yön de var: bir firma seçip onunla çalışan akademisyenleri, TÜBİTAK projelerini ve patentlerini görebilirsin.

Tarama ve veri toplama senin bilgisayarında çalışır. Dil modeli olarak Gemini API'nin ücretsiz katmanı kullanılır; ücretli servis gerekmez.

```
Scrapling · REA · Gemini
YÖK Akademik · YÖK Tez Merkezi · TR Dizin · OpenAIRE (DergiPark, üniversite arşivleri)
OpenAlex · Crossref · ORCID · Semantic Scholar · Google Scholar
TÜBİTAK (ARDEB, TEYDEB) · EPO (patent) · Bakanlık Ar-Ge / Tasarım Merkezi listesi
```

---

## Hızlı başlangıç

```bash
bash run.sh
```

Ardından **http://127.0.0.1:8000** adresini aç.

`run.sh` ilk çalıştırmada her şeyi kurar: Python ortamı, Scrapling tarayıcıları, REA (npm).

**Anahtarlar:** Yapay zekâ anahtarı (ör. Gemini: https://aistudio.google.com/apikey) uygulamada **Ayarlar** sayfasına yapıştırılır. İsteğe bağlı diğer anahtarlar proje kökündeki `.env` dosyasına yazılır:

```
OPENALEX_API_KEY=...   # isteğe bağlı, ücretsiz: https://openalex.org (hesap → API key)
EPO_KEY=...            # isteğe bağlı, ücretsiz: https://developers.epo.org (My Apps → Consumer Key)
EPO_SECRET=...         # patent sekmeleri yalnızca bu ikisi tanımlıysa görünür
```

OpenAlex anahtarsız da çalışır ama IP başına günlük ortak bütçe (~1000 istek) çabuk dolar; kendi anahtarınla kişisel bütçe kullanılır.

`.env` git'e girmez. Gemini anahtarı yoksa analiz ve sohbet basit kural tabanlı yedeğe (mock) düşer.

**Firma listesi:** `data/` klasörü git'te yok, bu yüzden yeni kurulumda Firmalar sayfası boş gelir. Bakanlığın Excel dosyaları CAPTCHA arkasında olduğu için elle indirilir (bağlantılar `scripts/import_arge.py` başında), sonra:

```bash
.venv/bin/python -m pip install openpyxl
.venv/bin/python scripts/import_arge.py Ar-Gemerkezleri.xlsx Tasarimmerkeziistatistik.xlsx
```

**Uzaktan bakmak için:** `cloudflared tunnel --url http://127.0.0.1:8000`. Uygulamada kimlik doğrulama olmadığından linki bilen herkes her şeyi yapabilir, kayıt silmek dahil. İşin bitince kapat. Tünel dışarıya 7844 portunu ister; yalnız 443'e izin veren ağlarda bağlanmaz.

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

Sağlayıcı, API adresi ve anahtar yalnızca **Ayarlar** sayfasından girilir (Gemini, ChatGPT, Claude ya da OpenAI uyumlu kendi sunucunuz); yapay zekâ için `.env` okunmaz. Ayarlar git'e girmeyen `.ai-settings.json` dosyasında durur; anahtarlar arayüze geri gönderilmez. Claude'da gömme modeli olmadığından sohbet yayınları kelime aramasıyla bulur.

Ücretsiz katmanda kota (429) ve yoğunluk (503) hataları olağandır. Hata alan istek sıradaki modelle (`GEMINI_FALLBACKS`) yeniden denenir; kotası dolan model 60 sn atlanır.

---

## Arayüz

| Menü | Ne yapar |
|---|---|
| **Ana sayfa** | Tek arama kutusu: incelenen akademisyen, üniversite ve firma önerir; ayrıca adı YÖK'te ya da konuyu yayınlarda aratır. |
| **Akademisyenler** | YÖK'te ad araması ve aday seçimi, incelenen profillerin listesi. YÖK'te olmayan kişi için "Site bağlantısıyla başlat". |
| **Üniversiteler** | YÖK'teki tüm üniversiteler. Fakülte → bölüm → akademisyen, birim yayınları. "Site dizini" aynı ağacı kurumun kendi sitesinden okur. |
| **Firmalar** | Resmi Ar-Ge ve Tasarım Merkezi olan firmalar. Firma sayfasında Akademisyenler, TÜBİTAK ve Patentler sekmeleri. |
| **Konular** | Bir alanda yazılmış yayınlar: OpenAlex, Crossref, Semantic Scholar, OpenAIRE ve TR Dizin birlikte aranır. Türkçe sorgu İngilizceye de çevrilir. |
| **Kütüphanem** | Favori makaleler ve akademisyenler. Yayın listeleri CSV ve BibTeX olarak indirilir. |
| **Sistem** | Servis durumu (yapay zekâ, REA, tarayıcı, EPO), öğrenilen site tarifleri, değişiklik taraması. |

**Profil sekmeleri:** Genel bakış, Yayınlar, Akademik geçmiş, Dersler, Tezler, Projeler ve diğer, İş birlikleri, Patentler, Asistan. "Yenile" düğmesi profili kaynaklardan baştan toplar; kayıt, sohbet ve favori korunur.

**Tema:** Sağ üstteki düğmeyle beyaz ya da kara; seçim hatırlanır, ilk açılışta bilgisayarın teması kullanılır. Hareketler sistemin "hareketi azalt" ayarına uyar.

---

## Nasıl çalışır

```
 ad → YÖK'te aday seçimi            (YÖK'te yoksa: kadro linki + ad)
        │
        ▼
 ┌──────────────┐   kurum sitesi kurumsal e-postanın alan adından bulunur
 │ Kişiyi bul   │   kayıtlı tarif / hafıza · arama motoru (site:) · LLM ajanı ∥ Spider
 │              │   YÖK'ten seçildiyse en çok 60 sn; site okunamazsa YÖK ile devam
 └──────┬───────┘
        ▼
 ┌──────────────┐   önce YÖK (ORCID burada netleşebilir), sonra paralel:
 │ Yayın topla  │   OpenAlex · Crossref · ORCID · TR Dizin · OpenAIRE · Tez Merkezi · Scholar
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ Birleştir    │   DOI · başlık · bulanık eşleşme · TR↔EN çeviri eşleşmesi
 │ & doğrula    │   doğrulandı / tek kaynak / çelişki / değişti
 └──────┬───────┘
        ▼
 ┌──────────────┐
 │ İş birlikleri│   firmalar, resmi Ar-Ge / Tasarım Merkezi listesiyle eşleştirilir
 └──────┬───────┘
        ▼
   Profil açılır ──► Patentler      EPO'dan, anahtar tanımlıysa
        │
        ├──────────► Analiz         "Yapay zekâ ile analiz et" denince; her cümle bir yayın kimliğine bağlı
        │
        └──────────► Sohbet         soru tipine göre CAG, RAG veya Hibrit otomatik seçilir
```

Her aşama arayüzde canlı akar. Ham teknik loglar **"Teknik ayrıntılar"** altında kapalı durur.

**Tek kişi, tek kayıt.** Aynı kişiye yeniden profil çıkarılırsa yeni kayıt açılmaz, mevcut kayıt güncellenir. Eşleştirme önce YÖK kimliğine, sonra ORCID'e bakar; ikisi de yoksa ad ve kurum birlikte aranır. Aynı adlı farklı kişiler ayrı kalır.

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

### YÖK Akademik: iki yol

**Liste ve arama (tarayıcısız).** Üniversite listesi, fakülte kadroları ve ad araması herkese açık sayfalardan gelir. Yapı tüm üniversitelerde aynı olduğundan her kurum için ayrı kod gerekmez. Ad araması REA'nın öğrendiği form isteğini kullanır. İstekler sıralıdır ve önbelleğe alınır (kadro 7 gün, ad araması 1 gün).

**Kişinin profili ve yayınları (tarayıcıyla).** YÖK bazı düz istemcilere `418` döndürür, arama da bir formun arkasındaki `POST` isteğidir.

- **Scrapling** gizli tarayıcıyla duvarı geçer.
- **REA** aynı tarayıcıya CDP üzerinden bağlanır, formu doldurur, Enter'a basar ve arkadaki `POST /AkademikArama/AkademisyenArama` isteğini gözler.
- Sonraki aramalarda tarif açık oturumun içinden doğrudan oynatılır.

### Öğrenilmiş tarifler

| Site | Tarif | Öğrenildi | Kullanım (3 Kasım 2026) |
|---|---|---|---|
| `yok.gov.tr` | `yok_search` | 16.10.2026 | 35 tekrar, 0 hata |
| `tez.yok.gov.tr` | `tez_search` | 30.10.2026 | 26 tekrar, 0 hata |
| `ankarabilim.edu.tr` | `profile_detail` | 16.10.2026 | 6 tekrar, 0 hata |

Tarifler `data/recipes/<alan-adı>.json` altında, REA kanıt kimliğiyle (`evidence_id`) birlikte tutulur. `data/` git'te olmadığından yeni kurulumda tarifler baştan öğrenilir. Güncel liste **Sistem → Öğrenilen tarifler** sayfasındadır.

### REA olmasa ne olur?

| Durum | Sonuç |
|---|---|
| Tarif zaten kayıtlı | Fark yok; tekrarı zaten Scrapling yapıyor. |
| **Ankara Bilim**, tarif yok | Kişi bulunur ama yalnızca kartta yazanlar gelir (ad, unvan). Bölüm, ilgi alanları ve ORCID gelmez. |
| **YÖK**, tarif yok | Ad araması ve kadro listeleri çalışır, ama kişinin YÖK yayınları ve görev geçmişi atlanır. Örnek: Mesut Ünlü'nün 22 yayınından 17 kayıt YÖK'ten geliyor. YÖK'ten gelen ORCID de kaybolur, OpenAlex'te yanlış kişiyle eşleşme riski artar. |
| **Tez Merkezi**, tarif yok | Tez kayıtları gelmez. Arama, oturuma bağlı bir form isteğidir. |
| Site güncellendi | Bozulan tarif kendiliğinden onarılamaz. |

**Dürüst sınır:** REA imkânsızı yapmıyor. Bir geliştirici tarayıcının ağ sekmesinden bu istekleri elle bulabilirdi. REA'nın katkısı bunu **otomatik** yapması: keşfetmek, kaydetmek ve bozulunca yeniden öğrenmek. Klasik HTML sitelerde katkısı sınırlıdır.

---

## İlkeler

- **Genel çözüm.** Belirli bir üniversiteye, siteye ya da firmaya özel kod yok.
- **Uydurma yok.** Analizdeki her cümle bir yayın kimliğine bağlı ve doğrulanıyor. Bulunamayan bilgi için "bulunamadı" deniyor; sahte yayın üretilmiyor.
- **Anlamayı model yapar, doğrulamayı kurallar.** Gemini karar verir, çıktısı sayfa metninde kontrol edilir.
- **Kibar tarama.** `robots.txt`'ye uyulur, sayfa ve derinlik sınırları vardır, sonuçlar önbelleğe alınır.
- **Kapalı kaynaklar otomatikleştirilmez.** Anahtarlı servisler anahtarsız kullanılmaz. Otomatik aramayı kapatan kaynaklara (DergiPark arama sayfası, TÜRKPATENT, Espacenet web araması) doğrudan gidilmez; varsa açık API kullanılır.
- **Kişisel veriye dikkat.** E-posta kişi kişi gösterilir; toplu e-posta listesi ya da dışa aktarımı yoktur.

---

## Yayınlar: toplama, birleştirme, doğrulama

**Kaynaklar:**

| Kaynak | Not |
|---|---|
| YÖK Akademik | REA tarifiyle. Türkçe yayınlarda en zengin kaynak. |
| OpenAlex | ORCID varsa onunla; yoksa ad + kurum (eğitim kurumu tercih edilir). |
| Crossref | ORCID filtresiyle. |
| ORCID | Kişi sayfasında ya da YÖK'te ORCID bulunursa. |
| TR Dizin | Ulusal dizin: makale ve TÜBİTAK projeleri. Yazar adıyla aranır, ad ve ORCID ile süzülür. |
| OpenAIRE | DergiPark, üniversite açık arşivleri, AVESİS, Aperta ve YÖK Açık Bilim kayıtları. DergiPark'a bu yoldan ulaşılır. |
| YÖK Tez Merkezi | REA tarifiyle, tarayıcısız. |
| Google Scholar | Best-effort; engellenirse akış bozulmaz, CAPTCHA çözülmez. |
| Web of Science | Profil açılınca Scrapling ile arka planda toplanır. Yazar kimliği doğrulanan makale ve bildiriler eklenir; mevcut yayınlarda WoS kaynak bağlantısı görünür. |

**Tekilleştirme** (`app/dedup.py`):

- aynı DOI ya da aynı normalize başlık
- bulanık başlık eşleşmesi (`rapidfuzz`, ≥92, yıl farkı ≤1)
- **TR↔EN çeviri eşleşmesi:** farklı dilde, aynı yıl, ortak yazar ya da aynı dergi olan çiftlerde Gemini'ye "aynı çalışma mı?" diye sorulur
- farklı DOI'ler asla birleştirilmez; tüm dil varyantları korunur

**Doğrulama** (`app/consensus.py`): her alan kaynak ağırlıklarıyla karşılaştırılır ve **doğrulandı / tek kaynak / çelişki / değişti** olarak etiketlenir.

**Yayın durumu:** Profilin yayın tablosundaki **Durum** sütunu kayıt türünü (makale, bildiri, yazılım, veri seti vb.) ve açıklamada açıkça belirtilen süreç bilgisini gösterir. Yazılım/veri arşivindeki “submitted” veya “under review” beyanı **ilgili makaleye** aittir; arşivin kendi durumu olarak sunulmaz. Gönderildi, değerlendirmede ve gönderime hazırlanıyor ayrı tutulur. Kanıt cümlesi ve kaynak durum metninin açıklamasındadır; kaynak bağlantısı varsa tıklanabilir. Açık beyan yoksa **Süreç bilgisi yok** görünür. DOI, WoS eşleşmesi veya birden fazla kaynak bulunması hakem değerlendirmesi/kabul kanıtı sayılmaz. Durum kayıtlı açıklamadan okunur; derginin güncel başvuru sistemini sorgulamaz. Eski profiller de açıldığında bu gösterimi alır.

**Birim yayınları:** YÖK dizininde veya kurum sitesinde seçilen fakülte/bölümün kayıtlı sonuçları açılışta gösterilir; kayıt varsa yeniden tarama başlamaz. Birim sonuçları sunucu yeniden başlatıldığında da korunur. Önceden birim kaydı oluşmamışsa mevcut akademisyen profilleri birleştirilerek gösterilir; eksik kişiler kendiliğinden taranmaz. **Tekrar tara**, aynı normal akademisyen profili akışıyla kaynakları yeniden toplar; önceki yayınlar bu sırada görünür kalır. Hiç kayıt olmayan birimde ilk tarama otomatik başlar. Aynı anda en fazla iki kişi hazırlanır ve WoS yayınları da eklenir. İlk 150 kişi / ilk 30 bölüm sınırı uygulanmaz. Ortak yayınlar DOI ve güvenli başlık eşleşmesiyle bir satırda birleşir; birimdeki yazarlar ve kaynak bağlantıları korunur. İlerleme, erişilemeyen kişiler ve eksik kalan kaynaklar görünür; taranan kaynakların her yayını kapsadığı garanti edilmez.

**Filtreler ve sıralama:** Profil, konu ve birim yayın tabloları kaynak, yıl aralığı ve aşama ile süzülebilir; başlık/yazar araması ve yıl/atıf sıralaması birlikte çalışır. Dışa aktarma süzülmüş listeyi kullanır. Akademik kadro varsayılan olarak makale sayısına göre sıralanır; atıf sayısı ve isim sırası seçilebilir. Kadroda isim ve yayın kaynağı filtresi vardır. Henüz profili toplanmamış kişinin yayın/atıf sayısı bilinmiyor olarak gösterilir.

**Konu aramasında WoS:** Açık kaynaklardan gelen sonuçlar bekletilmeden gösterilir; WoS, Scrapling ile kendi konu arama ekranında arka planda sorgulanır. Aynı yayın mevcut satıra WoS kaynağı ekler, yeni yayın ayrı satır olur. İlk 20 kayıt ve süre bütçesiyle sınırlı taramanın kapsamı arayüzde belirtilir. WoS erişilemezse diğer kaynakların sonuçları korunur.

---

## WoS yayınları ve JCR dergi çeyrekleri

Profil açılınca WoS'un kendi arama ekranında yazar kimliğiyle yayın aranır. ORCID/ResearcherID,
mevcut yayın eşleşmeleri ve destekleyici yazar/kurum bilgileri kullanılır; yalnız benzer ad yeni bir yayını
profile eklemek için yeterli değildir. DOI aynıysa kaynaklar aynı satırda birleşir. DOI yoksa başlık,
yıl ve yazar birlikte kontrol edilir; çelişkili DOI'ler birleştirilmez. Eksik yayınlar yeni satır olarak
eklenirken eski yayın kimlikleri, diğer kaynaklar, sohbet atıfları ve SJR bilgileri korunur.
Başlıkta küçük yazım hatası veya bir yıllık fark varsa eşleşme için ayrıca aynı tür, en az iki ortak yazar
ve neredeyse birebir uzun özet gerekir. Kaynaklar arasındaki yıl farkı WoS etiketinin açıklamasında korunur.

WoS kaynak etiketi kayıt sayfasına bağlanır, indeks bilgisi açıklamasında gösterilir. Konferans bildirileri
de kaynak olarak alınır; WoS'ta bulunması JCR çeyreği bulunduğu anlamına gelmez. Yeni buton gerekmez.
Yayın taraması sınırlı ve önbelleklidir; erişim hatası önceki doğrulanmış yayınları silmez. Tamamlanan
taramalar 1 gün, kısmi/hatalı taramalar 15 dakika sonra tekrar denenebilir. Giriş gerektiğinde tarama durur.
Profil ve birim taramalarında kişiye ait olduğu doğrulanan her WoS yayını toplama sürerken kaydedilir
ve tabloya aktarılır; bütün taramanın bitmesi beklenmez. İş yarıda kesilirse kaydedilmiş yayınlar
korunur ve yarım kayıt, sonraki taramayı önbellekten engellemez. Birim taraması ilk yayın geldiğinde
tamamlandı sayılmaz; diğer kayıtları toplamaya devam eder.

**Etkileşimli WoS doğrulaması:** WoS insan doğrulaması istediğinde uygulamada **WoS doğrulaması**
paneli açılır. Panel, taramanın kullandığı aynı tarayıcı oturumunun canlı görüntüsüdür; fare ve klavye
işlemleri o sayfaya iletilir. Doğrulamayı kullanıcı tamamlar. WoS içeriğinin geri geldiği doğrulanınca
panel kapanır ve profil, konu veya birim taraması kaldığı yerden devam eder. Doğrulama için en fazla
5 dakika beklenir; bu süre WoS tarama bütçesinden düşülmez. **Şimdilik gizle** beklemeyi sürdürür ve
panel yeniden açılabilir; **Taramayı atla** o doğrulama bekleyişini sonlandırır. Diğer kaynaklardan
toplanan sonuçlar korunur. Ayrı bir WoS oturumu açılmaz; ücretli çözücü, API anahtarı veya tarayıcı
eklentisi gerekmez. Bu işlem kurum aboneliği veya WoS giriş gereksiniminin yerini almaz.
Panel eklenmeden önce kaydedilmiş insan doğrulaması hataları ilk yeniden açılışta bir kez daha
denenir; eski hata önbelleği panelin açılmasını engellemez. Kullanıcının atladığı veya süresi dolan
yeni doğrulamalar bu geçiş kuralıyla tekrar tekrar başlatılmaz.
Profil açıkken bağlantı kesilirse WoS sonuç takibi yeniden bağlanır; sunucu yeniden başladığı için
iş kaybolmuşsa sınırlı sayıda yeniden başlatır. Doğrulama tamamlandığında sonuç takibi de uyanır.
Sunucu yeniden başlatılırsa açık WoS tarayıcı oturumu korunmaz ve doğrulama tekrar istenebilir.

Profil açıldığında DOI'si olan makaleler için WoS/JCR kontrolü arka planda başlar; profilin açılmasını bekletmez.
Mevcut SJR etiketi korunur, WoS/JCR sonucu ayrı ve kaynak sayfasına bağlı bir etiketle gösterilir.
WoS kaydındaki DOI yayınla birebir eşleşmelidir. JCR yılı sayfada açıklanmıyorsa yıl etikete eklenmez;
yayın yılı veya JCI yılı yerine geçirilmez. Yılın açıklanmadığı bilgisi ve kategoriler etiketin açıklamasında görünür.

Bilinen DOI–WoS bağlantıları `app/wos_records.json` dosyasında tutulur (başlangıç kaydı kullanıcı tarafından
verilen WoS bağlantısıdır; Q değeri kodda sabit değildir). Toplanan WoS yayınlarının kendi bağlantıları kullanılır;
bağlantısı bilinmeyen kayıtlar aynı doğrulanmış Scrapling oturumunda doğrudan WoS'un DOI alanında,
gerekirse başlık alanında aranır. Bu adımda Brave veya başka bir arama motoru kullanılmaz.
Her adayın tam kayıt sayfasındaki DOI yeniden kontrol edilir; arama listesinden çeyrek bilgisi alınmaz.
Doğru kayıt bulunmuş ancak JCR bilgisi yoksa başka aramalarla çeyrek tahmin edilmez.
Her yayının kaydının bulunması garanti edilmez.
Scrapling kayıt sayfasını okur; giriş/erişim engelinde tarama durur. Arayüzde yalnızca bulunan çeyrekler gösterilir.
Başarılı sonuçlar `data/wos/` altında 7 gün, sonuçsuz/hatalı kontroller 15 dakika saklanır.
Profil yeniden açıldığında süresi dolmuş kontroller otomatik yenilenir.
SJR filtreleri ve sayımları yalnızca SJR verisini kullanmaya devam eder.

---

## Firmalar ve sanayi iş birlikleri

Firma listesi, Sanayi ve Teknoloji Bakanlığı'nın Ar-Ge ve Tasarım Merkezi listelerinden gelir (`data/arge_merkezleri.json`). Aynı firmanın merkezleri tek satırda toplanır.

| Yön | Kanıtlar |
|---|---|
| **Akademisyen → firma** | Ortak yayın (OpenAlex'te kurum türü "company", TR Dizin'de firma adlı yazar kurumu), YÖK "Üniversite Dışı Deneyim", YÖK proje ve patent satırları, TR Dizin projeleri |
| **Firma → akademisyen** | OpenAlex ve TR Dizin ortak yayınları, özetinde firma geçen TÜBİTAK ARDEB projelerinin ekipleri, çıkarılmış profillerdeki iş birlikleri |
| **Firma → proje** | TÜBİTAK ARDEB ve tamamlanmış TEYDEB projeleri (PRODİS, Açık Bilim) |

Firma sonuçları 7 gün saklanır; OpenAlex kotası dolduğunda eksik sonuç saklanmaz. Konuya göre TÜBİTAK araması şimdilik yalnız API'de (`/api/tubitak/ardeb?q=`, `/api/tubitak/teydeb?q=`), arayüzde düğmesi yok.

**Sınır:** Sonuç eksik olabilir ama her satır kanıta dayanır. Gizli sözleşmeler ve yayına dönüşmeyen işler görünmez.

---

## Dergi çeyreği (Q1–Q4)

Yayınların dergi çeyreği, içe aktarılan SCImago (SJR) listelerinden gösterilir:

1. [scimagojr.com/journalrank.php](https://www.scimagojr.com/journalrank.php) adresinden her yıl için "Download data" ile dosyayı indirip `data/sjr/` klasörüne koyun.
2. `python scripts/import_sjr.py` komutunu çalıştırın. Yeni yıl çıkınca dosyayı ekleyip aynı komutu tekrarlamak yeterlidir.

Yayın, çıktığı yılın listesiyle eşleşir; o yılın listesi yoksa en son liste kullanılır ve etikette o yıl yazar. Dergi önce ISSN, yoksa adının birebir eşleşmesiyle bulunur. Alanlara göre çeyrek farklıysa aralık gösterilir (`SJR 2024 Q1–Q2`). SJR Scopus tabanlıdır ve WoS/JCR çeyreğiyle aynı değildir.

## Patentler

Kaynak EPO Open Patent Services'tir (Espacenet'in verisi; EP, WO ve TR yayınları). Anahtar tanımlı değilse patent sekmeleri görünmez.

- **Akademisyen:** Buluş sahibi adıyla aranır. Patentlerde ORCID olmadığı için aynı adlı başka kişiler karışabilir; patentin sahibi kişinin kendi kurumu ya da kendisiyse "kesin", değilse "olası" sayılır.
- **Firma:** Patent sahibi adıyla aranır.
- **Patent penceresi:** Özet, açıklama metni ve orijinal belgenin sayfaları. Tam metin yalnız EP ve WO için var; TR yayınlarında EPO metni vermiyor, sayfalar görüntü olarak gösterilir.
- **Kota:** Haftada 4 GB ve dakikada yaklaşık 10 arama. Açıklama metinleri `data/patents/` altında saklanır.

---

## Sohbet: CAG, RAG, Hibrit

Profil çıktıktan sonra kişi hakkında soru sorulabilir. Yöntemi soru tipi belirler:

| Yöntem | Ne zaman | Nasıl |
|---|---|---|
| **CAG** | Genel sorular ("ana araştırma alanı ne?") | Tüm profil modelin bağlamına konur; önek her soruda aynı olduğu için Gemini örtük önbelleği tekrarlarda kullanılır. |
| **RAG** | Ayrıntı soruları ("2019'da hangi dergide yayın yaptı?") | BM25 (Türkçe kök + TR↔EN genişletme) ve gömme araması, RRF ile birleştirilir. |
| **Hibrit** | İkisinin arası | Çekirdek profil + ilgili parçalar. |

Sohbetler `data/chats/` altında saklanır; profille birlikte açılır ve silinebilir. Cevaplardaki `[P#]` atıfları yayın listesindeki sıradır; profil yenilenip liste değişince numaralar güncellenir, listeden düşen yayının numarası yerine adı yazılır.

---

## Ayarlar

Hepsi isteğe bağlı ortam değişkenleri:

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PORT` | `8000` | Sunucu portu |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Ana model |
| `GEMINI_FAST_MODEL` | `gemini-3.5-flash-lite` | Kısa işler |
| `GEMINI_FALLBACKS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash` | Hata/kota durumunda sırayla denenir |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-001` | RAG gömme modeli |
| `LLM_MODE` | `auto` | `mock` modeli devre dışı bırakır |
| `CAG_BUDGET_TOKENS` | `30000` | Bu sınırı aşan bilgi tabanında CAG yerine Hibrit |
| `OPENALEX_API_KEY` | — | OpenAlex kişisel bütçesi |
| `OPENALEX_MAILTO` | `akademik-iz@example.org` | OpenAlex isteklerindeki iletişim adresi |
| `EPO_KEY` / `EPO_SECRET` | — | Patentler (EPO OPS) |
| `CRAWL_MAX_PAGES` / `_DEPTH` / `_CONCURRENCY` | `90` / `3` / `8` | Tarama sınırları |
| `BRAVE_API_KEY` | — | Varsa resmi Brave Search API kullanılır |
| `DDGS_BACKEND` | `brave,duckduckgo,google` | `ddgs` motor sırası |
| `GOOGLE_SEARCH_ENABLED` | `1` | Google sonuç sayfası araması |
| `GOOGLE_REA_ENABLED` | `1` | Google sayfasını REA ile yakalama |
| `REA_BIN` | `node_modules/.bin/rea` | REA CLI yolu |
| `REA_CHROME` | — | REA'nın kullanacağı Chromium yolu |
| `PLAYWRIGHT_BROWSERS_PATH` | — | Playwright tarayıcılarının klasörü |
| `WATCH_INTERVAL_MIN` | `0` (kapalı) | Periyodik değişiklik taraması |

---

## Proje yapısı

```
app/
  main.py          FastAPI uç noktaları, iş hattı, SSE akışı
  config.py        ayarlar, araç keşfi (REA, Chromium, Gemini)

  yokdir.py        YÖK dizini: üniversite → fakülte → akademisyen, ad araması
  directory.py     kurum sitesi dizini (Scrapling + Gemini)
  discover.py      sitede kişiyi bulma ve profil çıkarma
  navigator.py     LLM ajanı, sayfalama, site içi arama formu (REA)
  spider.py        Scrapling Spider; JS sayfalarda REA
  rea.py           REA CLI entegrasyonu, StealthBridge (Scrapling ↔ REA)
  recipes.py       tarifler: öğrenme, tekrar oynatma, değişiklik algılama

  sources.py       YÖK, OpenAlex, Crossref, ORCID, Scholar
  trsources.py     TR Dizin, OpenAIRE, YÖK Tez Merkezi, TÜBİTAK projeleri
  dedup.py         tekilleştirme (TR↔EN dahil)
  consensus.py     kaynaklar arası doğrulama
  analysis.py      kanıtlı araştırma analizi
  chat.py          CAG / RAG / Hibrit sohbet
  paper.py         yayın detayı ve özet

  industry.py      akademisyen → firma: sanayi iş birlikleri
  firms.py         firma → akademisyen, ARDEB ve TEYDEB projeleri
  patents.py       EPO patentleri, açıklama metni, belge sayfaları
  library.py       favoriler ve konu araması
  history.py       profil kayıtları, sohbetler, aynı kişiyi eşleştirme

  websearch.py     site: araması (ddgs → Brave API → Google → Brave sayfası)
  search_worker.py süre aşımında sonlandırılabilen ddgs işçisi
  google_search.py Google sonuç sayfası (Playwright + REA)
  net.py           erişim katmanı: TLS zincir onarımı, duvar ve yumuşak 404 tespiti
  llm.py           Gemini istemcisi (JSON şeması, akış, embedding, model zinciri)
  text.py          Türkçe metin işleme: kök, unvan, ad eşleşmesi, dil tespiti
scripts/
  import_arge.py   Bakanlık Excel dosyalarını data/arge_merkezleri.json'a çevirir
static/            web arayüzü (index.html, app.js, style.css)

git'e girmeyenler:
data/
  recipes/         REA tarifleri ve değişiklik olayları (site başına)
  chats/           sohbet geçmişi
  facts/           doğrulanmış bilgiler
  yok/             YÖK dizini önbelleği
  directory/       kurum sitesi dizini önbelleği
  firms/           firma sonuçları önbelleği
  patents/         patent açıklama metinleri
  arge_merkezleri.json   resmi Ar-Ge / Tasarım Merkezi listesi
runs/              profil sonuçları
```

---

## Bilinen sınırlar

- **Test seti yok.** Başarı oranı ve süre sistematik olarak ölçülmedi; denemeler tek tek sitelerde yapıldı (OSTİM, Bilkent, Boğaziçi, Koç, Ankara Bilim, KTÜ, TED, İTÜ).
- **Arama motorları:** Ücretsiz motorlar yoğun kullanımda engelliyor. Arama motorlarını ve Google'ı otomatik sorgulamak kullanım koşulları açısından gri alan; kalıcı çözüm resmi bir API (`BRAVE_API_KEY`).
- **Gemini ücretsiz katmanı:** Dakika ve gün sınırları var; yoğun kullanımda istekler yedek modellere kayar. Sayfa metinleri ve sorular Google'a gönderilir (kamuya açık kurum verisi).
- **Scholar eşleşmesi:** Ad benzerliğine dayanır, aynı adlı başka birinin yayını listeye girebilir.
- **Patentler:** Ada göre eşleştiği için "olası" etiketli kayıtlar başka kişiye ait olabilir. TÜRKPATENT'te olup EPO'ya yansımamış kayıtlar görünmez.
- **Firma listesi:** Yalnız resmi Ar-Ge ve Tasarım Merkezi olan firmaları kapsar; elle içe aktarıldığı için güncelliği son içe aktarma tarihine bağlıdır.
- **Tek kullanıcılı, yerel PoC.** Çalışan işler bellekte tutulur, kimlik doğrulama yoktur.

---

## Kaynaklar

- [Scrapling](https://github.com/D4Vinci/Scrapling) (BSD-3-Clause)
- [REA](https://github.com/morluto/rea) (MIT)
- [Gemini API](https://ai.google.dev/gemini-api/docs) · [OpenAlex API](https://docs.openalex.org) · [Crossref REST API](https://github.com/CrossRef/rest-api-doc)
- [YÖK Akademik](https://akademik.yok.gov.tr) · [YÖK Tez Merkezi](https://tez.yok.gov.tr) · [TR Dizin](https://search.trdizin.gov.tr) · [OpenAIRE Graph](https://graph.openaire.eu)
- [EPO Open Patent Services](https://developers.epo.org) · [Ar-Ge ve Tasarım Merkezleri](https://agtm.sanayi.gov.tr)

Proje kodu MIT lisanslıdır. Dış veri ve araçlarda kendi lisansları geçerlidir.
