from django import forms
from django.forms import inlineformset_factory

from apps.core.constants import CATEGORIES, COMPETITIONS, SUPPORT_KINDS
from apps.core.forms import LogoCleanMixin, StyledFormMixin

from .models import Need, Project, ProgressUpdate, Team


class TeamForm(LogoCleanMixin, StyledFormMixin, forms.ModelForm):
    logo_folder = "takimlar"
    minors_ack = forms.BooleanField(
        label="Takımda 18 yaşından küçük üye varsa bu hesabı danışman öğretmen / yetişkin sorumlu olarak "
        "yönettiğimi ve üyelerin kişisel verilerini (ad, fotoğraf, telefon) platforma girmeyeceğimi beyan ederim.",
        required=False,
    )

    class Meta:
        model = Team
        fields = [
            "kind", "name", "institution", "city", "member_count", "has_minor_members",
            "advisor_name", "founded_year", "about", "website", "logo",
        ]
        widgets = {
            "kind": forms.RadioSelect,
            "about": forms.Textarea(attrs={"rows": 5}),
            "logo": forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg,image/webp,image/gif"}),
        }

    def clean_member_count(self):
        value = self.cleaned_data["member_count"]
        if not 1 <= value <= 60:
            raise forms.ValidationError("Üye sayısı 1 ile 60 arasında olmalı.")
        return value

    def clean_founded_year(self):
        year = self.cleaned_data.get("founded_year")
        if year and not 1990 <= year <= 2100:
            raise forms.ValidationError("Geçerli bir yıl gir.")
        return year

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("has_minor_members") and not cleaned.get("minors_ack"):
            self.add_error("minors_ack", "Reşit olmayan üyeler için bu beyan zorunludur.")
        if cleaned.get("has_minor_members") and not cleaned.get("advisor_name"):
            self.add_error("advisor_name", "Reşit olmayan üye varsa danışman adı zorunludur.")
        return cleaned


class ProjectForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "title", "summary", "category", "competition", "competition_detail", "stage",
            "deadline", "description", "sponsor_benefits",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "sponsor_benefits": forms.Textarea(attrs={"rows": 3}),
            "deadline": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class NeedForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Need
        fields = ["kind", "title", "detail", "estimated_cost", "mentor_hours", "fulfilled"]

    def clean_estimated_cost(self):
        value = self.cleaned_data.get("estimated_cost")
        if value is not None and (value < 0 or value > 10_000_000):
            raise forms.ValidationError("Tutar 0 ile 10.000.000 ₺ arasında olmalı.")
        return value

    def clean_mentor_hours(self):
        value = self.cleaned_data.get("mentor_hours")
        if value is not None and value > 500:
            raise forms.ValidationError("En fazla 500 saat.")
        return value


NeedFormSet = inlineformset_factory(
    Project, Need, form=NeedForm, extra=1, can_delete=True, max_num=20, validate_max=True,
    min_num=1, validate_min=True,
)


class ProgressUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProgressUpdate
        fields = ["title", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class ProjectFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Ara", required=False, max_length=80)
    alan = forms.ChoiceField(label="Alan", required=False, choices=[("", "Tüm alanlar"), *CATEGORIES])
    yarisma = forms.ChoiceField(
        label="Yarışma", required=False, choices=[("", "Tüm yarışmalar"), *COMPETITIONS]
    )
    ihtiyac = forms.ChoiceField(
        label="İhtiyaç", required=False, choices=[("", "Tüm ihtiyaçlar"), *SUPPORT_KINDS]
    )
    sehir = forms.CharField(label="Şehir", required=False, max_length=20)


class DossierForm(forms.Form):
    dossier = forms.FileField(
        label="Sponsorluk dosyası (PDF, en fazla 5 MB)",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}),
        help_text="Dosyada reşit olmayan üyelerin fotoğrafı, telefonu ya da kimlik bilgisi olmasın.",
    )

    def clean_dossier(self):
        from apps.core.files import sanitize_pdf

        return sanitize_pdf(self.cleaned_data["dossier"])


class InviteForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(label="Davet edilecek kişinin e-postası", max_length=254)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class TransferCaptainForm(StyledFormMixin, forms.Form):
    member = forms.ModelChoiceField(label="Yeni kaptan", queryset=None)
    password = forms.CharField(label="Onay için parolan", strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, team=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["member"].queryset = team.memberships.select_related("user")
        self.fields["member"].label_from_instance = lambda m: f"{m.user.full_name} ({m.user.email})"

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Parola hatalı.")
        return password
