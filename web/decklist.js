// Anki Design — shared deck-list primitives.
//
// Both the home-page tree (Anki's <tr.deck> rows) and the congrats
// "Keep going" list (custom <div.ba-cg-row>) render the same row shape:
//
//     [chevron]  [name]  [counts]  [gear]
//
// The DOM containers differ (table row vs div) but the chevron / gear /
// collapse semantics are identical. This module owns:
//
//   - the chevron SVG markup
//   - the gear markup (Anki's own gears.svg, so it matches the rest of
//     the app pixel-for-pixel)
//   - the sessionStorage collapse state, shared across both views via a
//     single key (collapse a deck on the congrats page, it stays collapsed
//     when you return to the home tree)
//   - a generic visibility resolver that takes any ordered list of rows
//     plus extractor callbacks
//
// Pages that consume this module own the DOM container shape; this module
// only cares about the data attributes (`data-did`, `data-depth` / level)
// and class hooks (`ad-list-row-hidden`).
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

  function loadCollapsed() {
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) { return {}; }
  }

  function saveCollapsed(state) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
    catch (_) {}
  }

  function toggle(did) {
    var s = loadCollapsed();
    if (s[did]) delete s[did]; else s[did] = 1;
    saveCollapsed(s);
    return s;
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
        depth: d.depth || 0,
        new: d.new || 0,
        learn: d.learn || 0,
        review: d.review || 0,
        current: !!d.current,
        filtered: !!d.filtered,
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

  // Render an entire deck list into `container`. Both the home page and the
  // congrats Keep-going list call this with the same data shape, so the
  // resulting DOM is byte-identical. Callbacks are page-specific:
  //   - opts.onStudy(did)        — fired on row-name click
  //   - opts.onOptsClick(did, e) — fired on gear click (default: __adDeckOpts)
  function render(container, decks, opts) {
    if (!container) return;
    opts = opts || {};
    var state = loadCollapsed();
    var html = annotateParents(decks)
      .map(function (n) { return rowHTML(n, state); })
      .join('');
    container.innerHTML = html;
    applyVisibility(
      Array.prototype.slice.call(container.querySelectorAll('.ad-list-row')),
      function (r) { return r.getAttribute('data-did'); },
      function (r) { return parseInt(r.getAttribute('data-depth') || '0', 10); },
      state
    );

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
        applyVisibility(
          Array.prototype.slice.call(container.querySelectorAll('.ad-list-row')),
          function (r) { return r.getAttribute('data-did'); },
          function (r) { return parseInt(r.getAttribute('data-depth') || '0', 10); },
          s
        );
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
  }

  window.__adDeckList = {
    CHEV_SVG: CHEV_SVG,
    GEAR_HTML: GEAR_HTML,
    STORAGE_KEY: STORAGE_KEY,
    loadCollapsed: loadCollapsed,
    saveCollapsed: saveCollapsed,
    toggle: toggle,
    applyVisibility: applyVisibility,
    chevronHTML: chevronHTML,
    spacerHTML: spacerHTML,
    gearHTML: gearHTML,
    paintChev: paintChev,
    render: render,
  };
})();
