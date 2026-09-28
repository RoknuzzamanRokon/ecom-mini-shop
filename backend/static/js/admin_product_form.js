/* Product add / change form (templates/admin/shop/product/change_form.html).

   Progressive enhancement only. Every control touched here is a real form
   input that posts the same way without this script; the script adds:

     * Main photo: instant preview of a picked or dropped file, and unticking
       Remove when a new file is picked (Django rejects a form sending both).
     * Gallery: "Add photos" creates one inline row per picked or dropped
       image through inlines.js's own add link, then moves the file into the
       row's input. Tiles preview replacements, show in Position order, and
       drag to reorder, which rewrites the Position inputs 1..n.
     * Pricing: a live discount line under Old price, and quick-pick chips
       for the badge values the storefront styles.
     * Visibility: the storefront checklist re-runs as Status, Active,
       Category and Shop change, from json_script "mp-product-data".
     * The storefront preview card follows the form.

   Loaded with `defer`, so the DOM is parsed but inlines.js may not have set
   up yet (jQuery runs ready handlers after DOMContentLoaded). Nothing here
   depends on its setup order: its add link is looked up when needed, and
   gallery events are delegated so they reach rows it clones later. */
(function () {
  "use strict";

  var form = document.getElementById("product_form");
  if (!form) return;

  var data = { categories: {}, shops: {} };
  try {
    var dataNode = document.getElementById("mp-product-data");
    if (dataNode) data = JSON.parse(dataNode.textContent) || data;
  } catch (err) { /* keep the empty maps: the checklist keeps its saved state */ }

  function one(selector, root) { return (root || document).querySelector(selector); }
  function all(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function field(name) { return document.getElementById("id_" + name); }

  var canMoveFiles = (function () {
    try { return typeof DataTransfer === "function" && !!new DataTransfer().items; }
    catch (err) { return false; }
  })();

  function isImage(file) { return !!file && /^image\//.test(file.type); }

  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    return !!types && Array.prototype.indexOf.call(types, "Files") !== -1;
  }

  function putFile(input, file) {
    var transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
  }

  /* One object URL per input, released when its file changes. */
  function previewUrl(input) {
    if (!input) return "";
    var file = input.files && input.files[0];
    if (input._mpFile === file) return input._mpUrl || "";
    if (input._mpUrl) URL.revokeObjectURL(input._mpUrl);
    input._mpFile = file;
    input._mpUrl = file ? URL.createObjectURL(file) : "";
    return input._mpUrl;
  }

  function amount(value) {
    if (value === undefined || value === null || String(value).trim() === "") return null;
    var n = Number(String(value).replace(/,/g, ""));
    return isFinite(n) ? n : null;
  }

  function taka(n) {
    return "৳" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  var listeners = [];
  function onRefresh(fn) { listeners.push(fn); }
  function refresh() { listeners.forEach(function (fn) { fn(); }); }

  /* -- Main photo ------------------------------------------------------- */
  var cover = one("[data-mp-cover]");
  var coverInput = cover && one("[data-mp-cover-input]", cover);
  var coverClear = cover && one("[data-mp-cover-clear]", cover);
  var coverImg = cover && one("[data-mp-cover-img]", cover);
  var savedCoverSrc = coverImg ? coverImg.getAttribute("src") || "" : "";

  /* The main photo as it will be after saving: a new file, the saved one, or none. */
  function coverSrc() {
    if (!cover) return savedCoverSrc;
    var fresh = previewUrl(coverInput);
    if (fresh) return fresh;
    return coverClear && coverClear.checked ? "" : savedCoverSrc;
  }

  function renderCover() {
    if (!cover) return;
    var fresh = previewUrl(coverInput);
    var cleared = !fresh && !!(coverClear && coverClear.checked);
    var src = fresh || savedCoverSrc;
    var empty = one("[data-mp-cover-empty]", cover);
    var state = one("[data-mp-cover-state]", cover);
    var label = one("[data-mp-cover-upload-label]", cover);
    var fileLine = one("[data-mp-cover-file]", cover);

    if (src) coverImg.src = src; else coverImg.removeAttribute("src");
    coverImg.hidden = !src;
    empty.hidden = !!src;
    cover.classList.toggle("is-changed", !!fresh);
    cover.classList.toggle("is-cleared", cleared);

    state.hidden = !fresh && !cleared;
    state.textContent = fresh ? "New photo · saved with the product" : cleared ? "Removed when you save" : "";

    if (coverClear) {
      var clearButton = coverClear.parentNode;
      one(".material-symbols-outlined", clearButton).textContent = coverClear.checked ? "undo" : "delete";
      one("span:last-child", clearButton).textContent = coverClear.checked ? "Undo" : "Remove";
    }
    if (label) label.textContent = src ? "Replace" : "Upload";
    if (fileLine) {
      if (!fileLine._mpText) fileLine._mpText = fileLine.textContent;
      fileLine.textContent = fresh ? coverInput.files[0].name : fileLine._mpText;
    }
  }

  if (cover) {
    coverInput.addEventListener("change", function () {
      if (coverInput.files.length && coverClear) coverClear.checked = false;
      renderCover();
      refresh();
    });
    if (coverClear) {
      coverClear.addEventListener("change", function () {
        if (coverClear.checked) coverInput.value = "";
        renderCover();
        refresh();
      });
    }

    var frame = one("[data-mp-cover-frame]", cover);
    frame.addEventListener("dragover", function (event) {
      if (!hasFiles(event) || !canMoveFiles) return;
      event.preventDefault();
      frame.classList.add("is-drop");
    });
    frame.addEventListener("dragleave", function () { frame.classList.remove("is-drop"); });
    frame.addEventListener("drop", function (event) {
      if (!hasFiles(event) || !canMoveFiles) return;
      event.preventDefault();
      frame.classList.remove("is-drop");
      var file = Array.prototype.filter.call(event.dataTransfer.files, isImage)[0];
      if (!file) return;
      putFile(coverInput, file);
      coverInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  /* -- Gallery ------------------------------------------------------------ */
  var gallery = one("[data-mp-gallery]");
  var grid = gallery && one("[data-mp-gallery-grid]", gallery);
  var addTile = gallery && one("[data-mp-add]", gallery);
  var TILE = ".inline-related.mp-tile:not(.empty-form)";

  function tiles() { return grid ? all(TILE, grid) : []; }
  function tileFile(tile) { return one('input[type="file"]', tile); }
  function tileOrder(tile) { return one('input[name$="-order"]', tile); }
  function tileRemoved(tile) {
    var box = one('input[name$="-DELETE"]', tile);
    return !!(box && box.checked);
  }
  function tileIsSaved(tile) { return tile.classList.contains("has_original"); }
  function tileHasPhoto(tile) {
    var input = tileFile(tile);
    return tileIsSaved(tile) || !!(input && input.files && input.files.length);
  }

  function renderTile(tile) {
    var img = one("[data-mp-tile-img]", tile);
    var flag = one("[data-mp-tile-flag]", tile);
    var input = tileFile(tile);
    if (!img) return;
    if (!("mpSaved" in img.dataset)) img.dataset.mpSaved = tileIsSaved(tile) ? img.getAttribute("src") || "" : "";
    var fresh = previewUrl(input);
    var src = fresh || img.dataset.mpSaved;
    if (src) img.src = src; else img.removeAttribute("src");
    img.hidden = !src;
    tile.classList.toggle("has-photo", !!src);
    tile.classList.toggle("is-replaced", !!fresh && tileIsSaved(tile));
    if (flag) {
      flag.hidden = !fresh;
      flag.textContent = fresh ? (tileIsSaved(tile) ? "Replaced" : "New") : "";
    }
  }

  function nextPosition() {
    var highest = 0;
    tiles().forEach(function (tile) {
      var order = tileOrder(tile);
      if (order && tileHasPhoto(tile) && !tileRemoved(tile)) {
        highest = Math.max(highest, parseInt(order.value, 10) || 0);
      }
    });
    return highest + 1;
  }

  /* One inline row per image, made by inlines.js's own add link so the
     management form and row indexes stay its business. */
  function addFiles(files) {
    var addLink = gallery.querySelector(".add-row a");
    var template = gallery.querySelector(".inline-related.empty-form");
    if (!addLink || !template) return;
    Array.prototype.filter.call(files, isImage).forEach(function (file) {
      var position = nextPosition();
      addLink.click();
      var row = template.previousElementSibling;
      if (!row || !row.classList.contains("mp-tile")) return;
      putFile(tileFile(row), file);
      var order = tileOrder(row);
      if (order) order.value = position;
      renderTile(row);
    });
    showInPositionOrder();
    refresh();
  }

  /* Tiles are shown in Position order with the CSS `order` property; the
     DOM keeps formset order (saved rows, then new ones). It has to: when an
     unsaved row is removed, inlines.js renumbers every row's prefix index by
     DOM position, and a saved row moved behind a new one would lose its pk
     binding. Ties keep DOM order, as the gallery's ("order", "id") ordering
     does. A new tile without a photo yet sits at the end. */
  var LAST = 100000;

  function tilePosition(tile) {
    var order = tileOrder(tile);
    var n = order ? parseInt(order.value, 10) : NaN;
    return tileHasPhoto(tile) && isFinite(n) ? n : LAST;
  }

  function showInPositionOrder() {
    tiles().forEach(function (tile) {
      if (tileOrder(tile)) tile.style.order = tilePosition(tile);
    });
  }

  function visualTiles() {
    return tiles()
      .map(function (tile, index) { return { tile: tile, index: index, at: Number(tile.style.order) || 0 }; })
      .sort(function (a, b) { return a.at - b.at || a.index - b.index; })
      .map(function (entry) { return entry.tile; });
  }

  /* Positions 1..n in the given sequence. Tiles marked for removal are
     numbered too, so they hold their place; a deleted row is never saved.
     A new tile without a photo is left alone: giving it a position would
     make it a changed form, which then fails for want of an image. */
  function renumber(sequence) {
    var position = 0;
    sequence.forEach(function (tile) {
      var order = tileOrder(tile);
      if (!order || !tileHasPhoto(tile)) return;
      position += 1;
      if (String(order.value) !== String(position)) order.value = position;
    });
    showInPositionOrder();
  }

  if (gallery && grid) {
    tiles().forEach(renderTile);
    showInPositionOrder();

    if (addTile && canMoveFiles) addTile.hidden = false;

    grid.addEventListener("change", function (event) {
      var target = event.target;
      if (target.matches("[data-mp-add-input]")) {
        addFiles(target.files);
        target.value = "";
        return;
      }
      var tile = target.closest(TILE);
      if (!tile) return;
      if (target.type === "file") {
        var order = tileOrder(tile);
        if (!tileIsSaved(tile) && order && target.files.length && (order.value === "" || order.value === "0")) {
          order.value = nextPosition();
        }
        renderTile(tile);
      }
      // A typed Position moves its tile once committed (change, not input).
      showInPositionOrder();
      refresh();
    });

    // Rows inlines.js removes (the X on an unsaved tile).
    document.addEventListener("formset:removed", function (event) {
      if (event.detail && event.detail.formsetName && gallery.id === event.detail.formsetName + "-group") refresh();
    });

    // Files dropped anywhere on the gallery become new rows.
    var dragging = null;
    gallery.addEventListener("dragover", function (event) {
      if (dragging || !hasFiles(event) || !canMoveFiles) return;
      event.preventDefault();
      gallery.classList.add("is-drop");
    });
    gallery.addEventListener("dragleave", function (event) {
      if (!gallery.contains(event.relatedTarget)) gallery.classList.remove("is-drop");
    });
    gallery.addEventListener("drop", function (event) {
      if (dragging || !hasFiles(event) || !canMoveFiles) return;
      event.preventDefault();
      gallery.classList.remove("is-drop");
      addFiles(event.dataTransfer.files);
    });

    // Reorder by dragging a tile. Only tiles with a Position input move
    // (never on a view-only form), and never from inside a text box.
    grid.addEventListener("pointerdown", function (event) {
      var tile = event.target.closest(TILE);
      if (!tile) return;
      tile.draggable = !!tileOrder(tile) && tileHasPhoto(tile) && !event.target.closest("input, textarea, select");
    });
    grid.addEventListener("dragstart", function (event) {
      var tile = event.target.closest && event.target.closest(TILE);
      if (!tile || !tile.draggable) return;
      dragging = tile;
      tile.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      try { event.dataTransfer.setData("text/plain", tile.id); } catch (err) { /* old Edge */ }
    });
    grid.addEventListener("dragover", function (event) {
      if (!dragging) return;
      event.preventDefault();
      var over = event.target.closest(TILE);
      if (!over || over === dragging || !tileHasPhoto(over)) return;
      var box = over.getBoundingClientRect();
      var before = event.clientX - box.left < box.width / 2;
      var sequence = visualTiles().filter(function (tile) { return tile !== dragging; });
      sequence.splice(sequence.indexOf(over) + (before ? 0 : 1), 0, dragging);
      renumber(sequence);
    });
    grid.addEventListener("drop", function (event) {
      if (dragging) event.preventDefault();
    });
    grid.addEventListener("dragend", function () {
      if (!dragging) return;
      dragging.classList.remove("is-dragging");
      dragging.draggable = false;
      dragging = null;
      refresh();
    });

    // No way to move files between inputs: fall back to Django's add link.
    if (!canMoveFiles) gallery.classList.add("mp-gallery-fallback");
  }

  /* -- Photo count in the card header -------------------------------------- */
  var countNode = one("[data-mp-photo-count]");
  onRefresh(function () {
    // No main-photo widget means a view-only form: keep the server's count.
    if (!countNode || !cover) return;
    var n = coverSrc() ? 1 : 0;
    tiles().forEach(function (tile) {
      if (tileHasPhoto(tile) && !tileRemoved(tile)) n += 1;
    });
    countNode.textContent = n ? n + (n === 1 ? " photo" : " photos") : "";
  });

  /* -- Pricing: discount line and badge chips ------------------------------ */
  var price = field("price");
  var oldPrice = field("old_price");
  var badge = field("badge");

  if (price && oldPrice) {
    var hint = document.createElement("p");
    hint.className = "mp-price-hint";
    hint.setAttribute("aria-live", "polite");
    var oldRow = oldPrice.closest(".form-row");
    (oldRow || oldPrice.parentNode).appendChild(hint);

    var renderHint = function () {
      var now = amount(price.value);
      var was = amount(oldPrice.value);
      hint.textContent = "";
      if (was === null) {
        hint.dataset.tone = "muted";
        hint.textContent = "No discount shown on the product card.";
      } else if (now !== null && was > now) {
        hint.dataset.tone = "ok";
        var struck = document.createElement("s");
        struck.textContent = taka(was);
        hint.append("Customers see ", struck, " " + taka(now) + " · " +
          Math.round((was - now) * 100 / was) + "% off, saving " + taka(was - now) + ".");
      } else {
        hint.dataset.tone = "warn";
        hint.textContent = "Not a discount: the old price should be higher than the price.";
      }
    };
    price.addEventListener("input", renderHint);
    oldPrice.addEventListener("input", renderHint);
    renderHint();
  }

  if (badge) {
    var chips = document.createElement("div");
    chips.className = "mp-badge-chips";
    chips.setAttribute("role", "group");
    chips.setAttribute("aria-label", "Quick badges");
    ["", "NEW", "HOT", "SALE", "TOP"].forEach(function (value) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "mp-badge-chip";
      chip.dataset.badge = value;
      chip.textContent = value || "None";
      chip.addEventListener("click", function () {
        badge.value = value;
        badge.dispatchEvent(new Event("input", { bubbles: true }));
      });
      chips.appendChild(chip);
    });
    badge.insertAdjacentElement("afterend", chips);

    var renderChips = function () {
      var current = badge.value.trim().toUpperCase();
      all(".mp-badge-chip", chips).forEach(function (chip) {
        chip.setAttribute("aria-pressed", String(chip.dataset.badge === current));
      });
    };
    badge.addEventListener("input", renderChips);
    renderChips();
  }

  /* -- Storefront checklist ------------------------------------------------ */
  var checklist = one("[data-mp-checklist]");
  var statusField = field("status");
  var activeField = field("is_active");
  var categoryField = field("category");
  var shopField = field("shop");

  function optionText(select) {
    var option = select.options[select.selectedIndex];
    return option ? option.text : "";
  }

  function renderChecklist() {
    if (!checklist) return;
    // A view-only form has no inputs: keep the saved result.
    if (!statusField && !activeField && !categoryField && !shopField) return;

    function set(key, ok, detail) {
      var row = one('[data-check="' + key + '"]', checklist);
      if (!row) return;
      row.classList.toggle("is-ok", ok);
      row.classList.toggle("is-fail", !ok);
      if (detail !== undefined) one("[data-check-detail]", row).textContent = detail;
      one("[data-check-state]", row).textContent = ok ? "passes" : "fails";
    }

    if (activeField) set("active", activeField.checked, activeField.checked ? "" : "Switched off");
    if (statusField) set("published", statusField.value === "PUBLISHED", optionText(statusField));
    if (categoryField) {
      var category = data.categories[categoryField.value];
      if (category) set("category", !!category.live, category.live ? category.name : category.name + " is inactive");
      else set("category", false, categoryField.value ? optionText(categoryField) + " (save to check)" : "None chosen");
    }
    if (shopField) {
      var shop = data.shops[shopField.value];
      if (shop) {
        set("shop", !!shop.live, shop.name);
        set("seller", !!shop.sellerLive, shop.seller);
      } else {
        var unknown = shopField.value ? optionText(shopField) + " (save to check)" : "None chosen";
        set("shop", false, unknown);
        set("seller", false, shopField.value ? "Save to check" : "No shop");
      }
    }

    var rows = all("[data-check]", checklist);
    var passed = rows.filter(function (row) { return row.classList.contains("is-ok"); }).length;
    var live = passed === rows.length;
    checklist.classList.toggle("is-live", live);
    one("[data-mp-checklist-title]", checklist).textContent =
      live ? "Visible on the storefront" : "Hidden from the storefront";
    one("[data-mp-checklist-score]", checklist).textContent = passed + "/" + rows.length;
  }

  [statusField, activeField, categoryField, shopField].forEach(function (input) {
    if (input) input.addEventListener("change", renderChecklist);
  });
  renderChecklist();

  /* -- Storefront preview -------------------------------------------------- */
  var preview = one("[data-mp-preview]");
  var nameField = field("name");

  function renderPreview() {
    if (!preview) return;
    // A view-only form has no inputs: keep the saved product.
    if (!nameField && !price) return;

    if (nameField) one("[data-mp-preview-name]", preview).textContent = nameField.value.trim() || "Product name";

    if (price) {
      var now = amount(price.value);
      // The card prints the API's decimal string, e.g. ৳1480.00.
      one("[data-mp-preview-price]", preview).textContent = "৳" + (now === null ? "0.00" : now.toFixed(2));
    }
    if (oldPrice) {
      var was = amount(oldPrice.value);
      var oldNode = one("[data-mp-preview-old]", preview);
      oldNode.hidden = was === null;
      oldNode.textContent = was === null ? "" : "৳" + was.toFixed(2);
    }
    if (badge) {
      var value = badge.value.trim().toUpperCase();
      var badgeNode = one("[data-mp-preview-badge]", preview);
      badgeNode.hidden = !value;
      badgeNode.textContent = value;
      badgeNode.dataset.badge = value;
    }
    if (categoryField) {
      var category = data.categories[categoryField.value];
      one("[data-mp-preview-category]", preview).textContent = category ? category.name : "General";
    }
    if (shopField) {
      var shop = data.shops[shopField.value];
      one("[data-mp-preview-shop-wrap]", preview).hidden = !shop;
      one("[data-mp-preview-shop]", preview).textContent = shop ? shop.name : "";
    }
    if (cover) {
      var src = coverSrc();
      var img = one("[data-mp-preview-img]", preview);
      if (src) img.src = src; else img.removeAttribute("src");
      img.hidden = !src;
      one("[data-mp-preview-noimg]", preview).hidden = !!src;
    }
  }

  [nameField, price, oldPrice, badge].forEach(function (input) {
    if (input) input.addEventListener("input", renderPreview);
  });
  [categoryField, shopField].forEach(function (input) {
    if (input) input.addEventListener("change", renderPreview);
  });
  onRefresh(renderPreview);

  renderCover();
  refresh();
})();
