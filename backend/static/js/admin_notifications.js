/*
 * The notification bell in the Django admin header
 * (notifications/templates/notifications/admin/bell.html).
 *
 * It uses the same /api/notifications/ endpoints as the Console's bell, signed
 * in through the admin's session cookie; POSTs carry the page's CSRF token.
 * The badge re-counts every 60 s while the tab is visible, and when the tab
 * comes back. Opening the bell loads the 10 newest STAFF notifications. A
 * notification's link is a Console path, so it opens there in a new tab.
 * Text from the server is only ever set with textContent.
 */
(function () {
  "use strict";

  var POLL_MS = 60000;
  var SHOWN = 10;
  // Material Symbols per category, as in frontend/src/lib/notifications.ts.
  var ICONS = {
    ORDERS: "local_shipping",
    SELLER_ORDERS: "shopping_bag",
    PAYMENTS: "payments",
    SUPPORT: "support_agent",
    ACCOUNT: "badge",
    SHOPS: "storefront",
    CATALOG: "inventory_2",
    INVENTORY: "warehouse",
    REVIEWS: "reviews",
    WALLET: "toll",
    STAFF_QUEUE: "assignment",
  };

  function start() {
    var root = document.getElementById("mp-notif");
    if (!root) return;

    var summary = root.querySelector("summary");
    var badge = root.querySelector(".mp-notif-badge");
    var body = root.querySelector("[data-notif-body]");
    var readAll = root.querySelector("[data-notif-readall]");
    var tokenInput = document.querySelector("#logout-form input[name=csrfmiddlewaretoken]");
    var csrf = tokenInput ? tokenInput.value : "";
    var appUrl = root.dataset.appUrl.replace(/\/+$/, "");
    var unread = parseInt(root.dataset.unread, 10) || 0;
    var items = [];
    var loadedAt = 0;

    function setUnread(count) {
      unread = Math.max(0, count);
      badge.hidden = unread === 0;
      badge.textContent = unread > 99 ? "99+" : String(unread);
      summary.setAttribute(
        "aria-label",
        unread === 0 ? "Notifications" : unread + " unread notification" + (unread === 1 ? "" : "s")
      );
      readAll.disabled = unread === 0;
    }

    function getJson(url) {
      return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(
        function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        }
      );
    }

    function post(url, keepalive) {
      return fetch(url, {
        method: "POST",
        credentials: "same-origin",
        keepalive: !!keepalive,
        headers: { "X-CSRFToken": csrf, Accept: "application/json" },
      });
    }

    function recount() {
      getJson(root.dataset.countUrl)
        .then(function (data) {
          if (typeof data.unread === "number") setUnread(data.unread);
        })
        .catch(function () {
          // Offline or throttled: keep the last number rather than flash to 0.
        });
    }

    function ago(iso) {
      var then = new Date(iso).getTime();
      if (isNaN(then)) return "";
      var minutes = Math.floor((loadedAt - then) / 60000);
      if (minutes < 1) return "just now";
      if (minutes < 60) return minutes + " min ago";
      var hours = Math.floor(minutes / 60);
      if (hours < 24) return hours + " h ago";
      var days = Math.floor(hours / 24);
      if (days < 7) return days + " d ago";
      return new Date(iso).toLocaleDateString();
    }

    function el(tag, className, text) {
      var node = document.createElement(tag);
      if (className) node.className = className;
      if (text) node.textContent = text;
      return node;
    }

    function showState(text, withRetry) {
      body.replaceChildren();
      var p = el("p", "mp-notif-state", text);
      if (withRetry) {
        var retry = el("button", "mp-notif-retry", "Retry");
        retry.type = "button";
        retry.addEventListener("click", load);
        p.appendChild(document.createElement("br"));
        p.appendChild(retry);
      }
      body.appendChild(p);
    }

    function markRead(item) {
      if (item.read_at !== null) return;
      item.read_at = new Date().toISOString();
      setUnread(unread - 1);
      render();
      // keepalive lets the request finish even as the link opens.
      post(root.dataset.readUrl.replace("/0/", "/" + item.id + "/"), true).catch(function () {});
    }

    function renderItem(item) {
      var isUnread = item.read_at === null;
      var node = item.action_url ? el("a", "mp-notif-item") : el("button", "mp-notif-item");
      if (item.action_url) {
        node.href = appUrl + item.action_url;
        node.target = "_blank";
        node.rel = "noopener noreferrer";
      } else {
        node.type = "button";
      }
      if (isUnread) node.classList.add("is-unread");
      if (item.priority === "HIGH") node.classList.add("is-high");

      var icon = el("span", "mp-notif-icon");
      icon.setAttribute("aria-hidden", "true");
      icon.appendChild(el("span", "material-symbols-outlined", ICONS[item.category] || "notifications"));

      var text = el("span", "mp-notif-text");
      text.appendChild(el("span", "mp-notif-item-title", item.title));
      if (item.body) text.appendChild(el("span", "mp-notif-item-body", item.body));
      var time = el("time", "mp-notif-item-time", ago(item.occurred_at));
      time.dateTime = item.occurred_at;
      text.appendChild(time);

      node.appendChild(icon);
      node.appendChild(text);
      if (isUnread) {
        var dot = el("span", "mp-notif-dot");
        dot.appendChild(el("span", "visually-hidden", "Unread"));
        node.appendChild(dot);
      }
      node.addEventListener("click", function () {
        markRead(item);
      });
      return node;
    }

    function render() {
      if (!items.length) {
        showState("You're all caught up.");
        return;
      }
      var list = el("div", "mp-notif-list");
      items.forEach(function (item) {
        list.appendChild(renderItem(item));
      });
      body.replaceChildren(list);
    }

    function load() {
      showState("Loading your notifications…");
      getJson(root.dataset.listUrl)
        .then(function (page) {
          loadedAt = Date.now();
          items = (page.results || []).slice(0, SHOWN);
          render();
        })
        .catch(function () {
          showState("Notifications couldn't be loaded.", true);
        });
      recount();
    }

    // On phones the panel is pinned to the screen's width (CSS); the header
    // wraps there, so put it just under wherever the bell ended up.
    var phone = window.matchMedia("(max-width: 600px)");
    var panel = root.querySelector(".mp-notif-panel");
    function place() {
      panel.style.top = phone.matches ? Math.round(summary.getBoundingClientRect().bottom + 8) + "px" : "";
    }

    root.addEventListener("toggle", function () {
      if (!root.open) return;
      place();
      load();
    });

    readAll.addEventListener("click", function () {
      readAll.disabled = true;
      post(root.dataset.readAllUrl)
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          var now = new Date().toISOString();
          items.forEach(function (item) {
            if (item.read_at === null) item.read_at = now;
          });
          setUnread(0);
          render();
        })
        .catch(function () {
          readAll.disabled = unread === 0;
          showState("Notifications couldn't be marked as read.", true);
        });
    });

    window.setInterval(function () {
      if (document.visibilityState === "visible") recount();
    }, POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") recount();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
