/* SINAPSE · toc-observer.js — TOC pegajoso con sección activa (v1)
   Progressive enhancement puro: si el JS no corre, el TOC sigue funcionando
   como índice de anclas. Añade la clase .toc-sticky (la CSS solo la fija en
   desktop) y resalta con aria-current="true" el enlace de la sección visible. */
(function () {
  var toc = document.querySelector('.toc');
  if (!toc || !('IntersectionObserver' in window)) return;

  toc.classList.add('toc-sticky');

  var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
  if (!links.length) return;

  var byId = {};
  var sections = [];
  links.forEach(function (a) {
    var id = a.getAttribute('href').slice(1);
    var sec = document.getElementById(id);
    if (sec) { byId[id] = a; sections.push(sec); }
  });

  var current = null;
  function setCurrent(id) {
    if (id === current) return;
    if (current && byId[current]) byId[current].removeAttribute('aria-current');
    current = id;
    if (byId[id]) byId[id].setAttribute('aria-current', 'true');
  }

  // La sección activa es la más alta cuyo tope ya pasó el 30% del viewport.
  var visible = {};
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
    var top = sections.filter(function (s) { return visible[s.id]; });
    if (top.length) setCurrent(top[0].id);
  }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });

  sections.forEach(function (s) { obs.observe(s); });
})();
