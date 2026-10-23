from django import forms

from apps.core.constants import SUPPORT_KINDS
from apps.core.forms import StyledFormMixin
from apps.projects.models import Need, Project

from .models import Agreement, MentorSession, Message, Report, SupportRequest


def _need_label(need):
    if need.estimated_cost:
        remaining = need.remaining_amount
        left = f"{int(remaining):,}".replace(",", ".")
        return f"{need.project.title}: {need.title} (kalan {left} ₺)"
    return f"{need.project.title}: {need.title}"


class _RequestBase(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ["kind", "need", "amount", "mentor_hours", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 5})}

    def _setup_need(self, queryset):
        field = self.fields["need"]
        field.queryset = queryset.select_related("project").prefetch_related("contributions")
        field.required = False
        field.empty_label = "Belirli bir ihtiyaç değil / genel destek"
        field.label_from_instance = _need_label

    def _check_need(self, cleaned, project=None):
        need = cleaned.get("need")
        if need is None:
            return
        if project is not None and need.project_id != project.pk:
            self.add_error("need", "Bu ihtiyaç seçtiğin projeye ait değil.")
        elif cleaned.get("kind") and need.kind != cleaned["kind"]:
            self.add_error("need", "Seçtiğin ihtiyacın türü, destek türüyle aynı olmalı.")

    def clean_amount(self):
        value = self.cleaned_data.get("amount")
        if value is not None and (value < 0 or value > 50_000_000):
            raise forms.ValidationError("Geçerli bir tutar gir.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == "mentorluk" and not cleaned.get("mentor_hours"):
            self.add_error("mentor_hours", "Mentörlük için saat belirt.")
        return cleaned


class SponsorOfferForm(_RequestBase):
    """Destekçi bir projeye destek teklif eder."""

    def __init__(self, *args, sponsor=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        offered = set(sponsor.support_types or [])
        wanted = project.need_kinds
        kinds = [(k, v) for k, v in SUPPORT_KINDS if k in offered and (k in wanted or not wanted)]
        self.fields["kind"].choices = kinds or [(k, v) for k, v in SUPPORT_KINDS if k in offered]
        self._setup_need(Need.objects.filter(project=project, fulfilled=False))
        self.fields["note"].label = "Takıma mesajın"
        self.fields["amount"].label = "Teklif ettiğin desteğin tahmini değeri (₺)"

    def clean(self):
        cleaned = super().clean()
        self._check_need(cleaned, self.project)
        return cleaned


class TeamAskForm(_RequestBase):
    """Takım bir destekçiden destek ister; yalnızca KENDİ aktif projelerini seçebilir."""

    project = forms.ModelChoiceField(label="Hangi projen için?", queryset=Project.objects.none())

    class Meta(_RequestBase.Meta):
        fields = ["project", "kind", "need", "amount", "mentor_hours", "note"]

    def __init__(self, *args, team=None, sponsor=None, **kwargs):
        super().__init__(*args, **kwargs)
        active = Project.objects.public().filter(team=team)
        self.fields["project"].queryset = active
        self.fields["project"].widget.attrs["class"] = "input"
        offered = set(sponsor.support_types or [])
        self.fields["kind"].choices = [(k, v) for k, v in SUPPORT_KINDS if k in offered]
        self._setup_need(Need.objects.filter(project__in=active, fulfilled=False))
        self.fields["note"].label = "Destekçiye mesajın"
        self.fields["amount"].label = "İhtiyacın tahmini değeri (₺)"

    def clean(self):
        cleaned = super().clean()
        self._check_need(cleaned, cleaned.get("project"))
        return cleaned


class CallApplyForm(StyledFormMixin, forms.ModelForm):
    """Takım bir destek çağrısına başvurur; tür ve tutar çağrıdan gelir."""

    project = forms.ModelChoiceField(label="Hangi projenle başvuruyorsun?", queryset=Project.objects.none())

    class Meta:
        model = SupportRequest
        fields = ["project", "need", "note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 5})}
        labels = {"note": "Neden sizi seçmeliler?"}

    def __init__(self, *args, team=None, call=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.call = call
        projects = Project.objects.public().filter(team=team)
        if call.categories:
            projects = projects.filter(category__in=call.categories)
        self.fields["project"].queryset = projects
        self.fields["project"].widget.attrs["class"] = "input"
        need = self.fields["need"]
        need.queryset = Need.objects.filter(project__in=projects, kind=call.kind, fulfilled=False) \
            .select_related("project").prefetch_related("contributions")
        need.required = False
        need.empty_label = "Belirli bir ihtiyaç değil"
        need.label_from_instance = _need_label

    def clean(self):
        cleaned = super().clean()
        need, project = cleaned.get("need"), cleaned.get("project")
        if need is not None and project is not None and need.project_id != project.pk:
            self.add_error("need", "Bu ihtiyaç seçtiğin projeye ait değil.")
        return cleaned


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "class": "input",
                                                 "placeholder": "Mesajını yaz…", "maxlength": 2000})}
        labels = {"body": "Mesaj"}

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Boş mesaj gönderilemez.")
        return body


class AgreementForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Agreement
        fields = [
            "support_summary", "team_obligations", "sponsor_obligations", "payment_channel",
            "start_date", "end_date",
        ]
        widgets = {
            "support_summary": forms.Textarea(attrs={"rows": 3}),
            "team_obligations": forms.Textarea(attrs={"rows": 4}),
            "sponsor_obligations": forms.Textarea(attrs={"rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "Bitiş tarihi başlangıçtan önce olamaz.")
        return cleaned


class CompleteForm(StyledFormMixin, forms.ModelForm):
    received = forms.BooleanField(
        label="Desteğin bize ulaştığını onaylıyorum. (Bu onay destekçiye Kanat puanı kazandırır.)",
        required=True,
    )
    rating = forms.TypedChoiceField(
        label="Süreçten ne kadar memnun kaldınız?", coerce=int,
        choices=[(5, "5 — Harika"), (4, "4 — İyi"), (3, "3 — Orta"), (2, "2 — Zayıf"), (1, "1 — Kötü")],
        widget=forms.RadioSelect,
    )

    fulfilled_needs = forms.ModelMultipleChoiceField(
        label="Bu destekle karşılanan ihtiyaçlar", queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = SupportRequest
        fields = ["delivered_value", "rating", "thanks_note", "thanks_public"]
        widgets = {"thanks_note": forms.Textarea(attrs={"rows": 3, "maxlength": 400})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Yalnızca bu projenin açık ihtiyaçları seçilebilir.
        self.fields["fulfilled_needs"].queryset = self.instance.project.needs.filter(fulfilled=False)

    def clean_delivered_value(self):
        value = self.cleaned_data.get("delivered_value")
        if value is not None and (value < 0 or value > 50_000_000):
            raise forms.ValidationError("Geçerli bir tutar gir.")
        return value


class MentorSessionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MentorSession
        fields = ["date", "hours", "topic"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class ReportForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "detail"]
