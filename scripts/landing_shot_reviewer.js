/* landing_shot_reviewer.js — dress the reviewer for the anki.design landing shot.
 *
 * Companion to landing_shot.js. DOM-only, discarded on the next render. The
 * only edit is the header queue counts, so they agree with the deck table in
 * the hero shot (Medicine::Pathology & Clinical → 10 new / 3 learn / 82 due).
 *
 * Usage: scripts/snap.sh out/reviewer.png main --js-file=scripts/landing_shot_reviewer.js
 */
(function () {
  var COUNTS = { "ba-rv-c-new": 10, "ba-rv-c-learn": 3, "ba-rv-c-due": 82 };
  Object.keys(COUNTS).forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(COUNTS[id]);
  });

  var st = document.createElement("style");
  st.textContent = "::-webkit-scrollbar{width:0!important;height:0!important}";
  document.head.appendChild(st);
})();
