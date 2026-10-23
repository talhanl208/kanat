from datetime import timedelta

from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.legal import version_of

from .models import Agreement

DEFAULT_TEAM_OBLIGATIONS = (
    "Desteği yalnızca bu projede kullanmak. Destekçinin adını/logosunu proje sayfasında belirtilen "
    "görünürlük kapsamında ve yalnızca sözleşme süresince kullanmak. Sözleşme bitiminde desteğin nasıl "
    "kullanıldığını proje günlüğünde kısaca paylaşmak."
)
DEFAULT_SPONSOR_OBLIGATIONS = (
    "Desteği kararlaştırılan kapsam ve tarihte teslim etmek. Projenin fikri mülkiyeti üzerinde hak "
    "iddia etmemek. Takım üyelerinin kişisel verilerini talep etmemek; iletişimi platform veya takım "
    "sorumlusu üzerinden yürütmek."
)
DEFAULT_PAYMENT_CHANNEL = (
    "Nakdi destekler okulun / üniversitenin veya takımın bağlı olduğu tüzel kişinin resmi hesabına; "
    "ürün ve hizmet destekleri doğrudan teslim."
)


def initial_for(support_request) -> dict:
    today = timezone.localdate()
    kind = support_request.get_kind_display().lower()
    value = f" (tahmini değeri {int(support_request.amount):,} ₺)".replace(",", ".") if support_request.amount else ""
    hours = f", {support_request.mentor_hours} saat" if support_request.mentor_hours else ""
    return {
        "support_summary": f"{support_request.sponsor.name}, “{support_request.project.title}” projesine "
                           f"{kind}{hours}{value} sağlayacaktır.",
        "team_obligations": DEFAULT_TEAM_OBLIGATIONS,
        "sponsor_obligations": DEFAULT_SPONSOR_OBLIGATIONS,
        "payment_channel": DEFAULT_PAYMENT_CHANNEL,
        "start_date": today,
        "end_date": support_request.project.deadline or (today + timedelta(days=180)),
    }


def render_body(agreement: Agreement, support_request) -> str:
    project = support_request.project
    return render_to_string("matching/agreement_body.txt", {
        "a": agreement,
        "team": project.team,
        "project": project,
        "sponsor": support_request.sponsor,
        "req": support_request,
        "version": version_of("sponsorluk-sozlesmesi"),
    }).strip()


def save_agreement(form, support_request) -> Agreement:
    agreement = form.save(commit=False)
    project = support_request.project
    agreement.request = support_request
    agreement.team_name = project.team.name
    agreement.sponsor_name = support_request.sponsor.name
    agreement.project_title = project.title
    agreement.template_version = version_of("sponsorluk-sozlesmesi")
    agreement.seal(render_body(agreement, support_request))
    agreement.save()
    return agreement
