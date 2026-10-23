"""
Yerel geliştirme için KURGUSAL örnek veri oluşturur. Üretimde çalıştırmayın.

    python manage.py demo_verisi --parola "GucluBirParola!42"

Tüm takım, kurum ve kişi adları uydurmadır; gerçek kişi/kurumlarla ilgisi yoktur.
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ConsentRecord, User
from apps.core.legal import version_of
from apps.matching.agreements import initial_for, render_body
from apps.matching.models import Agreement, MentorSession, Message, SupportRequest
from apps.notifications.models import Notification
from apps.projects.models import Need, Project, ProgressUpdate, Team, TeamInvite, TeamMembership
from apps.rankings.models import Award, PointEntry
from apps.rankings.services import award_completion, award_mentor_session, issue_awards, Period, month_bounds, MONTHS_TR
from apps.sponsors.models import Sponsor, SponsorCall

DOMAIN = "demo.kanat.test"

TEAMS = [
    {
        "key": "bozok", "name": "Bozok Otonom", "institution": "Anadolu Teknoloji Üniversitesi",
        "city": "Konya", "members": 9, "minors": False, "advisor": "",
        "about": "Makine, elektronik ve yazılım öğrencilerinden oluşan, üçüncü yılına giren bir otonom araç takımıyız.",
        "project": {
            "title": "Arazi Kâşifi", "category": "ika", "competition": "teknofest", "stage": "prototip",
            "detail": "TEKNOFEST 2027 İnsansız Kara Aracı Yarışması",
            "summary": "Engebeli arazide şerit ve engel algılayarak ilerleyen tekerlekli otonom kara aracı.",
            "description": "Geçen yıl paletli şasiyle başladığımız aracı bu yıl tekerlekli ve süspansiyonlu yapıya "
                           "taşıyoruz. ROS 2 tabanlı yazılımımız stereo kamera ve LiDAR verisini birleştirerek "
                           "engel haritası çıkarıyor. Prototip sahada ilk testlerini geçti; yarışma öncesi motor "
                           "ve şasi tarafında güçlenmemiz gerekiyor.",
            "benefits": "Araç gövdesinde logo, yarışma sunumunda ve sosyal medyada teşekkür, atölye ziyareti.",
            "needs": [
                ("malzeme", "4 adet fırçasız DC motor ve sürücü", "48V, en az 500W", 18000, None),
                ("hizmet", "Alüminyum şasi için CNC kesim", "6061 alüminyum, 5 parça", 9000, None),
                ("mentorluk", "ROS 2 ve gömülü sistem mentörlüğü", "Haftada 1 saat", None, 12),
                ("ulasim", "Final için ulaşım ve konaklama", "9 kişi, 4 gece", 15000, None),
            ],
        },
    },
    {
        "key": "tomris", "name": "Tomris Roket", "institution": "Mavi Ufuk Fen Lisesi", "city": "İzmir",
        "members": 6, "minors": True, "advisor": "Danışman öğretmen Selin Aydemir",
        "about": "Lise öğrencilerinden oluşan roket takımıyız; hesap danışman öğretmenimiz tarafından yönetiliyor.",
        "project": {
            "title": "Tomris-1 orta irtifa roketi", "category": "roket", "competition": "teknofest",
            "stage": "test", "detail": "TEKNOFEST Roket Yarışması — orta irtifa",
            "summary": "3 km irtifaya faydalı yük taşıyan, iki aşamalı paraşüt sistemli model roket.",
            "description": "Aviyonik kartımızı kendimiz tasarladık; şimdi gövdeyi karbon fibere geçirip "
                           "kurtarma sistemini sahada denemek istiyoruz.",
            "benefits": "Roket gövdesinde logo, okul web sitesinde ve tören sunumunda teşekkür.",
            "needs": [
                ("malzeme", "Karbon fiber gövde tüpü", "2 m, 114 mm çap", 22000, None),
                ("hizmet", "Motor test standı kullanımı", "1 günlük test", 6000, None),
                ("mentorluk", "Aviyonik ve kurtarma sistemi mentörlüğü", "", None, 8),
            ],
        },
    },
    {
        "key": "sifa", "name": "Toprak Nabzı", "institution": "Orta Anadolu Üniversitesi", "city": "Ankara",
        "members": 3, "minors": False, "advisor": "", "kind": "takim",
        "about": "Tarım ve biyomühendislik öğrencileri olarak çiftçinin cebine sığan ölçüm araçları geliştiriyoruz.",
        "project": {
            "title": "Kâğıttan nitrat sensörü", "category": "tarim", "competition": "tubitak_2209",
            "stage": "tasarim", "detail": "TÜBİTAK 2209-A",
            "summary": "Topraktaki nitratı 5 dakikada ölçen, telefonla okunabilen düşük maliyetli kâğıt sensör.",
            "description": "Aşırı gübre kullanımını azaltmak için tarlada hızlı ölçüm yapan bir sensör "
                           "geliştiriyoruz. Laboratuvar sarf malzemesi ve kalibrasyon desteğine ihtiyacımız var.",
            "benefits": "Saha denemelerinde kooperatif üyelerine ücretsiz ölçüm, raporda teşekkür.",
            "needs": [
                ("malzeme", "Laboratuvar sarf malzemesi", "Reaktif, filtre kâğıdı, pipet", 7500, None),
                ("mentorluk", "Biyosensör kalibrasyonu", "", None, 6),
            ],
        },
    },
    {
        "key": "kayi", "name": "Kayı Siber", "institution": "Marmara Kıyı Meslek Yüksekokulu", "city": "İstanbul",
        "members": 4, "minors": False, "advisor": "",
        "about": "Siber güvenlik meraklısı ön lisans öğrencileriyiz.",
        "project": {
            "title": "Okul Kalkanı", "category": "siber", "competition": "tubitak_2242",
            "stage": "prototip", "detail": "TÜBİTAK 2242 — Siber güvenlik",
            "summary": "Okullar için oltalama (phishing) farkındalık simülatörü ve eğitim paneli.",
            "description": "Öğretmen ve öğrencilere zararsız sahte oltalama e-postaları göndererek farkındalık "
                           "ölçen ve kısa eğitimler sunan açık kaynak bir platform geliştiriyoruz.",
            "benefits": "Proje deposunda ve tanıtım videosunda destekçi adı.",
            "needs": [
                ("hizmet", "Bulut sunucu (12 ay)", "2 vCPU, 4 GB RAM", 6000, None),
                ("mentorluk", "Sızma testi ve güvenli kod mentörlüğü", "", None, 10),
            ],
        },
    },
    {
        "key": "mavi", "name": "Mavi Vatan Su Altı", "institution": "Karadeniz Denizcilik Lisesi",
        "city": "Trabzon", "members": 7, "minors": True, "advisor": "Danışman öğretmen Kemal Yazıcı",
        "about": "Denizcilik lisesi öğrencileriyiz; ilk su altı aracımızı yapıyoruz.",
        "project": {
            "title": "Ağ Bekçisi", "category": "deniz", "competition": "teknofest",
            "stage": "tasarim", "detail": "TEKNOFEST İnsansız Su Altı Sistemleri",
            "summary": "Balık çiftliklerindeki ağları denetleyip yırtıkları bildiren su altı robotu.",
            "description": "Kameralı, altı iticili bir ROV tasarlıyoruz. Gövde ve elektronik su geçirmezlik "
                           "testleri için havuz ve konnektör desteği arıyoruz.",
            "benefits": "Araç üzerinde logo ve tanıtım günlerinde stantta yer.",
            "needs": [
                ("malzeme", "IP68 su geçirmez konnektörler", "12 adet", 9500, None),
                ("maddi", "Havuz testi kirası", "3 seans", 4000, None),
                ("hizmet", "PCB üretimi", "4 katman, 10 adet", 3500, None),
            ],
        },
    },
    {
        "key": "engelsiz", "name": "Engelsiz Adım", "institution": "Porsuk Anadolu Lisesi",
        "city": "Eskişehir", "members": 4, "minors": True, "advisor": "Danışman öğretmen Aylin Tekin",
        "about": "Görme engelli arkadaşımız için başlayan bir okul projesi.",
        "project": {
            "title": "Titreşimli yön bilekliği", "category": "sosyal", "competition": "tubitak_2204",
            "stage": "prototip", "detail": "TÜBİTAK 2204-A Lise Araştırma Projeleri",
            "summary": "Görme engelli bireylere titreşimle yön gösteren, telefonla eşleşen bileklik.",
            "description": "Bileklik, telefondaki rota bilgisini dört yönlü titreşime çeviriyor. Kullanıcı "
                           "testlerini doğru tasarlamak için mentörlüğe ihtiyacımız var.",
            "benefits": "Proje posterinde ve okul sergisinde teşekkür.",
            "needs": [
                ("malzeme", "Titreşim motoru ve BLE modülleri", "", 3000, None),
                ("mentorluk", "Kullanıcı testi tasarımı", "", None, 5),
            ],
        },
    },
    {
        "key": "watt", "name": "Yeşil Watt", "institution": "Argeus Meslek Yüksekokulu", "city": "Kayseri",
        "members": 11, "minors": False, "advisor": "",
        "about": "Verimlilik yarışmaları için elektrikli araç geliştiren bir takımız.",
        "project": {
            "title": "Akıllı batarya yönetimi", "category": "elektrikli_arac", "competition": "tubitak_diger",
            "stage": "tasarim", "detail": "Elektrikli araç verimlilik yarışması",
            "summary": "Güneş destekli elektrikli araç için hücre dengeleyen batarya yönetim sistemi.",
            "description": "Kendi BMS kartımızı ve yazılımımızı geliştiriyoruz; hücre seti ve yazılım "
                           "mentörlüğü arıyoruz.",
            "benefits": "Araç kaportasında logo, pist günlerinde davet.",
            "needs": [
                ("malzeme", "LiFePO4 hücre seti", "32 hücre", 40000, None),
                ("mentorluk", "BMS yazılımı", "", None, 10),
            ],
        },
    },
]

SPONSORS = [
    {"key": "devre", "name": "Anadolu Devre Elektronik", "kind": "firma", "league": "kobi", "city": "Konya",
     "sector": "Elektronik üretim", "types": ["malzeme", "hizmet"],
     "interests": ["ika", "iha", "robotik", "deniz"], "comps": ["teknofest"], "min": 3000, "max": 40000,
     "hours": None, "offer": "PCB, motor sürücü, fırçasız motor, konnektör", "verified": True,
     "about": "Konya'da kart tasarımı ve dizgi yapan bir KOBİ'yiz; öğrenci takımlarına malzeme ve PCB üretimi sağlıyoruz."},
    {"key": "makine", "name": "Selçuklu Hassas Makine", "kind": "firma", "league": "kobi", "city": "Konya",
     "sector": "Talaşlı imalat", "types": ["hizmet", "malzeme"], "interests": ["ika", "roket", "elektrikli_arac"],
     "comps": [], "min": 2000, "max": 25000, "hours": None, "offer": "CNC, alüminyum, şasi, kaynak",
     "verified": True, "about": "CNC işleme ve kaynak atölyemizde takımların parçalarını üretiyoruz."},
    {"key": "gokboru", "name": "Gökbörü Havacılık", "kind": "firma", "league": "buyuk", "city": "Ankara",
     "sector": "Havacılık ve savunma", "types": ["maddi", "mentorluk"], "interests": ["iha", "roket", "ika"],
     "comps": ["teknofest"], "min": 10000, "max": 150000, "hours": 20, "offer": "aviyonik, test, mentörlük",
     "verified": True, "about": "Mühendislerimiz gönüllü mentörlük yapıyor; havacılık takımlarına nakdi destek veriyoruz."},
    {"key": "ufuk", "name": "Ufuk Yazılım Akademisi", "kind": "firma", "league": "kobi", "city": "İstanbul",
     "sector": "Yazılım eğitimi", "types": ["mentorluk", "hizmet"], "interests": ["siber", "yapay_zeka", "egitim"],
     "comps": [], "min": None, "max": 10000, "hours": 16, "offer": "bulut sunucu, siber güvenlik, sızma testi",
     "verified": True, "about": "Siber güvenlik ve yazılım eğitmenlerimizle takımlara mentörlük veriyoruz."},
    {"key": "deniz", "name": "Deniz Arslan", "kind": "mentor", "league": "mikro", "city": "İzmir",
     "sector": "Gömülü sistemler danışmanı", "types": ["mentorluk"], "interests": ["roket", "iha", "deniz"],
     "comps": [], "min": None, "max": None, "hours": 8, "offer": "aviyonik, gömülü sistem, kurtarma sistemi",
     "verified": False, "about": "Kurgusal örnek mentör profili. Aviyonik ve gömülü sistemlerde 12 yıllık deneyim."},
    {"key": "toprak", "name": "Toprak Ana Tarım Kooperatifi", "kind": "kurum", "league": "mikro", "city": "Ankara",
     "sector": "Tarım", "types": ["maddi", "malzeme"], "interests": ["tarim", "enerji"], "comps": [],
     "min": 1000, "max": 15000, "hours": None, "offer": "laboratuvar, saha denemesi, sarf malzemesi",
     "verified": True, "about": "Üyelerimizin tarlalarını saha denemelerine açıyor, küçük bütçeli destek veriyoruz."},
    {"key": "karadeniz", "name": "Fırtına Vadisi Enerji", "kind": "firma", "league": "buyuk", "city": "Trabzon",
     "sector": "Enerji", "types": ["maddi", "ulasim"], "interests": ["enerji", "deniz", "elektrikli_arac"],
     "comps": [], "min": 3000, "max": 100000, "hours": None, "offer": "ulaşım, konaklama, havuz",
     "verified": True, "about": "Karadeniz'deki genç mühendisleri desteklemek için burs ve sponsorluk fonu ayırıyoruz."},
    {"key": "kilavuz", "name": "Kılavuz Mühendislik Derneği", "kind": "kurum", "league": "mikro",
     "city": "Eskişehir", "sector": "Sivil toplum", "types": ["mentorluk", "ulasim"],
     "interests": ["sosyal", "egitim", "saglik"], "comps": [], "min": None, "max": 8000, "hours": 12,
     "offer": "kullanıcı testi, erişilebilirlik, ulaşım", "verified": False,
     "about": "Emekli mühendislerden oluşan derneğimiz lise takımlarına mentörlük veriyor."},
]


class Command(BaseCommand):
    help = "Kurgusal demo verisi oluşturur (yalnızca yerel geliştirme)."

    def add_arguments(self, parser):
        parser.add_argument("--parola", help="Tüm demo hesapları için parola (verilmezse rastgele)")
        parser.add_argument("--sifirla", action="store_true", help="Önce eski demo verisini sil")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Demo verisi yalnızca DJANGO_DEBUG=1 iken oluşturulabilir.")
        password = opts["parola"] or secrets.token_urlsafe(12)
        self.password = password
        with transaction.atomic():
            if opts["sifirla"]:
                User.objects.filter(email__endswith="@" + DOMAIN).delete()
                Agreement.objects.filter(request__isnull=True).delete()
            if User.objects.filter(email__endswith="@" + DOMAIN).exists():
                raise CommandError("Demo verisi zaten var. Yeniden oluşturmak için --sifirla ekleyin.")
            projects = {t["key"]: self._team(t, password) for t in TEAMS}
            sponsors = {s["key"]: self._sponsor(s, password) for s in SPONSORS}
            self._stories(projects, sponsors)

        self.stdout.write(self.style.SUCCESS("Demo verisi hazır."))
        self.stdout.write(f"  Takım hesabı:    bozok@{DOMAIN}")
        self.stdout.write(f"  Destekçi hesabı: devre@{DOMAIN}")
        self.stdout.write(f"  Parola:          {password}")

    # ------------------------------------------------------------------ #
    def _user(self, key, name, role, password):
        user = User.objects.create_user(
            email=f"{key}@{DOMAIN}", password=password, full_name=name, role=role,
            email_verified=True, adult_declared_at=timezone.now(),
        )
        for kind in ("aydinlatma", "kullanim", "yas"):
            ConsentRecord.objects.create(
                user=user, kind=kind, version=version_of({"yas": "kullanim"}.get(kind, kind)), granted=True
            )
        return user

    def _team(self, t, password):
        user = self._user(t["key"], f"{t['name']} sorumlusu", User.Role.TEAM, password)
        verified = t["key"] != "watt"
        team = Team.objects.create(
            owner=user, name=t["name"], institution=t["institution"], city=t["city"],
            member_count=t["members"], has_minor_members=t["minors"], advisor_name=t["advisor"],
            about=t["about"], founded_year=2024, verified=verified,
            verification_method="yonetici" if verified else "",
        )
        p = t["project"]
        project = Project.objects.create(
            team=team, title=p["title"], summary=p["summary"], description=p["description"],
            category=p["category"], competition=p["competition"], competition_detail=p["detail"],
            stage=p["stage"], sponsor_benefits=p["benefits"],
            deadline=timezone.localdate() + timedelta(days=150),
        )
        for kind, title, detail, cost, hours in p["needs"]:
            Need.objects.create(
                project=project, kind=kind, title=title, detail=detail,
                estimated_cost=Decimal(cost) if cost else None, mentor_hours=hours,
            )
        ProgressUpdate.objects.create(
            project=project, title="Takım kuruldu, ilk tasarım hazır",
            body="İlk tasarım incelememizi yaptık; ihtiyaç listemizi bu sayfada güncel tutuyoruz.",
        )
        return project

    def _sponsor(self, s, password):
        user = self._user(s["key"], f"{s['name']} yetkilisi", User.Role.SPONSOR, password)
        return Sponsor.objects.create(
            owner=user, kind=s["kind"], name=s["name"], league=s["league"], sector=s["sector"],
            city=s["city"], about=s["about"], support_types=s["types"], interest_categories=s["interests"],
            competitions=s["comps"], budget_min=s["min"], budget_max=s["max"],
            mentor_hours_per_month=s["hours"], offerings=s["offer"], verified=s["verified"],
            verification_method="yonetici" if s["verified"] else "",
            max_active_projects=5 if s["key"] == "devre" else None,
        )

    # ------------------------------------------------------------------ #
    def _req(self, project, sponsor, kind, *, by="destekci", amount=None, hours=None, note=None,
             need=None, call=None):
        from apps.matching.engine import score_match

        return SupportRequest.objects.create(
            project=project, sponsor=sponsor, initiated_by=by, kind=kind, need=need, call=call,
            amount=Decimal(amount) if amount else None, mentor_hours=hours,
            note=note or "Merhaba, projenizi inceledik ve destek olmak isteriz.",
            match_score=score_match(project, sponsor).score,
        )

    def _agree(self, req, approve=True):
        initial = initial_for(req)
        agreement = Agreement(
            request=req, team_name=req.project.team.name, sponsor_name=req.sponsor.name,
            project_title=req.project.title, template_version=version_of("sponsorluk-sozlesmesi"),
            **initial,
        )
        agreement.seal(render_body(agreement, req))
        if approve:
            agreement.team_approved_at = agreement.sponsor_approved_at = timezone.now()
            req.status = "anlasma"
        else:
            req.status = "kabul"
        req.responded_at = req.created_at + timedelta(hours=20)
        req.save()
        agreement.save()
        return agreement

    def _complete(self, req, value, rating, thanks, when, mark_needs=True):
        SupportRequest.objects.filter(pk=req.pk).update(created_at=when - timedelta(days=12))
        req.refresh_from_db()
        if req.status != "anlasma":
            self._agree(req)
        req.delivered_value = Decimal(value) if value else None
        req.rating = rating
        req.thanks_note = thanks
        req.thanks_public = True
        req.status = "tamamlandi"
        req.completed_at = when
        req.save()
        award_completion(req)
        if mark_needs:
            req.project.needs.filter(kind=req.kind).update(fulfilled=True)
        PointEntry.objects.filter(request=req).update(created_at=when)

    def _stories(self, P, S):
        now = timezone.now()
        last_month = now - timedelta(days=now.day + 3)

        r = self._req(P["bozok"], S["devre"], "malzeme", amount=18000)
        self._complete(r, 18000, 5, "Motorlar ve sürücüler zamanında geldi; araç ilk kez tam güçle yokuş çıktı!",
                       now - timedelta(days=4))
        Message.objects.create(request=r, sender=r.project.team.owner,
                               body="Teşekkürler! Test videosunu proje günlüğüne ekledik.")

        r = self._req(P["tomris"], S["gokboru"], "maddi", amount=30000)
        self._complete(r, 30000, 5, "Karbon fiber gövdemizi bu destekle aldık. Teşekkürler Gökbörü ekibi!", last_month)

        r = self._req(P["mavi"], S["karadeniz"], "maddi", by="takim", amount=4000)
        self._complete(r, 4000, 5, "İlk havuz testimizi yaptık; aracımız ilk kez suya girdi.",
                       now - timedelta(days=2))

        r = self._req(P["sifa"], S["toprak"], "malzeme", amount=7500)
        self._complete(r, 7500, 4, "Sarf malzemeleri ve saha denemesi için kooperatife teşekkürler.",
                       now - timedelta(days=7))

        r = self._req(P["kayi"], S["ufuk"], "mentorluk", hours=10)
        self._agree(r)
        for days, hrs, topic in [(20, 2, "Tehdit modelleme"), (13, 3, "Güvenli kimlik doğrulama"),
                                 (6, 3, "Sızma testi tatbikatı")]:
            session = MentorSession.objects.create(
                request=r, date=timezone.localdate() - timedelta(days=days), hours=Decimal(hrs), topic=topic,
                confirmed_at=now - timedelta(days=days - 1),
            )
            entry = award_mentor_session(session)
            if entry:
                PointEntry.objects.filter(pk=entry.pk).update(created_at=now - timedelta(days=days - 1))
        self._complete(r, None, 5, "Ufuk ekibi bize güvenli kod yazmayı öğretti; projemiz çok daha sağlam.",
                       now - timedelta(days=1))

        r = self._req(P["bozok"], S["makine"], "hizmet", amount=9000)
        self._agree(r)

        r = self._req(P["tomris"], S["deniz"], "mentorluk", hours=8)
        self._agree(r, approve=False)

        self._req(P["engelsiz"], S["kilavuz"], "mentorluk", by="takim", hours=5,
                  note="Merhaba, kullanıcı testlerimizi tasarlamak için mentörlüğünüze ihtiyacımız var.")
        self._req(P["watt"], S["gokboru"], "maddi", amount=40000,
                  note="Batarya projenize nakdi destek vermek istiyoruz; detayları konuşalım.")

        # Ortak kanat: 40.000 ₺'lik batarya ihtiyacını iki destekçi paylaşıyor
        battery = P["watt"].needs.get(kind="malzeme")
        r = self._req(P["watt"], S["makine"], "malzeme", amount=15000, need=battery)
        self._complete(r, 15000, 5, "Hücre setinin ilk yarısı geldi; batarya kutusunu kapattık.",
                       now - timedelta(days=9), mark_needs=False)
        r = self._req(P["watt"], S["devre"], "malzeme", amount=10000, need=battery, by="takim")
        self._complete(r, 10000, 5, "Selçuklu Hassas Makine ile birlikte bataryamızın büyük kısmı tamam!",
                       now - timedelta(days=3), mark_needs=False)

        # Takım üyeleri ve bekleyen bir davet
        captain = P["bozok"].team.owner
        for key, name in [("bozok-yazilim", "Elif Kaya"), ("bozok-mekanik", "Mert Demir")]:
            member = self._user(key, name, User.Role.TEAM, self.password)
            TeamMembership.objects.create(team=P["bozok"].team, user=member)
        TeamInvite.create_for(P["bozok"].team, f"bozok-elektronik@{DOMAIN}", captain)

        # Destek çağrıları
        today = timezone.localdate()
        call = SponsorCall.objects.create(
            sponsor=S["devre"], title="İnsansız araç takımlarına motor sürücü kartı",
            description="Kara, hava ve su altı araçları geliştiren 3 takıma, kendi ürettiğimiz 4 kanallı motor "
                        "sürücü kartından ve PCB baskı hizmetinden oluşan destek paketi veriyoruz. "
                        "Başvurunuzda aracınızın güç ihtiyacını ve yarışma takviminizi yazın.",
            kind="malzeme", categories=["ika", "iha", "deniz"], amount_per_team=Decimal(6000), slots=3,
            deadline=today + timedelta(days=18),
        )
        mavi = P["mavi"]
        self._req(mavi, S["devre"], "malzeme", by="takim", amount=6000, call=call,
                  need=mavi.needs.filter(kind="malzeme").first(),
                  note="Su altı aracımızın altı iticisi için sürücü kartına ihtiyacımız var; takvimimiz ektedir.")
        SponsorCall.objects.create(
            sponsor=S["ufuk"], title="Siber güvenlik ve yapay zekâ takımlarına mentörlük",
            description="Eğitmenlerimiz iki takıma üç ay boyunca ayda 4 saat birebir mentörlük verecek: "
                        "tehdit modelleme, güvenli kod incelemesi ve sunum provası.",
            kind="mentorluk", categories=["siber", "yapay_zeka", "egitim"], mentor_hours=12, slots=2,
            deadline=today + timedelta(days=9),
        )
        SponsorCall.objects.create(
            sponsor=S["karadeniz"], title="TEKNOFEST finalistlerine ulaşım desteği",
            description="Finale kalan ve Karadeniz'den yola çıkacak takımların otobüs biletlerini karşılıyoruz.",
            kind="ulasim", categories=[], amount_per_team=Decimal(8000), slots=4,
            deadline=today + timedelta(days=30),
        )

        # Örnek bildirimler
        Notification.objects.bulk_create([
            Notification(user=S["devre"].owner, kind="talep", title="Mavi Vatan Su Altı, çağrına başvurdu",
                         body="Ağ Bekçisi: malzeme / ürün", url="/eslesmeler/"),
            Notification(user=S["devre"].owner, kind="teslim", title="Teşekkürler! Desteğin ulaştı",
                         body="Yeşil Watt desteğini teslim aldı.", url="/eslesmeler/"),
            Notification(user=captain, kind="sozlesme", title="Sözleşme iki tarafça onaylandı",
                         body="Arazi Kâşifi ↔ Selçuklu Hassas Makine", url="/eslesmeler/"),
            Notification(user=captain, kind="cagri",
                         title="Projene uygun bir destek çağrısı: İnsansız araç takımlarına motor sürücü kartı",
                         body="Anadolu Devre Elektronik", url=call.get_absolute_url()),
            Notification(user=captain, kind="takim", title="Elif Kaya takıma katıldı", url="/projeler/takimim/uyeler/"),
        ])

        # Demo hesapları aynı demo alan adını paylaştığı için puan denetimi hepsini incelemeye alır.
        # Gösterim amacıyla yalnızca bir süreci incelemede bırakıyoruz.
        PointEntry.objects.update(held=False, hold_reason="")
        PointEntry.objects.filter(request__sponsor=S["toprak"]).update(
            held=True, hold_reason="Takım ve destekçi hesapları aynı ağ adresinden giriş yapmış.")

        # Geçen ayın ödülleri
        start, end = month_bounds(last_month.year, last_month.month)
        period = Period("ay", f"{MONTHS_TR[last_month.month - 1]} {last_month.year}", start, end)
        issue_awards(period, Award.Kind.MONTH)
