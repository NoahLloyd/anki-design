// Anki Design — redesigned congrats page.
// Replaces Anki's stock Svelte panel with a session debrief: big-number stats
// for the deck just finished, and a clickable tree of other decks with work.
// Data is bootstrapped from window.__baCongratsData (set by Python before this
// script runs).
(function () {
  "use strict";
  if (window.__ankiDesignCongrats) return;
  window.__ankiDesignCongrats = true;

  function send(cmd) {
    try { if (typeof pycmd === "function") pycmd("ba:" + cmd); } catch (_) {}
  }
  function bridge(cmd) {
    // Anki's congrats page uses bridgeCommand for the customStudy link; keep
    // compatibility by routing through the same channel.
    try {
      if (typeof bridgeCommand === "function") bridgeCommand(cmd);
      else if (typeof pycmd === "function") pycmd(cmd);
    } catch (_) {}
  }

  function fmtN(n) {
    if (n == null) return "0";
    return Number(n).toLocaleString();
  }
  // "3:42" for minutes:seconds, or "12s" for sub-minute. Total time on this
  // deck today — meant to feel like a workout summary, not a stopwatch.
  function fmtTime(totalSec) {
    var s = Math.max(0, Math.round(totalSec || 0));
    if (s < 60) return s + "<span class=\"sub\">s</span>";
    var m = Math.floor(s / 60);
    var rs = s % 60;
    if (m < 60) {
      return m + "<span class=\"sub\">m</span>" + (rs ? " " + rs + "<span class=\"sub\">s</span>" : "");
    }
    var h = Math.floor(m / 60);
    var rm = m % 60;
    return h + "<span class=\"sub\">h</span>" + (rm ? " " + rm + "<span class=\"sub\">m</span>" : "");
  }
  // Per-card avg in seconds, rounded to one decimal if under 10s.
  function fmtPerCard(sec) {
    if (!sec) return "—";
    var x = sec;
    if (x < 10) return (Math.round(x * 10) / 10) + "<span class=\"sub\">s</span>";
    return Math.round(x) + "<span class=\"sub\">s</span>";
  }
  function pct(n, total) {
    if (!total) return 0;
    return Math.round((n / total) * 100);
  }

  // ---- DOM builders ---- //

  function statHTML(n, label, sub) {
    var labelHTML = label + (sub ? '<b>' + sub + '</b>' : '');
    return ''
      + '<div class="ba-cg-stat">'
      +   '<div class="ba-cg-stat-n">' + n + '</div>'
      +   '<div class="ba-cg-stat-l">' + labelHTML + '</div>'
      + '</div>';
  }

  function statsBlockHTML(d) {
    var thisN = d.thisDeck || 0;
    var todayN = d.todayTotal || 0;
    var timeSec = d.timeSec || 0;
    var perCard = thisN > 0 ? (timeSec / thisN) : 0;
    if (thisN === 0) {
      return '<div class="ba-cg-empty">'
        + 'No reviews on this deck today. '
        + (todayN > 0 ? ('You did <b style="color:var(--rf-ink)">' + fmtN(todayN) + '</b> on other decks.')
                      : 'Pick something below to start.')
        + '</div>';
    }
    return ''
      + '<div class="ba-cg-stats">'
      +   statHTML(fmtN(thisN),   'cards',    'this deck')
      +   statHTML(fmtN(todayN),  'today',    'all decks')
      +   statHTML(fmtTime(timeSec), 'time',  'this deck')
      +   statHTML(fmtPerCard(perCard), 'per card', '')
      + '</div>';
  }

  function accuracyHTML(d) {
    var b = d.breakdown || {};
    var again = b.again || 0, hard = b.hard || 0, good = b.good || 0, easy = b.easy || 0;
    var total = again + hard + good + easy;
    if (total === 0) return '';
    function cell(cls, label, n) {
      return ''
        + '<div class="ba-cg-acc-cell ' + cls + '">'
        +   '<div class="ba-cg-acc-row">'
        +     '<span class="ba-cg-acc-label">' + label + '</span>'
        +     '<span class="ba-cg-acc-pct">' + pct(n, total) + '%</span>'
        +   '</div>'
        +   '<div class="ba-cg-acc-n">' + fmtN(n) + '</div>'
        + '</div>';
    }
    return ''
      + '<div class="ba-cg-acc">'
      +   cell('again', 'Again', again)
      +   cell('hard',  'Hard',  hard)
      +   cell('good',  'Good',  good)
      +   cell('easy',  'Easy',  easy)
      + '</div>';
  }

  function countCell(n, cls) {
    var z = !n ? ' zero' : '';
    return '<span class="' + cls + z + '">' + (n || 0) + '</span>';
  }

  function deckRowHTML(node) {
    var name = node.name == null ? '' : String(node.name);
    var depth = node.depth || 0;
    var n = node.new || 0, l = node.learn || 0, r = node.review || 0;
    return ''
      + '<button class="ba-cg-deck" data-depth="' + depth + '" '
      +         'data-did="' + node.did + '" type="button">'
      +   '<span class="ba-cg-deck-name">' + escapeHTML(name) + '</span>'
      +   '<span class="ba-cg-deck-counts">'
      +     countCell(n, 'new')
      +     countCell(l, 'learn')
      +     countCell(r, 'review')
      +   '</span>'
      + '</button>';
  }

  function decksBlockHTML(decks) {
    if (!decks || !decks.length) {
      return ''
        + '<div class="ba-cg-clear">'
        +   '<b>Everything’s clear.</b> No other decks have cards to study right now. '
        +   'Come back tomorrow, or '
        +   '<a href="javascript:void(0)" onclick="bridgeCommand(\'customStudy\')">try custom study</a>.'
        + '</div>';
    }
    var head = ''
      + '<div class="ba-cg-decks-h">'
      +   '<span class="ba-cg-decks-h-title">Keep going</span>'
      +   '<span class="ba-cg-decks-h-sub">Other decks with work</span>'
      + '</div>';
    var rows = decks.map(deckRowHTML).join('');
    return head + '<div class="ba-cg-decks">' + rows + '</div>';
  }

  function footHTML() {
    return ''
      + '<div class="ba-cg-foot">'
      +   'Want to study off-schedule? '
      +   '<a href="javascript:void(0)" onclick="bridgeCommand(\'customStudy\')">Custom study</a>.'
      + '</div>';
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c];
    });
  }

  function build() {
    var d = window.__baCongratsData || {};
    var deckName = d.deckName || 'this deck';
    var wrap = document.createElement('div');
    wrap.className = 'ba-cg';
    wrap.innerHTML = ''
      + '<header class="ba-cg-head">'
      +   '<span class="ba-cg-eyebrow">Done for now</span>'
      +   '<h1 class="ba-cg-deck">' + escapeHTML(deckName) + '</h1>'
      + '</header>'
      + statsBlockHTML(d)
      + accuracyHTML(d)
      + decksBlockHTML(d.otherDecks)
      + footHTML();

    // Wire deck-row clicks → jump straight into that deck's reviewer.
    wrap.addEventListener('click', function (e) {
      var btn = e.target.closest && e.target.closest('.ba-cg-deck');
      if (!btn) return;
      var did = btn.getAttribute('data-did');
      if (did) send('study:' + did);
    });

    return wrap;
  }

  function mount() {
    if (document.querySelector('.ba-cg')) return;
    // Anki's Svelte page is async; wait for the body to exist.
    if (!document.body) {
      document.addEventListener('DOMContentLoaded', mount);
      return;
    }
    // Find Anki's congrats container and hide it (CSS does this too, but we
    // also remove children to stop screen readers from announcing both).
    var stock = document.querySelector('.congrats');
    if (stock) stock.setAttribute('aria-hidden', 'true');
    document.body.appendChild(build());
    // Force scroll to top — the Svelte announcer (an absolutely-positioned
    // element at the bottom of the doc) can leave the viewport mid-page on
    // some renders. We want the headline visible.
    try {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    } catch (_) {}
  }

  // The Svelte mount can win our race; observe for late insertion and rebuild
  // if the page swaps state on us.
  function watch() {
    if (!window.MutationObserver) return;
    var mo = new MutationObserver(function () {
      // Just guarantee our overlay exists; if Anki re-renders we don't
      // duplicate (build() is idempotent via the .ba-cg presence check).
      mount();
    });
    try { mo.observe(document.documentElement, { childList: true, subtree: true }); }
    catch (_) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { mount(); watch(); });
  } else {
    mount();
    watch();
  }
})();
