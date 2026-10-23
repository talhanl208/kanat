"""Platform genelinde kullanılan seçenek listeleri."""

CATEGORIES = [
    ("iha", "İnsansız hava araçları"),
    ("ika", "İnsansız kara araçları"),
    ("roket", "Roket ve uzay"),
    ("deniz", "Deniz ve su altı sistemleri"),
    ("robotik", "Robotik ve otonom sistemler"),
    ("yapay_zeka", "Yapay zekâ ve yazılım"),
    ("siber", "Siber güvenlik"),
    ("elektrikli_arac", "Elektrikli ve verimli araçlar"),
    ("enerji", "Enerji ve çevre"),
    ("saglik", "Sağlık ve biyoteknoloji"),
    ("tarim", "Tarım ve gıda teknolojileri"),
    ("egitim", "Eğitim teknolojileri"),
    ("sosyal", "Sosyal inovasyon ve engelsiz yaşam"),
    ("ulasim", "Akıllı ulaşım ve şehirler"),
    ("diger", "Diğer"),
]

COMPETITIONS = [
    ("teknofest", "TEKNOFEST"),
    ("tubitak_2204", "TÜBİTAK 2204 Lise Öğrencileri Araştırma Projeleri"),
    ("tubitak_2209", "TÜBİTAK 2209 Üniversite Öğrencileri Araştırma Projeleri"),
    ("tubitak_2242", "TÜBİTAK 2242 Üniversite Öğrencileri Proje Yarışmaları"),
    ("tubitak_diger", "Diğer TÜBİTAK programları"),
    ("hackathon", "Hackathon / ideathon"),
    ("uluslararasi", "Uluslararası yarışma"),
    ("bagimsiz", "Bağımsız proje / erken girişim"),
    ("diger", "Diğer"),
]

# Takımın ihtiyaç türleri == destekçinin sunabildiği destek türleri
SUPPORT_KINDS = [
    ("maddi", "Maddi destek"),
    ("malzeme", "Malzeme / ürün"),
    ("mentorluk", "Mentörlük"),
    ("hizmet", "Üretim / hizmet"),
    ("ulasim", "Ulaşım / konaklama"),
]
MONETARY_KINDS = {"maddi", "malzeme", "hizmet", "ulasim"}

STAGES = [
    ("fikir", "Fikir"),
    ("tasarim", "Tasarım"),
    ("prototip", "Prototip"),
    ("test", "Test ve iyileştirme"),
    ("final", "Yarışma / final"),
]

SPONSOR_KINDS = [
    ("firma", "Firma"),
    ("kurum", "Kurum, vakıf veya dernek"),
    ("mentor", "Bireysel mentör"),
]

# Sıralamada küçük işletmeler büyüklerle ezilmesin diye ligler
LEAGUES = [
    ("mikro", "Mikro ve bireysel"),
    ("kobi", "KOBİ"),
    ("buyuk", "Büyük kurum"),
]

CITIES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya",
    "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum",
    "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir",
    "Gaziantep", "Giresun", "Gümüşhane", "Hakkâri", "Hatay", "Iğdır", "Isparta", "İstanbul",
    "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kilis",
    "Kırıkkale", "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa",
    "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize",
    "Sakarya", "Samsun", "Şanlıurfa", "Siirt", "Sinop", "Şırnak", "Sivas", "Tekirdağ", "Tokat",
    "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak",
]
CITY_CHOICES = [(c, c) for c in CITIES]

# Aramada kısaltmalar ve yaygın İngilizce karşılıklar da bulunsun diye
CATEGORY_KEYWORDS = {
    "iha": "iha uav drone insansiz hava",
    "ika": "ika ugv otonom arac insansiz kara",
    "roket": "roket model roket uzay uydu",
    "deniz": "isas rov auv su alti insansiz deniz",
    "robotik": "robot robotik otonom",
    "yapay_zeka": "yapay zeka ai makine ogrenmesi yazilim",
    "siber": "siber guvenlik cyber",
    "elektrikli_arac": "elektrikli arac efficiency verimlilik batarya",
    "enerji": "enerji yenilenebilir gunes ruzgar",
    "saglik": "saglik biyomedikal biyoteknoloji",
    "tarim": "tarim gida ziraat",
    "egitim": "egitim teknolojileri",
    "sosyal": "sosyal inovasyon engelsiz erisilebilirlik",
    "ulasim": "ulasim akilli sehir",
}

CATEGORY_LABELS = dict(CATEGORIES)
COMPETITION_LABELS = dict(COMPETITIONS)
SUPPORT_LABELS = dict(SUPPORT_KINDS)
