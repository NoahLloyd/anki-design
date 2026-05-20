/* BetterAnki — left sidebar (info + nav).
   Prepends a <aside class="ba-side"> to <body> on every themed page. The
   sidebar shows: identity + today's standing (date, streak, due/new/learning)
   + primary nav + quick actions + sync/settings. Python pushes live data via
   window.__baSetStanding({...}) after each render. */
(function () {
  "use strict";
  if (window.__betterankiSide) return;
  window.__betterankiSide = true;

  function send(cmd) {
    try { if (typeof pycmd === "function") pycmd("ba:" + cmd); } catch (e) {}
  }

  // ---- icons (inline SVG, stroke uses currentColor) -------------------- //
  // Lightweight stroke set tuned to feel editorial, not iconographic.
  var ICONS = {
    decks:    '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 12l9 4 9-4"/><path d="M3 17l9 4 9-4"/>',
    add:      '<path d="M12 5v14"/><path d="M5 12h14"/>',
    browse:   '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
    stats:    '<path d="M4 19V9"/><path d="M10 19V5"/><path d="M16 19v-8"/><path d="M22 19h-22"/>',
    create:   '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "import": '<path d="M12 4v12"/><path d="M6 10l6-6 6 6"/><path d="M4 20h16"/>',
    sync:     '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h0a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5h0a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v0a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
  };
  function iconSVG(name) {
    var body = ICONS[name];
    if (!body) return "";
    return '<svg class="ba-side-icon" viewBox="0 0 24 24" width="14" height="14" '
         + 'fill="none" stroke="currentColor" stroke-width="1.7" '
         + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         + body + '</svg>';
  }

  // ---- nav rows -------------------------------------------------------- //
  function makeRow(it) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "ba-side-item";
    b.setAttribute("data-cmd", it.cmd);
    if (it.active) b.setAttribute("data-active", "true");
    if (it.cls) b.classList.add(it.cls);
    var inner = iconSVG(it.cmd)
              + '<span class="ba-side-l">' + it.label + "</span>";
    if (it.dot) inner += '<span class="ba-side-dot"></span>';
    if (it.key) inner += '<span class="ba-side-key">' + it.key + "</span>";
    b.innerHTML = inner;
    b.addEventListener("click", function (e) { e.preventDefault(); send(it.cmd); });
    return b;
  }

  function build() {
    var aside = document.createElement("aside");
    aside.className = "ba-side";
    aside.innerHTML = ''
      // Wordmark
      + '<div class="ba-side-head">'
      +   '<span class="ba-side-mark">Better Anki</span>'
      + '</div>'
      // Cross-deck totals — hidden in single-deck mode (the hero owns them).
      + '<dl class="ba-side-totals">'
      +   '<div class="ba-side-stat ba-side-stat--due">'
      +     '<dt>Due</dt><dd data-x="due">—</dd></div>'
      +   '<div class="ba-side-stat ba-side-stat--new">'
      +     '<dt>New</dt><dd data-x="new">—</dd></div>'
      +   '<div class="ba-side-stat ba-side-stat--learn">'
      +     '<dt>Learning</dt><dd data-x="learn">—</dd></div>'
      + '</dl>';

    // Primary nav
    var nav = document.createElement("nav");
    nav.className = "ba-side-nav";
    [
      { cmd: "decks",  label: "Decks",  key: "D", active: true },
      { cmd: "add",    label: "Add",    key: "A" },
      { cmd: "browse", label: "Browse", key: "B" },
      { cmd: "stats",  label: "Stats",  key: "T" },
    ].forEach(function (it) { nav.appendChild(makeRow(it)); });
    aside.appendChild(nav);

    // Quick actions
    var quick = document.createElement("div");
    quick.className = "ba-side-quick";
    [
      { cmd: "create", label: "New deck",    cls: "ba-side-act" },
      { cmd: "import", label: "Import file", cls: "ba-side-act" },
    ].forEach(function (it) { quick.appendChild(makeRow(it)); });
    aside.appendChild(quick);

    // Streak + lifetime stats moved out of the sidebar and into the
    // practice/heatmap section on the main page.

    // Foot — sync + settings.
    var foot = document.createElement("div");
    foot.className = "ba-side-foot";
    [
      { cmd: "sync",     label: "Sync",     key: "Y", dot: true },
      { cmd: "settings", label: "Settings", key: ",", cls: "ba-side-settings" },
    ].forEach(function (it) { foot.appendChild(makeRow(it)); });
    aside.appendChild(foot);

    return aside;
  }

  // ---- state cache (so Python can push before the DOM is built) ------- //
  var pending = { standing: null, active: null, sync: null };

  function applyStanding(d) {
    if (!d) return;
    var keys = ["streak", "due", "new", "learn", "today", "todayMin", "total"];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var els = document.querySelectorAll('[data-x="' + k + '"]');
      if (!els.length) continue;
      var v = d[k];
      var txt = (typeof v === "number") ? fmtNum(v) : (v == null ? "—" : String(v));
      for (var j = 0; j < els.length; j++) els[j].textContent = txt;
    }
    // 7-day mini-grid (oldest → today). Each entry true/false.
    if (d.last7 && d.last7.length === 7) {
      var dots = document.querySelectorAll(".ba-side-7d-dot");
      for (var k2 = 0; k2 < 7; k2++) {
        if (!dots[k2]) continue;
        dots[k2].classList.toggle("ba-on", !!d.last7[k2]);
      }
    }
    // In single-deck mode the hero owns Due/New/Learning, so hide the
    // sidebar copy to avoid doubling the same numbers.
    var aside = document.querySelector(".ba-side");
    if (aside) aside.classList.toggle("ba-side--single", !!d.singleDeck);
  }
  function applyActive(cmd) {
    var els = document.querySelectorAll(".ba-side-item");
    for (var i = 0; i < els.length; i++) {
      if (els[i].getAttribute("data-cmd") === cmd) els[i].setAttribute("data-active", "true");
      else els[i].removeAttribute("data-active");
    }
  }
  function applySync(state) {
    var el = document.querySelector('.ba-side-item[data-cmd="sync"]');
    if (!el) return;
    el.classList.remove("ba-sync-pending", "ba-sync-full", "ba-sync-active");
    if (state === "pending") el.classList.add("ba-sync-pending");
    else if (state === "full") el.classList.add("ba-sync-full");
    else if (state === "active") el.classList.add("ba-sync-active");
  }

  function inject() {
    if (document.querySelector(".ba-side")) return;
    var aside = build();
    document.body.insertBefore(aside, document.body.firstChild || null);
    document.body.classList.add("ba-with-side");
    if (pending.standing) applyStanding(pending.standing);
    if (pending.active)   applyActive(pending.active);
    if (pending.sync)     applySync(pending.sync);
  }

  // ---- public hooks ---------------------------------------------------- //
  function fmtNum(n) {
    if (n === null || n === undefined) return "—";
    return (typeof n === "number") ? n.toLocaleString() : String(n);
  }
  window.__baSetStanding = function (d) {
    pending.standing = d || pending.standing;
    applyStanding(d);
  };
  window.__baSetActive = function (cmd) {
    pending.active = cmd;
    applyActive(cmd);
  };
  window.__baSetSync = function (state) {
    pending.sync = state;
    applySync(state);
  };

  // Bootstrap from the <head>-embedded standing data (set by the addon
  // before any body script runs) — eliminates the eval-vs-IIFE race.
  if (window.__baStandingData) pending.standing = window.__baStandingData;

  if (document.readyState !== "loading") inject();
  else document.addEventListener("DOMContentLoaded", inject);

  var moScheduled = false;
  try {
    new MutationObserver(function () {
      if (moScheduled) return;
      moScheduled = true;
      requestAnimationFrame(function () {
        moScheduled = false;
        if (!document.querySelector(".ba-side")) inject();
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}
})();
