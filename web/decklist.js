// Anki Design — shared deck-list primitives.
//
// Both the home-page tree and the congrats "Keep going" list render the
// same row shape:
//
//     [chevron]  [name]  [counts]  [gear]
//
// This module owns:
//
//   - the chevron / gear markup
//   - the collapse state (see "Collapse state" below)
//   - a generic visibility resolver for a flat, depth-tagged row list
//   - drag-to-move (reparenting) wiring
//
// Pages that consume this module own the DOM container; this module only
// cares about the data attributes (`data-did`, `data-depth`) and class
// hooks (`ad-list-row-hidden`).
(function () {
  "use strict";
  if (window.__adDeckList) return;

  // Down chevron at rest; CSS rotates it -90° when ad-list-chev--collapsed.
  var CHEV_SVG =
    '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" ' +
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true"><polyline points="3,4.6 6,7.6 9,4.6"/></svg>';

  // Use Anki's own gear bitmap so the icon visually matches Anki's other
  // chrome (browser, deck options dialog).
  var GEAR_HTML =
    '<img src="/_anki/imgs/gears.svg" class="ad-list-gear-img" alt="">';

  var STORAGE_KEY = "__adCollapsedDecks";
  var SEED_KEY = "__adCollapsedSeeded";

  function slice(list) { return Array.prototype.slice.call(list || []); }

  function listOpts() {
    var o = window.__baOpts && window.__baOpts.deckList;
    return o || {};
  }

  // ---- Collapse state --------------------------------------------------
  // Three modes (Settings → Deck list → "Sub-decks on startup"):
  //
  //   remember  — Anki's own persisted flag. Each row arrives with
  //               `collapsed` read from the collection; toggles are written
  //               back through Python (`ba:deck:collapse:<did>`), so the
  //               state survives restarts and syncs, and matches what
  //               AnkiMobile / AnkiWeb show. This is the default.
  //   expanded  — everything open at launch; toggles live for the session
  //               only (sessionStorage) and never touch the collection.
  //   collapsed — every parent closed at launch; same session-only toggles.
  function startupMode() {
    var m = listOpts().startup || "remember";
    return (m === "expanded" || m === "collapsed") ? m : "remember";
  }

  var memState = null;  // remember-mode working copy for this page

  function loadSession() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) { return {}; }
  }

  function saveSession(state) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
    catch (_) {}
  }

  // Build the starting collapse set for a render from the row data.
  function initialState(decks) {
    var mode = startupMode();
    var i;
    if (mode === "remember") {
      var st = {};
      for (i = 0; i < decks.length; i++) {
        if (decks[i].collapsed && decks[i].isParent) st[String(decks[i].did)] = 1;
      }
      memState = st;
      return st;
    }
    if (mode === "collapsed") {
      var seeded = false;
      try { seeded = sessionStorage.getItem(SEED_KEY) === "1"; } catch (_) {}
      if (!seeded) {
        var all = {};
        for (i = 0; i < decks.length; i++) {
          if (decks[i].isParent) all[String(decks[i].did)] = 1;
        }
        saveSession(all);
        try { sessionStorage.setItem(SEED_KEY, "1"); } catch (_) {}
        return all;
      }
    }
    return loadSession();
  }

  // Current collapse set — whatever the last render established.
  function loadCollapsed() {
    if (startupMode() === "remember") return memState || {};
    return loadSession();
  }

  function saveCollapsed(state) {
    if (startupMode() === "remember") { memState = state; return; }
    saveSession(state);
  }

  function toggle(did) {
    var key = String(did);
    if (startupMode() === "remember") {
      var s = memState || (memState = {});
      if (s[key]) delete s[key]; else s[key] = 1;
      // Persist through Anki's own collapse flag. We send the resulting
      // state (not "toggle") so rapid clicks can't drift out of step with
      // the backend; Python writes it without re-rendering the page.
      try {
        if (typeof pycmd === "function") {
          pycmd("ba:deck:collapse:" + key + ":" + (s[key] ? "1" : "0"));
        }
      } catch (_) {}
      return s;
    }
    var st = loadSession();
    if (st[key]) delete st[key]; else st[key] = 1;
    saveSession(st);
    return st;
  }

  // Walk a flat ordered list of rows. For each row, hide it iff any
  // ancestor (by depth) is in the collapsed set. `getDid(row)` returns the
  // deck id string; `getDepth(row)` returns a non-negative integer.
  function applyVisibility(rows, getDid, getDepth, state) {
    state = state || loadCollapsed();
    var stack = []; // { did, depth } entries, deepest last
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var depth = getDepth(row);
      while (stack.length && stack[stack.length - 1].depth >= depth) stack.pop();
      var hidden = false;
      for (var k = 0; k < stack.length; k++) {
        if (state[stack[k].did]) { hidden = true; break; }
      }
      row.classList.toggle("ad-list-row-hidden", hidden);
      stack.push({ did: getDid(row), depth: depth });
    }
  }

  // Build the inner HTML for a chevron control. `did` may be 0/empty for
  // a leaf — caller renders the spacer markup instead in that case.
  function chevronHTML(did, collapsed) {
    return '<button class="ad-list-chev'
      + (collapsed ? ' ad-list-chev--collapsed' : '')
      + '" type="button" data-did="' + did + '"'
      + ' aria-label="' + (collapsed ? 'Expand' : 'Collapse')
      + ' sub-decks" tabindex="-1">'
      + CHEV_SVG + '</button>';
  }

  function spacerHTML() {
    return '<span class="ad-list-chev ad-list-chev--spacer" aria-hidden="true"></span>';
  }

  function gearHTML(did) {
    return '<button class="ad-list-gear" type="button" data-did="' + did + '"'
      + ' title="Deck options" aria-label="Deck options">'
      + GEAR_HTML + '</button>';
  }

  // Update a chevron element's collapsed state visually + aria. Used by
  // page-specific click handlers after toggle().
  function paintChev(chevEl, collapsed) {
    chevEl.classList.toggle("ad-list-chev--collapsed", collapsed);
    chevEl.setAttribute("aria-label",
      (collapsed ? "Expand" : "Collapse") + " sub-decks");
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c];
    });
  }

  // Walk the (flat, depth-tagged) deck list and attach an `isParent` flag.
  // A row is a parent iff the NEXT row has a deeper depth.
  function annotateParents(decks) {
    var out = [];
    for (var i = 0; i < decks.length; i++) {
      var d = decks[i];
      var next = decks[i + 1];
      out.push({
        did: d.did,
        name: d.name,
        path: d.path || d.name,
        depth: d.depth || 0,
        new: d.new || 0,
        learn: d.learn || 0,
        review: d.review || 0,
        current: !!d.current,
        filtered: !!d.filtered,
        collapsed: !!d.collapsed,
        isParent: !!(next && (next.depth || 0) > (d.depth || 0)),
      });
    }
    return out;
  }

  function countCell(n, cls) {
    var z = !n ? ' zero' : '';
    return '<span class="' + cls + z + '">' + (n || 0) + '</span>';
  }

  function rowHTML(node, collapsedState) {
    var name = node.name == null ? '' : String(node.name);
    var depth = node.depth || 0;
    var did = node.did;
    var collapsed = !!(collapsedState && collapsedState[did]);
    var chev = node.isParent
      ? chevronHTML(did, collapsed)
      : spacerHTML();
    var attrs = ' data-did="' + did + '" data-depth="' + depth + '"';
    if (node.current)  attrs += ' data-current="true"';
    if (node.filtered) attrs += ' data-filtered="true"';
    return ''
      + '<div class="ad-list-row"' + attrs + '>'
      +   chev
      +   '<button class="ad-list-name" type="button" data-did="' + did + '">'
      +     escapeHTML(name)
      +   '</button>'
      +   '<span class="ad-list-counts">'
      +     countCell(node.new,    'new')
      +     countCell(node.learn,  'learn')
      +     countCell(node.review, 'review')
      +   '</span>'
      +   gearHTML(did)
      + '</div>';
  }

  function rowsOf(container) {
    return slice(container.querySelectorAll('.ad-list-row'));
  }
  function rowDid(r) { return r.getAttribute('data-did'); }
  function rowDepth(r) { return parseInt(r.getAttribute('data-depth') || '0', 10); }

  // ---- Drag to move ---------------------------------------------------
  // Rows are HTML5 drag sources. Dropping a deck on another deck moves it
  // underneath (Anki's reparent op — same as its native table); a nested
  // deck also gets a "top level" drop zone at the head of the list. You
  // can't drop a deck on itself, on its own descendants, or on the parent
  // it already has.
  function wireDrag(container, opts) {
    var drag = { did: null, depth: 0, blocked: {} };
    var zone = null;

    function ensureZone() {
      if (zone) return zone;
      zone = document.createElement('div');
      zone.className = 'ad-list-dropzone';
      zone.textContent = 'Drop here to make it a top-level deck';
      container.insertBefore(zone, container.firstChild);
      return zone;
    }
    function clearTargets() {
      rowsOf(container).forEach(function (r) { r.classList.remove('ad-list-row--drop'); });
      if (zone) zone.classList.remove('ad-list-dropzone--over');
    }
    function cleanup() {
      clearTargets();
      rowsOf(container).forEach(function (r) { r.classList.remove('ad-list-row--dragging'); });
      container.classList.remove('ad-list--dragging');
      if (zone) zone.classList.remove('ad-list-dropzone--show');
      drag.did = null;
      drag.blocked = {};
    }
    function finish(targetDid) {
      var src = drag.did;
      cleanup();
      if (src == null) return;
      if (opts.onMove) { opts.onMove(src, targetDid); return; }
      try {
        if (typeof pycmd === "function") {
          pycmd('ba:deck:reparent:' + src + ':' + targetDid);
        }
      } catch (_) {}
    }

    rowsOf(container).forEach(function (row) {
      row.setAttribute('draggable', 'true');
    });

    container.addEventListener('dragstart', function (e) {
      var row = e.target.closest && e.target.closest('.ad-list-row');
      if (!row) return;
      // No drags from the chevron / gear, or while a rename input is up.
      if (e.target.closest('.ad-list-chev, .ad-list-gear, input')) {
        e.preventDefault();
        return;
      }
      var all = rowsOf(container);
      var idx = all.indexOf(row);
      drag.did = rowDid(row);
      drag.depth = rowDepth(row);
      drag.blocked = {};
      drag.blocked[drag.did] = 1;
      var i;
      for (i = idx + 1; i < all.length; i++) {       // descendants
        if (rowDepth(all[i]) <= drag.depth) break;
        drag.blocked[rowDid(all[i])] = 1;
      }
      for (i = idx - 1; i >= 0; i--) {                // current parent
        if (rowDepth(all[i]) < drag.depth) { drag.blocked[rowDid(all[i])] = 1; break; }
      }
      try {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(drag.did));
      } catch (_) {}
      container.classList.add('ad-list--dragging');
      row.classList.add('ad-list-row--dragging');
      if (drag.depth > 0) ensureZone().classList.add('ad-list-dropzone--show');
    });

    container.addEventListener('dragover', function (e) {
      if (drag.did == null) return;
      clearTargets();
      var z = e.target.closest && e.target.closest('.ad-list-dropzone');
      if (z) {
        if (drag.depth === 0) return;
        e.preventDefault();
        try { e.dataTransfer.dropEffect = 'move'; } catch (_) {}
        z.classList.add('ad-list-dropzone--over');
        return;
      }
      var row = e.target.closest && e.target.closest('.ad-list-row');
      if (!row) return;
      if (drag.blocked[rowDid(row)]) return;
      e.preventDefault();
      try { e.dataTransfer.dropEffect = 'move'; } catch (_) {}
      row.classList.add('ad-list-row--drop');
    });

    container.addEventListener('drop', function (e) {
      if (drag.did == null) return;
      var z = e.target.closest && e.target.closest('.ad-list-dropzone');
      if (z) {
        e.preventDefault();
        if (drag.depth > 0) finish(0); else cleanup();
        return;
      }
      var row = e.target.closest && e.target.closest('.ad-list-row');
      if (!row) return;
      e.preventDefault();
      var did = rowDid(row);
      if (drag.blocked[did]) { cleanup(); return; }
      finish(did);
    });

    container.addEventListener('dragend', cleanup);
  }

  // Render an entire deck list into `container`. Both the home page and the
  // congrats Keep-going list call this with the same data shape, so the
  // resulting DOM is byte-identical. Callbacks are page-specific:
  //   - opts.onStudy(did)        — fired on row-name click
  //   - opts.onOptsClick(did, e) — fired on gear click (default: __adDeckOpts)
  //   - opts.onMove(did, target) — fired on drop (default: ba:deck:reparent)
  //   - opts.dragMove            — false to disable drag-to-move for this list
  function render(container, decks, opts) {
    if (!container) return;
    opts = opts || {};
    var nodes = annotateParents(decks);
    var state = initialState(nodes);
    var html = nodes
      .map(function (n) { return rowHTML(n, state); })
      .join('');
    container.innerHTML = html;
    applyVisibility(rowsOf(container), rowDid, rowDepth, state);

    if (!container.__adWired) {
      container.__adWired = true;
      container.addEventListener('click', function (e) {
        // Chevron: toggle children visibility for this row's deck.
        var chev = e.target.closest && e.target.closest('.ad-list-chev');
        if (chev && chev.tagName === 'BUTTON') {
          e.preventDefault();
          e.stopPropagation();
          var did = chev.getAttribute('data-did');
          if (!did) return;
          var s = toggle(did);
          paintChev(chev, !!s[did]);
          applyVisibility(rowsOf(container), rowDid, rowDepth, s);
          return;
        }
        // Gear: open the deck-options menu.
        var gear = e.target.closest && e.target.closest('.ad-list-gear');
        if (gear) {
          e.preventDefault();
          e.stopPropagation();
          var gdid = parseInt(gear.getAttribute('data-did') || '0', 10);
          if (!gdid) return;
          if (opts.onOptsClick) opts.onOptsClick(gdid, e);
          else if (window.__adDeckOpts) window.__adDeckOpts(gdid, e);
          return;
        }
        // Name (or anywhere else on the row that's not a control): study.
        var row = e.target.closest && e.target.closest('.ad-list-row');
        if (row && opts.onStudy) {
          var ndid = parseInt(row.getAttribute('data-did') || '0', 10);
          if (ndid) opts.onStudy(ndid, e);
        }
      });
      if (opts.dragMove !== false && listOpts().dragMove !== false) {
        wireDrag(container, opts);
      }
    }
  }

  window.__adDeckList = {
    CHEV_SVG: CHEV_SVG,
    GEAR_HTML: GEAR_HTML,
    STORAGE_KEY: STORAGE_KEY,
    startupMode: startupMode,
    loadCollapsed: loadCollapsed,
    saveCollapsed: saveCollapsed,
    toggle: toggle,
    applyVisibility: applyVisibility,
    chevronHTML: chevronHTML,
    spacerHTML: spacerHTML,
    gearHTML: gearHTML,
    paintChev: paintChev,
    annotateParents: annotateParents,
    render: render,
  };
})();
