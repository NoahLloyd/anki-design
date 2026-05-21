/* Anki Design — make entire deck rows clickable to start studying.

   Anki's default row only wires the deck-name link (and shift-click for
   selection). Clicking blank space or the count cells does nothing. We
   add a row-level handler so the whole row is the study target — except
   inner anchors (deck name, gears) which keep their own onclick. */
(function () {
  "use strict";
  if (window.__adDeckRowWired) return;
  window.__adDeckRowWired = true;

  function onRowClick(e) {
    if (e.shiftKey) return;                      // native: select
    if (e.button !== undefined && e.button !== 0) return;
    // Inner anchors carry their own pycmd onclick (deck name → open,
    // gears → opts). Let them handle their clicks and skip ours so we
    // don't double-fire on the deck name.
    if (e.target.closest && e.target.closest("a")) return;
    var tr = e.currentTarget;
    var did = tr.id;
    if (!did) return;
    e.preventDefault();
    try { pycmd("open:" + did); } catch (_) {}
  }

  function wire() {
    var rows = document.querySelectorAll("tr.deck");
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.__adRowWired) continue;
      r.__adRowWired = true;
      r.addEventListener("click", onRowClick);
    }
  }

  function init() {
    wire();
    if (window.MutationObserver) {
      var mo = new MutationObserver(wire);
      mo.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
