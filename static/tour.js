/* Rehber: uygulamayı baştan sona, adım adım anlatan turlar (driver.js üzerinde).
 *
 * Her adım ekrandaki bir bölümü öne çıkarır, gerisini karartır ve yanında kısa bir açıklama gösterir. Tur sayfalar
 * arasında kendisi dolaşır, sekmeleri kendisi açar; kullanıcı yalnız "İleri" ve "Geri" düğmelerine basar.
 *
 * Bir adımın biçimi:
 *   { sel, title, text, side?, pre?, wait?, must? }
 *     sel   : öne çıkarılacak öğe (CSS seçici, seçici listesi ya da öğe döndüren işlev). Yoksa açıklama ortada görünür.
 *     pre   : adımdan önce yapılacak iş (sayfaya git, sekmeyi aç). Tur bunu kendisi çalıştırır.
 *     wait  : öğenin ekrana gelmesi için en çok bekleme (ms). Öğe gelmezse adım sessizce atlanır;
 *     must  : true ise atlanmaz, açıklama ekranın ortasında gösterilir (sayfa değişen adımlar).
 * Arayüzde bir bölümün adı ya da yeri değişirse ilgili adımın `sel` değeri güncellenir.
 */
(function () {
  "use strict";
  const makeDriver = window.driver && window.driver.js && window.driver.js.driver;
  if (!makeDriver) return;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const shown = (el) => Boolean(el && el.isConnected && el.getClientRects().length);
  const OSTIM = "ostim-teknik-universitesi";

  // ------------------------------------------------------------------ adım öncesi işler
  const go = (hash) => async () => {
    if (location.hash === hash) return;
    location.hash = hash;
    await sleep(650);  // sayfa geçiş animasyonu ve ilk çizim
  };
  const press = (sel, pause = 350) => async () => {
    const el = $$(sel).find(shown);
    if (el && !el.classList.contains("active") && el.getAttribute("aria-selected") !== "true") { el.click(); await sleep(pause); }
  };
  const tab = (key) => press(`.tabs .tab[data-tab="${key}"]`);
  const audience = (key) => press(`.audience-tabs [data-audience="${key}"]`, 500);
  // Kapalı bir <details> bölümünü açar (öğrenci bakışındaki fakülte, bölüm, dönem ve ders satırları).
  const unfold = (sel, pause = 700) => async () => {
    const el = $$(sel).find(shown);
    if (el && !el.open) { el.open = true; await sleep(pause); }
  };
  const both = (...jobs) => async () => { for (const job of jobs) await job(); };
  // Akademisyen bakışında ilk fakülteyi ve ilk bölümü seçer (seçili olan yoksa).
  const pick = (column) => async () => {
    if ($(`${column} .unit.active`)) return;
    const first = $$(`${column} .unit`).find(shown);
    if (first) { first.click(); await sleep(900); }
  };

  // ------------------------------------------------------------------ turlar
  const home = () => [
    { pre: go("#/"), must: true, title: "Akademik İz'e hoş geldiniz",
      text: "Bu rehber uygulamayı baştan sona anlatır. Her adımda ekranın bir bölümü aydınlatılır, gerisi kararır. Siz yalnızca <b>İleri</b> düğmesine basın; sayfalar arasında rehber kendisi dolaşır. İstediğiniz an sağ üstteki çarpıyla çıkabilirsiniz." },
    { must: true, title: "Bu uygulama ne yapar?",
      text: "Akademik İz üç şeyi bir arada gösterir: <b>akademisyenleri</b> (yayınları, dersleri, projeleri), <b>üniversiteleri</b> (fakülte, bölüm, ders planı) ve <b>firmaları</b> (hangi akademisyenlerle çalıştıkları). Bilgiler YÖK, OpenAlex, TR Dizin gibi açık kaynaklardan ve kurumların kendi sitelerinden toplanır." },
    { sel: "#side .brand", side: "right", title: "Logo: ana sayfaya dönüş", text: "Uygulamanın neresinde olursanız olun, bu logoya basınca ana sayfaya dönersiniz." },
    { sel: "#nav", side: "right", title: "Ana menü", text: "Uygulamanın bütün bölümleri bu menüdedir. Şimdi her birine sırayla bakacağız." },
    { sel: '#nav [data-nav="home"]', side: "right", title: "Ana sayfa", text: "Arama kutusunun ve son incelediklerinizin bulunduğu başlangıç ekranı." },
    { sel: '#nav [data-nav="akademisyenler"]', side: "right", title: "Akademisyenler", text: "Bir akademisyeni adıyla arayıp profilini çıkardığınız bölüm. Yanındaki sayı, şimdiye kadar incelediğiniz profil sayısıdır." },
    { sel: '#nav [data-nav="universiteler"]', side: "right", title: "Üniversiteler", text: "Türkiye'deki üniversitelerin listesi. Bir üniversiteyi açınca fakültelerini, bölümlerini, kadrosunu ve ders planlarını görürsünüz." },
    { sel: '#nav [data-nav="firmalar"]', side: "right", title: "Firmalar", text: "Ar-Ge yapan firmalar. Bir firmayı açınca hangi akademisyenlerle çalıştığını, projelerini ve patentlerini görürsünüz." },
    { sel: '#nav [data-nav="ara"]', side: "right", title: "Konu bul", text: "Bir araştırma konusu yazarsınız; o konuda yazılmış yayınlar ve o alanda çalışan kişiler listelenir." },
    { sel: '#nav [data-nav="danisman"]', side: "right", title: "Danışman bul", text: "Tez ya da proje için konu yazarsınız; o konuda yayını olan akademisyenler önerilir." },
    { sel: '#nav [data-nav="kutuphane"]', side: "right", title: "Kütüphanem", text: "Yıldızladığınız yayınlar ile favorilere eklediğiniz akademisyen, üniversite ve firmalar burada toplanır." },
    { sel: '.side-foot [data-nav="sistem"]', side: "right", title: "Ayarlar", text: "Yapay zekâ anahtarı, arama servisleri ve tarama hızı buradan ayarlanır. Rehberin son bölümünde ayrıntısıyla anlatılacak." },
    { sel: "#env", side: "right", title: "Durum göstergesi", text: "Yapay zekânın hazır olup olmadığını gösterir. <b>Yeşil</b> nokta hazır demektir; kapalıysa analiz ve sohbet özellikleri çalışmaz, diğer her şey çalışmaya devam eder." },
    { sel: "#menuBtn", side: "bottom", title: "Menüyü daralt", text: "Soldaki menüyü daraltıp içeriğe daha çok yer açar. Tekrar basınca menü geri gelir." },
    { sel: "#crumbs", side: "bottom", title: "Neredeyim?", text: "Bulunduğunuz sayfanın yolu burada yazar. Yoldaki bir adıma basarak bir önceki sayfaya dönebilirsiniz." },
    { sel: "#themeBtn", side: "left", title: "Açık / koyu görünüm", text: "Ekranı açık renkten koyu renge, koyudan açığa çevirir. Seçiminiz hatırlanır." },
    { sel: "#omni", side: "bottom", title: "Tek arama kutusu", text: "Buraya bir <b>akademisyen adı</b>, <b>üniversite</b>, <b>firma</b> ya da <b>konu</b> yazın. Yazdıkça eşleşenler altında listelenir; birini seçince ilgili sayfa açılır." },
    { sel: ".hero-try", side: "bottom", title: "Hazır örnekler", text: "Ne yazacağınızı bilmiyorsanız bu örneklerden birine basın; arama kutusu sizin yerinize doldurulur." },
    { sel: ".entry-grid", side: "top", title: "Kısa yollar", text: "Akademisyenler, üniversiteler ve firmalar bölümüne tek tıkla gider. Kartlardaki sayılar o bölümde kaç kayıt olduğunu gösterir." },
    { sel: ".entry-grid.two", side: "top", title: "Araçlar", text: "Konu bulma ve danışman bulma araçlarına buradan da ulaşabilirsiniz." },
    { sel: ".list-card", side: "top", title: "Son incelenenler", text: "En son baktığınız akademisyen, üniversite ve firmalar burada sıralanır. Birine basınca kaldığınız yerden devam edersiniz." },
    { sel: ".list-card .person-row", side: "top", title: "Kayıtlı bir profil", text: "Her satır daha önce çıkarılmış bir profildir: ad, unvan, yayın sayısı ve kurum. Satıra basınca profil açılır." },
    { sel: ".list-card .h-del", side: "left", title: "Kaydı sil", text: "Bu düğme profili listeden kaldırır. Silmeden önce onay istenir; silinen profil yeniden aranıp çıkarılabilir." },
  ];

  const people = () => [
    { pre: go("#/akademisyenler"), sel: ".section-head", must: true, side: "bottom", title: "Akademisyenler", text: "Yeni bir akademisyen aramak ve daha önce çıkardığınız profilleri görmek için bu sayfa kullanılır." },
    { sel: "#pSearch", side: "bottom", title: "Akademisyen ara", text: "Kişinin <b>adını ve soyadını</b> yazıp aramayı başlatın. Aynı adda birden çok kişi çıkarsa kurumuna göre doğru olanı seçersiniz." },
    { sel: "#pResults", side: "bottom", title: "Arama sonuçları", text: "Bulunan kişiler burada listelenir. Birini seçince kaynaklar taranır ve profil birkaç dakikada hazırlanır." },
    { sel: "[data-byurl]", side: "bottom", title: "Bağlantıyla ekle", text: "Kişinin YÖK Akademik ya da Google Scholar sayfasının adresi elinizdeyse, aramak yerine adresi yapıştırıp doğrudan o kişiyi ekleyebilirsiniz." },
    { sel: "#pInterest", side: "bottom", title: "İlgi alanına göre süz", text: "Kayıtlı profilleri araştırma alanına göre daraltır. Örneğin yalnızca yapay zekâ çalışanları görmek için kullanılır." },
    { sel: ".seg", side: "bottom", title: "Görünüm", text: "Listeyi kart ya da satır olarak gösterir. İçerik aynıdır, yalnızca dizilişi değişir." },
    { sel: "#pList", side: "top", title: "İncelenen profiller", text: "Daha önce çıkardığınız bütün profiller. Bir profile basınca yeniden taramadan, kayıtlı haliyle açılır." },
  ];

  const profile = (ctx) => !ctx.chat ? [
    { pre: go("#/akademisyenler"), must: true, title: "Henüz kayıtlı profil yok",
      text: "Akademisyen profilini anlatabilmem için önce bir profil çıkarılmış olmalı. Bu sayfadaki arama kutusuna bir akademisyenin adını yazın, sonuçlardan kişiyi seçin ve taramanın bitmesini bekleyin. Ardından Rehber'den <b>Akademisyen profili</b> turunu yeniden başlatın." },
  ] : [
    { pre: go(`#/profil/${ctx.chat}`), sel: ".profile-hero", must: true, wait: 9000, side: "bottom", title: "Akademisyen profili",
      text: "Bir akademisyen hakkında toplanan her şey bu sayfadadır. Üstte kimlik bilgileri, altında sekmeler halinde yayınlar, dersler, tezler, projeler ve iş birlikleri bulunur." },
    { sel: ".ph-institution", side: "left", title: "Kurumu", text: "Akademisyenin çalıştığı üniversite ve logosu. Kapak rengi de kurumun renginden gelir." },
    { sel: "#phPhoto", side: "right", title: "Fotoğraf", text: "YÖK ya da üniversite sayfasındaki fotoğrafı. Fotoğraf yoksa adının baş harfleri gösterilir. Üzerine basınca büyük hali açılır." },
    { sel: ".profile-hero .identity-info, .profile-hero h1", side: "bottom", title: "Ad ve unvan", text: "Akademisyenin unvanı (Prof. Dr., Doç. Dr. …), adı ve kurumu." },
    { sel: ".profile-hero .kebab-btn", side: "left", title: "İşlemler", text: "Bu düğme iki işlem açar: <b>Favorilere ekle</b> profili Kütüphanem'e kaydeder; <b>Yenile</b> kaynakları yeniden tarayıp profili günceller." },
    { sel: ".profile-hero .kpis", side: "top", title: "Özet sayılar", text: "Profilin altı temel sayısı tek satırda. Şimdi her birinin ne anlama geldiğine bakalım." },
    { sel: ".profile-hero .kpis .kpi:nth-child(1)", side: "top", title: "Benzersiz yayın", text: "Akademisyenin yayın sayısı. Aynı yayın birden çok kaynakta bulunsa bile <b>bir kez</b> sayılır; bu yüzden \"benzersiz\" denir." },
    { sel: ".profile-hero .kpis .kpi:nth-child(2)", side: "top", title: "Toplam atıf", text: "Başka araştırmacıların bu kişinin yayınlarına yaptığı gönderme sayısı. Bir yayına ne kadar çok atıf yapılırsa, o çalışma o kadar çok kullanılmış demektir." },
    { sel: ".profile-hero .kpis .kpi:nth-child(3)", side: "top", title: "Ders", text: "YÖK kayıtlarına göre verdiği ders sayısı. Ayrıntısı \"Dersler\" sekmesindedir." },
    { sel: ".profile-hero .kpis .kpi-h", side: "top", title: "H-indeks",
      text: "Verimlilik ve etkiyi tek sayıda özetler. <b>H-indeks 5</b> demek, en az 5'er atıf almış 5 yayını var demektir. Sayı kaynağa göre değişir (her kaynak farklı yayınları sayar); bu yüzden hangi kaynaktan geldiği yanında yazar." },
    { sel: ".profile-hero .kpis .kpi:nth-child(5)", side: "top", title: "Yönetilen tez", text: "Danışmanlığını yaptığı yüksek lisans ve doktora tezlerinin sayısı." },
    { sel: ".profile-hero .kpis .kpi:nth-child(6)", side: "top", title: "İş birliği", text: "Birlikte çalıştığı kişi ve kurum sayısı: ortak yayınlar, projeler ve sanayi çalışmaları." },
    { sel: ".tabs", side: "bottom", title: "Sekmeler", text: "Profilin ayrıntıları konularına göre sekmelere ayrılmıştır. Sekme adının yanındaki sayı o sekmedeki kayıt sayısıdır. Sırayla hepsini açacağız." },

    { pre: tab("pubs"), sel: '.tabs .tab[data-tab="pubs"]', side: "bottom", title: "Yayınlar sekmesi", text: "Akademisyenin bütün makale, bildiri, kitap ve tezleri. Profil açıldığında bu sekme görünür." },
    { sel: "#profileWosState", side: "bottom", title: "Tarama durumu", text: "Kaynakların taranma durumunu bildirir. Bir kaynak yanıt vermediyse burada yazar; o ana kadar alınan kayıtlar korunur." },
    { sel: "#profileSourcesPicker", side: "left", title: "Kaynaklar", text: "Yayınların hangi kaynaklardan toplanacağını seçersiniz (YÖK, OpenAlex, TR Dizin, OpenAIRE, Web of Science …). Seçimi değiştirip <b>Seçilenleri tara</b> derseniz yalnızca o kaynaklar yeniden taranır." },
    { sel: ".publication-table thead", side: "bottom", title: "Sütun başlıkları", text: "Bir başlığa basınca tablo o sütuna göre <b>sıralanır</b>. Başlığın yanındaki huni simgesi o sütunda <b>süzme</b> penceresini açar." },
    { sel: ".publication-table th:nth-child(1)", side: "bottom", title: "# sütunu", text: "Yayının sıra numarası (P1, P2 …). Sohbet asistanı cevap verirken yayınlara bu numaralarla gönderme yapar." },
    { sel: ".publication-table th:nth-child(2)", side: "bottom", title: "Başlık", text: "Yayının adı ve altında yayımlandığı dergi ya da kongre. Huni simgesiyle başlıkta kelime arayabilir, dergi çeyreğine göre süzebilirsiniz." },
    { sel: ".publication-table th:nth-child(3)", side: "bottom", title: "Durum", text: "Yayının türü (makale, bildiri, tez, kitap) ve varsa yayın süreci (kabul edildi, basımda …)." },
    { sel: ".publication-table th:nth-child(4)", side: "bottom", title: "Yıl", text: "Yayın yılı. Ok aşağı bakıyorsa en yeni yayın en üsttedir. Huni simgesiyle yıl aralığı seçilir." },
    { sel: ".publication-table th:nth-child(5)", side: "bottom", title: "Kaynak", text: "Yayının hangi kaynaklarda bulunduğu. Her renkli etiket bir kaynaktır." },
    { sel: ".publication-table th:nth-child(6)", side: "bottom", title: "Doğrulama", text: "Yayının kaç ayrı kaynakta bulunduğu. <b>✓ 2 kaynak</b> yayının iki yerde de aynı kişiye ait göründüğünü, yani daha güvenilir olduğunu söyler. \"Tek kaynak\" yanlış demek değildir, yalnızca tek yerde geçtiğini belirtir." },
    { sel: ".publication-table th:nth-child(7)", side: "bottom", title: "Atıf", text: "Bu yayına yapılan atıf sayısı. Çizgi (—) atıf bilgisinin kaynakta bulunmadığını gösterir; sıfır demek değildir." },
    { sel: "#pubs tr:first-child .t-title", side: "bottom", title: "Yayını aç", text: "Yayının adına basınca sağdan bir pencere açılır: özet, yazarlar, dergi bilgisi ve tam metne giden bağlantılar orada yer alır." },
    { sel: "#pubs tr:first-child .publication-status", side: "bottom", title: "Tür ve süreç", text: "Bu yayının türü ve yayın aşaması." },
    { sel: "#pubs tr:first-child .chips", side: "bottom", title: "Kaynak etiketleri", text: "Bu yayının bulunduğu kaynaklar. Aynı yayın birden çok kaynakta varsa hepsi burada yan yana durur." },
    { sel: "#pubs tr:first-child .vb", side: "bottom", title: "Doğrulama rozeti", text: "Yeşil onay, yayının birden çok kaynakta doğrulandığını gösterir." },
    { sel: "#pubs tr:first-child .star", side: "left", title: "Yıldızla", text: "Yayını Kütüphanem'e kaydeder. Tekrar basınca kayıttan çıkarır." },
    { sel: "#pubCount", side: "top", title: "Kayıt sayısı", text: "Tabloda kaç yayın gösterildiği ve toplamı. Süzme yaptığınızda bu sayı azalır." },
    { sel: "#pubClear", side: "top", title: "Filtreleri temizle", text: "Yaptığınız bütün süzmeleri kaldırıp tabloyu ilk haline döndürür." },
    { sel: "#pubPageSize", side: "top", title: "Sayfa başına kayıt", text: "Bir sayfada kaç yayın gösterileceğini seçersiniz." },
    { sel: "#pubNext", side: "top", title: "Sayfalar", text: "Yayınlar bir sayfaya sığmıyorsa bu oklarla ileri ve geri gidilir." },
    { sel: '.dt-export[data-export="pubs"]', side: "top", title: "Dışa aktar", text: "Tablodaki yayınları dosya olarak indirir; Excel'de açıp rapor hazırlamak için kullanılır." },

    { pre: tab("career"), sel: '.tabs .tab[data-tab="career"]', side: "bottom", title: "Akademik geçmiş", text: "Kişinin kariyeri: hangi kurumda, hangi unvanla, hangi yıllarda çalıştığı ve nerede okuduğu." },
    { sel: '[data-panel="career"] .card:nth-child(1)', side: "top", title: "Akademik görevler", text: "Araştırma görevliliğinden profesörlüğe, yıl yıl çalıştığı kurumlar ve unvanları." },
    { sel: '[data-panel="career"] .card:nth-child(2)', side: "top", title: "Öğrenim", text: "Lisans, yüksek lisans ve doktorasını nerede ve ne zaman yaptığı." },
    { sel: '[data-panel="career"] .card:nth-child(3)', side: "top", title: "İdari görevler", text: "Dekanlık, bölüm başkanlığı, rektör yardımcılığı gibi yöneticilik görevleri." },
    { sel: '[data-panel="career"] .card:nth-child(4)', side: "top", title: "Üniversite dışı deneyim", text: "Şirketlerde, kamu kurumlarında ya da kurullarda yaptığı işler." },

    { pre: tab("courses"), sel: '.tabs .tab[data-tab="courses"]', side: "bottom", title: "Dersler", text: "YÖK kayıtlarına göre verdiği dersler." },
    { sel: '[data-panel="courses"] .list-row', side: "top", title: "Bir ders", text: "Dersin adı, düzeyi (ön lisans, lisans, yüksek lisans, doktora), haftalık saati ve verildiği dönem." },

    { pre: tab("theses"), sel: '.tabs .tab[data-tab="theses"]', side: "bottom", title: "Tezler", text: "Danışmanlığını yaptığı tezler ve kendi tezleri (YÖK Tez Merkezi kayıtları)." },
    { sel: '[data-panel="theses"] [data-jury]', side: "bottom", title: "Jüri öner", text: "Bir tez seçersiniz; uygulama o tezin konusunda yayın yapmış akademisyenleri jüri adayı olarak önerir." },
    { sel: '[data-panel="theses"] .list-row', side: "top", title: "Bir tez", text: "Tezin türü, durumu, başlığı, yazarı ve yılı." },

    { pre: tab("more"), sel: '.tabs .tab[data-tab="more"]', side: "bottom", title: "Projeler", text: "Yürüttüğü ya da görev aldığı araştırma projeleri: TÜBİTAK, BAP, AB projeleri." },
    { sel: '[data-panel="more"] .proj-row', side: "top", title: "Bir proje", text: "Projenin adı, türü, durumu ve bütçe/tarih bilgisi. Satıra basınca ayrıntısı açılır." },

    { pre: tab("collab"), sel: '.tabs .tab[data-tab="collab"]', side: "bottom", title: "İş birlikleri", text: "Kimlerle ve hangi kurumlarla birlikte çalıştığı." },
    { sel: "#industryBox .card", side: "top", title: "Sanayi ve Ar-Ge iş birlikleri", text: "Yayınlarından, YÖK deneyim kayıtlarından ve projelerinden çıkarılan firma bağlantıları. Kartın köşesindeki düğme bu bilgiyi yeniden tarar." },
    { sel: "#industryBox .cl-card", side: "top", title: "Birlikte çalıştığı kişi", text: "Ortak yayını ya da projesi olan bir akademisyen: adı, unvanı ve kurumu. Karta basınca o kişinin kısa bilgisi açılır." },

    { pre: tab("patents"), sel: '.tabs .tab[data-tab="patents"]', side: "bottom", title: "Patentler", text: "Buluş sahibi olarak adının geçtiği patentler. Sıfır yazıyorsa kayıtlı patenti bulunamamıştır." },

    { pre: tab("score"), sel: '.tabs .tab[data-tab="score"]', side: "bottom", title: "Doçentlik ve teşvik puanı", text: "Yayın ve çalışmalarından, doçentlik başvurusu ve akademik teşvik için yaklaşık puan hesaplanır." },
    { sel: "#scoreBox", side: "top", wait: 7000, title: "Puan hesabı", text: "Her yayın türü için puan ve toplam gösterilir. Bu hesap <b>bilgi amaçlıdır</b>; resmî puan değildir, başvuruda kurumun hesabı geçerlidir." },

    { pre: tab("interests"), sel: '.tabs .tab[data-tab="interests"]', side: "bottom", title: "Ekstra bilgi", text: "Yayınların dergi kalitesine, kaynağa ve türe göre dağılımı ile YÖK'teki ek bilgiler." },
    { sel: "#profileQuartiles", side: "top", title: "Dergi çeyreği (Q1–Q4)", text: "Dergiler alanlarındaki etkilerine göre dört dilime ayrılır. <b>Q1</b> en çok atıf alan ilk %25'lik dilimdir, <b>Q4</b> son dilimdir. Burada yayınların kaçının hangi dilimde olduğu yazar." },
    { sel: "#profileSources", side: "top", title: "Kaynak dağılımı", text: "Yayınların kaçının hangi kaynakta bulunduğu. Bir yayın birden çok kaynakta sayılabilir." },
    { sel: "#yokStatsBox", side: "top", title: "YÖK istatistikleri", text: "YÖK Akademik'in kendi verdiği sayılar: Web of Science yayın ve atıfları ile yayın türlerinin ulusal / uluslararası dağılımı." },
    { sel: "#yokAreaBox", side: "top", title: "Araştırma alanları", text: "YÖK'te kayıtlı temel alanı, bilim alanı ve anahtar kelimeleri." },
    { sel: "#yokMetricsBox", side: "top", title: "Metrikler", text: "Web of Science gibi kaynaklardaki yayın, atıf ve h-indeks değerleri yan yana." },
    { sel: "#yokSdgBox", side: "top", title: "Sürdürülebilir Kalkınma Amaçları", text: "Çalışmalarının Birleşmiş Milletler'in 17 kalkınma amacından hangileriyle ilgili olduğu." },

    { pre: tab("chat"), sel: '.tabs .tab[data-tab="chat"]', side: "bottom", title: "Asistan", text: "Bu akademisyen hakkında soru sorabileceğiniz yapay zekâ asistanı." },
    { sel: ".chat-wrap", side: "top", title: "Profil asistanı", text: "Sorunuzu günlük dille yazarsınız; asistan yalnızca bu profilde toplanan bilgilere dayanarak cevap verir ve dayandığı yayının numarasını ([P3] gibi) yanına yazar." },
    { sel: "#thread .chip", side: "top", title: "Hazır sorular", text: "Ne soracağınızı bilmiyorsanız bu örnek sorulardan birine basın." },
    { sel: "#askForm", side: "top", title: "Soru yazın", text: "Sorunuzu buraya yazıp <b>Gönder</b>'e basın. Asistanın çalışması için Ayarlar'da bir yapay zekâ anahtarı girilmiş olmalıdır." },
  ];

  const university = () => [
    { pre: go("#/universiteler"), sel: ".section-head", must: true, side: "bottom", title: "Üniversiteler", text: "YÖK'te kayıtlı bütün üniversiteler. Örnek olarak <b>OSTİM Teknik Üniversitesi</b>'ni inceleyeceğiz." },
    { sel: "#uQ", side: "bottom", title: "Üniversite ara", text: "Üniversitenin adından birkaç harf yazınca liste daralır." },
    { sel: "#uGrid .uni-card", side: "bottom", wait: 9000, title: "Üniversite kartı", text: "Her kart bir üniversitedir. Karta basınca sayfası açılır; üzerinde beklerseniz kısa bilgisi görünür. En çok kullanılan üniversiteler listenin başındadır." },

    { pre: both(go(`#/universite/${OSTIM}`), audience("overview")), sel: ".identity-hero", must: true, wait: 9000, side: "bottom", title: "Üniversite sayfası", text: "Üstte üniversitenin logosu, adı ve temel bilgileri; altında farklı kullanıcılar için hazırlanmış görünümler bulunur." },
    { sel: "#uLogo", side: "right", title: "Logo", text: "Üniversitenin resmî logosu." },
    { sel: "#uMeta", side: "bottom", title: "Künye satırı", text: "Şehir, kuruluş yılı, türü (devlet / vakıf) ve resmî site bağlantısı." },
    { sel: ".identity-hero .kebab-btn", side: "left", title: "Ayarlar ve yenileme", text: "Üniversite bilgilerini yeniden taramak ya da bu üniversiteden yeni bir akademisyen eklemek için kullanılır." },
    { sel: ".audience-tabs", side: "bottom", title: "Altı görünüm", text: "Aynı üniversite altı farklı gözle gösterilir: genel bakış, akademisyen, öğrenci, aday, patentler ve yapay zekâ. Sırayla hepsine bakacağız." },

    { pre: audience("overview"), sel: '.audience-tabs [data-audience="overview"]', side: "bottom", title: "Genel bakış", text: "Üniversitenin kimlik bilgileri tek sayfada." },
    { sel: "#universityOverview .overview-facts, #universityOverview .card", side: "top", wait: 9000, title: "Üniversite künyesi", text: "Rektör, kuruluş yılı, öğrenci ve akademisyen sayısı, sıralamalar ve iş birliği yapılan firmalar gibi bilgiler. Her bilginin kaynağı yanında gösterilir." },
    { sel: "#universityOverview [data-refresh-facts]", side: "left", title: "Bilgileri yenile", text: "Künye bilgilerini kaynaklardan yeniden okur." },

    { pre: both(audience("academic"), pick("#colFac")), sel: '.audience-tabs [data-audience="academic"]', side: "bottom", title: "Akademisyen bakışı", text: "Üniversitenin yapısını soldan sağa üç sütunda gösterir: fakülte → bölüm → akademisyen." },
    { sel: "#colFac", side: "right", wait: 9000, title: "1. sütun: Fakülteler", text: "Üniversitenin fakülte, enstitü ve yüksekokulları. Birine basınca bölümleri sağdaki sütunda açılır. Rehber ilk fakülteyi sizin için seçti." },
    { sel: '#colFac [data-filter="colFac"]', side: "bottom", title: "Sütunda ara", text: "Her sütunun üstünde kendi arama kutusu vardır; uzun listede aradığınızı hızla bulursunuz." },
    { pre: pick("#colDep"), sel: "#colDep", side: "left", wait: 9000, title: "2. sütun: Bölümler", text: "Seçilen fakültenin bölümleri ve her birindeki akademisyen sayısı. Üstte dekan, bölümün yanında bölüm başkanı yazar." },
    { sel: "#colDep .fac-lead", side: "bottom", title: "Dekan", text: "Fakültenin dekanı ve göreve başladığı tarih." },
    { sel: "#colStaff", side: "left", wait: 9000, title: "3. sütun: Akademisyenler", text: "Seçilen bölümün kadrosu. Bir kişiye basınca kısa bilgisi açılır; oradan profilini çıkarabilirsiniz." },

    { pre: audience("student"), sel: '.audience-tabs [data-audience="student"]', side: "bottom", title: "Öğrenci bakışı", text: "Bir öğrencinin merak ettikleri: programlar, dersler, ücretler, Erasmus ve kampüs." },
    { sel: ".sv-hero", side: "bottom", title: "Öğrenci rehberi", text: "Aşağıdaki başlıklardan birini seçersiniz; bilgi üniversitenin resmî sayfalarından, kaynağıyla birlikte gelir." },
    { sel: ".sv-tiles", side: "bottom", title: "Konu başlıkları", text: "Altı başlık vardır. Önce en önemlisine, lisans programlarına bakalım." },
    { pre: press('[data-sv-tile="undergrad"]', 900), sel: '[data-sv-tile="undergrad"]', side: "bottom", title: "Lisans programları", text: "Fakülteler, bölümler ve her bölümün dönem dönem ders planı." },
    { sel: ".sv-panel .student-tree, .sv-panel", side: "top", wait: 9000, title: "Fakülte listesi", text: "Fakülteler alt alta sıralanır. Bir fakülteye basınca bölümleri açılır." },
    { pre: unfold(".sv-panel [data-student-faculty]", 1200), sel: ".sv-panel [data-student-faculty]", side: "top", wait: 9000, title: "Bir fakülte", text: "Rehber ilk fakülteyi açtı. İçinde o fakültenin bölümleri görünür." },
    { pre: unfold(".sv-panel [data-student-department]", 1500), sel: ".sv-panel [data-student-department]", side: "top", wait: 9000, title: "Bir bölüm", text: "Bölüme basınca ders planı gelir. OSTİM'in dersleri hazır veriden okunduğu için hemen açılır; başka üniversitelerde ilk açılış biraz sürebilir." },
    { sel: ".sv-panel .department-courses", side: "top", wait: 12000, title: "Ders planı", text: "Bölümün bütün dersleri dönemlere ayrılmış halde: 1. dönemden 8. döneme, sonunda seçmeli dersler." },
    { sel: ".sv-panel .student-section-meta", side: "top", title: "Kaynak ve tarih", text: "Derslerin nereden ve ne zaman alındığı yazar. Yanındaki <b>Yeniden tara</b> düğmesi ders planını üniversitenin sitesinden baştan okur." },
    { pre: unfold(".sv-panel .student-term", 500), sel: ".sv-panel .student-term", side: "top", wait: 9000, title: "Bir dönem", text: "Döneme basınca o dönemin dersleri açılır. Yanındaki sayı dönemde kaç ders olduğunu gösterir." },
    { pre: unfold(".sv-panel .student-term[open] .student-course", 900), sel: ".sv-panel .student-term[open] .student-course", side: "top", title: "Bir ders", text: "Dersin kodu ve adı. Derse basınca içeriği açılır: <b>AKTS</b> (dersin iş yükünü gösteren kredi), dersin amacı, haftalık konular, değerlendirme (vize, final yüzdeleri) ve öğrenme çıktıları." },
    { sel: ".sv-panel .student-course[open] .source-link", side: "top", title: "Kaynağı aç", text: "Bu bağlantı dersin üniversite sitesindeki asıl sayfasını yeni sekmede açar." },
    { pre: press('[data-sv-tile="graduate"]', 700), sel: '[data-sv-tile="graduate"]', side: "bottom", title: "Yüksek lisans ve doktora", text: "Tezli ve tezsiz programlar ile başvuru koşulları." },
    { pre: press('[data-sv-tile="fees"]', 700), sel: '[data-sv-tile="fees"]', side: "bottom", title: "Ücretler ve burslar", text: "Üniversitenin yayımladığı öğrenim ücretleri, burs oranları ve hangi döneme ait oldukları." },
    { pre: press('[data-sv-tile="erasmus"]', 700), sel: '[data-sv-tile="erasmus"]', side: "bottom", title: "Erasmus ve değişim", text: "Anlaşmalı üniversiteler, ülkeler ve başvuru bilgileri." },
    { pre: press('[data-sv-tile="work_travel"]', 700), sel: '[data-sv-tile="work_travel"]', side: "bottom", title: "Work and Travel", text: "Üniversitenin bu programla ilgili yayımladığı duyurular." },
    { pre: press('[data-sv-tile="campus"]', 900), sel: '[data-sv-tile="campus"]', side: "bottom", title: "Kampüs ve ulaşım", text: "Yerleşkelerin konumu, harita ve kampüse giden toplu taşıma hatları." },
    { sel: ".sv-panel", side: "top", wait: 9000, title: "Seçilen başlığın içeriği", text: "Hangi başlığı seçtiyseniz bilgisi burada açılır. Her bilginin altında alındığı resmî sayfanın bağlantısı bulunur." },
    { sel: ".student-footnote", side: "top", title: "Uyarı notu", text: "Ücret ve başvuru bilgileri değişebilir; başvurmadan önce üniversitenin güncel duyurusuna bakmanız önerilir." },

    { pre: audience("candidate"), sel: '.audience-tabs [data-audience="candidate"]', side: "bottom", title: "Aday bakışı", text: "Üniversite sınavına hazırlanan bir adayın ihtiyacı: taban puanlar, başarı sıraları ve kontenjanlar (YÖK Atlas verisi)." },
    { sel: "#candidateView .aday-stats", side: "bottom", wait: 12000, title: "Özet", text: "Üniversitenin program sayısı, toplam kontenjanı ve doluluk oranı." },
    { sel: "#candidateView .aday-filters", side: "bottom", title: "Süzgeçler", text: "Programları adıyla arayabilir, puan türüne (SAY, EA, SÖZ, DİL) ve düzeye göre süzebilir, başarı sırasına ya da puana göre sıralayabilirsiniz." },
    { sel: "#candidateView [data-aday-list]", side: "top", title: "Program listesi", text: "Programlar fakültelere göre gruplanır. Her satırda taban puan, başarı sırası, kontenjan, öğretim dili ve burs durumu yer alır." },
    { sel: "#candidateView .aday-table tbody tr, #candidateView .aday-row", side: "top", title: "Bir program", text: "Satıra basınca önceki yılların puanları, kontenjanın nasıl dolduğu ve programın YÖK Atlas sayfası açılır." },

    { pre: audience("patents"), sel: '.audience-tabs [data-audience="patents"]', side: "bottom", title: "Patentler", text: "Üniversitenin başvuru sahibi olduğu patentler." },
    { sel: "#uniPatents .card", side: "top", wait: 9000, title: "Patent listesi", text: "Patentin adı, yılı ve buluş sahipleri. Üstteki kutudan patentlerde arama yapılır; bir patente basınca ayrıntısı açılır." },

    { pre: audience("ai"), sel: '.audience-tabs [data-audience="ai"]', side: "bottom", title: "AI bakışı", text: "Üniversite hakkında yapay zekâya soru sorabileceğiniz görünüm." },
    { sel: "#aiView .ai-topics", side: "right", wait: 7000, title: "Konu başlıkları", text: "Sık sorulan konular gruplanmıştır. Bir başlığa basınca hazır soruları görünür." },
    { sel: "#aiView .ai-main", side: "left", title: "Soru ve cevap", text: "Sorunuzu yazarsınız; cevap üniversitenin resmî sayfalarından toplanan bilgiye dayanır ve kaynağı gösterilir." },
  ];

  const firm = (ctx) => [
    { pre: go("#/firmalar"), sel: ".section-head", must: true, side: "bottom", title: "Firmalar", text: "Ar-Ge ve tasarım merkezi olan firmalar. Örnek olarak <b>HAVELSAN</b>'ı inceleyeceğiz." },
    { sel: "#firmQ", side: "bottom", title: "Firma ara", text: "Firmanın adını yazınca liste daralır." },
    { sel: "#firmSector", side: "bottom", title: "Sektör", text: "Firmaları sektörüne göre süzer: savunma, yazılım, otomotiv gibi." },
    { sel: "#firmCity", side: "bottom", title: "Şehir", text: "Firmaları bulundukları şehre göre süzer." },
    { sel: "#fBody", side: "top", wait: 9000, title: "Firma listesi", text: "Süzgeçlere uyan firmalar. Bir firmaya basınca sayfası açılır." },
    ...(!ctx.firm ? [
      { must: true, title: "HAVELSAN listede bulunamadı", text: "Firma listesi bu bilgisayarda yüklü değil ya da HAVELSAN listede yok. Listeden herhangi bir firmayı açarak aynı bölümleri görebilirsiniz; firma sayfası her firmada aynı düzendedir." },
    ] : [
      { pre: both(go(`#/firma/${ctx.firm}`), tab("overview")), sel: "#firmHead", must: true, wait: 12000, side: "bottom", title: "Firma sayfası: HAVELSAN", text: "Üstte firmanın logosu, adı, sektörü ve şehri; altında akademiyle ilişkisini gösteren sayılar ve sekmeler bulunur." },
      { sel: "#firmHead .identity-avatar", side: "right", title: "Logo", text: "Firmanın logosu. Bulunamazsa adının baş harfleri gösterilir." },
      { sel: "#firmHead .chips", side: "bottom", title: "Etiketler", text: "Firmanın Ar-Ge merkezi mi tasarım merkezi mi olduğu, sektörü ve şehri." },
      { sel: "#firmHead .kebab-btn", side: "left", title: "İşlemler", text: "Firmayı favorilere eklemek ve bilgilerini yeniden taramak için kullanılır." },
      { sel: ".stat-row", side: "bottom", title: "Özet sayılar", text: "Firmanın akademiyle bağını üç sayıda özetler." },
      { sel: ".stat-row .stat:nth-child(1)", side: "bottom", title: "Akademisyen", text: "Bu firmayla ortak yayını, projesi ya da deneyimi bulunan akademisyen sayısı." },
      { sel: ".stat-row .stat:nth-child(2)", side: "bottom", title: "Ortak yayın ve proje", text: "Firmanın adının geçtiği yayın ve proje sayısı." },
      { sel: ".stat-row .stat:nth-child(3)", side: "bottom", title: "Üniversite", text: "Bu akademisyenlerin kaç farklı üniversiteden geldiği." },
      { sel: ".tabs", side: "bottom", title: "Sekmeler", text: "Firma bilgileri beş sekmeye ayrılmıştır. Sırayla açalım." },

      { pre: tab("overview"), sel: '.tabs .tab[data-tab="overview"]', side: "bottom", title: "Genel bakış", text: "Firmanın künyesi ve kısa tanıtımı." },
      { sel: "#firmOverview", side: "top", wait: 9000, title: "Firma künyesi", text: "Kuruluş yılı, çalışan sayısı, faaliyet alanı ve resmî site gibi bilgiler; her birinin kaynağı gösterilir." },
      { sel: "[data-firm-refresh-facts]", side: "left", title: "Künyeyi yenile", text: "Firma bilgilerini kaynaklardan yeniden okur." },

      { pre: tab("people"), sel: '.tabs .tab[data-tab="people"]', side: "bottom", title: "Akademisyenler", text: "Bu firmayla çalışmış akademisyenler." },
      { sel: "#firmPeopleQ", side: "bottom", title: "Kişi ara", text: "Listedeki akademisyenleri ada ya da üniversiteye göre arar." },
      { sel: "#firmPeople .firm-person-card", side: "top", wait: 9000, title: "Bir akademisyen", text: "Kişinin adı, üniversitesi ve firmayla bağının türü (ortak yayın, proje, deneyim). Karta basınca kanıt olan yayın ve projeler açılır." },

      { pre: tab("tubitak"), sel: '.tabs .tab[data-tab="tubitak"]', side: "bottom", title: "Projeler", text: "Firmanın kamu destekli ve uluslararası projeleri." },
      { sel: "#firmWebBox", side: "top", wait: 9000, title: "İnternette öne çıkan projeler", text: "Firmanın kendi sitesinde ve haberlerde öne çıkan projeleri." },
      { sel: "#cordisBox", side: "top", title: "AB projeleri", text: "Avrupa Birliği'nin CORDIS veritabanındaki projeleri: Horizon 2020, Horizon Europe." },
      { sel: "#teydebBox", side: "top", title: "TÜBİTAK TEYDEB projeleri", text: "TÜBİTAK'ın sanayiye verdiği Ar-Ge destekleri kapsamındaki projeler." },

      { pre: tab("patents"), sel: '.tabs .tab[data-tab="patents"]', side: "bottom", title: "Patentler", text: "Firmanın başvuru sahibi olduğu patentler (Avrupa Patent Ofisi verisi). Bu sekme için Ayarlar'da patent anahtarı tanımlı olmalıdır." },
      { sel: "#firmPatentsBox", side: "top", wait: 9000, title: "Patent listesi", text: "Patentin adı, başvuru yılı ve buluş sahipleri. Bir patente basınca özeti açılır." },

      { pre: tab("firmai"), sel: '.tabs .tab[data-tab="firmai"]', side: "bottom", title: "Asistan", text: "Firma hakkında yapay zekâya soru sorabileceğiniz bölüm." },
      { sel: "#firmAi", side: "top", title: "Firma asistanı", text: "\"Hangi üniversitelerle çalışıyor?\", \"Hangi alanlarda proje yapmış?\" gibi sorular sorabilirsiniz. Cevap bu sayfada toplanan bilgilere dayanır." },
    ]),
  ];

  const tools = () => [
    { pre: go("#/ara"), sel: ".section-head", must: true, side: "bottom", title: "Konu bul", text: "Bir kişiyi değil bir <b>konuyu</b> aramak için kullanılır." },
    { sel: ".va", side: "bottom", wait: 5000, title: "Sesli araştırma asistanı", text: "Burada bir yapay zekâ asistanıyla konuşarak yayın ararsın. <b>Asistanla konuş</b>'a basınca seni karşılar; konunu sesli anlatabilir, yazabilir ya da 📎 düğmesiyle bir belge (PDF, Word) verebilirsin. Bulduğu yayınlar sağda kartlar olarak listelenir; güncel bilgi için web'de de arar." },
    { sel: ".va-stage", side: "right", title: "Asistanın yüzü", text: "Küre asistanın durumunu gösterir: boştayken yavaşça nefes alır, seni dinlerken sesine, konuşurken kendi sesine göre büyür, araştırırken etrafında halkalar döner. Adını, sesini ve tonunu Ayarlar'dan değiştirebilirsin." },
    { sel: "#searchForm", side: "bottom", title: "Konu yazın", text: "Örneğin \"derin öğrenme\" ya da \"batarya yönetim sistemi\" yazıp arayın." },
    { sel: "#topicSources", side: "bottom", title: "Kaynak seçimi", text: "Aramanın hangi yayın kaynaklarında yapılacağını seçersiniz." },
    { sel: "#sResults, #shelves", side: "top", title: "Sonuçlar", text: "O konuda yazılmış yayınlar ve o alanda en çok yayını olan akademisyenler burada listelenir." },

    { pre: go("#/danisman"), sel: ".va", must: true, wait: 5000, side: "bottom", title: "Danışman bul asistanı", text: "Tez ya da TÜBİTAK 2209-A projen için danışmanı asistanla konuşarak bulabilirsin: konunu ve üniversiteni söyle, uygun akademisyenleri nedenleriyle anlatsın ve kartlar olarak listelesin." },
    { sel: "#aForm", side: "bottom", title: "Danışman bul (klasik)", text: "Asistan yerine formu kullanmak istersen: konunu yaz, üniversiteni seç ve ara." },
    { sel: "#aQ", side: "bottom", title: "Konunuz", text: "Çalışmak istediğiniz konuyu birkaç kelimeyle yazın." },
    { sel: "#aUni", side: "bottom", title: "Üniversite", text: "Aramayı tek bir üniversiteyle sınırlamak isterseniz buradan seçersiniz; boş bırakırsanız hepsinde aranır." },
    { sel: "#aResults", side: "top", title: "Önerilen akademisyenler", text: "Konunuzda yayını olan akademisyenler, ilgili yayınlarıyla birlikte sıralanır." },

    { pre: go("#/kutuphane"), sel: ".section-head", must: true, side: "bottom", title: "Kütüphanem", text: "Yıldızladığınız ve favorilere eklediğiniz her şey burada toplanır." },
    { sel: ".library-tabs, .tabs", side: "bottom", title: "Dört liste", text: "Yayınlar, akademisyenler, üniversiteler ve firmalar ayrı sekmelerdedir. Bir kaydı listeden çıkarmak için üzerindeki <b>Çıkar</b> düğmesine basılır." },
  ];

  const settings = () => [
    { pre: go("#/sistem"), sel: ".section-head", must: true, side: "bottom", title: "Ayarlar", text: "Uygulamanın çalışması için gereken anahtarlar ve hız ayarları. Çoğu bir kez yapılır." },
    { sel: "#aiCard", side: "bottom", wait: 7000, title: "Yapay zekâ", text: "Analiz, sohbet ve sayfa okuma için kullanılacak yapay zekâ servisi burada seçilir." },
    { sel: "#aiProvider", side: "bottom", title: "Sağlayıcı", text: "Gemini, ChatGPT, Claude ya da kendi sunucunuz. Hangisinin anahtarı elinizdeyse onu seçin." },
    { sel: "#aiKey", side: "bottom", title: "API anahtarı", text: "Seçtiğiniz servisten aldığınız anahtarı buraya yapıştırın. Anahtar yalnızca bu bilgisayarda saklanır ve ekranda bir daha gösterilmez." },
    { sel: "#aiModel", side: "bottom", title: "Model", text: "Kullanılacak modelin adı. Emin değilseniz önerilen değeri bırakın." },
    { sel: "#aiSave", side: "top", title: "Kaydet ve kullan", text: "Ayarı kaydeder ve bağlantıyı hemen dener. Başarılıysa altında \"Kullanımda\" yazar." },
    { sel: "#aiList", side: "top", title: "Bağlantıyı dene", text: "Kaydetmeden önce anahtarın çalışıp çalışmadığını kontrol eder." },
    { sel: "#speedCard", side: "top", wait: 7000, title: "YÖK hızı", text: "YÖK'ün sitesine ne kadar sık istek gönderileceği. <b>2</b> güvenli ayardır. Yükseltirseniz tarama hızlanır ama YÖK'ün sizi geçici olarak engelleme riski artar; engel yerseniz kademeyi düşürün." },
    { sel: "#assistantCard", side: "bottom", wait: 7000, title: "Sesli asistan", text: "Konu bul ve Danışman bul'daki asistanın adı, sesi (kadın ya da erkek, farklı karakterler), konuşma tonu (samimi, resmî, neşeli, sakin) ve hitabı (sen / siz) buradan ayarlanır." },
    { sel: "#searchCard", side: "top", wait: 7000, title: "Arama servisleri", text: "Serper.dev ya da Google Custom Search anahtarı girerseniz, veri setinde olmayan üniversitelerin ders planı çok daha hızlı bulunur. Anahtarı girip <b>Dene</b> düğmesiyle çalıştığını kontrol edebilirsiniz." },
    { sel: "#scoreCard", side: "top", title: "Puan ayarları", text: "Doçentlik ve teşvik puanı hesabında kullanılan ölçütler." },
    { sel: "#sysState", side: "top", wait: 7000, title: "Durum", text: "Uygulamanın parçalarının hazır olup olmadığı: yapay zekâ, tarayıcı, REA ve patent servisi. Kırmızı görünen satır o parçanın kurulu olmadığını söyler." },
    { sel: "[data-recipes]", side: "top", title: "Öğrenilen tarifler", text: "Uygulama bir sitede bilgiyi nasıl bulduğunu \"tarif\" olarak kaydeder ve bir sonraki sefer aynı yoldan hızlıca gider. Bu düğme öğrenilen tarifleri listeler." },
    { sel: "[data-scan]", side: "top", title: "Değişiklikleri tara", text: "Sitelerde yapı değişikliği olup olmadığını kontrol eder; değişen sitelerin tarifi yeniden öğrenilir." },
    { must: true, title: "Rehber tamamlandı", text: "Uygulamanın bütün bölümlerini gördünüz. Rehberi istediğiniz zaman sağ alttaki <b>Rehber</b> düğmesinden yeniden açabilir, yalnızca merak ettiğiniz bölümü baştan izleyebilirsiniz." },
  ];

  const TOURS = [
    { id: "home", title: "Ana sayfa ve menü", sub: "Uygulamanın düzeni, menü ve arama", build: home },
    { id: "people", title: "Akademisyen arama", sub: "Kişi bulma ve kayıtlı profiller", build: people },
    { id: "profile", title: "Akademisyen profili", sub: "Yayınlar, h-indeks, dersler, tezler, asistan", build: profile },
    { id: "university", title: "Üniversite: OSTİM", sub: "Altı görünüm, fakülteler, ders planı", build: university },
    { id: "firm", title: "Firma: HAVELSAN", sub: "Akademisyenler, projeler, patentler", build: firm },
    { id: "tools", title: "Araçlar", sub: "Konu bul, danışman bul, kütüphanem", build: tools },
    { id: "settings", title: "Ayarlar", sub: "Yapay zekâ, arama servisleri, hız", build: settings },
  ];

  // ------------------------------------------------------------------ çalıştırıcı
  const store = {
    get() { try { return JSON.parse(localStorage.getItem("guide-done") || "[]"); } catch { return []; } },
    add(id) { try { localStorage.setItem("guide-done", JSON.stringify([...new Set([...this.get(), id])])); } catch { /* yalnız bu oturum */ } },
    clear() { try { localStorage.removeItem("guide-done"); } catch { /* yok */ } },
  };
  let running = null;

  function find(spec) {
    if (!spec.sel) return null;
    if (typeof spec.sel === "function") { const el = spec.sel(); return shown(el) ? el : null; }
    for (const part of spec.sel.split(/,\s*(?![^\[]*\])/)) {
      const el = $$(part).find(shown);
      if (el) return el;
    }
    return null;
  }

  // Turun örnek kayıtları: OSTİM'den bir akademisyen profili (yoksa kayıtlı ilk profil) ve HAVELSAN'ın firma kimliği.
  async function context() {
    const ctx = { chat: "", firm: "" };
    const json = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(String(r.status)); return r.json(); };
    try {
      const chats = await json("/api/chats");
      const low = (v) => String(v || "").toLocaleLowerCase("tr");
      const pick = chats.find((c) => low(c.institution).includes("ostim")) || chats[0];
      ctx.chat = pick ? pick.id : "";
    } catch { /* profil turu "önce profil çıkarın" adımını gösterir */ }
    try {
      const firms = await json("/api/firms?q=havelsan");
      const rows = firms.items || firms.firms || [];
      const pick = rows.find((x) => /havelsan/i.test(x.name || "")) || rows[0];
      ctx.firm = pick ? pick.id : "";
    } catch { /* firma turu listeyi anlatıp biter */ }
    return ctx;
  }

  async function start(ids) {
    if (running) return;
    panel(false);
    const ctx = await context();
    const specs = ids.flatMap((id) => TOURS.find((t) => t.id === id).build(ctx).map((s) => ({ ...s, tour: id })));
    const state = running = { cancelled: false, busy: false };

    // from konumundan başlayarak dir yönünde gösterilebilecek ilk adımı bulur: önce adımın hazırlığını yapar,
    // sonra öğenin ekrana gelmesini bekler. Öğesi gelmeyen adım atlanır ("must" olanlar ortada gösterilir).
    async function reach(from, dir) {
      for (let i = from; i >= 0 && i < specs.length; i += dir) {
        const spec = specs[i];
        if (state.cancelled) return -1;
        try { if (spec.pre) await spec.pre(); } catch { /* hazırlık yapılamadıysa adım yine denenir */ }
        if (!spec.sel) return i;
        const until = Date.now() + (spec.wait || 3500);
        let el = find(spec);
        while (!el && Date.now() < until && !state.cancelled) { await sleep(150); el = find(spec); }
        spec.el = el;
        if (el || spec.must) return i;
      }
      return -1;
    }

    const busy = (on) => { state.busy = on; document.documentElement.classList.toggle("tour-busy", on); };
    const move = async (dir) => {
      if (state.busy) return;
      busy(true);
      const now = tour.getActiveIndex() ?? 0;
      const next = await reach(now + dir, dir);
      busy(false);
      if (state.cancelled) return;
      if (next < 0) { if (dir > 0) { state.finished = true; tour.destroy(); } return; }
      // Bir turun son adımından çıkılırken o tur tamamlanmış sayılır (baştan sona anlatımda bölüm bölüm işaretlenir).
      if (dir > 0 && specs[next].tour !== specs[now].tour) store.add(specs[now].tour);
      tour.moveTo(next);
    };

    const tour = makeDriver({
      animate: true, smoothScroll: true, allowClose: true, overlayClickBehavior: "none",
      overlayColor: "#05070c", overlayOpacity: 0.68, stagePadding: 8, stageRadius: 14, popoverOffset: 14,
      disableActiveInteraction: true, allowKeyboardControl: true, popoverClass: "guide-popover",
      showProgress: true, progressText: "{{current}} / {{total}}",
      nextBtnText: "İleri →", prevBtnText: "← Geri", doneBtnText: "Bitir", closeBtnLabel: "Rehberi kapat",
      steps: specs.map((spec) => ({
        element: () => (spec.el && spec.el.isConnected ? spec.el : find(spec)) || undefined,
        popover: { title: spec.title, description: spec.text, side: spec.side || "bottom", align: spec.align || "start" },
      })),
      onNextClick: () => { move(1); },
      onPrevClick: () => { move(-1); },
      onDestroyed: () => {
        state.cancelled = true;
        document.documentElement.classList.remove("tour-busy", "tour-on");
        if (state.finished) store.add(specs[specs.length - 1].tour);
        running = null;
        panel(true);
      },
    });
    document.documentElement.classList.add("tour-on");
    busy(true);
    const first = await reach(0, 1);
    busy(false);
    if (first < 0 || state.cancelled) { running = null; document.documentElement.classList.remove("tour-on"); panel(true); return; }
    tour.drive(first);
  }

  // ------------------------------------------------------------------ Rehber düğmesi ve bölüm listesi
  const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  const PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="7 4 20 12 7 20"/></svg>';
  const COMPASS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><polygon points="15.6 8.4 13.6 13.6 8.4 15.6 10.4 10.4"/></svg>';

  function panel(open) {
    const box = $("#guidePanel");
    if (!box) return;
    if (open) {
      const done = store.get();
      $(".guide-progress b", box).style.width = `${Math.round(done.filter((id) => TOURS.some((t) => t.id === id)).length / TOURS.length * 100)}%`;
      $(".guide-progress-text", box).textContent = `${done.filter((id) => TOURS.some((t) => t.id === id)).length} / ${TOURS.length} bölüm tamamlandı`;
      $$("[data-guide]", box).forEach((row) => row.classList.toggle("done", done.includes(row.dataset.guide)));
    }
    box.hidden = !open;
    $("#guideFab").setAttribute("aria-expanded", String(open));
  }

  function mount() {
    if ($("#guideFab")) return;
    const fab = document.createElement("button");
    fab.id = "guideFab"; fab.type = "button"; fab.className = "guide-fab";
    fab.setAttribute("aria-controls", "guidePanel"); fab.setAttribute("aria-expanded", "false");
    fab.innerHTML = `${COMPASS}<span>Rehber</span>`;
    const box = document.createElement("section");
    box.id = "guidePanel"; box.className = "guide-panel"; box.hidden = true;
    box.setAttribute("aria-label", "Rehber");
    box.innerHTML = `<header><div><small>AKADEMİK İZ</small><h2>Rehber</h2></div><button type="button" class="guide-x" aria-label="Kapat">×</button></header>
      <p class="guide-lead">Uygulamayı adım adım anlatır. Siz yalnızca <b>İleri</b> düğmesine basarsınız; sayfaları rehber açar.</p>
      <button type="button" class="guide-all" data-guide-all>${PLAY}<span><b>Baştan sona anlat</b><small>Bütün bölümler sırayla · yaklaşık 15 dakika</small></span></button>
      <div class="guide-progress"><b></b></div><p class="guide-progress-text"></p>
      <ol class="guide-list">${TOURS.map((t, i) => `<li><button type="button" data-guide="${t.id}"><i>${i + 1}</i><span><b>${t.title}</b><small>${t.sub}</small></span><em>${CHECK}</em></button></li>`).join("")}</ol>
      <button type="button" class="guide-reset" data-guide-reset>İlerlemeyi sıfırla</button>`;
    document.body.append(fab, box);
    fab.addEventListener("click", () => panel(box.hidden));
    $(".guide-x", box).addEventListener("click", () => panel(false));
    $("[data-guide-all]", box).addEventListener("click", () => start(TOURS.map((t) => t.id)));
    $("[data-guide-reset]", box).addEventListener("click", () => { store.clear(); panel(true); });
    $$("[data-guide]", box).forEach((row) => row.addEventListener("click", () => start([row.dataset.guide])));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !box.hidden && !running) panel(false); });
    // İlk açılışta rehber kendini bir kez tanıtır.
    let seen = true;
    try { seen = Boolean(localStorage.getItem("guide-seen")); localStorage.setItem("guide-seen", "1"); } catch { /* tanıtım atlanır */ }
    if (!seen) setTimeout(() => { if (!running) panel(true); }, 1400);
  }

  window.AkademikIzRehber = { start: (id) => start(id ? [id] : TOURS.map((t) => t.id)), open: () => panel(true) };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
