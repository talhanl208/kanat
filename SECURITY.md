# Güvenlik politikası

## Açık bildirme

Kanat'ta bir güvenlik açığı bulduysanız lütfen **herkese açık bir issue açmayın**.
Bunun yerine `.env` içindeki `KANAT_SECURITY_CONTACT` adresine (canlı sitede
`/.well-known/security.txt` dosyasında yazar) e-posta gönderin ve şunları ekleyin:

- Açığın kısa açıklaması ve etkisi
- Yeniden üretme adımları (varsa kavram kanıtı)
- Etkilenen sayfa / sürüm

Bildirimi 5 iş günü içinde yanıtlarız. İyi niyetle, kullanıcı verisine zarar vermeden ve
hizmeti aksatmadan yapılan araştırmalar için hukuki yola başvurmayız.

## Kapsam dışı

- Hız sınırı olmayan, durum değiştirmeyen GET istekleri
- Yalnızca eski / desteklenmeyen tarayıcıları etkileyen sorunlar
- Kullanıcının kendi hesabında kendine karşı yapabildiği işlemler (self-XSS vb.)

## Uygulanan önlemler (özet)

| Tehdit | Önlem |
| --- | --- |
| Parola sızıntısı | Argon2id; en az 10 karakter, yaygın/sayısal parola reddi; isteğe bağlı TOTP iki adımlı doğrulama (yönetim paneli için zorunlu), tek kullanımlık kurtarma kodları (yalnızca özetleri saklanır), kod tekrar kullanımı engeli |
| Kaba kuvvet | Giriş (IP + e-posta), 2FA kodu, kayıt, parola sıfırlama, mesaj, davet, çağrı ve başvurularda hız sınırı; üretimde sayaçlar süreçler arasında paylaşılır (Redis ya da veritabanı önbelleği) |
| Hesap numaralandırma | Kayıt ve parola sıfırlamada ekranda fark yok; bilgi yalnızca e-posta sahibine gider |
| XSS | Django otomatik kaçışlama, katı CSP (nonce), satır içi stil/betik yok, SVG rozetinde ayrı CSP |
| CSRF | Django CSRF koruması, SameSite=Lax çerezler, durum değiştiren her işlem POST |
| Clickjacking | `X-Frame-Options: DENY` ve `frame-ancestors 'none'` |
| IDOR | Her nesne sahiplik/taraf kontrolüyle alınır; yetkisiz erişimde 404 |
| Açık yönlendirme | `next` parametresi `url_has_allowed_host_and_scheme` ile doğrulanır |
| Dosya yükleme | Görseller: boyut sınırı, Pillow doğrulaması, WebP'ye yeniden kodlama (EXIF silinir), rastgele ad. PDF'ler: imza ve bütünlük kontrolü, sıkıştırılmış akışlar ve ad kaçışları dahil JavaScript/Launch/EmbeddedFile/XFA/form taraması, şifreli PDF reddi, web'den erişilemeyen klasör, yalnızca yetkili indirme (`attachment` + `CSP: sandbox`) |
| Yetki yükseltme | Takım içinde kaptan/üye ayrımı: bağlayıcı adımlar yalnızca kaptan; davet e-posta adresine bağlı, belirteç özetle saklanır |
| Sıralama manipülasyonu | Yalnızca doğrulanmış destekçiler sıralanır; aynı çifte azalan puan; şüpheli işaretlerde puan incelemeye alınır (insan kararı) |
| Taciz | Engelleme, şikâyet; reşit olmayana uygunsuz yaklaşım bildirimleri yönetime acil e-postayla |
| Kişisel veri sızıntısı (günlükler) | E-posta doğrulama ve değiştirme bağlantıları adres taşımaz; IP'ler anahtarlı özetle saklanır |
| Oturum | HttpOnly + Secure çerezler, girişte oturum anahtarı yenileme, 7 gün ömür |
| Taşıma | Üretimde HTTPS yönlendirme ve HSTS (1 yıl) |
| Sözleşme bütünlüğü | Metnin SHA-256 özeti, onay için parola, metin değişince onaylar düşer |
| Gizlilik | IP adresleri anahtarlı özetle saklanır, üçüncü taraf betik/yazı tipi yok |
| Tedarik zinciri | Dependabot, pip-audit, bandit, gitleaks, Docker derleme ve tarayıcı testleri (CI) |
| Yönetim paneli | Kanat giriş akışı dışında giriş yok (admin login kapalı), 2FA zorunlu, adres ortam değişkeniyle gizlenebilir |
