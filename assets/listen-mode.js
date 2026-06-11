/* SINAPSE · listen-mode.js — modo escucha (v1 · 2026-06-10)
   Inyecta una barra de reproducción en cada número.
   · Si <body data-audio="ruta/al/n00N-xx.mp3"> existe y el archivo responde,
     usa <audio> nativo (MP3 generado con scripts/make-podcast.py + TTS local).
   · Si no, lee con speechSynthesis (Web Speech API): trocea párrafos en
     frases <190 chars (límite de Chrome), resalta el bloque activo,
     velocidad y voz persistentes en localStorage("sinapse-audio").
   Sin dependencias. No requiere markup: se monta sobre section.sec. */
(function () {
  "use strict";
  if (window.__sinapseListen) return;
  window.__sinapseListen = true;

  var LANG = (document.documentElement.lang || "es").slice(0, 2);
  var T = LANG === "en"
    ? { play: "▶ Listen", pause: "⏸ Pause", ready: "ready", end: "end",
        section: "section", noTTS: "TTS not supported", close: "hide player" }
    : { play: "▶ Escuchar", pause: "⏸ Pausa", ready: "listo", end: "fin",
        section: "sección", noTTS: "sin soporte TTS", close: "ocultar reproductor" };

  var EXCLUDE = ".tags,.chart,.atlas,.atlas-map,.atlas-map-v2,.bars,.refs," +
                ".toc,.reader-prefs,figure,svg,.sec-num,.pulso-num,.ti-cat,.byline";

  function readableBlocks() {
    var nodes = document.querySelectorAll(
      "section.sec h2, section.sec h3, section.sec p, section.sec dt, section.sec dd, section.sec li");
    var out = [];
    nodes.forEach(function (el) {
      if (el.closest(EXCLUDE)) return;
      var txt = el.textContent.replace(/\s+/g, " ").trim();
      if (txt.length > 2) out.push({ el: el, txt: txt });
    });
    return out;
  }

  function chunk(s, max) {
    if (s.length <= max) return [s];
    var i = s.lastIndexOf(",", max);
    if (i < max * 0.4) i = s.lastIndexOf(" ", max);
    if (i <= 0) i = max;
    var head = s.slice(0, i + 1).trim(), rest = s.slice(i + 1).trim();
    return [head].concat(chunk(rest, max));
  }

  function sentences(txt) {
    var raw = txt.match(/[^.!?…]+[.!?…]+\s*|[^.!?…]+$/g) || [txt];
    var out = [];
    raw.forEach(function (s) { chunk(s.trim(), 190).forEach(function (c) { out.push(c); }); });
    return out;
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }

  function buildBar(inner) {
    var bar = el("aside", { class: "listen-bar", role: "region",
                            "aria-label": LANG === "en" ? "Audio player" : "Reproductor de audio" });
    inner.forEach(function (n) { bar.appendChild(n); });
    var close = el("button", { class: "lb-close", title: T.close, "aria-label": T.close, text: "✕" });
    close.addEventListener("click", function () {
      bar.remove();
      try { sessionStorage.setItem("sinapse-audio-hidden", "1"); } catch (e) {}
    });
    bar.appendChild(close);
    document.body.appendChild(bar);
    return bar;
  }

  function mountAudio(src) {
    var a = el("audio", { controls: "", preload: "none", src: src });
    buildBar([a]);
  }

  function mountTTS() {
    var synth = window.speechSynthesis;
    if (!synth) return;
    var blocks = readableBlocks();
    if (!blocks.length) return;

    var queue = blocks.map(function (b) { return { el: b.el, parts: sentences(b.txt) }; });
    var total = queue.reduce(function (n, q) { return n + q.parts.length; }, 0);

    var prefs = {};
    try { prefs = JSON.parse(localStorage.getItem("sinapse-audio") || "{}"); } catch (e) {}

    var btn = el("button", { class: "lb-primary", text: T.play });
    var prev = el("button", { title: "⏮", text: "⏮" });
    var next = el("button", { title: "⏭", text: "⏭" });
    var rate = el("select", {});
    [0.85, 1, 1.15, 1.3, 1.5].forEach(function (r) {
      var o = el("option", { value: r, text: r + "×" });
      if (r === (prefs.rate || 1)) o.selected = true;
      rate.appendChild(o);
    });
    var voice = el("select", {});
    var progWrap = el("span", { class: "lb-progress" }, [el("i", {})]);
    var status = el("span", { class: "lb-status", text: T.ready });
    buildBar([btn, prev, next, rate, voice, progWrap, status]);
    var prog = progWrap.firstChild;

    function loadVoices() {
      voice.innerHTML = "";
      var vs = synth.getVoices().filter(function (v) {
        return v.lang.toLowerCase().indexOf(LANG) === 0;
      });
      if (!vs.length) vs = synth.getVoices();
      vs.forEach(function (v) {
        var o = el("option", { value: v.name,
          text: v.name.replace(/(Microsoft|Google)\s*/, "").slice(0, 20) });
        if (v.name === prefs.voice) o.selected = true;
        voice.appendChild(o);
      });
    }
    loadVoices();
    synth.onvoiceschanged = loadVoices;

    var pi = 0, si = 0, playing = false;

    function mark(node) {
      document.querySelectorAll(".is-reading").forEach(function (e) { e.classList.remove("is-reading"); });
      if (node) {
        node.classList.add("is-reading");
        node.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
    function done() {
      var n = si;
      for (var i = 0; i < pi; i++) n += queue[i].parts.length;
      return n;
    }
    function update() {
      prog.style.width = (100 * done() / total).toFixed(1) + "%";
      if (playing) {
        var sec = queue[Math.min(pi, queue.length - 1)].el.closest("section.sec");
        var h = sec && sec.querySelector(".sec-title, h2");
        status.textContent = T.section + ": " + (h ? h.textContent.replace(/\s+/g, " ").trim().slice(0, 18) : "—");
      } else status.textContent = T.ready;
    }
    function stop(msg) {
      playing = false; synth.cancel(); mark(null);
      btn.textContent = T.play;
      status.textContent = msg || T.ready;
      if (msg === T.end) { pi = 0; si = 0; prog.style.width = "0%"; }
    }
    function speak() {
      if (!playing) return;
      if (pi >= queue.length) { stop(T.end); return; }
      var q = queue[pi];
      if (si === 0) mark(q.el);
      var u = new SpeechSynthesisUtterance(q.parts[si]);
      u.lang = LANG;
      u.rate = parseFloat(rate.value);
      var v = synth.getVoices().find(function (x) { return x.name === voice.value; });
      if (v) u.voice = v;
      u.onend = function () {
        si++;
        if (si >= q.parts.length) { si = 0; pi++; }
        update(); speak();
      };
      u.onerror = function () { stop(T.ready); };
      synth.speak(u);
    }
    function savePrefs() {
      try { localStorage.setItem("sinapse-audio",
        JSON.stringify({ rate: parseFloat(rate.value), voice: voice.value })); } catch (e) {}
    }

    btn.addEventListener("click", function () {
      if (playing) { stop(); return; }
      playing = true; btn.textContent = T.pause;
      synth.cancel(); speak(); update();
    });
    function jump(dir) {
      var secs = Array.prototype.slice.call(document.querySelectorAll("section.sec"));
      var cur = queue[Math.min(pi, queue.length - 1)].el.closest("section.sec");
      var i = Math.max(0, Math.min(secs.length - 1, secs.indexOf(cur) + dir));
      var target = secs[i];
      var idx = queue.findIndex(function (q) { return q.el.closest("section.sec") === target; });
      if (idx >= 0) { pi = idx; si = 0; }
      synth.cancel();
      if (playing) speak(); else mark(queue[pi].el);
      update();
    }
    prev.addEventListener("click", function () { jump(-1); });
    next.addEventListener("click", function () { jump(1); });
    rate.addEventListener("change", function () { savePrefs(); if (playing) { synth.cancel(); speak(); } });
    voice.addEventListener("change", function () { savePrefs(); if (playing) { synth.cancel(); speak(); } });

    // Chrome se duerme en utterances largas / pestaña en background
    setInterval(function () { if (playing && synth.speaking) { synth.pause(); synth.resume(); } }, 9000);
  }

  function init() {
    try { if (sessionStorage.getItem("sinapse-audio-hidden")) return; } catch (e) {}
    if (!document.querySelector("section.sec")) return;
    var src = document.body.getAttribute("data-audio");
    if (src) {
      fetch(src, { method: "HEAD" }).then(function (r) {
        if (r.ok) mountAudio(src); else mountTTS();
      }).catch(mountTTS);
    } else mountTTS();
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", init);
  else init();
})();
