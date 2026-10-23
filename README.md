# Kanat — Geleceğin Yönünü Değiştiren Hayatlar

TEKNOFEST, TÜBİTAK (2204, 2209, 2242…) ve benzeri yarışmalarda proje yürüten takımları;
**maddi destek, malzeme, üretim/hizmet, mentörlük ve ulaşım** sunan destekçilerle ihtiyaca göre
eşleştiren, açık kaynak bir sponsor bulma platformu.

> İsim önerisi: **Kanat**. “Bir projeye kanat ol” cümlesi hem destekçiye hem takıma aynı anda
> seslenir. İlk fikir olan **GEYÖDEH** (Geleceğin Yönünü Değiştiren Hayatlar) sloganda yaşıyor.
> İsmi değiştirmek için `.env` içinde `KANAT_SITE_NAME=GEYÖDEH` yazmanız yeterli.

Sürüm 2 ile gelenlerin listesi: [`docs/DEGISIKLIKLER.md`](docs/DEGISIKLIKLER.md)

## Neler var?

### Takımlar için
- Takım ya da bireysel kayıt; okul, şehir, üye sayısı, danışman bilgisi
- **Takım üyeleri:** kaptan, arkadaşlarını e-postayla davet eder; üyeler projeleri güncelleyip
  yazışabilir. Sözleşme onayı, teslim onayı gibi bağlayıcı adımlar kaptanda kalır; kaptanlık devredilebilir
- Proje: alan, yarışma/program, aşama, son tarih, “destekçiye sunduklarımız”
- Somut ihtiyaç listesi (tür + tutar ya da mentörlük saati), karşılanma yüzdesi
- **Sponsorluk dosyası (PDF):** betik/gömülü dosya taramasından geçer, yalnızca destekçiler indirebilir
- Proje günlüğü: destekçiler katkılarının nereye gittiğini görür (yeni girdiler bildirim olarak gider)
- **Profil gücü:** eksik adımları gösteren tıklanabilir kontrol listesi
- Panelde uyum puanına göre önerilen destekçiler ve projeye uyan destek çağrıları

### Destekçiler için
- Destek türleri, ilgi alanları, desteklenen yarışmalar, bütçe aralığı, mentörlük kapasitesi
- **Kapasite sınırı:** “aynı anda en fazla N takım”; dolunca yeni talep gelmez, önerilerde görünmezsin
- Ürün/hizmet anahtar kelimeleri (ör. “PCB, CNC, lityum batarya”) ihtiyaç listeleriyle eşleşir
- **Destek çağrıları:** “3 İHA takımına motor desteği” gibi çağrı aç; uyan takımlara haber gider,
  başvurular uyum puanına göre sıralanır, kontenjan otomatik işler
- **Etki raporu:** yıllık, yazdırılabilir rapor (takım, şehir, alan, tutar, mentörlük saati, teşekkürler);
  kurumsal sosyal sorumluluk raporlarına hazır

### Eşleştirme (`apps/matching/engine.py`)
- 100 puan: destek türü 35, alan 20, bütçe 15, anahtar kelime 10, konum 10, yarışma 10
- Kural tabanlı ve açıklanabilir: her puanın yanında *neden* eşleştiği yazar
- Anahtar kelimeler **kelime başından** eşleşir: Türkçe ekleri tanır (“motor” → “motorlar”),
  kelime ortasında yanlış eşleşme yapmaz (“elektromotor”)
- Engellenmiş, kapasitesi dolmuş ya da zaten süreçteki çiftler önerilmez

### Ortak kanat (birlikte destek)
- Büyük bir ihtiyacı birden çok destekçi parça parça üstlenebilir; her kalemin ne kadarının
  karşılandığı çubukla görünür, katkılar tutarı karşılayınca kalem kendiliğinden kapanır
- Birlikte destek verenler bonus puan ve “Ortak kanat” rozeti kazanır

### Destek süreci
1. Talep / teklif / çağrı başvurusu → 2. Kabul → 3. Sponsorluk sözleşmesi (hazır şablon)
→ 4. İki taraf **parolasıyla** onaylar → 5. Kaptan “teslim aldık” der, puan ve teşekkür bırakır
- Sözleşmenin SHA-256 özeti saklanır; metin değişirse onaylar düşer
- Mentörlük oturumlarını destekçi kaydeder, takım kaptanı onaylar
- Her süreçte mesajlaşma, şikâyet ve **engelleme**; 30 gün yanıtlanmayan talepler kendiliğinden kapanır

### Bildirimler
- Zil simgesiyle uygulama içi bildirim merkezi; yeni talep, yanıt, mesaj, sözleşme, teslim, ödül, çağrı
- E-posta bildirimleri (tercihle kapatılabilir, tek tıkla abonelikten çıkma — RFC 8058),
  mesaj e-postaları seyreltilir (aynı yazışma için yarım saatte en fazla bir e-posta)
- Haftalık öneri özeti: destekçilere yeni uygun projeler, takımlara yeni çağrılar ve destekçiler

### Sıralama, unvanlar ve ödüller (`apps/rankings/services.py`)
- Puan **yalnızca takımın onayladığı** olaylardan doğar
- Tutar karekökle ölçeklenir (10.000 ₺ → 38, 100.000 ₺ → 120 puan): KOBİ'ler ve mentörler de zirveye çıkar
- Fırsat eşitliği (+25), hızlı yanıt (+5), memnuniyet (+15/+8), mentörlük saati (10/saat), ortak kanat (+10)
- **Ligler** (mikro, KOBİ, büyük kurum), **unvanlar** (Kanat adayı → Doğan → Şahin → Kartal → Anka),
  **7 rozet**, **ödüller** (Ayın Kanadı, Yılın Ankası, Yılın Kılavuzu, Fırsat Eşitliği; doğrulama kodlu belge)
- **Hileye karşı:** sıralamaya yalnızca doğrulanmış destekçiler girer; aynı takıma yıl içinde 2. destek
  yarım, sonrakiler puansız; mentörlük ayda en çok 20 saat sayılır; aynı ağdan giriş, aynı e-posta alan adı,
  24 saatten kısa “tamamlanma” ya da doğrulanmamış takıma yüksek tutar gibi durumlarda puan silinmez,
  yönetici onaylayana kadar **incelemede** bekler
- Destekçinin kendi sitesine koyabileceği canlı SVG rozet, teşekkür duvarı

### Doğrulama
- Takım: kaptanın doğrulanmış `.edu.tr` / `.k12.tr` / `meb.gov.tr` e-postası varsa otomatik
- Destekçi: kurumsal e-posta alan adı web sitesiyle eşleşiyorsa otomatik (ücretsiz e-posta sağlayıcıları ve
  `com.tr` gibi genel uzantı hileleri reddedilir)
- Diğerleri başvuru formuyla; yönetici panelinden onay/ret, sonuç bildirim olarak gider

### KVKK ve sözleşmeler — ayrıntılar `docs/KVKK_KONTROL_LISTESI.md`
- Aydınlatma metni (v1.1), açık rıza (isteğe bağlı, ayrı), çerez politikası, kullanım koşulları, sözleşme şablonu
- Sürümlü onay kayıtları; metin güncellenince kullanıcıdan **yeniden onay** istenir
- Veri indirme (JSON), e-posta değiştirme, hesap kapatma (anonimleştirme), KVKK başvuru formu
- **Saklama süreleri otomatik:** güvenlik kayıtları, bildirimler, kapanmış süreç mesajları, doğrulanmamış
  hesaplar vb. her gün çalışan görevle silinir
- 18 yaş beyanı; reşit olmayan üyeli takımlarda hesabı danışman yönetir; “çocuğa uygunsuz yaklaşım”
  şikâyetleri yönetime acil e-postayla düşer

### Güvenlik — ayrıntılar `SECURITY.md`
- Argon2id, **iki adımlı doğrulama** (TOTP + tek kullanımlık kurtarma kodları; yönetim paneli için zorunlu)
- Hız sınırları (üretimde süreçler arası paylaşılan önbellekle), katı CSP (nonce), IDOR koruması,
  görsel yeniden kodlama, PDF etkin içerik taraması, açık yönlendirme ve hesap numaralandırma koruması
- E-posta bağlantılarında adres açık taşınmaz; davet belirteçlerinin yalnızca özeti saklanır
- CI'da bandit, pip-audit, gitleaks, Docker derleme ve tarayıcı testleri

### Tasarım
- “Çini × devre” teması: İznik kobaltı, turkuaz ve mercan; Selçuklu yıldızı ve Göktürk harfleri
  (𐱅𐰇𐰼𐰚 “Türk”, 𐰴𐰣𐱃 “Kanat”)
- Hero'da canlı gök haritası (takımlar turkuaz, destekçiler altın yıldız, aralarında eşleşme çizgileri)
- Gençlere sözler bandı, sayfa geçişleri (View Transitions API), açık/koyu tema, mobil uyum,
  `prefers-reduced-motion` desteği; yazı tipleri kendi sunucumuzdan

## Kurulum (yerel)

Python 3.12+ gerekir.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # DJANGO_DEBUG=1 kalabilir
python manage.py migrate
python manage.py demo_verisi --parola "Demo-Parola-2026!"   # kurgusal örnek veri
python manage.py createsuperuser
python manage.py runserver
```

Demo hesapları (parola yukarıda verdiğiniz):

| Hesap | Ne görürsün |
| --- | --- |
| `bozok@demo.kanat.test` | Takım kaptanı: üyeler, davet, bildirimler, sözleşme |
| `bozok-yazilim@demo.kanat.test` | Aynı takımın üyesi (kaptan yetkileri yok) |
| `watt@demo.kanat.test` | Doğrulanmamış takım, ortak kanatla yarı karşılanmış batarya ihtiyacı |
| `devre@demo.kanat.test` | Destekçi: çağrı, başvuru, etki raporu, sıralamada 1. |

- Yönetim paneli: http://localhost:8000/yonetim-kapisi/ (geliştirmede 2FA zorunlu değil;
  üretimde zorunlu — `KANAT_ADMIN_REQUIRE_2FA`)
- E-postalar geliştirmede terminale yazılır (doğrulama ve davet bağlantılarını oradan kopyalayın)

## Testler

```bash
python manage.py test                        # 120 test
pip install -r requirements-dev.txt && python -m playwright install chromium
KANAT_E2E=1 python manage.py test apps.core.tests_e2e   # 4 tarayıcı testi (CSP, mobil taşma, 2FA girişi…)
bandit -r apps config -x "*/tests*.py,*/migrations/*" -ll
pip-audit -r requirements.txt
```

## Yayına alma

### Docker ile (önerilen)
```bash
cp .env.example .env   # DJANGO_DEBUG=0, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, KANAT_DOMAIN,
                       # POSTGRES_PASSWORD, KANAT_SITE_URL, e-posta ve KVKK alanlarını doldurun
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```
Compose; PostgreSQL, Redis, uygulama, otomatik HTTPS'li Caddy ve günlük bakım zamanlayıcısını ayağa kaldırır.
Sponsorluk dosyalarının klasörü web sunucusuna **bağlanmaz**. Yedek için `deploy/yedekle.sh`.

### Docker olmadan
`deploy/nginx.conf.example`, `deploy/crontab.example` ve `deploy/entrypoint.sh` içindeki adımlar:
`migrate`, `createcachetable`, `collectstatic`, gunicorn + nginx, günlük `gunluk_bakim`.

### Kontrol
`python manage.py check --deploy` — Kanat'a özel uyarılar da verir (paylaşılmayan önbellek, boş KVKK
bilgileri, varsayılan yönetim adresi, kapalı 2FA, localhost site adresi). Ardından
`docs/KVKK_KONTROL_LISTESI.md` içindeki hukuki adımları tamamlayın.

## Bakım komutları

| Komut | Ne yapar |
| --- | --- |
| `gunluk_bakim` | Son tarih hatırlatmaları, 30 günlük zaman aşımı, çağrı kapatma, KVKK saklama süreleri, ayın/yılın ödülleri (ilk 3 gün), pazartesi haftalık özet |
| `haftalik_ozet` | Haftalık öneri e-postalarını elle gönderir |
| `odulleri_dagit --ay 2026-10` / `--yil 2026` | Ödülleri elle dağıtır (tekrar çalıştırmak güvenli) |
| `demo_verisi --sifirla` | Kurgusal demo verisini yeniden kurar (yalnızca `DJANGO_DEBUG=1`) |

## Proje yapısı

```
config/              ayarlar (ortam değişkenleriyle), URL'ler
apps/core/           ana sayfa, yasal metinler, güvenlik başlıkları, hız sınırı, görsel/PDF denetimi,
                     doğrulama, profil gücü, saklama süreleri, günlük bakım, sağlık ucu, üretim kontrolleri
apps/accounts/       e-posta ile giriş, 2FA (TOTP), e-posta değiştirme, rıza kayıtları, veri indirme/silme
apps/projects/       takım, üyeler ve davetler, proje, ihtiyaç (ortak kanat), sponsorluk dosyası, günlük
apps/sponsors/       destekçi profili, paneli, destek çağrıları, etki raporu
apps/matching/       eşleştirme motoru, talepler, mesajlar, sözleşme, mentörlük, şikâyet, engelleme
apps/rankings/       puan defteri (hile denetimi), sıralama, unvanlar, rozetler, ödüller, SVG rozet
apps/notifications/  bildirim merkezi, e-posta gönderimi, abonelikten çıkma, haftalık özet
templates/           arayüz (satır içi stil/betik yok, CSP uyumlu)
static/              CSS, JS (gök haritası dahil), kendi sunucumuzdaki yazı tipleri
deploy/              Caddy, nginx örneği, cron örneği, yedekleme betiği, konteyner başlangıcı
docs/                KVKK kontrol listesi, değişiklik günlüğü
```

## Ölçek notu

Eşleştirme önerileri istek anında Python'da hesaplanıyor; birkaç bin proje/destekçiye kadar rahat çalışır.
E-postalar istek içinde (işlem tamamlandıktan sonra) gönderiliyor. Daha büyük ölçekte önerileri arka planda
önceden hesaplamak ve e-postaları bir kuyruğa (ör. Celery/RQ) almak gerekir.

## Lisans

Kod MIT lisansıyla açıktır (`LICENSE`). Yazı tipleri SIL Open Font License 1.1 ile dağıtılır.
Demo verisindeki tüm takım, kurum ve kişi adları kurgusaldır.
