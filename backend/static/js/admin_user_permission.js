/* ==========================================================================
   MINISHOP ADMIN - USER ACCESS CONSOLE
   --------------------------------------------------------------------------
   Drives templates/admin/auth/user/change_form.html and the permission board
   rendered by rbac.widgets.PermissionMatrixWidget.

   Every control here is an affordance over the real inputs: the only things
   that get submitted are the `user_permissions` / `groups` checkboxes Django
   itself would have rendered. The tab buttons, the rail, the roll-up
   checkboxes and the column buttons carry no name, so the POST payload is
   identical to a stock CheckboxSelectMultiple no matter what the operator
   clicks. That also means a browser with JS disabled still gets a fully usable
   (if unassisted) form.
   ========================================================================== */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  /* ----------------------------------------------------------------------
     TABS
     ---------------------------------------------------------------------- */
  function initTabs(root) {
    var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-mp-tab]"));
    var panes = Array.prototype.slice.call(root.querySelectorAll("[data-mp-pane]"));
    if (!tabs.length) return;

    var storageKey = "mp-user-tab:" + window.location.pathname;

    function activate(name, remember) {
      var matched = false;
      tabs.forEach(function (tab) {
        var on = tab.getAttribute("data-mp-tab") === name;
        matched = matched || on;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      if (!matched) return false;

      panes.forEach(function (pane) {
        var on = pane.getAttribute("data-mp-pane") === name;
        pane.classList.toggle("is-active", on);
        pane.hidden = !on;
      });

      if (remember) {
        try {
          window.sessionStorage.setItem(storageKey, name);
        } catch (err) {
          /* Private mode or blocked storage: the tab just will not persist. */
        }
      }
      return true;
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activate(tab.getAttribute("data-mp-tab"), true);
      });
    });

    // Roving arrow-key navigation across the tablist.
    root.addEventListener("keydown", function (event) {
      var current = document.activeElement;
      if (!current || !current.hasAttribute || !current.hasAttribute("data-mp-tab")) return;
      var step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      event.preventDefault();
      var index = tabs.indexOf(current);
      var next = tabs[(index + step + tabs.length) % tabs.length];
      next.focus();
      activate(next.getAttribute("data-mp-tab"), true);
    });

    // A validation error in a collapsed tab is an error nobody can find, so an
    // errored pane always wins over the remembered one.
    var errored = root.querySelector(".mp-pane .errorlist, .mp-pane .errors");
    if (errored) {
      var pane = errored.closest("[data-mp-pane]");
      if (pane && activate(pane.getAttribute("data-mp-pane"), false)) return;
    }

    var stored = null;
    try {
      stored = window.sessionStorage.getItem(storageKey);
    } catch (err) {
      stored = null;
    }
    if (stored) activate(stored, false);
  }

  /* ----------------------------------------------------------------------
     PERMISSION BOARD
     ---------------------------------------------------------------------- */
  function initBoard(board, root) {
    var permissions = Array.prototype.slice.call(board.querySelectorAll("[data-pm-perm]"));
    if (!permissions.length) return;

    var sections = Array.prototype.slice.call(board.querySelectorAll("[data-pm-section]"));
    var rows = Array.prototype.slice.call(board.querySelectorAll("[data-pm-row]"));
    var railLinks = Array.prototype.slice.call(board.querySelectorAll("[data-pm-rail]"));
    var masterAll = board.querySelector("[data-pm-all]");
    var countEl = board.querySelector("[data-pm-count]");
    var emptyEl = board.querySelector("[data-pm-empty]");

    // The hero gauge reports ADMIN-PANEL permissions specifically, so only the
    // board that opts in with data-pm-hero drives it. Without this the MiniShop
    // RBAC board would overwrite the same three nodes and the two counts would
    // fight over the header on every keystroke.
    var ownsHero = board.hasAttribute("data-pm-hero");
    var grantedEl = ownsHero ? root.querySelector("[data-mp-granted]") : null;
    var totalEl = ownsHero ? root.querySelector("[data-mp-total]") : null;
    var gaugeEl = ownsHero ? root.querySelector("[data-mp-gauge]") : null;

    var railByKey = {};
    railLinks.forEach(function (link) {
      railByKey[link.getAttribute("data-pm-rail")] = link;
    });

    function visible(el) {
      return !el.hidden;
    }

    /**
     * Set a roll-up checkbox from the state of the boxes it governs:
     * all on -> checked, none on -> clear, anything else -> indeterminate.
     */
    function rollUp(box, children) {
      if (!box) return;
      var on = children.filter(function (input) { return input.checked; }).length;
      box.checked = on > 0 && on === children.length;
      box.indeterminate = on > 0 && on < children.length;
    }

    function permsIn(scope) {
      return Array.prototype.slice.call(scope.querySelectorAll("[data-pm-perm]"));
    }

    function refresh() {
      var grantedTotal = 0;

      rows.forEach(function (row) {
        var children = permsIn(row);
        var on = children.filter(function (input) { return input.checked; }).length;
        row.classList.toggle("is-granted", on > 0);
        rollUp(row.querySelector("[data-pm-row-all]"), children);
      });

      sections.forEach(function (section) {
        var children = permsIn(section);
        var on = children.filter(function (input) { return input.checked; }).length;
        grantedTotal += on;

        section.classList.toggle("has-grants", on > 0);
        rollUp(section.querySelector("[data-pm-section-all]"), children);

        var chip = section.querySelector("[data-pm-section-count]");
        if (chip) chip.textContent = on + "/" + children.length;

        var link = railByKey[section.getAttribute("data-pm-section")];
        if (link) {
          link.classList.toggle("has-grants", on > 0);
          var badge = link.querySelector("[data-pm-rail-count]");
          if (badge) badge.textContent = String(on);
        }
      });

      rollUp(masterAll, permissions);

      if (countEl) countEl.textContent = String(grantedTotal);
      if (grantedEl) grantedEl.textContent = String(grantedTotal);
      if (totalEl) totalEl.textContent = String(permissions.length);
      if (gaugeEl) {
        var pct = permissions.length ? (grantedTotal / permissions.length) * 100 : 0;
        gaugeEl.style.width = pct.toFixed(1) + "%";
      }
    }

    function apply(inputs, checked) {
      inputs.forEach(function (input) {
        // A disabled box is one the operator may not change (a role-inherited
        // grant, or a permission they cannot delegate). It stays in the counted
        // set so the totals stay honest, but no cascade may move it -- and it
        // would submit nothing anyway, so flipping it here would only lie.
        if (input.disabled) return;
        if (input.checked !== checked) input.checked = checked;
      });
      refresh();
    }

    /* Cascade: master / section / row. Each only touches what is currently
       visible, so a filtered board and "select all" compose the way the
       operator expects -- "select all of what I am looking at". */
    if (masterAll) {
      masterAll.addEventListener("change", function () {
        apply(
          permissions.filter(function (input) {
            var row = input.closest("[data-pm-row]");
            var section = input.closest("[data-pm-section]");
            return (!row || visible(row)) && (!section || visible(section));
          }),
          masterAll.checked
        );
      });
    }

    sections.forEach(function (section) {
      var box = section.querySelector("[data-pm-section-all]");
      if (box) {
        box.addEventListener("change", function () {
          apply(
            permsIn(section).filter(function (input) {
              var row = input.closest("[data-pm-row]");
              return !row || visible(row);
            }),
            box.checked
          );
        });
      }

      // Column buttons toggle one action down the whole section. They flip to
      // "all on" unless everything visible is already on, which makes a second
      // press clear the column.
      section.querySelectorAll("[data-pm-col]").forEach(function (button) {
        button.addEventListener("click", function () {
          var action = button.getAttribute("data-pm-col");
          var targets = permsIn(section).filter(function (input) {
            var row = input.closest("[data-pm-row]");
            return input.getAttribute("data-action") === action && (!row || visible(row));
          });
          if (!targets.length) return;
          var allOn = targets.every(function (input) { return input.checked; });
          apply(targets, !allOn);
        });
      });
    });

    rows.forEach(function (row) {
      var box = row.querySelector("[data-pm-row-all]");
      if (!box) return;
      box.addEventListener("change", function () {
        apply(permsIn(row), box.checked);
      });
    });

    permissions.forEach(function (input) {
      input.addEventListener("change", refresh);
    });

    /* ------------------------------------------------------------------
       SEARCH
       ------------------------------------------------------------------ */
    var search = board.querySelector("[data-pm-search]");
    if (search) {
      var runFilter = function () {
        var term = search.value.trim().toLowerCase();
        var anyVisible = false;

        sections.forEach(function (section) {
          var sectionHaystack = section.getAttribute("data-search") || "";
          var sectionMatches = !term || sectionHaystack.indexOf(term) !== -1;
          var shown = 0;

          Array.prototype.slice.call(
            section.querySelectorAll("[data-pm-row]")
          ).forEach(function (row) {
            var hit =
              !term ||
              sectionMatches ||
              (row.getAttribute("data-search") || "").indexOf(term) !== -1;
            row.hidden = !hit;
            if (hit) shown += 1;
          });

          section.hidden = shown === 0;
          if (!section.hidden) anyVisible = true;

          var link = railByKey[section.getAttribute("data-pm-section")];
          if (link) link.hidden = section.hidden;
        });

        if (emptyEl) emptyEl.hidden = anyVisible;
      };

      search.addEventListener("input", runFilter);
      search.addEventListener("search", runFilter);
      search.addEventListener("keydown", function (event) {
        // The board is rendered inside the change form, so this field is a
        // form control: without this, Enter implicitly submits and silently
        // saves the user while they were only narrowing the list.
        if (event.key === "Enter") {
          event.preventDefault();
          return;
        }
        // Escape clears the filter without leaving the field.
        if (event.key === "Escape" && search.value) {
          event.preventDefault();
          search.value = "";
          runFilter();
        }
      });
    }

    /* ------------------------------------------------------------------
       RAIL: click + scroll-spy
       ------------------------------------------------------------------ */
    railLinks.forEach(function (link) {
      link.addEventListener("click", function () {
        railLinks.forEach(function (other) { other.classList.remove("is-current"); });
        link.classList.add("is-current");
      });
    });

    if ("IntersectionObserver" in window && sections.length) {
      var spy = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var key = entry.target.getAttribute("data-pm-section");
            railLinks.forEach(function (link) {
              link.classList.toggle("is-current", link.getAttribute("data-pm-rail") === key);
            });
          });
        },
        // Band just under the sticky chrome, so the highlighted rail item is
        // the section actually sitting at the top of the reading area.
        { rootMargin: "-120px 0px -68% 0px", threshold: 0 }
      );
      sections.forEach(function (section) { spy.observe(section); });
    } else if (railLinks.length) {
      railLinks[0].classList.add("is-current");
    }

    refresh();
  }

  /* ----------------------------------------------------------------------
     SUPERUSER BANNER
     ---------------------------------------------------------------------- */
  function initSuperuser(root) {
    var toggle = root.querySelector("#id_is_superuser");
    var banner = root.querySelector("[data-mp-superbanner]");
    var pane = root.querySelector('[data-mp-pane="permissions"]');
    if (!toggle || !banner || !pane) return;

    function sync() {
      banner.hidden = !toggle.checked;
      pane.classList.toggle("is-superuser", toggle.checked);
    }

    toggle.addEventListener("change", sync);
    sync();
  }

  /* ----------------------------------------------------------------------
     UNSAVED-CHANGES HINT
     ---------------------------------------------------------------------- */
  function initDirty(root) {
    var note = root.querySelector("[data-mp-dirty]");
    var form = root.querySelector("form");
    if (!note || !form) return;

    var mark = function (event) {
      // The board's filter field is inside the form but changes nothing that
      // gets saved, so narrowing the list must not read as an edit.
      var target = event && event.target;
      if (target && target.hasAttribute && target.hasAttribute("data-pm-search")) {
        return;
      }
      note.hidden = false;
      form.removeEventListener("change", mark);
      form.removeEventListener("input", mark);
    };

    form.addEventListener("change", mark);
    form.addEventListener("input", mark);
    form.addEventListener("submit", function () { note.hidden = true; });
  }

  /**
   * Move the role formset's "add another" control up into the section header.
   *
   * inlines.js builds that link itself and appends it after the last form, and
   * it only accepts a pre-existing button through a JS option Django never
   * passes from the server. Relocating the node afterwards keeps the click
   * handler inlines.js bound to it, so no behaviour is reimplemented here.
   *
   * A MutationObserver is used rather than running once: both this file and
   * inlines.js act on DOM-ready and their order is not guaranteed, so the link
   * may not exist yet when this runs.
   */
  function initRoleAddButton(root) {
    var slot = root.querySelector("[data-mp-addrole-slot]");
    var group = root.querySelector(".mp-roles");
    if (!slot || !group) return;

    function relocate() {
      var addRow = group.querySelector(".add-row");
      if (!addRow || addRow.parentNode === slot) return false;
      slot.appendChild(addRow);
      return true;
    }

    if (relocate()) return;

    var observer = new MutationObserver(function () {
      if (relocate()) observer.disconnect();
    });
    observer.observe(group, { childList: true, subtree: true });

    // inlines.js hides the control once max_num is reached; stop watching
    // regardless so the observer cannot outlive the page's settling.
    window.setTimeout(function () { observer.disconnect(); }, 5000);
  }

  ready(function () {
    // The user console wraps its form in .mp-shell; the role form is the stock
    // change form with a board in one fieldset, so there is nothing to wrap.
    // Every initialiser below bails out on its own when its markup is absent,
    // which is what lets one file serve both pages.
    var root = document.querySelector(".mp-shell") || document.body;

    initTabs(root);
    initSuperuser(root);
    initDirty(root);
    initRoleAddButton(root);

    root.querySelectorAll("[data-pm-board]").forEach(function (board) {
      initBoard(board, root);
    });
  });
})();
