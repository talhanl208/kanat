from django import forms
from django.contrib.auth import password_validation
from django.urls import reverse
from django.utils.html import format_html

from .models import User


class RegisterForm(forms.Form):
    role = forms.ChoiceField(
        label="Platforma nasıl katılıyorsun?",
        choices=[
            (User.Role.TEAM, "Takımım ya da projem için destek arıyorum"),
            (User.Role.SPONSOR, "Firma, kurum veya mentör olarak destek vermek istiyorum"),
        ],
        widget=forms.RadioSelect,
    )
    full_name = forms.CharField(label="Ad soyad", max_length=120)
    email = forms.EmailField(label="E-posta", max_length=254)
    password1 = forms.CharField(
        label="Parola", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="En az 10 karakter; yaygın ya da yalnızca rakamdan oluşan parolalar kabul edilmez.",
    )
    password2 = forms.CharField(
        label="Parola (tekrar)", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    # Zorunlu beyanlar — her biri ayrı kutucuk, önceden işaretli değil.
    adult = forms.BooleanField(
        label="18 yaşını doldurdum. (Takımında reşit olmayan üyeler varsa hesabı danışman öğretmen açmalıdır.)",
        required=True,
    )
    privacy_notice = forms.BooleanField(required=True)
    terms = forms.BooleanField(required=True)
    # İsteğe bağlı açık rıza — hizmet şartı DEĞİLDİR (KVKK: açık rıza hizmete bağlanamaz).
    marketing = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        link = '<a href="{}" target="_blank" rel="noopener">{}</a>'
        self.fields["privacy_notice"].label = format_html(
            link + " okudum.", reverse("core:legal", args=["aydinlatma"]), "KVKK aydınlatma metnini"
        )
        self.fields["terms"].label = format_html(
            link + " kabul ediyorum.", reverse("core:legal", args=["kullanim"]), "Kullanım koşullarını"
        )
        self.fields["marketing"].label = format_html(
            "İsteğe bağlı: bülten ve duyurular için " + link + " kapsamında e-posta almak istiyorum.",
            reverse("core:legal", args=["acik-riza"]), "açık rıza metni",
        )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parolalar eşleşmiyor.")
        if p1:
            probe = User(email=cleaned.get("email", ""), full_name=cleaned.get("full_name", ""))
            try:
                password_validation.validate_password(p1, probe)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(label="E-posta", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(
        label="Parola", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["full_name"]


class MarketingConsentForm(forms.Form):
    marketing = forms.BooleanField(
        label="Bülten ve duyurular için e-posta almak istiyorum (açık rıza).", required=False
    )


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label="Parolan", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )
    confirm = forms.CharField(
        label='Onaylamak için büyük harflerle "SİL" yaz', max_length=5,
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Parola hatalı.")
        return password

    def clean_confirm(self):
        value = self.cleaned_data["confirm"].strip()
        if value not in {"SİL", "SIL"}:
            raise forms.ValidationError('Lütfen "SİL" yaz.')
        return value


class PasswordConfirmForm(forms.Form):
    """Sözleşme onayı gibi kritik işlemlerde parolayı yeniden sorar."""

    password = forms.CharField(
        label="Onay için parolan", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Parola hatalı.")
        return password


class NotificationPrefForm(forms.Form):
    email_notifications = forms.BooleanField(
        label="Yeni talep, mesaj, sözleşme ve teslim bildirimlerini e-postayla da al", required=False
    )


class TwoFactorCodeForm(forms.Form):
    code = forms.CharField(
        label="Doğrulama kodu", max_length=20, strip=True,
        widget=forms.TextInput(attrs={
            "autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True,
            "placeholder": "123456", "class": "input",
        }),
        help_text="Doğrulama uygulamandaki 6 haneli kod ya da kurtarma kodlarından biri.",
    )


class TwoFactorEnableForm(forms.Form):
    code = forms.CharField(
        label="Uygulamadaki 6 haneli kod", max_length=8, strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric",
                                      "class": "input", "placeholder": "123456"}),
    )


class TwoFactorDisableForm(PasswordConfirmForm):
    code = forms.CharField(
        label="Doğrulama kodu ya da kurtarma kodu", max_length=20, strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "class": "input"}),
    )


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(label="Yeni e-posta adresin", max_length=254)
    password = forms.CharField(
        label="Parolan", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_new_email(self):
        email = self.cleaned_data["new_email"].strip().lower()
        if email == self.user.email:
            raise forms.ValidationError("Bu zaten şu anki adresin.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Parola hatalı.")
        return password
