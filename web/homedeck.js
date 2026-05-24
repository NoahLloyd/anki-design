// Anki Design — home-page deck list.
//
// Hides Anki's <table>-based deck tree and renders the SAME deck list
// component the congrats Keep-going page uses, via __adDeckList.render().
// Data comes from window.__baDeckTree (a flat depth-tagged array injected
// by Python in _full_deck_tree_payload). Both views share one render path
// so the row markup, chevron, gear, collapse logic, and styling are
// literally the same code in both places.
(function () {
  "use strict";
  if (window.__adHomeDeckWired) return;
  window.__adHomeDeckWired = true;

  function dl() { return window.__adDeckList; }

  function bridge(cmd) {
    try {
      if (typeof pycmd === "function") pycmd(cmd);
    } catch (_) {}
  }

  function getContainer() {
    var existing = document.querySelector('.ad-list--home');
    if (existing) return existing;
    var center = document.querySelector('.ba-home') || document.querySelector('center');
    if (!center) return null;
    var div = document.createElement('div');
    div.className = 'ad-list ad-list--home';
    // Insert before Anki's table so visual order matches (table is hidden
    // by CSS but Anki's other practice/heatmap blocks still follow it).
    var table = center.querySelector(':scope > table');
    if (table && table.parentNode) {
      table.parentNode.insertBefore(div, table);
    } else {
      center.insertBefore(div, center.firstChild);
    }
    return div;
  }

  function paint() {
    if (!dl()) return;
    var data = window.__baDeckTree || [];
    var container = getContainer();
    if (!container) return;
    dl().render(container, data, {
      // Clicking a deck row in Anki's table fires `open:<did>` which our
      // hook in __init__.py rewrites to "start studying" (skips overview).
      // Same dispatch keeps that behaviour.
      onStudy: function (did) { bridge('open:' + did); },
    });
  }

  function init() {
    // Anki re-renders the deck browser by calling `mw.deckBrowser.refresh()`,
    // which causes webview_will_set_content to fire and the whole page (this
    // script included) to reload. So we only need to render once at startup.
    // (A MutationObserver here used to loop: paint replaced innerHTML, the
    // observer saw that mutation, scheduled another paint on the next rAF,
    // and clicks couldn't land on rows that vanished mid-flight.)
    paint();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
