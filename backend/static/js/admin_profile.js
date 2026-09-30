/*
 * /admin/profile/ enhancements (templates/admin/profile.html).
 *
 * The page is complete without this file. It adds: copy-to-clipboard buttons,
 * the Console & API / Admin panel tabs with a permission filter, a preview of
 * a newly chosen photo, and the current-section highlight in the sub-nav.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-pf]");
    if (!root) return;
    root.classList.add("pf-js");

    var live = root.querySelector("[data-pf-live]");
    function announce(message) {
      if (!live) return;
      live.textContent = "";
      window.setTimeout(function () { live.textContent = message; }, 30);
    }

    initCopy(root, announce);
    initPermissions(root, announce);
    initPhotoPreview(root);
    initScrollSpy(root);
    focusHashedField();
  });

  /* ---------------------------------------------------------------- copy */
  function initCopy(root, announce) {
    root.addEventListener("click", function (event) {
      var button = event.target.closest("[data-pf-copy]");
      if (!button || !navigator.clipboard) return;
      navigator.clipboard.writeText(button.getAttribute("data-pf-copy")).then(function () {
        var icon = button.querySelector(".material-symbols-outlined");
        button.classList.add("is-done");
        if (icon) icon.textContent = "check";
        announce("Copied to clipboard");
        window.setTimeout(function () {
          button.classList.remove("is-done");
          if (icon) icon.textContent = "content_copy";
        }, 1600);
      }, function () {
        announce("Couldn't copy. Select the text instead.");
      });
    });
  }

  /* ---------------------------------------------------------- permissions */
  function initPermissions(root, announce) {
    var tablist = root.querySelector("[data-pf-tabs]");
    var search = root.querySelector("[data-pf-search]");
    var input = root.querySelector("[data-pf-filter]");
    var nomatch = root.querySelector("[data-pf-nomatch]");
    if (!tablist) return;

    var tabs = Array.prototype.slice.call(tablist.querySelectorAll("[data-pf-tab]"));
    var panels = {};
    tabs.forEach(function (tab) {
      var key = tab.getAttribute("data-pf-tab");
      panels[key] = root.querySelector('[data-pf-panel="' + key + '"]');
    });

    // Remember each group's server-rendered open state, to restore it when
    // the filter is cleared.
    root.querySelectorAll("[data-pf-group]").forEach(function (group) {
      group.dataset.pfOpen = group.open ? "1" : "0";
    });

    tablist.hidden = false;
    if (search) search.hidden = false;

    function select(tab, moveFocus) {
      tabs.forEach(function (other) {
        var on = other === tab;
        other.setAttribute("aria-selected", on ? "true" : "false");
        other.tabIndex = on ? 0 : -1;
        var panel = panels[other.getAttribute("data-pf-tab")];
        if (panel) panel.hidden = !on;
      });
      if (moveFocus) tab.focus();
      applyFilter();
    }

    tablist.addEventListener("click", function (event) {
      var tab = event.target.closest("[data-pf-tab]");
      if (tab) select(tab, false);
    });

    tablist.addEventListener("keydown", function (event) {
      var index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      var next = null;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      if (event.key === "Home") next = tabs[0];
      if (event.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        event.preventDefault();
        select(next, true);
      }
    });

    function activePanel() {
      var selected = tabs.filter(function (tab) { return tab.getAttribute("aria-selected") === "true"; })[0];
      return selected ? panels[selected.getAttribute("data-pf-tab")] : null;
    }

    var pending = null;
    function applyFilter() {
      var panel = activePanel();
      if (!panel || !input) return;
      var query = input.value.trim().toLowerCase();
      var visible = 0;

      panel.querySelectorAll("[data-pf-group]").forEach(function (group) {
        var items = group.querySelectorAll("[data-pf-item]");
        var shown = 0;
        items.forEach(function (item) {
          var match = !query || item.getAttribute("data-pf-item").indexOf(query) !== -1;
          item.hidden = !match;
          if (match) shown += 1;
        });
        if (query) {
          group.hidden = shown === 0;
          group.open = shown > 0;
        } else {
          group.hidden = false;
          group.open = group.dataset.pfOpen === "1";
        }
        visible += shown;
      });

      if (nomatch) nomatch.hidden = !query || visible > 0;
      if (query) {
        window.clearTimeout(pending);
        pending = window.setTimeout(function () {
          announce(visible === 1 ? "1 permission matches" : visible + " permissions match");
        }, 400);
      }
    }

    if (input) input.addEventListener("input", applyFilter);
    select(tabs[0], false);
  }

  /* ------------------------------------------------------- photo preview */
  function initPhotoPreview(root) {
    var input = root.querySelector('input[type="file"][name="avatar"]');
    var preview = root.querySelector("[data-pf-preview]");
    if (!input || !preview || !window.URL) return;
    var original = preview.innerHTML;
    var url = null;

    input.addEventListener("change", function () {
      if (url) URL.revokeObjectURL(url);
      var file = input.files && input.files[0];
      if (!file || file.type.indexOf("image/") !== 0) {
        preview.innerHTML = original;
        return;
      }
      url = URL.createObjectURL(file);
      var img = document.createElement("img");
      img.src = url;
      img.alt = "";
      preview.innerHTML = "";
      preview.appendChild(img);
    });
  }

  /* ---------------------------------------------------------- scroll spy */
  function initScrollSpy(root) {
    var links = Array.prototype.slice.call(root.querySelectorAll("[data-pf-spy]"));
    var sections = links.map(function (link) {
      return document.getElementById(link.getAttribute("href").slice(1));
    });
    if (!links.length || sections.indexOf(null) !== -1) return;
    // Just below the sticky header + sub-nav (matches scroll-margin-top).
    var THRESHOLD = 140;
    var queued = false;

    function mark() {
      queued = false;
      var atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      var current = 0;
      var currentTop = -Infinity;
      sections.forEach(function (section, index) {
        var top = section.getBoundingClientRect().top;
        // The section that most recently passed under the bar. Security sits
        // beside Personal on wide screens, so a tie keeps the earlier link.
        if ((top <= THRESHOLD || atBottom) && top > currentTop + 1) {
          current = index;
          currentTop = top;
        }
      });
      links.forEach(function (link, index) {
        if (index === current) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    }

    function queue() {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(mark);
    }

    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    mark();
  }

  /* ------------------------------------------- "+ Add" lands on the field */
  function focusHashedField() {
    if (!window.location.hash) return;
    var target = document.getElementById(window.location.hash.slice(1));
    if (target && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName)) {
      target.focus({ preventScroll: false });
    }
  }
})();
