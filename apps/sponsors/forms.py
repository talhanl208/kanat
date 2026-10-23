from django import forms

from apps.core.constants import CATEGORIES, COMPETITIONS, LEAGUES, SUPPORT_KINDS
from apps.core.forms import LogoCleanMixin, StyledFormMixin

from .models import Sponsor, SponsorCall


class SponsorForm(LogoCleanMixin, StyledFormMixin, forms.ModelForm):
    logo_folder = "destekciler"

    support_types = forms.MultipleChoiceField(
        label="Sunabildiğin destek türleri", choices=SUPPORT_KINDS,
        widget=forms.CheckboxSelectMultiple,
    )
    interest_categories = forms.MultipleChoiceField(
        label="İlgilendiğin alanlar (boş bırakırsan tüm alanlar)", choices=CATEGORIES,
        widget=forms.CheckboxSelectMultiple, required=False,
    )
    competitions = forms.MultipleChoiceField(
        label="Desteklediğin yarışma / programlar (boş bırakırsan hepsi)", choices=COMPETITIONS,
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta:
        model = Sponsor
        fields = [
            "kind", "name", "league", "sector", "city", "serves_all_turkey", "website", "about",
            "support_types", "interest_categories", "competitions", "budget_min", "budget_max",
            "mentor_hours_per_month", "max_active_projects", "offerings", "accepting_requests", "logo",
        ]
        widgets = {
            "kind": forms.RadioSelect,
            "league": forms.RadioSelect(choices=LEAGUES),
            "about": forms.Textarea(attrs={"rows": 5}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"}),
        }

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("budget_min"), cleaned.get("budget_max")
        if low is not None and high is not None and low > high:
            self.add_error("budget_max", "En fazla bütçe, en az bütçeden küçük olamaz.")
        for name in ("budget_min", "budget_max"):
            value = cleaned.get(name)
            if value is not None and value > 50_000_000:
                self.add_error(name, "Bu tutar çok yüksek görünüyor.")
        types = cleaned.get("support_types") or []
        if "mentorluk" in types and not cleaned.get("mentor_hours_per_month"):
            self.add_error("mentor_hours_per_month", "Mentörlük sunuyorsan aylık kapasiteni yaz.")
        offerings = cleaned.get("offerings", "")
        if offerings and len([k for k in offerings.split(",") if k.strip()]) > 25:
            self.add_error("offerings", "En fazla 25 anahtar kelime.")
        return cleaned


class SponsorFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Ara", required=False, max_length=80)
    destek = forms.ChoiceField(
        label="Destek türü", required=False, choices=[("", "Tüm destek türleri"), *SUPPORT_KINDS]
    )
    alan = forms.ChoiceField(label="Alan", required=False, choices=[("", "Tüm alanlar"), *CATEGORIES])
    lig = forms.ChoiceField(label="Ölçek", required=False, choices=[("", "Tüm ölçekler"), *LEAGUES])


class SponsorCallForm(StyledFormMixin, forms.ModelForm):
    categories = forms.MultipleChoiceField(
        label="Hangi alanlardan takımlar başvurabilir? (boş bırakırsan tüm alanlar)", choices=CATEGORIES,
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta:
        model = SponsorCall
        fields = ["title", "kind", "description", "categories", "amount_per_team", "mentor_hours",
                  "slots", "deadline"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "deadline": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, sponsor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if sponsor is not None:
            offered = set(sponsor.support_types or [])
            self.fields["kind"].choices = [(k, v) for k, v in SUPPORT_KINDS if k in offered] or SUPPORT_KINDS

    def clean_slots(self):
        slots = self.cleaned_data["slots"]
        if not 1 <= slots <= 50:
            raise forms.ValidationError("1 ile 50 arasında bir sayı gir.")
        return slots

    def clean_deadline(self):
        from django.utils import timezone

        deadline = self.cleaned_data["deadline"]
        today = timezone.localdate()
        if deadline < today:
            raise forms.ValidationError("Son başvuru tarihi geçmişte olamaz.")
        if (deadline - today).days > 365:
            raise forms.ValidationError("Çağrı en fazla bir yıl açık kalabilir.")
        return deadline

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == "mentorluk" and not cleaned.get("mentor_hours"):
            self.add_error("mentor_hours", "Mentörlük çağrısı için takım başına saat yaz.")
        amount = cleaned.get("amount_per_team")
        if amount is not None and (amount < 0 or amount > 10_000_000):
            self.add_error("amount_per_team", "Geçerli bir tutar gir.")
        return cleaned


class CallFilterForm(StyledFormMixin, forms.Form):
    destek = forms.ChoiceField(
        label="Destek türü", required=False, choices=[("", "Tüm destek türleri"), *SUPPORT_KINDS]
    )
    alan = forms.ChoiceField(label="Alan", required=False, choices=[("", "Tüm alanlar"), *CATEGORIES])
