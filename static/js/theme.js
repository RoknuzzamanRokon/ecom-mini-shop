/* ==========================================================================
   MiniShop theme switcher
   --------------------------------------------------------------------------
   Two independent axes, both persisted to localStorage:
     data-theme="<id>"  on <html>  -- which palette
     class="dark"       on <html>  -- light or dark rendering of that palette

   The palettes themselves live in static/css/theme.css. This file only
   decides which one is active and draws the picker.
   ========================================================================== */
(function () {
  "use strict";

  var THEME_KEY = "minishop-theme";
  var DARK_KEY = "minishop-dark";
  var DEFAULT_THEME = "ai";

  var THEMES = [
    {
      id: "ai",
      ja: "褐色と生成り",
      romaji: "Kachi-iro to Kinari",
      en: "Kachi Indigo",
      note: "Indigo-dyed workwear on undyed cotton",
      swatch: ["#21486B", "#BA8630", "#101F2E", "#A5273D"]
    },
    {
      id: "sumi",
      ja: "墨と朱印",
      romaji: "Sumi to Shuin",
      en: "Sumi & Seal",
      note: "Ink on washi, one seal-red mark",
      swatch: ["#262019", "#A83A18", "#342C23", "#7E2B3D"]
    },
    {
      id: "shu",
      ja: "朱色",
      romaji: "Shu-iro",
      en: "Torii Vermilion",
      note: "Shrine vermilion, used with discipline",
      swatch: ["#c2371a", "#b98322", "#1a1411", "#b32f14"]
    },
    {
      id: "matsu",
      ja: "常磐松",
      romaji: "Tokiwa Matsu",
      en: "Tokiwa Pine",
      note: "Evergreen and old gold, tea-ceremony calm",
      swatch: ["#2e5e49", "#b07c22", "#1d4234", "#a82a38"]
    },
    {
      id: "den",
      ja: "電光信号",
      romaji: "Denkō Shingō",
      en: "Signal Graphite",
      note: "Engineered greys, one electric signal",
      swatch: ["#1D2A36", "#00B3CC", "#0E141C", "#C81E3C"]
    },
    {
      id: "haizakura",
      ja: "灰桜",
      romaji: "Haizakura",
      en: "Ash Blossom",
      note: "Department-store plum, ash and brass",
      swatch: ["#5a2b48", "#b08a45", "#2e1727", "#a62f4c"]
    },
    {
      id: "current",
      ja: "現行",
      romaji: "Genkō",
      en: "Current (before)",
      note: "The palette the shop ships today",
      swatch: ["#2563eb", "#fbbf24", "#1d4ed8", "#e11d48"]
    }
  ];

  var root = document.documentElement;

  function read(key, fallback) {
    try {
      var v = localStorage.getItem(key);
      return v === null ? fallback : v;
    } catch (e) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* private mode, or storage disabled -- the choice just won't persist */
    }
  }

  function currentTheme() {
    return read(THEME_KEY, DEFAULT_THEME);
  }

  function isDark() {
    return read(DARK_KEY, "0") === "1";
  }

  function applyTheme(id) {
    root.setAttribute("data-theme", id);
    write(THEME_KEY, id);
    paintList();
  }

  function applyMode(dark) {
    root.classList.toggle("dark", dark);
    write(DARK_KEY, dark ? "1" : "0");
    paintModes();
  }

  /* ---------------------------------------------------------------- render */

  var listEl, panelEl, toggleEl;

  function paintList() {
    if (!listEl) return;
    var active = currentTheme();

    listEl.innerHTML = THEMES.map(function (t) {
      var on = t.id === active;
      return (
        '<button type="button" data-theme-id="' + t.id + '" aria-pressed="' + on + '" ' +
        'class="theme-option group flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors ' +
        (on ? 'bg-primary/10' : 'hover:bg-surface-sunken') + '">' +

          '<span class="grid h-9 w-9 shrink-0 grid-cols-2 overflow-hidden rounded-md ring-1 ring-black/10">' +
            t.swatch.map(function (c) {
              return '<span style="background:' + c + '"></span>';
            }).join("") +
          '</span>' +

          '<span class="min-w-0 flex-1">' +
            '<span class="flex items-baseline gap-1.5">' +
              '<span class="truncate text-[13px] font-bold ' + (on ? 'text-primary' : 'text-ink') + '">' + t.ja + '</span>' +
              '<span class="truncate text-[10px] uppercase tracking-wider text-ink-faint">' + t.en + '</span>' +
            '</span>' +
            '<span class="mt-0.5 block truncate text-[11px] text-ink-muted">' + t.note + '</span>' +
          '</span>' +

          (on
            ? '<span class="material-symbols-outlined shrink-0 text-[18px] text-primary">check_circle</span>'
            : '<span class="material-symbols-outlined shrink-0 text-[18px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100">radio_button_unchecked</span>') +
        '</button>'
      );
    }).join("");

    listEl.querySelectorAll("[data-theme-id]").forEach(function (b) {
      b.addEventListener("click", function () {
        applyTheme(b.getAttribute("data-theme-id"));
      });
    });
  }

  function paintModes() {
    var dark = isDark();
    document.querySelectorAll(".theme-mode").forEach(function (b) {
      var on = (b.getAttribute("data-mode") === "dark") === dark;
      b.setAttribute("aria-pressed", String(on));
      b.className = b.className.replace(/\s*(bg-primary|text-on-primary|bg-surface|text-ink-muted)\b/g, "");
      b.className += on ? " bg-primary text-on-primary" : " bg-surface text-ink-muted";
    });
  }

  /* ---------------------------------------------------------------- panel */

  function openPanel() {
    panelEl.classList.remove("hidden");
    toggleEl.setAttribute("aria-expanded", "true");
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onOutside, true);
  }

  function closePanel() {
    panelEl.classList.add("hidden");
    toggleEl.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("click", onOutside, true);
  }

  function isOpen() {
    return !panelEl.classList.contains("hidden");
  }

  function onKey(e) {
    if (e.key === "Escape") {
      closePanel();
      toggleEl.focus();
    }
  }

  function onOutside(e) {
    var wrap = document.getElementById("theme-switcher");
    if (wrap && !wrap.contains(e.target)) closePanel();
  }

  /* ---------------------------------------------------------------- init */

  function init() {
    panelEl = document.getElementById("theme-panel");
    toggleEl = document.getElementById("theme-toggle");
    listEl = document.getElementById("theme-list");
    if (!panelEl || !toggleEl || !listEl) return;

    /* The inline head script already set these; re-assert in case it failed. */
    root.setAttribute("data-theme", currentTheme());
    root.classList.toggle("dark", isDark());

    paintList();
    paintModes();

    toggleEl.addEventListener("click", function () {
      isOpen() ? closePanel() : openPanel();
    });
    document.getElementById("theme-close").addEventListener("click", function () {
      closePanel();
      toggleEl.focus();
    });
    document.querySelectorAll(".theme-mode").forEach(function (b) {
      b.addEventListener("click", function () {
        applyMode(b.getAttribute("data-mode") === "dark");
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
