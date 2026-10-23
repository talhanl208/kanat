"""
Otomatik doğrulama kuralları.

Takım:     kaptanın DOĞRULANMIŞ e-postası .edu.tr, .k12.tr ya da meb.gov.tr alan adındaysa.
Destekçi:  sahibinin DOĞRULANMIŞ e-postası ücretsiz bir sağlayıcıdan değilse ve alan adı,
           profildeki web sitesinin alan adıyla eşleşiyorsa (ör. ali@firma.com.tr ↔ https://firma.com.tr).
Diğer durumlarda kullanıcı doğrulama başvurusu yapar, yönetici inceler.
Otomatik doğrulama koşulu ortadan kalkarsa (e-posta/site değişirse) rozet düşer;
yönetici doğrulaması ise korunur.
"""
from __future__ import annotations

from urllib.parse import urlparse

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.tr", "outlook.com", "outlook.com.tr",
    "live.com", "msn.com", "yahoo.com", "yahoo.com.tr", "ymail.com", "yandex.com", "yandex.com.tr",
    "yandex.ru", "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "pm.me",
    "aol.com", "gmx.com", "gmx.net", "mail.com", "mail.ru", "zoho.com", "tutanota.com", "windowslive.com",
}
# Kayıt dışı bırakılan "genel" ikinci seviye alan adları (kimse bunların sahibi değildir)
PUBLIC_SUFFIXES = {
    "com.tr", "net.tr", "org.tr", "gen.tr", "biz.tr", "info.tr", "web.tr", "tv.tr", "av.tr", "dr.tr",
    "bel.tr", "pol.tr", "tsk.tr", "k12.tr", "edu.tr", "gov.tr", "name.tr", "tel.tr", "bbs.tr",
    "co.uk", "org.uk", "com", "net", "org", "io", "tr", "app", "dev", "co",
}
EDU_SUFFIXES = (".edu.tr", ".k12.tr")
EDU_EXACT = {"meb.gov.tr"}


def email_domain(email: str) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower()


def website_host(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_edu_domain(domain: str) -> bool:
    return domain in EDU_EXACT or domain.endswith(EDU_SUFFIXES) or domain.endswith(".meb.gov.tr")


def domains_match(mail_domain: str, host: str) -> bool:
    if not mail_domain or not host or host in PUBLIC_SUFFIXES or mail_domain in FREE_EMAIL_DOMAINS:
        return False
    if "." not in host:
        return False
    return mail_domain == host or mail_domain.endswith("." + host)


def auto_verify_team(team) -> bool:
    owner = team.owner
    ok = owner.email_verified and is_edu_domain(email_domain(owner.email))
    changed = False
    if ok and not team.verified:
        team.verified, team.verification_method = True, "edu"
        changed = True
    elif not ok and team.verified and team.verification_method == "edu":
        team.verified, team.verification_method = False, ""
        changed = True
    if changed:
        type(team).objects.filter(pk=team.pk).update(
            verified=team.verified, verification_method=team.verification_method
        )
    return team.verified


def auto_verify_sponsor(sponsor) -> bool:
    owner = sponsor.owner
    ok = owner.email_verified and domains_match(email_domain(owner.email), website_host(sponsor.website))
    changed = False
    if ok and not sponsor.verified:
        sponsor.verified, sponsor.verification_method = True, "alan_adi"
        changed = True
    elif not ok and sponsor.verified and sponsor.verification_method == "alan_adi":
        sponsor.verified, sponsor.verification_method = False, ""
        changed = True
    if changed:
        type(sponsor).objects.filter(pk=sponsor.pk).update(
            verified=sponsor.verified, verification_method=sponsor.verification_method
        )
    return sponsor.verified


def auto_verify_for_user(user) -> None:
    team = user.owned_team
    if team is not None:
        auto_verify_team(team)
    sponsor = user.sponsor_or_none
    if sponsor is not None:
        auto_verify_sponsor(sponsor)
