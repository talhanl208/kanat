"""
Gençlere sözler. Kaynağı kesin olan sözler kullanıldı; platformun kendi sözleri imzasızdır.
"""
import random

QUOTES = [
    {"text": "İstikbal göklerdedir.", "author": "Mustafa Kemal Atatürk"},
    {"text": "Hayatta en hakiki mürşit ilimdir.", "author": "Mustafa Kemal Atatürk"},
    {"text": "Bütün ümidim gençliktedir.", "author": "Mustafa Kemal Atatürk"},
    {
        "text": "Ey Türk gençliği! Birinci vazifen, Türk istiklâlini, Türk Cumhuriyetini, "
        "ilelebet muhafaza ve müdafaa etmektir.",
        "author": "Mustafa Kemal Atatürk, Gençliğe Hitabe",
    },
    {"text": "Yurtta sulh, cihanda sulh.", "author": "Mustafa Kemal Atatürk"},
    {"text": "Bir lehimin tuttuğu yerde bir hayal de tutunur.", "author": ""},
    {"text": "Atölyede geçen her gece, yarının bir sabahıdır.", "author": ""},
    {"text": "Bugün çizdiğin devre, yarın bir ülkenin yönünü çizer.", "author": ""},
    {"text": "Kanat bulamayan fikir yoktur; yalnızca henüz tanışmamış insanlar vardır.", "author": ""},
]


def random_quote():
    return random.choice(QUOTES)  # noqa: S311 - kriptografik değil, süs amaçlı
