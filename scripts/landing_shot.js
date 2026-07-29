/* landing_shot.js — dress the deck home for the anki.design landing shot.
 *
 * Runs inside mw.web (via snap.sh --js-file=) right before the Qt grab. It
 * does NOT touch the collection: every edit here is DOM-only and disappears
 * on the next render. The demo collection's own numbers are already realistic
 * (see scripts/seed_demo.py); this just curates them into one frame —
 * a shorter deck list, non-zero learning counts, and a session histogram with
 * a legible shape — so the whole product story fits a single 16:10 crop.
 *
 * The streak and heatmap are left exactly as the seeder generated them.
 *
 * Usage: scripts/snap.sh out/hero.png main --width=1280 --height=860 \
 *          --js-file=scripts/landing_shot.js
 */
(function () {
  var qa = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // ---------------------------------------------------------------- decks --
  // [new, learning, due]. Parents are the exact sum of their children so the
  // table survives a close read.
  var DECKS = {
    "Languages":                    [26, 7, 198],
    "French — Top words":           [5, 1, 31],
    "Japanese — JLPT N5":           [8, 2, 57],
    "Spanish — Top words":          [13, 4, 110],
    "Medicine":                     [19, 5, 151],
    "Anatomy — Bones":              [4, 1, 28],
    "Pathology & Clinical":         [10, 3, 82],
    "Pharmacology":                 [5, 1, 41],
    "Science":                      [8, 2, 63],
    "Chemistry — Constants & Laws": [3, 1, 25],
    "Periodic Table":               [5, 1, 38],
  };

  var setCount = function (el, n) {
    if (!el) return;
    el.textContent = String(n);
    el.classList.toggle("zero", n === 0);
  };

  qa(".ad-list-row").forEach(function (row) {
    var nameEl = row.querySelector(".ad-list-name");
    var name = nameEl ? nameEl.textContent.trim() : "";
    var plan = DECKS[name];
    if (!plan) { row.remove(); return; }          // trim to the curated set
    var counts = row.querySelector(".ad-list-counts");
    if (!counts) return;
    setCount(counts.querySelector(".new"), plan[0]);
    setCount(counts.querySelector(".learn"), plan[1]);
    setCount(counts.querySelector(".review"), plan[2]);
  });

  // -------------------------------------------------------------- sidebar --
  // Column totals across the curated table: 53 new / 14 learning / 412 due.
  var totals = { due: 412, new: 53, learn: 14 };
  Object.keys(totals).forEach(function (k) {
    var el = document.querySelector('dd[data-x="' + k + '"]');
    if (el) el.textContent = String(totals[k]);
  });

  // ---------------------------------------------------------------- today --
  // A believable day: a strong morning block, a real break (the empty stub at
  // noon), then an afternoon second wind. The header total is summed from
  // these, so the panel stays internally consistent if you retune them.
  var HOURS = [
    ["7 AM", 22], ["8 AM", 45], ["9 AM", 73], ["10 AM", 58], ["11 AM", 27],
    ["12 PM", 0], ["1 PM", 35], ["2 PM", 54], ["3 PM", 41], ["4 PM", 15],
    ["5 PM", 26], ["6 PM", 48], ["7 PM", 36], ["8 PM", 17],
  ];
  var TOTAL = HOURS.reduce(function (a, h) { return a + h[1]; }, 0);
  var MINUTES = 78;
  var peak = HOURS.reduce(function (a, h) { return Math.max(a, h[1]); }, 1);

  var headNums = qa(".ba-today-head .ba-today-n");
  if (headNums[0]) headNums[0].textContent = TOTAL.toLocaleString();
  if (headNums[1]) headNums[1].textContent = String(MINUTES);

  var barWrap = document.querySelector(".ba-today-bars");
  var cols = qa(".ba-today-bar-col", barWrap);
  if (barWrap && cols.length) {
    var template = cols[0];
    cols.slice(HOURS.length).forEach(function (c) { c.remove(); });
    while (qa(".ba-today-bar-col", barWrap).length < HOURS.length) {
      barWrap.appendChild(template.cloneNode(true));
    }
    qa(".ba-today-bar-col", barWrap).forEach(function (col, i) {
      var label = HOURS[i][0], n = HOURS[i][1];
      var bar = col.querySelector(".ba-today-bar");
      var count = col.querySelector(".ba-today-bar-count");
      var tipH = col.querySelector(".ba-today-bar-tip-h");
      var tipD = col.querySelector(".ba-today-bar-tip-d");
      if (count) count.textContent = n > 0 ? String(n) : "";
      if (bar) {
        // Mirrors _pulse_html(): bars cap at 88% so the count label above
        // never collides; empty hours collapse to a 4% tick.
        bar.style.height = (n > 0 ? Math.max(8, (n / peak) * 88) : 4).toFixed(1) + "%";
        bar.classList.toggle("is-empty", n === 0);
      }
      if (tipH) tipH.textContent = label;
      if (tipD) tipD.innerHTML = "<b>" + n + "</b> cards · <b>" + Math.round(n / 6) + " min</b>";
    });
  }

  var labels = qa(".ba-today-labels span");
  if (labels[0] && !labels[0].classList.contains("ba-today-now")) {
    labels[0].textContent = HOURS[0][0];
  }

  // ------------------------------------------------------------ chrome fix --
  // The grab includes the scrollbar gutter; hide it so the frame edge is clean.
  var st = document.createElement("style");
  st.textContent = "::-webkit-scrollbar{width:0!important;height:0!important}";
  document.head.appendChild(st);
})();
