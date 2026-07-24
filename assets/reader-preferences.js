/* ──────────────────────────────────────────────────────────────────────
   Sinapse · reader-preferences.js
   Panel de preferencias de lectura para el usuario final.

   - Persiste paleta / tema / tamaño / densidad en localStorage.
   - Aplica los atributos sobre <html> y las variables --fs-body / --measure.
   - Vainilla JS — sin dependencias.

   Uso:
     <script src="/assets/reader-preferences.js" defer></script>

   Atributos opcionales sobre el script:
     data-key="sinapse-prefs"   (clave localStorage; default sinapse-prefs)
     data-mount="auto"          ("auto" inyecta el botón flotante; "none" no monta UI)

   Para montar la UI en un sitio distinto, llama window.SinapsePrefs.mount(parent).
   ────────────────────────────────────────────────────────────────────── */

(function(){
  'use strict';

  const SCRIPT = document.currentScript;
  const STORAGE_KEY = SCRIPT?.dataset.key || 'sinapse-prefs';
  const AUTO_MOUNT = (SCRIPT?.dataset.mount || 'auto') !== 'none';

  const DEFAULTS = {
    palette: 'aurora',      // aurora · vermilion · verde · tinta
    theme:   'paper',       // paper · sepia · eink
    fontSize: 17,           // 15-22 px
    measure: 42,            // 32-52 rem (ancho de columna)
    density: 'spacious',    // compact · regular · spacious
    dyslexia: 'off'         // off · on (Lexend + BDA Style Guide 2023)
  };

  const PALETTES = [
    { id: 'aurora',    label: 'Aurora',    swatch: 'oklch(0.50 0.19 262)' },
    { id: 'vermilion', label: 'Vermellón', swatch: 'oklch(0.58 0.22 32)'  },
    { id: 'verde',     label: 'Verde',     swatch: 'oklch(0.46 0.13 140)' },
    { id: 'tinta',     label: 'Tinta',     swatch: 'oklch(0.78 0.20 118)' }
  ];

  const THEMES = [
    { id: 'paper', label: 'Papel'  },
    { id: 'sepia', label: 'Sepia'  },
    { id: 'eink',  label: 'E-ink'  }
  ];

  const DENSITIES = [
    { id: 'compact',  label: 'Compacta' },
    { id: 'regular',  label: 'Normal'   },
    { id: 'spacious', label: 'Aireada'  }
  ];

  const DYSLEXIA = [
    { id: 'off', label: 'Estándar' },
    { id: 'on',  label: 'Dislexia' }
  ];

  /* ─── State ─── */
  function load(){
    try{
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      return Object.assign({}, DEFAULTS, stored);
    } catch { return Object.assign({}, DEFAULTS); }
  }
  function save(state){
    try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }catch{}
  }
  // Lexend se carga SOLO al activar el modo dislexia (ahorra una familia de
  // fuentes completa en el ~95% de las cargas). Idempotente.
  function ensureLexend(){
    if (document.getElementById('sinapse-lexend')) return;
    const l = document.createElement('link');
    l.id = 'sinapse-lexend'; l.rel = 'stylesheet';
    l.href = 'https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700&display=swap';
    document.head.appendChild(l);
  }
  function apply(state){
    const html = document.documentElement;
    html.setAttribute('data-palette', state.palette);
    html.setAttribute('data-theme',   state.theme);
    html.setAttribute('data-density', state.density);
    html.setAttribute('data-dyslexia', state.dyslexia || 'off');
    if ((state.dyslexia || 'off') === 'on') ensureLexend();
    html.style.setProperty('--fs-body', state.fontSize + 'px');
    html.style.setProperty('--measure', state.measure + 'rem');
  }

  let state = load();
  apply(state);

  function setKey(key, value){
    state = Object.assign({}, state, { [key]: value });
    apply(state);
    save(state);
    render();
  }
  function reset(){
    state = Object.assign({}, DEFAULTS);
    apply(state);
    save(state);
    render();
  }

  /* ─── Panel UI (built once, toggled with .open) ─── */
  let toggleBtn, panel;

  function mount(parent){
    parent = parent || document.body;
    if (toggleBtn) return; // already mounted

    // Styles (inlined so the script is fully self-contained)
    const style = document.createElement('style');
    style.textContent = `
      .reader-prefs-toggle{
        position:fixed;right:20px;bottom:20px;z-index:60;
        width:44px;height:44px;border-radius:50%;
        background:var(--paper,#f7f6f3);color:var(--ink,#2a2820);
        border:1px solid var(--rule,#d0cfca);
        box-shadow:0 4px 14px rgba(0,0,0,.08);
        font:14px var(--serif, Georgia, serif);
        cursor:pointer;display:flex;align-items:center;justify-content:center;
        transition:transform .15s ease, box-shadow .15s ease;
      }
      .reader-prefs-toggle:hover{transform:translateY(-1px);box-shadow:0 6px 18px rgba(0,0,0,.12)}
      .reader-prefs-toggle svg{width:18px;height:18px}

      .reader-prefs{
        position:fixed;right:20px;bottom:74px;z-index:61;
        width:300px;max-height:calc(100vh - 110px);overflow-y:auto;
        background:var(--paper,#f7f6f3);color:var(--ink,#2a2820);
        border:1px solid var(--rule,#d0cfca);border-radius:10px;
        box-shadow:0 12px 40px rgba(0,0,0,.15);
        padding:16px 18px 18px;
        font:13px/1.45 var(--serif, Georgia, serif);
        opacity:0;pointer-events:none;transform:translateY(8px);
        transition:opacity .15s ease, transform .15s ease;
      }
      .reader-prefs.open{opacity:1;pointer-events:auto;transform:translateY(0)}

      .reader-prefs h2{
        font-family:var(--mono, monospace);
        font-size:10px;font-weight:500;
        text-transform:uppercase;letter-spacing:.12em;
        color:var(--ink-3,#888);margin:0 0 14px;
      }
      .reader-prefs .group{margin-bottom:14px}
      .reader-prefs .group:last-of-type{margin-bottom:0}
      .reader-prefs label.row{
        display:flex;justify-content:space-between;align-items:baseline;
        font-family:var(--mono, monospace);font-size:10px;
        text-transform:uppercase;letter-spacing:.08em;
        color:var(--ink-2,#666);margin-bottom:6px;
      }
      .reader-prefs label.row .v{color:var(--ink-3,#999);font-variant-numeric:tabular-nums}

      .reader-prefs .seg{
        display:grid;gap:4px;
        grid-template-columns:repeat(var(--cols,3),minmax(0,1fr));
        border:1px solid var(--rule,#d0cfca);border-radius:6px;padding:3px;
      }
      .reader-prefs .seg button{
        appearance:none;border:0;background:transparent;color:var(--ink-2,#444);
        font:inherit;font-size:12px;padding:6px 4px;border-radius:4px;cursor:pointer;
        text-align:center;line-height:1.2;
      }
      .reader-prefs .seg button:hover{background:var(--rule-2,#e5e3dd)}
      .reader-prefs .seg button[aria-pressed="true"]{
        background:var(--ink,#2a2820);color:var(--paper,#f7f6f3);
      }
      .reader-prefs .seg.palette button{display:flex;align-items:center;justify-content:flex-start;gap:6px;padding-left:8px}
      .reader-prefs .seg.palette .sw{
        display:inline-block;width:10px;height:10px;border-radius:50%;flex:none;
      }

      .reader-prefs input[type=range]{
        width:100%;-webkit-appearance:none;background:transparent;margin:6px 0 0;height:18px;
      }
      .reader-prefs input[type=range]::-webkit-slider-runnable-track{
        height:2px;background:var(--rule,#d0cfca);border-radius:1px;
      }
      .reader-prefs input[type=range]::-moz-range-track{
        height:2px;background:var(--rule,#d0cfca);border-radius:1px;
      }
      .reader-prefs input[type=range]::-webkit-slider-thumb{
        -webkit-appearance:none;width:14px;height:14px;border-radius:50%;
        background:var(--accent,#345fcc);margin-top:-6px;border:0;cursor:pointer;
      }
      .reader-prefs input[type=range]::-moz-range-thumb{
        width:14px;height:14px;border-radius:50%;background:var(--accent,#345fcc);border:0;cursor:pointer;
      }

      .reader-prefs .foot{
        margin-top:14px;padding-top:10px;border-top:1px solid var(--rule-2,#e5e3dd);
        display:flex;justify-content:space-between;align-items:center;
        font-family:var(--mono, monospace);font-size:10px;
        text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3,#888);
      }
      .reader-prefs .foot button{
        appearance:none;border:0;background:transparent;color:var(--ink-2,#666);
        font:inherit;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
        cursor:pointer;padding:4px 0;
      }
      .reader-prefs .foot button:hover{color:var(--accent,#345fcc)}

      @media print{ .reader-prefs, .reader-prefs-toggle{display:none !important} }
    `;
    document.head.appendChild(style);

    // Toggle button
    toggleBtn = document.createElement('button');
    toggleBtn.className = 'reader-prefs-toggle';
    toggleBtn.setAttribute('aria-label','Preferencias de lectura');
    toggleBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 6h11M4 12h11M4 18h7"/>
        <circle cx="19" cy="6" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="14" cy="18" r="2"/>
      </svg>`;
    toggleBtn.addEventListener('click', () => panel.classList.toggle('open'));
    parent.appendChild(toggleBtn);

    // Panel
    panel = document.createElement('aside');
    panel.className = 'reader-prefs';
    panel.setAttribute('role','dialog');
    panel.setAttribute('aria-label','Preferencias de lectura');
    parent.appendChild(panel);
    // Los clicks dentro del panel no deben burbujear al handler global de
    // "click afuera" (render() reconstruye el panel y desprende el target).
    panel.addEventListener('click', function(e){ e.stopPropagation(); });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!panel.classList.contains('open')) return;
      if (panel.contains(e.target) || toggleBtn.contains(e.target)) return;
      panel.classList.remove('open');
    });
    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') panel.classList.remove('open');
    });

    render();
  }

  function seg(opts, current, onPick, extraClass){
    const cols = opts.length;
    const wrap = document.createElement('div');
    wrap.className = 'seg ' + (extraClass || '');
    wrap.style.setProperty('--cols', cols);
    opts.forEach(o => {
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-pressed', String(o.id === current));
      b.dataset.value = o.id;
      if (o.swatch){
        const sw = document.createElement('span');
        sw.className = 'sw';
        sw.style.background = o.swatch;
        b.appendChild(sw);
      }
      const label = document.createElement('span');
      label.textContent = o.label;
      b.appendChild(label);
      b.addEventListener('click', () => onPick(o.id));
      wrap.appendChild(b);
    });
    return wrap;
  }

  function render(){
    if (!panel) return;
    panel.innerHTML = '';

    const h = document.createElement('h2');
    h.textContent = 'Preferencias de lectura';
    panel.appendChild(h);

    const xBtn = document.createElement('button');
    xBtn.textContent = '\u2715';
    xBtn.setAttribute('aria-label', 'Cerrar preferencias');
    xBtn.style.cssText = 'position:absolute;top:10px;right:12px;border:none;background:none;color:var(--ink-3,#888);font-size:16px;line-height:1;cursor:pointer;padding:4px';
    xBtn.addEventListener('click', function(){ panel.classList.remove('open'); });
    panel.appendChild(xBtn);

    // Palette
    const gP = document.createElement('div'); gP.className = 'group';
    const lP = document.createElement('label'); lP.className = 'row';
    lP.innerHTML = '<span>Paleta</span><span class="v">' +
      (PALETTES.find(p => p.id === state.palette)?.label || '') + '</span>';
    gP.appendChild(lP);
    gP.appendChild(seg(PALETTES, state.palette, v => setKey('palette', v), 'palette'));
    panel.appendChild(gP);

    // Theme
    const gT = document.createElement('div'); gT.className = 'group';
    const lT = document.createElement('label'); lT.className = 'row';
    lT.innerHTML = '<span>Modo</span><span class="v">' +
      (THEMES.find(t => t.id === state.theme)?.label || '') + '</span>';
    gT.appendChild(lT);
    gT.appendChild(seg(THEMES, state.theme, v => setKey('theme', v)));
    panel.appendChild(gT);

    // Font size
    const gF = document.createElement('div'); gF.className = 'group';
    const lF = document.createElement('label'); lF.className = 'row';
    lF.innerHTML = '<span>Cuerpo</span><span class="v">' + state.fontSize + ' px</span>';
    gF.appendChild(lF);
    const sF = document.createElement('input');
    sF.type = 'range'; sF.min = 15; sF.max = 22; sF.step = 1; sF.value = state.fontSize;
    sF.setAttribute('aria-label', 'Tamaño de letra');
    sF.addEventListener('input', e => setKey('fontSize', parseInt(e.target.value, 10)));
    gF.appendChild(sF);
    panel.appendChild(gF);

    // Measure
    const gM = document.createElement('div'); gM.className = 'group';
    const lM = document.createElement('label'); lM.className = 'row';
    lM.innerHTML = '<span>Ancho de columna</span><span class="v">' + state.measure + ' rem</span>';
    gM.appendChild(lM);
    const sM = document.createElement('input');
    sM.type = 'range'; sM.min = 32; sM.max = 52; sM.step = 1; sM.value = state.measure;
    sM.setAttribute('aria-label', 'Ancho de columna');
    sM.addEventListener('input', e => setKey('measure', parseInt(e.target.value, 10)));
    gM.appendChild(sM);
    panel.appendChild(gM);

    // Density
    const gD = document.createElement('div'); gD.className = 'group';
    const lD = document.createElement('label'); lD.className = 'row';
    lD.innerHTML = '<span>Densidad</span><span class="v">' +
      (DENSITIES.find(d => d.id === state.density)?.label || '') + '</span>';
    gD.appendChild(lD);
    gD.appendChild(seg(DENSITIES, state.density, v => setKey('density', v)));
    panel.appendChild(gD);

    // Accesibilidad: dislexia
    const gA = document.createElement('div'); gA.className = 'group';
    const lA = document.createElement('label'); lA.className = 'row';
    lA.innerHTML = '<span>Accesibilidad</span><span class="v">' +
      (DYSLEXIA.find(d => d.id === state.dyslexia)?.label || 'Estándar') + '</span>';
    gA.appendChild(lA);
    gA.appendChild(seg(DYSLEXIA, state.dyslexia, v => setKey('dyslexia', v), 'dys'));
    const hint = document.createElement('p'); hint.className = 'dys-hint';
    hint.textContent = 'Lexend + BDA: tracking, line-height, sin cursivas ni capitular.';
    gA.appendChild(hint);
    panel.appendChild(gA);

    // Footer
    const foot = document.createElement('div'); foot.className = 'foot';
    const fL = document.createElement('span'); fL.textContent = 'Sinapse · v1.1';
    const fR = document.createElement('button'); fR.type = 'button'; fR.textContent = 'Restablecer';
    fR.addEventListener('click', reset);
    foot.appendChild(fL); foot.appendChild(fR);
    panel.appendChild(foot);
  }

  /* ─── Auto-mount ─── */
  if (AUTO_MOUNT){
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => mount());
    } else {
      mount();
    }
  }

  /* ─── Public API ─── */
  window.SinapsePrefs = {
    mount,
    get: () => Object.assign({}, state),
    set: (key, value) => setKey(key, value),
    reset
  };

})();
