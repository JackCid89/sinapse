/* SINAPSE · toc-observer.js — menú de navegación lateral (drawer) + sección activa (v2)
   Progressive enhancement: sin JS, el índice inline (.toc) sigue siendo un
   índice de anclas normal. Con JS, el índice se convierte en un cajón lateral
   izquierdo desplegable (botón hamburguesa), con la sección activa resaltada.
   El .toc inline se oculta (html.js-nav .toc { display:none }). */
(function () {
  var toc = document.querySelector('.toc');
  if (!toc) return;
  var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
  if (!links.length) return;

  var lang = (document.documentElement.lang || "es").slice(0, 2);
  var T = lang === "en"
    ? { head: "Sections", open: "Open sections menu", close: "Close menu" }
    : { head: "Secciones", open: "Abrir menú de secciones", close: "Cerrar menú" };

  document.documentElement.classList.add("js-nav");

  // ── botón hamburguesa ─────────────────────────────────────────────
  var toggle = document.createElement("button");
  toggle.className = "nav-toggle";
  toggle.setAttribute("aria-label", T.open);
  toggle.setAttribute("aria-expanded", "false");
  toggle.innerHTML = "<span></span><span></span><span></span>";
  document.body.appendChild(toggle);

  // ── cajón ─────────────────────────────────────────────────────────
  var drawer = document.createElement("nav");
  drawer.className = "nav-drawer";
  drawer.setAttribute("aria-label", T.head);
  var head = document.createElement("div");
  head.className = "nav-drawer-head";
  head.textContent = T.head;
  drawer.appendChild(head);

  var ol = document.createElement("ol");
  var byId = {}, sections = [];
  links.forEach(function (a) {
    var id = a.getAttribute("href").slice(1);
    var num = a.querySelector(".num");
    var lblEl = a.querySelector("span:last-child");
    var li = document.createElement("li");
    var na = document.createElement("a");
    na.href = "#" + id;
    na.innerHTML = '<span class="n">' + (num ? num.textContent : "") + "</span>" +
                   "<span>" + (lblEl ? lblEl.textContent : a.textContent.trim()) + "</span>";
    na.addEventListener("click", function () { close(); });
    li.appendChild(na);
    ol.appendChild(li);
    var sec = document.getElementById(id);
    if (sec) { byId[id] = na; sections.push(sec); }
  });
  drawer.appendChild(ol);
  document.body.appendChild(drawer);

  var backdrop = document.createElement("div");
  backdrop.className = "nav-backdrop";
  document.body.appendChild(backdrop);

  function open() {
    drawer.classList.add("open"); backdrop.classList.add("open");
    toggle.classList.add("open"); toggle.setAttribute("aria-expanded", "true");
  }
  function close() {
    drawer.classList.remove("open"); backdrop.classList.remove("open");
    toggle.classList.remove("open"); toggle.setAttribute("aria-expanded", "false");
  }
  toggle.addEventListener("click", function () {
    drawer.classList.contains("open") ? close() : open();
  });
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") close();
  });

  // ── sección activa ────────────────────────────────────────────────
  if (!("IntersectionObserver" in window)) return;
  var current = null, visible = {};
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
    var top = sections.filter(function (s) { return visible[s.id]; });
    if (!top.length) return;
    var id = top[0].id;
    if (id === current) return;
    if (current && byId[current]) byId[current].removeAttribute("aria-current");
    current = id;
    if (byId[id]) byId[id].setAttribute("aria-current", "true");
  }, { rootMargin: "-30% 0px -60% 0px", threshold: 0 });
  sections.forEach(function (s) { obs.observe(s); });
})();
