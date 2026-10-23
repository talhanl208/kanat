/* Kanat — arayüz davranışları. Satır içi betik yoktur; CSP ile uyumludur. */
(function () {
  "use strict";

  var azHareket = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function guvenliOku(anahtar) {
    try { return window.localStorage.getItem(anahtar); } catch (e) { return null; }
  }
  function guvenliYaz(anahtar, deger) {
    try { window.localStorage.setItem(anahtar, deger); } catch (e) { /* özel pencere vb. */ }
  }

  /* ---- Tema ------------------------------------------------------------- */
  var temaDugme = document.querySelector("[data-tema-degistir]");
  if (temaDugme) {
    temaDugme.addEventListener("click", function () {
      var kok = document.documentElement;
      var simdiki = kok.getAttribute("data-theme") ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var yeni = simdiki === "dark" ? "light" : "dark";
      var uygulandi = false;
      var degistir = function () {
        if (uygulandi) return;
        uygulandi = true;
        kok.setAttribute("data-theme", yeni);
      };
      if (document.startViewTransition && !azHareket) {
        document.startViewTransition(degistir);
        setTimeout(degistir, 400); // tarayıcı kareleri kısıtlıyorsa geçiş beklemesin
      } else { degistir(); }
      guvenliYaz("kanat-tema", yeni);
      temaDugme.setAttribute("aria-pressed", String(yeni === "dark"));
    });
  }

  /* ---- Bildirimler -------------------------------------------------------- */
  document.querySelectorAll(".bildirim").forEach(function (el, i) {
    var kapat = function () {
      el.classList.add("kapaniyor");
      setTimeout(function () { el.remove(); }, 300);
    };
    var dugme = el.querySelector("button");
    if (dugme) dugme.addEventListener("click", kapat);
    if (!el.classList.contains("error")) setTimeout(kapat, 6500 + i * 600);
  });

  /* ---- Uyum halkaları ve ilerleme çubukları -------------------------------- */
  function sayiyaSinirla(deger) {
    var n = parseInt(deger, 10);
    if (isNaN(n)) return 0;
    return Math.max(0, Math.min(100, n));
  }
  function canlandir(el) {
    if (el.hasAttribute("data-uyum")) {
      el.style.setProperty("--uyum", sayiyaSinirla(el.getAttribute("data-uyum")));
    }
    if (el.hasAttribute("data-yuzde")) {
      el.style.width = sayiyaSinirla(el.getAttribute("data-yuzde")) + "%";
    }
  }
  var hedefler = document.querySelectorAll("[data-uyum], [data-yuzde], .adimlar");
  if ("IntersectionObserver" in window && !azHareket) {
    var gozcu = new IntersectionObserver(function (girdiler) {
      girdiler.forEach(function (g) {
        if (!g.isIntersecting) return;
        if (g.target.classList.contains("adimlar")) g.target.classList.add("gorundu");
        else canlandir(g.target);
        gozcu.unobserve(g.target);
      });
    }, { threshold: 0.25 });
    hedefler.forEach(function (el) { gozcu.observe(el); });
  } else {
    hedefler.forEach(function (el) {
      if (el.classList.contains("adimlar")) el.classList.add("gorundu"); else canlandir(el);
    });
  }

  // Yazdırırken henüz ekrana girmemiş çubuklar da dolu görünsün
  window.addEventListener("beforeprint", function () { hedefler.forEach(canlandir); });

  /* ---- Gençlere sözler: döner söz bandı ----------------------------------- */
  var sozKutu = document.querySelector("[data-sozler]");
  if (sozKutu) {
    var veri = [];
    try { veri = JSON.parse(document.getElementById("soz-verisi").textContent); } catch (e) { veri = []; }
    var metin = sozKutu.querySelector("blockquote");
    var kaynak = sozKutu.querySelector("figcaption");
    var noktalar = document.querySelector(".soz-noktalar");
    var sira = 0, zamanlayici = null;

    function goster(i) {
      sira = (i + veri.length) % veri.length;
      sozKutu.classList.add("degisiyor");
      setTimeout(function () {
        metin.textContent = "“" + veri[sira].text + "”";
        kaynak.textContent = veri[sira].author ? "— " + veri[sira].author : "— Kanat";
        sozKutu.classList.remove("degisiyor");
        if (noktalar) {
          noktalar.querySelectorAll("button").forEach(function (b, j) {
            b.setAttribute("aria-current", String(j === sira));
          });
        }
      }, azHareket ? 0 : 450);
    }
    function baslat() {
      if (azHareket || veri.length < 2) return;
      clearInterval(zamanlayici);
      zamanlayici = setInterval(function () { goster(sira + 1); }, 7000);
    }
    if (noktalar && veri.length > 1) {
      veri.forEach(function (_, j) {
        var b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-label", (j + 1) + ". söz");
        b.setAttribute("aria-current", String(j === 0));
        b.addEventListener("click", function () { goster(j); baslat(); });
        noktalar.appendChild(b);
      });
    }
    sozKutu.addEventListener("mouseenter", function () { clearInterval(zamanlayici); });
    sozKutu.addEventListener("mouseleave", baslat);
    baslat();
  }

  /* ---- Çerez bilgilendirmesi (yalnızca zorunlu çerezler) -------------------- */
  var cerez = document.querySelector("[data-cerez]");
  if (cerez && guvenliOku("kanat-cerez-bilgi") !== "1") {
    cerez.hidden = false;
    cerez.querySelector("button").addEventListener("click", function () {
      guvenliYaz("kanat-cerez-bilgi", "1");
      cerez.hidden = true;
    });
  }

  /* ---- Geri alınamaz işlemler için onay ----------------------------------- */
  document.querySelectorAll("form[data-onay]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-onay"))) e.preventDefault();
    });
  });

  /* ---- Formların çift gönderimini engelle --------------------------------- */
  document.querySelectorAll("form[method='post'], form[method='POST']").forEach(function (form) {
    form.addEventListener("submit", function () {
      var dugme = form.querySelector("button[type='submit'], button:not([type])");
      if (dugme && !form.hasAttribute("data-onay")) {
        setTimeout(function () { dugme.disabled = true; }, 0);
      }
    });
  });

  /* ---- Yazdır / PDF olarak kaydet ----------------------------------------- */
  document.querySelectorAll("[data-yazdir]").forEach(function (b) {
    b.addEventListener("click", function () { window.print(); });
  });

  /* ---- Panoya kopyala ------------------------------------------------------ */
  document.querySelectorAll("[data-kopyala]").forEach(function (b) {
    b.addEventListener("click", function () {
      var hedef = document.getElementById(b.getAttribute("data-kopyala"));
      if (!hedef || !navigator.clipboard) return;
      navigator.clipboard.writeText(hedef.textContent.replace(/\s+/g, " ").trim()).then(function () {
        var eski = b.textContent;
        b.textContent = "Kopyalandı";
        setTimeout(function () { b.textContent = eski; }, 1800);
      });
    });
  });

  /* ---- İhtiyaç satırı ekleme (Django formset) ------------------------------- */
  var ekle = document.querySelector("[data-satir-ekle]");
  if (ekle) {
    ekle.addEventListener("click", function () {
      var onEk = ekle.getAttribute("data-satir-ekle");
      var toplam = document.getElementById("id_" + onEk + "-TOTAL_FORMS");
      var sablon = document.getElementById("bos-satir");
      var hedef = document.querySelector("[data-satirlar]");
      var sayi = parseInt(toplam.value, 10);
      var maks = parseInt(document.getElementById("id_" + onEk + "-MAX_NUM_FORMS").value, 10);
      if (sayi >= maks) return;
      var parca = sablon.content.cloneNode(true);
      parca.querySelectorAll("[name], [id], [for]").forEach(function (el) {
        ["name", "id", "for"].forEach(function (oz) {
          if (el.hasAttribute(oz)) el.setAttribute(oz, el.getAttribute(oz).replace(/__prefix__/g, String(sayi)));
        });
      });
      hedef.appendChild(parca);
      toplam.value = String(sayi + 1);
      var ilk = hedef.lastElementChild && hedef.lastElementChild.querySelector("select, input");
      if (ilk) ilk.focus();
    });
  }
})();
