# Değişiklik günlüğü

## 2.0 — 23 Ekim 2026

### Kapatılan eksikler
- **Puan hilesine karşı koruma:** sıralama ve ödüller yalnızca doğrulanmış destekçiler için; aynı takım–destekçi
  çiftine yıl içinde azalan puan (tam / yarım / puansız); mentörlük ayda en çok 20 saat; şüpheli işaretlerde
  (aynı ağdan giriş, aynı kurumsal alan adı, 24 saatten kısa tamamlanma, doğrulanmamış takıma yüksek tutar)
  puanlar silinmeden **incelemeye** alınır; yönetim panelinde “incelemeden çıkar / geçersiz say” aksiyonları;
  fırsat eşitliği bonusu yalnızca doğrulanmış takımlara
- **Bildirimler:** uygulama içi bildirim merkezi (zil), e-posta bildirimleri, mesaj e-postalarının seyreltilmesi,
  tek tıkla abonelikten çıkma (RFC 8058 başlıklarıyla), haftalık öneri özeti
- **Türkçe arama:** “tübitak / TÜBİTAK / Tubitak” aynı sonuç; hafif ek atma (“motorlar” → “motor”);
  kısaltmalar (İHA, İKA, ROV…); mevcut kayıtlar için veri göçü
- **Takım üyeleri:** e-posta daveti (belirtecin yalnızca özeti saklanır, davet e-posta adresine bağlı),
  kaptan/üye yetkileri, üye çıkarma, ayrılma, kaptanlık devri; üyesi olan kaptanın hesabını kapatması engellenir
- **Doğrulama:** okul e-postasıyla takım, kurumsal alan adıyla destekçi otomatik doğrulama; diğerleri için
  başvuru formu ve yönetici onayı
- **Sponsorluk dosyası:** PDF yükleme; JavaScript/Launch/EmbeddedFile/XFA/form/şifreli içerik taraması
  (sıkıştırılmış akışlar ve ad kaçışları dahil); herkese açık olmayan klasörde, yalnızca destekçiye indirme
- **Engelleme:** takım ve destekçi birbirini engelleyebilir; bekleyen talepler kapanır, öneriler ve
  listeler engeli dikkate alır
- **İki adımlı doğrulama:** TOTP (RFC 6238, bağımlılıksız), tekrar kullanım engeli, 8 kurtarma kodu,
  yönetim paneli için zorunlu; Django admin giriş sayfası kapatıldı, giriş Kanat akışından geçer;
  yönetici için “2FA sıfırla” ve “askıya al” aksiyonları
- **E-posta değiştirme:** bağlantı yeni adrese gider, eski adrese bilgi verilir; adresler URL'de taşınmaz
- **Paylaşılan hız sınırı:** üretimde Redis yoksa veritabanı önbelleği (süreçler arası paylaşılır)
- **KVKK saklama süreleri:** günlük otomatik temizlik; aydınlatma metni ve kullanım koşulları v1.1,
  güncellenen metinler için yeniden onay akışı
- **Destekçi kapasitesi**, **son tarihi geçen projelerin listeden kalkması**, **30 gün yanıtsız taleplerin
  kapanması**, **kelime başı anahtar kelime eşleşmesi**
- **Yayın altyapısı:** Dockerfile (root olmayan kullanıcı, sağlık kontrolü), docker-compose (PostgreSQL,
  Redis, Caddy otomatik HTTPS, günlük zamanlayıcı), nginx ve cron örnekleri, yedekleme betiği,
  `/saglik/` ucu, isteğe bağlı Sentry, Kanat'a özel `check --deploy` uyarıları
- **Testler:** 48 → 120 birim/entegrasyon testi + 4 tarayıcı testi; CI'da tarayıcı ve Docker işleri

### Yenilikler
- **Ortak kanat:** bir ihtiyacı birden çok destekçinin parça parça karşılaması, ihtiyaç başına doluluk
  çubuğu, otomatik kapanma, bonus puan ve rozet
- **Destek çağrıları:** destekçinin açtığı, kontenjanlı, alan filtreli çağrılar; uyan takımlara bildirim;
  uyum puanına göre sıralı başvurular
- **Etki raporu:** destekçiye yıllık, yazdırılabilir kurumsal sosyal sorumluluk özeti
- **Profil gücü:** takım ve destekçi için tıklanabilir tamamlama listesi
