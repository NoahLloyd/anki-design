/* Anki Design — expandable parent decks on the homepage.

   Anki's tree is always rendered fully expanded by us
   (see _patch_deck_tree_always_expanded in __init__.py), so every row
   is in the DOM. This script identifies parent rows (those whose
   immediately-following rows are indented deeper), replaces Anki's
   `+ / -` text toggle with a chevron button, and folds descendants
   in-place. State is session-only (sessionStorage) — we don't touch
   the backend collapse flags. */
(function () {
  "use strict";
  if (window.__adDeckTreeWired) return;
  window.__adDeckTreeWired = true;

  var STORAGE_KEY = "__adCollapsedDecks";

  // Down-pointing chevron at rest (matches existing chevron-down.svg).
  // CSS rotates it -90° to point right when .ad-collapsed.
  var CHEV_SVG =
    '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true"><polyline points="3,4.6 6,7.6 9,4.6"/></svg>';

  function loadState() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) { return {}; }
  }
  function saveState(s) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s)); }
    catch (_) {}
  }

  // Anki indents children with `&nbsp;` * 6 * (level-1). The nbsps live
  // in the leading text node of td.decktd; counting them gives the row
  // its depth.
  function levelOf(row) {
    var td = row.querySelector("td.decktd");
    if (!td) return 0;
    var text = "";
    for (var n = td.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) { text += n.nodeValue; continue; }
      break;
    }
    var nbsp = (text.match(/ /g) || []).length;
    return Math.floor(nbsp / 6);
  }

  // Build per-row metadata: level, direct kids (used to detect "is parent"),
  // and immediate parent (used to walk the ancestor chain for visibility).
  function buildIndex(rows) {
    var meta = [];
    for (var i = 0; i < rows.length; i++) {
      meta.push({ row: rows[i], level: levelOf(rows[i]), kids: [], parent: null });
    }
    var stack = [];
    for (var i = 0; i < meta.length; i++) {
      while (stack.length && meta[stack[stack.length - 1]].level >= meta[i].level) {
        stack.pop();
      }
      if (stack.length) {
        var p = stack[stack.length - 1];
        meta[i].parent = meta[p].row;
        meta[p].kids.push(meta[i].row);
      }
      stack.push(i);
    }
    return meta;
  }

  // A row is hidden iff any ancestor has state[id] === truthy. This keeps
  // nested collapses correct: grandparent expanded + parent collapsed
  // should still hide the grandchild.
  function applyVisibility(meta, state) {
    var parentMap = new Map();
    for (var i = 0; i < meta.length; i++) parentMap.set(meta[i].row, meta[i].parent);
    for (var i = 0; i < meta.length; i++) {
      var row = meta[i].row;
      var hide = false;
      var p = parentMap.get(row);
      while (p) {
        if (state[p.id]) { hide = true; break; }
        p = parentMap.get(p);
      }
      row.classList.toggle("ad-hidden", hide);
    }
  }

  function makeChevron(did, collapsed) {
    var a = document.createElement("a");
    a.className = "collapse ad-chev" + (collapsed ? " ad-collapsed" : "");
    a.href = "#";
    a.setAttribute("role", "button");
    a.setAttribute("tabindex", "-1");
    a.setAttribute("aria-label",
                   collapsed ? "Expand sub-decks" : "Collapse sub-decks");
    a.setAttribute("data-did", did);
    a.innerHTML = CHEV_SVG;
    return a;
  }

  // Idempotent: safe to run repeatedly. Looks at the row's current state
  // and brings it in line with the desired classification (parent vs leaf).
  // The wire pass can be triggered by the MutationObserver before Anki has
  // finished appending child rows — so a row's parent/leaf status may flip
  // between passes. Don't cache a "wired" flag; reconcile every time.
  function wireRow(entry, state, onToggle) {
    var row = entry.row;
    var col = row.querySelector(
      ":scope > td.decktd > a.collapse, :scope > td.decktd > span.collapse"
    );
    if (!col) return;

    var isParent = entry.kids.length > 0;
    var hasChev = col.classList.contains("ad-chev");
    var hasSpacer = col.classList.contains("ad-spacer");

    if (isParent) {
      if (hasChev) return;                      // already a chevron parent
      var did = row.id;
      var btn = makeChevron(did, !!state[did]);
      col.replaceWith(btn);
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var s = loadState();
        var now = !s[did];
        if (now) s[did] = 1; else delete s[did];
        saveState(s);
        btn.classList.toggle("ad-collapsed", now);
        btn.setAttribute("aria-label",
                         now ? "Expand sub-decks" : "Collapse sub-decks");
        onToggle(s);
      });
      return;
    }

    // Leaf.
    if (hasSpacer && !hasChev) return;
    col.classList.remove("ad-chev", "ad-collapsed");
    col.classList.add("ad-spacer");
  }

  function wire() {
    var rows = document.querySelectorAll("tr.deck");
    if (!rows.length) return;
    var meta = buildIndex(rows);
    var state = loadState();
    function onToggle(newState) { applyVisibility(meta, newState); }
    for (var i = 0; i < meta.length; i++) wireRow(meta[i], state, onToggle);
    applyVisibility(meta, state);
  }

  function init() {
    wire();
    if (window.MutationObserver) {
      // Anki re-renders the deck browser after operations (study, rename,
      // etc.). Coalesce mutations into one rAF tick before re-wiring.
      var pending = 0;
      var mo = new MutationObserver(function () {
        if (pending) return;
        pending = requestAnimationFrame(function () { pending = 0; wire(); });
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
