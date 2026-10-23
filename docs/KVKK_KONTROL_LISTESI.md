# KVKK ve hukuki uyum kontrol listesi

Kod tarafında KVKK'nın gerektirdiği mekanizmalar hazır. Ancak **hukuki uyum yalnızca kodla
sağlanmaz.** Siteyi gerçek kullanıcılara açmadan önce aşağıdaki maddeleri tamamlayın.
Bu liste hukuki danışmanlık değildir; metinleri mutlaka bir hukukçuya inceletin.

## Kodda hazır olanlar

- [x] Aydınlatma metni, kayıt sırasında ayrı kutucukla "okudum" onayı (açık rıza ile karıştırılmadan)
- [x] Açık rıza yalnızca isteğe bağlı bülten için; hizmet şartına bağlanmamış, önceden işaretli değil
- [x] Rızanın tek tıkla geri alınması ve tüm onayların sürüm + zaman damgasıyla saklanması (`ConsentRecord`)
- [x] 18 yaş beyanı; reşit olmayan üyeli takımlarda danışman beyanı ve üye verisi girilmemesi uyarısı
- [x] Veri minimizasyonu: T.C. kimlik no, telefon, adres, fotoğraf istenmiyor
- [x] İlgili kişi hakları: verileri JSON olarak indirme, düzeltme, hesabı kapatma (anonimleştirme), başvuru formu (30 gün takibi)
- [x] Otomatik eşleştirme puanının gerekçesi her zaman gösteriliyor (md. 11/1-g itiraz hakkı için şeffaflık)
- [x] Yalnızca zorunlu çerezler; analitik/reklam yok, yazı tipleri kendi sunucumuzdan (yurt dışına IP aktarımı yok)
- [x] IP adresleri takma adlandırılmış (HMAC) saklanıyor
- [x] Güvenlik kayıtları (`AuditLog`) değiştirilemez
- [x] Saklama süreleri kodda tanımlı ve her gün otomatik uygulanıyor (`gunluk_bakim`, `settings.RETENTION_DAYS`)
- [x] Hukuki metin sürümü değişince kullanıcıdan yeniden onay isteniyor
- [x] Puan denetimi gibi otomatik değerlendirmeler tek başına sonuç doğurmuyor; şüpheli durumda yönetici karar veriyor
- [x] Sponsorluk dosyaları herkese açık değil; yükleme ekranında reşit olmayan üyelerin verilerini koymama uyarısı
- [x] E-posta bildirimleri tek tıkla kapatılabiliyor (işlem bildirimidir, pazarlama içermez)

## Yayına almadan önce sizin yapmanız gerekenler

- [ ] **Veri sorumlusunu belirleyin.** Kişi mi, şirket mi, dernek mi? `.env` içindeki `KANAT_DATA_CONTROLLER_*` alanlarını doldurun.
- [ ] **Metinleri bir hukukçuya inceletin**, köşeli parantezli alanları doldurun, ardından `KANAT_LEGAL_DRAFT_NOTICE=0` yapın.
- [ ] **Barındırma yeri:** Sunucu yurt dışındaysa KVKK md. 9 (2024 değişikliği sonrası standart sözleşme / bildirim yükümlülükleri) kapsamında işlem yapın ve aydınlatma metnini güncelleyin. Mümkünse Türkiye'de barındırın.
- [ ] **VERBİS:** Kayıt yükümlülüğünüz olup olmadığını Kurul'un güncel istisna kararlarına göre kontrol edin.
- [ ] **Saklama ve imha politikası:** Koddaki varsayılan süreleri (`RETENTION_DAYS`) hukukçunuzla gözden geçirip yazılı politikaya dönüştürün; `gunluk_bakim` görevinin her gün çalıştığından emin olun.
- [ ] **Yedekler:** Yedekler kişisel veri içerir; şifreli saklayın ve saklama süresini politikaya ekleyin.
- [ ] **Veri işleyen sözleşmeleri:** Barındırma ve e-posta hizmeti aldığınız firmalarla sözleşme yapın.
- [ ] **Veri ihlali planı:** İhlali Kurul'a en kısa sürede (Kurul kararına göre 72 saat) bildirme ve ilgili kişilere duyurma prosedürü hazırlayın.
- [ ] **Ticari elektronik ileti:** Bülten ticari nitelikteyse İYS kaydı yapın (6563 sayılı Kanun).
- [ ] **5651 sayılı Kanun:** Yer sağlayıcı yükümlülüklerinizi (trafik kayıtlarının saklanması vb.) hukukçunuzla değerlendirin.
- [ ] **Şikâyet süreci:** Yönetim panelindeki şikâyetleri düzenli inceleyecek bir sorumlu atayın; özellikle "reşit olmayan bir üyeye uygunsuz yaklaşım" bildirimlerine aynı gün bakın.
- [ ] **Doğrulanmış destekçi:** Firmaları "doğrulandı" işaretlemeden önce kurumsal e-posta veya resmi kayıtlardan teyit edin.

## Neden para platformdan geçmiyor?

Ödemeleri platform üzerinden almak; ödeme hizmetleri mevzuatı, bağış toplama izni, vergi ve
emanet sorumluluğu gibi ağır yükümlülükler doğurur. Kanat bu yüzden yalnızca buluşturur,
sözleşmeyi kayıt altına alır ve teşekkürü görünür kılar. Nakdi desteklerin takımın bağlı
olduğu okul, üniversite veya derneğin resmi hesabına yapılması önerilir.
