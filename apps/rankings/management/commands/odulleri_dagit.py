"""
Aylık / yıllık ödülleri dağıtır. Zamanlayıcı (cron, systemd timer) ile çalıştırın:

    # Her ayın 1'inde, bir önceki ayın ödülleri
    python manage.py odulleri_dagit --ay 2026-10
    # Her yıl 1 Ocak'ta
    python manage.py odulleri_dagit --yil 2026
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.rankings.models import Award
from apps.rankings.services import Period, issue_awards, month_bounds, MONTHS_TR


class Command(BaseCommand):
    help = "Kanat sıralamasına göre Ayın Kanadı / Yılın Ankası ödüllerini verir."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--ay", help="YYYY-AA biçiminde ay, örn. 2026-10")
        group.add_argument("--yil", type=int, help="Yıl, örn. 2026")
        parser.add_argument("--ilk", type=int, default=3, help="Her ligde ödül alacak sıra sayısı")

    def handle(self, *args, **opts):
        if opts["ay"]:
            try:
                year, month = (int(x) for x in opts["ay"].split("-"))
                start, end = month_bounds(year, month)
            except (ValueError, IndexError) as exc:
                raise CommandError("Ay biçimi YYYY-AA olmalı.") from exc
            period = Period("ay", f"{MONTHS_TR[month - 1]} {year}", start, end)
            kind = Award.Kind.MONTH
        else:
            year = opts["yil"]
            period = Period("yil", str(year), date(year, 1, 1), date(year + 1, 1, 1))
            kind = Award.Kind.YEAR

        issued = issue_awards(period, kind, top=opts["ilk"])
        for award in issued:
            league = award.league or "genel"
            self.stdout.write(f"{award.get_kind_display()} {award.period} [{league}] "
                              f"#{award.rank} {award.sponsor} — {award.points} puan — kod {award.code}")
        self.stdout.write(self.style.SUCCESS(f"{len(issued)} ödül verildi ({period.label})."))
