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
        send("deck:" + cmd + ":" + did);
      });
    });

    return menu;
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
    var anchor = evt && evt.currentTarget;
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
})();
