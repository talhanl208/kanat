/*
 * Gök haritası: turkuaz yıldızlar takımları, altın yıldızlar destekçileri temsil eder.
 * Aralıklarla bir takım ile bir destekçi arasında "eşleşme" çizgisi çekilir.
 * prefers-reduced-motion açıksa tek bir durağan kare çizilir.
 */
(function () {
  "use strict";
  var tuval = document.querySelector("[data-gok]");
  if (!tuval || !tuval.getContext) return;
  var ctx = tuval.getContext("2d");
  var azHareket = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var W = 0, H = 0, yildizlar = [], toz = [], eslesmeler = [], fare = null, sonEslesme = 0, kare = null;

  var TURKUAZ = "20,179,173", ALTIN = "232,188,87", BEYAZ = "230,236,255";

  function rastgele(a, b) { return a + Math.random() * (b - a); }

  function kur() {
    var r = tuval.getBoundingClientRect();
    W = r.width; H = r.height;
    tuval.width = Math.round(W * dpr); tuval.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var adet = Math.round(Math.min(64, Math.max(22, (W * H) / 16000)));
    yildizlar = [];
    for (var i = 0; i < adet; i++) {
      var destekci = i % 3 === 0;
      yildizlar.push({
        x: rastgele(0, W), y: rastgele(0, H), vx: rastgele(-0.12, 0.12), vy: rastgele(-0.08, 0.08),
        r: destekci ? rastgele(1.8, 2.8) : rastgele(1.2, 2.2), renk: destekci ? ALTIN : TURKUAZ,
        destekci: destekci, faz: rastgele(0, Math.PI * 2)
      });
    }
    toz = [];
    for (var j = 0; j < Math.round(adet * 2.2); j++) {
      toz.push({ x: rastgele(0, W), y: rastgele(0, H), r: rastgele(0.3, 0.9), a: rastgele(0.15, 0.55) });
    }
  }

  function yeniEslesme(t) {
    var takimlar = yildizlar.filter(function (s) { return !s.destekci; });
    var destekciler = yildizlar.filter(function (s) { return s.destekci; });
    if (!takimlar.length || !destekciler.length) return;
    var a = takimlar[Math.floor(Math.random() * takimlar.length)];
    var enYakin = null, mesafe = Infinity;
    destekciler.forEach(function (d) {
      var m = Math.hypot(d.x - a.x, d.y - a.y);
      if (m < mesafe && m > 60) { mesafe = m; enYakin = d; }
    });
    if (enYakin) eslesmeler.push({ a: a, b: enYakin, bas: t, sure: 3800 });
  }

  function yildizCiz(s, parlak) {
    var g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 6);
    g.addColorStop(0, "rgba(" + s.renk + "," + (0.55 * parlak) + ")");
    g.addColorStop(1, "rgba(" + s.renk + ",0)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(s.x, s.y, s.r * 6, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(" + s.renk + "," + Math.min(1, 0.6 + 0.4 * parlak) + ")";
    if (s.destekci) {               // destekçi: sekiz köşeli Selçuklu yıldızı
      ctx.save(); ctx.translate(s.x, s.y); ctx.rotate(s.faz * 0.2);
      ctx.fillRect(-s.r, -s.r, s.r * 2, s.r * 2);
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-s.r, -s.r, s.r * 2, s.r * 2);
      ctx.restore();
    } else {
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
    }
  }

  function ciz(t) {
    ctx.clearRect(0, 0, W, H);
    toz.forEach(function (p) {
      ctx.fillStyle = "rgba(" + BEYAZ + "," + p.a + ")";
      ctx.fillRect(p.x, p.y, p.r, p.r);
    });

    // Yakın yıldızlar arasında soluk ağ
    for (var i = 0; i < yildizlar.length; i++) {
      for (var j = i + 1; j < yildizlar.length; j++) {
        var a = yildizlar[i], b = yildizlar[j];
        var m = Math.hypot(a.x - b.x, a.y - b.y);
        if (m < 120) {
          ctx.strokeStyle = "rgba(" + BEYAZ + "," + (0.07 * (1 - m / 120)) + ")";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      if (fare) {
        var mf = Math.hypot(yildizlar[i].x - fare.x, yildizlar[i].y - fare.y);
        if (mf < 160) {
          ctx.strokeStyle = "rgba(" + yildizlar[i].renk + "," + (0.35 * (1 - mf / 160)) + ")";
          ctx.beginPath(); ctx.moveTo(fare.x, fare.y); ctx.lineTo(yildizlar[i].x, yildizlar[i].y); ctx.stroke();
        }
      }
    }

    // Eşleşme çizgileri: çizilir, parlar, söner
    eslesmeler = eslesmeler.filter(function (e) { return t - e.bas < e.sure; });
    eslesmeler.forEach(function (e) {
      var ilerleme = (t - e.bas) / e.sure;
      var cizim = Math.min(1, ilerleme / 0.35);
      var solma = ilerleme > 0.7 ? 1 - (ilerleme - 0.7) / 0.3 : 1;
      var x = e.a.x + (e.b.x - e.a.x) * cizim, y = e.a.y + (e.b.y - e.a.y) * cizim;
      var g = ctx.createLinearGradient(e.a.x, e.a.y, e.b.x, e.b.y);
      g.addColorStop(0, "rgba(" + TURKUAZ + "," + 0.9 * solma + ")");
      g.addColorStop(1, "rgba(" + ALTIN + "," + 0.9 * solma + ")");
      ctx.strokeStyle = g; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.moveTo(e.a.x, e.a.y); ctx.lineTo(x, y); ctx.stroke();
      if (cizim < 1) {
        ctx.fillStyle = "rgba(255,255,255," + solma + ")";
        ctx.beginPath(); ctx.arc(x, y, 2.4, 0, Math.PI * 2); ctx.fill();
      } else {
        var halka = (ilerleme - 0.35) * 60;
        ctx.strokeStyle = "rgba(" + ALTIN + "," + 0.5 * solma + ")";
        ctx.beginPath(); ctx.arc(e.b.x, e.b.y, 4 + halka, 0, Math.PI * 2); ctx.stroke();
      }
    });

    var eslesenler = new Set();
    eslesmeler.forEach(function (e) { eslesenler.add(e.a); eslesenler.add(e.b); });
    yildizlar.forEach(function (s) {
      var parilti = 0.65 + 0.35 * Math.sin(t / 900 + s.faz);
      yildizCiz(s, eslesenler.has(s) ? 1.6 : parilti);
    });
  }

  function adim(t) {
    yildizlar.forEach(function (s) {
      s.x += s.vx; s.y += s.vy;
      if (s.x < -10) s.x = W + 10; if (s.x > W + 10) s.x = -10;
      if (s.y < -10) s.y = H + 10; if (s.y > H + 10) s.y = -10;
    });
    if (t - sonEslesme > 1700) { yeniEslesme(t); sonEslesme = t; }
    ciz(t);
    kare = window.requestAnimationFrame(adim);
  }

  kur();
  if (azHareket) { ciz(0); return; }
  kare = window.requestAnimationFrame(adim);

  var zaman;
  window.addEventListener("resize", function () { clearTimeout(zaman); zaman = setTimeout(kur, 150); });
  var kapsayici = tuval.parentElement;
  kapsayici.addEventListener("pointermove", function (e) {
    var r = tuval.getBoundingClientRect();
    fare = { x: e.clientX - r.left, y: e.clientY - r.top };
  });
  kapsayici.addEventListener("pointerleave", function () { fare = null; });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { window.cancelAnimationFrame(kare); }
    else { kare = window.requestAnimationFrame(adim); }
  });
})();
