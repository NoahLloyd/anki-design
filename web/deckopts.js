/* Anki Design — custom deck-options menu behavior.

   Triggered by `window.__adDeckOpts(deckId, event)`, called from the gear
   button next to the deck name. Renders a small floating menu anchored to
   the gear; clicking an item dispatches a `ba:deck:<action>:<did>` pycmd
   for Python to handle. */
(function () {
  "use strict";
  if (window.__adDeckOpts) return;

  var CURRENT = null;  // active menu DOM node, if any

  function icon(paths) {
    return '<svg class="ad-menu-icon" viewBox="0 0 24 24" fill="none" '
         + 'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
         + 'stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>';
  }

  // Lightweight stroke set matching the sidebar icons.
  var ICONS = {
    rename:  '<path d="M4 20h4l11-11-4-4L4 16v4z"/><path d="M14 6l4 4"/>',
    options: '<circle cx="12" cy="12" r="3"/>'
           + '<path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1'
           + 'a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1'
           + 'a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8'
           + 'l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4'
           + 'h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 '
           + '2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h0a1.6 1.6 0 0 0 1-1.5V3a2 2 0 '
           + '0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5h0a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 '
           + '2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v0a1.6 1.6 0 0 0 1.5 '
           + '1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
    export:  '<path d="M12 16V4"/><path d="M6 10l6-6 6 6"/><path d="M4 20h16"/>',
    rebuild: '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/>',
    empty:   '<path d="M3 6h18"/><path d="M8 6V4h8v2"/>'
           + '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    delete:  '<path d="M3 6h18"/><path d="M8 6V4h8v2"/>'
           + '<path d="M10 11v6"/><path d="M14 11v6"/>'
           + '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  };

  // Each entry: { cmd, label, icon, danger?, sep_before? }
  var ITEMS = [
    { cmd: "rename",  label: "Rename",           icon: "rename" },
    { cmd: "options", label: "Options…",         icon: "options" },
    { cmd: "export",  label: "Export deck…",     icon: "export" },
    { cmd: "rebuild", label: "Rebuild (filtered)", icon: "rebuild" },
    { cmd: "empty",   label: "Empty (filtered)",   icon: "empty" },
    { cmd: "delete",  label: "Delete deck",      icon: "delete", danger: true, sep_before: true },
  ];

  function send(cmd) {
    try { if (typeof pycmd === "function") pycmd("ba:" + cmd); } catch (e) {}
  }

  function close() {
    if (!CURRENT) return;
    var node = CURRENT;
    CURRENT = null;
    node.classList.remove("ad-menu--open");
    // Allow the transition to finish before removing from the DOM.
    setTimeout(function () {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    }, 160);
    document.removeEventListener("mousedown", outsideClick, true);
    document.removeEventListener("keydown", escClose, true);
    window.removeEventListener("resize", close);
    window.removeEventListener("scroll", close, true);
  }

  function outsideClick(e) {
    if (!CURRENT) return;
    if (CURRENT.contains(e.target)) return;
    close();
  }
  function escClose(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  function build(did) {
    var menu = document.createElement("div");
    menu.className = "ad-menu";
    menu.setAttribute("role", "menu");
    var html = "";
    ITEMS.forEach(function (it) {
      if (it.sep_before) html += '<div class="ad-menu-sep" role="separator"></div>';
      var cls = "ad-menu-item" + (it.danger ? " ad-menu-danger" : "");
      html += '<button type="button" class="' + cls + '" role="menuitem" '
            + 'data-cmd="' + it.cmd + '">'
            +   icon(ICONS[it.icon] || "")
            +   '<span class="ad-menu-l">' + it.label + '</span>'
            + '</button>';
    });
    menu.innerHTML = html;

    Array.prototype.forEach.call(menu.querySelectorAll(".ad-menu-item"), function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var cmd = btn.getAttribute("data-cmd");
        close();
        // Rename happens inline on the home-page row when possible.
        // Falls back to the native dialog (handled by Python) if the
        // row isn't visible — e.g., we're on the overview header.
        if (cmd === "rename" && startInlineRename(did)) return;
        send("deck:" + cmd + ":" + did);
      });
    });

    return menu;
  }

  /* Inline rename — swap the deck-name anchor with a real <input> styled
     identically so the row visually doesn't change. Enter submits via
     pycmd; Escape or empty/unchanged blur restores the anchor. Exposed
     as `window.__adStartDeckRename` for keyboard / programmatic entry
     points (e.g., from a F2 shortcut or screenshot harness).

     We use a native <input>, not contenteditable: Qt WebEngine's editing
     commands on contenteditable have unpredictable interactions with
     Anki's top-level shortcuts (Backspace, etc.), whereas <input>'s
     keyboard handling is rock-solid because the browser owns it. */
  window.__adStartDeckRename = startInlineRename;
  function startInlineRename(did) {
    // Two entry points share this flow: the deck row in the multi-deck
    // table (`a.deck` inside `tr.deck`) and the single-deck hero header
    // (`h1.ba-deck-name`). The latter is tagged with `data-did` so we can
    // pick the right one. The hero header is checked first because in
    // single-deck mode Anki still renders the (hidden) `tr.deck` row in
    // the DOM, and we want to edit the visible name, not the hidden one.
    var anchor = document.querySelector('h1.ba-deck-name[data-did="' + did + '"]');
    if (anchor && anchor.offsetParent === null) anchor = null;
    if (!anchor) {
      anchor = document.querySelector('tr.deck[id="' + did + '"] td.decktd > a.deck');
      if (anchor && anchor.offsetParent === null) anchor = null;
    }
    if (!anchor) return false;
    if (anchor.parentNode.querySelector(".ad-deck-rename")) return true; // editing

    var original = anchor.textContent;
    var input = document.createElement("input");
    input.type = "text";
    input.className = "ad-deck-rename";
    if (anchor.tagName && anchor.tagName.toLowerCase() === "h1") {
      input.classList.add("ad-deck-rename--hero");
    }
    if (anchor.classList.contains("filtered")) input.classList.add("filtered");
    input.spellcheck = false;
    input.setAttribute("aria-label", "Rename deck");
    input.value = original;
    // Auto-size to the current text so the field hugs the name like the
    // anchor did. `size` is in `ch`; bump by a couple so the caret has
    // breathing room and the field doesn't visibly grow as you type.
    function autosize() {
      input.size = Math.max((input.value || "").length + 2, 4);
    }
    autosize();
    input.addEventListener("input", autosize);

    anchor.style.display = "none";
    anchor.parentNode.insertBefore(input, anchor.nextSibling);

    // Prevent the row's open-deck click handler from firing while editing.
    input.addEventListener("mousedown", function (e) { e.stopPropagation(); });
    input.addEventListener("click", function (e) { e.stopPropagation(); });

    var done = false;
    function cancel() {
      if (done) return;
      done = true;
      if (input.parentNode) input.parentNode.removeChild(input);
      anchor.style.display = "";
    }
    function commit() {
      if (done) return;
      var v = (input.value || "").trim();
      if (!v || v === original) { cancel(); return; }
      done = true;
      input.disabled = true;
      try {
        pycmd("ba:deck:rename-to:" + did + ":" + encodeURIComponent(v));
      } catch (e) {}
    }
    input.addEventListener("keydown", function (e) {
      // Stop propagation on every key so Anki's top-level QShortcuts
      // (`a`, `b`, `d`, `s`, `t`, `y`) don't fire while typing a name.
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        cancel();
      }
    });
    input.addEventListener("keyup", function (e) { e.stopPropagation(); });
    input.addEventListener("keypress", function (e) { e.stopPropagation(); });
    input.addEventListener("blur", function () { commit(); });

    // Focus + select-all on the next frame so layout settles first.
    requestAnimationFrame(function () {
      input.focus();
      try { input.select(); } catch (_) {}
    });
    return true;
  }

  function position(menu, anchor) {
    var r = anchor.getBoundingClientRect();
    // Render off-screen first to measure.
    menu.style.visibility = "hidden";
    document.body.appendChild(menu);
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    var pad = 6;
    // Default: below the gear, right-aligned with it. Flip up if not enough room.
    var top = window.scrollY + r.bottom + pad;
    if (r.bottom + pad + mh > window.innerHeight) {
      top = window.scrollY + r.top - pad - mh;
    }
    var left = window.scrollX + r.right - mw;
    if (left < window.scrollX + 8) left = window.scrollX + 8;
    menu.style.top = top + "px";
    menu.style.left = left + "px";
    menu.style.visibility = "";
  }

  window.__adDeckOpts = function (did, evt) {
    if (evt) {
      evt.preventDefault();
      evt.stopPropagation();
    }
    // The shared deck-list (__adDeckList.render) delegates clicks on the
    // row container, so evt.currentTarget there is the whole list — too
    // wide to anchor a menu off, which puts the menu at the bottom of the
    // list instead of next to the clicked gear. Walk up from the real
    // click target to the gear button first; fall back to currentTarget
    // for the non-delegated callers (single-deck hero, Anki's native
    // gear anchor, the congrats title).
    var anchor = null;
    if (evt) {
      if (evt.target && evt.target.closest) {
        anchor = evt.target.closest('.ad-list-gear');
      }
      if (!anchor) anchor = evt.currentTarget;
    }
    // Toggle off if clicking the same gear that opened the menu.
    if (CURRENT && CURRENT._anchor === anchor) {
      close();
      return;
    }
    close();
    if (!anchor) return;
    var menu = build(did);
    menu._anchor = anchor;
    position(menu, anchor);
    // Stagger the open class one frame so the transition runs.
    requestAnimationFrame(function () { menu.classList.add("ad-menu--open"); });
    CURRENT = menu;
    document.addEventListener("mousedown", outsideClick, true);
    document.addEventListener("keydown", escClose, true);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    // Focus the first item for keyboard access.
    var first = menu.querySelector(".ad-menu-item");
    if (first) first.focus();
  };

  /* Wire the native gear `<a>` (Anki renders one per deck row in the home
     table) so it opens our custom menu instead of Anki's QMenu. Without
     this, multi-deck home pages would still get the legacy modal-based
     rename and the rest of the native deck-options dialog. */
  function wireGears() {
    var gears = document.querySelectorAll("tr.deck img.gears");
    for (var i = 0; i < gears.length; i++) {
      var a = gears[i].closest("a");
      if (!a || a.__adGearWired) continue;
      var row = a.closest("tr.deck");
      if (!row || !row.id) continue;
      a.__adGearWired = true;
      // Drop Anki's inline `onclick='return pycmd("opts:<did>")'` so the
      // QMenu never opens, then own the click ourselves.
      a.removeAttribute("onclick");
      (function (anchor, did) {
        anchor.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          // currentTarget is the anchor so position() can anchor the menu
          // off the actual gear cell.
          window.__adDeckOpts(did, e);
        });
      })(a, row.id);
    }
  }

  function initGears() {
    wireGears();
    if (window.MutationObserver) {
      // Anki re-renders the deck list after operations (study, rename,
      // collapse). Coalesce mutations into one rAF tick before re-wiring.
      var pending = 0;
      var mo = new MutationObserver(function () {
        if (pending) return;
        pending = requestAnimationFrame(function () {
          pending = 0;
          wireGears();
        });
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGears);
  } else {
    initGears();
  }
})();
