/* Anki Design — left sidebar (info + nav).
   Prepends a <aside class="ba-side"> to <body> on every themed page. The
   sidebar shows: identity + today's standing (date, streak, due/new/learning)
   + primary nav + quick actions + sync/settings. Python pushes live data via
   window.__baSetStanding({...}) after each render. */
(function () {
  "use strict";
  if (window.__ankiDesignSide) return;
  window.__ankiDesignSide = true;

  function send(cmd) {
    try { if (typeof pycmd === "function") pycmd("ba:" + cmd); } catch (e) {}
  }

  // ---- icons (inline SVG, stroke uses currentColor) -------------------- //
  // Lightweight stroke set tuned to feel editorial, not iconographic.
  // Each icon is structured so the parts most worth animating on hover are
  // wrapped in groups with stable class hooks (see sidebar.css).
  var ICONS = {
    decks:
      '<g class="ba-i-decks-top"><path d="M3 7l9-4 9 4-9 4-9-4z"/></g>' +
      '<g class="ba-i-decks-mid"><path d="M3 12l9 4 9-4"/></g>' +
      '<g class="ba-i-decks-bot"><path d="M3 17l9 4 9-4"/></g>',
    add:
      '<g class="ba-i-plus">' +
        '<path d="M12 5v14"/><path d="M5 12h14"/>' +
      '</g>',
    browse:
      '<g class="ba-i-search-lens">' +
        '<circle cx="11" cy="11" r="6.5"/>' +
      '</g>' +
      '<g class="ba-i-search-handle">' +
        '<path d="M20 20l-4.3-4.3"/>' +
      '</g>',
    stats:
      '<g class="ba-i-bars">' +
        '<path class="ba-i-bar ba-i-bar-1" d="M4 19V9"/>' +
        '<path class="ba-i-bar ba-i-bar-2" d="M10 19V5"/>' +
        '<path class="ba-i-bar ba-i-bar-3" d="M16 19v-8"/>' +
      '</g>' +
      '<path d="M22 19h-22"/>',
    create:
      '<g class="ba-i-plus">' +
        '<path d="M12 5v14"/><path d="M5 12h14"/>' +
      '</g>',
    submit:
      '<g class="ba-i-submit">' +
        '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>' +
      '</g>',
    "import":
      '<g class="ba-i-import">' +
        '<path class="ba-i-import-stem"  d="M12 4v12"/>' +
        '<path class="ba-i-import-head"  d="M6 10l6-6 6 6"/>' +
      '</g>' +
      '<path d="M4 20h16"/>',
    sync:
      '<g class="ba-i-sync">' +
        '<path d="M21 12a9 9 0 1 1-3-6.7"/>' +
        '<path d="M21 4v5h-5"/>' +
      '</g>',
    settings:
      '<g class="ba-i-gear">' +
        '<circle cx="12" cy="12" r="3"/>' +
        '<path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h0a1.6 1.6 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 1 1.5h0a1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v0a1.6 1.6 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>' +
      '</g>',
  };
  function iconSVG(name, extraClass) {
    var body = ICONS[name];
    if (!body) return "";
    var cls = "ba-side-icon" + (extraClass ? " " + extraClass : "");
    return '<svg class="' + cls + '" viewBox="0 0 24 24" width="14" height="14" '
         + 'fill="none" stroke="currentColor" stroke-width="1.7" '
         + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         + body + '</svg>';
  }

  // ---- nav rows -------------------------------------------------------- //
  // Sync row needs an extra <svg> for the success-check overlay that fades
  // in over the cloud icon when a sync completes with real changes. Both
  // glyphs live in a positioned wrapper so we can cross-fade them without
  // shifting the row layout.
  var SYNC_CHECK_SVG =
    '<svg class="ba-sync-check" viewBox="0 0 24 24" width="14" height="14" ' +
      'fill="none" stroke="currentColor" stroke-width="2.2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M5 12.5l4.5 4.5L19 7"/>' +
    '</svg>';

  function makeRow(it) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "ba-side-item";
    b.setAttribute("data-cmd", it.cmd);
    if (it.active) b.setAttribute("data-active", "true");
    if (it.cls) b.classList.add(it.cls);
    var iconBlock = (it.cmd === "sync")
      ? '<span class="ba-sync-iconwrap">' + iconSVG(it.cmd) + SYNC_CHECK_SVG + '</span>'
      : iconSVG(it.cmd);
    // .ba-side-l-text wraps the label so the sync row can rewrite it in
    // place ("Sync" → "Syncing…" → "Synced") without touching siblings.
    var inner = iconBlock
              + '<span class="ba-side-l"><span class="ba-side-l-text">'
              + it.label + '</span></span>';
    if (it.dot) inner += '<span class="ba-side-dot"></span>';
    if (it.key) inner += '<span class="ba-side-key">' + it.key + "</span>";
    b.innerHTML = inner;
    b.addEventListener("click", function (e) { e.preventDefault(); send(it.cmd); });
    return b;
  }

  // Morphing "New deck" row. Idle: looks like any sidebar action row. Active:
  // the label swaps for an inline input — Enter creates, Esc/blur cancels.
  // The icon column anchors the transition so nothing jumps. We hold the open
  // state on the wrapper element and toggle a single `data-state` so all
  // transitions are CSS-driven.
  function makeNewDeckRow() {
    var row = document.createElement("div");
    row.className = "ba-side-item ba-side-act ba-side-newdeck";
    row.setAttribute("data-cmd", "create");
    row.setAttribute("data-state", "idle");
    // The icon slot holds two SVGs stacked in the same 14×14 box: the
    // idle plus and the active submit (right arrow). They cross-fade as
    // the state changes — the shared horizontal stroke of both glyphs
    // makes the swap read as a morph rather than a flicker.
    //
    // Label + input share their own flex slot so they overlap in place;
    // CSS fades one in as the other fades out — no layout shift.
    row.innerHTML =
      '<span class="ba-side-newdeck-icons" aria-hidden="true">' +
        iconSVG("create", "ba-side-newdeck-icon--plus") +
        iconSVG("submit", "ba-side-newdeck-icon--submit") +
      '</span>' +
      '<span class="ba-side-newdeck-swap">' +
        '<span class="ba-side-newdeck-label">New deck</span>' +
        '<input type="text" class="ba-side-newdeck-input" autocomplete="off" ' +
          'spellcheck="false" placeholder="Name a deck…" tabindex="-1" />' +
      '</span>';

    var input = row.querySelector(".ba-side-newdeck-input");
    var iconBtn = row.querySelector(".ba-side-newdeck-icons");

    function open() {
      if (row.getAttribute("data-state") === "active") { input.focus(); return; }
      row.setAttribute("data-state", "active");
      input.removeAttribute("tabindex");
      // Defer focus one frame so the layout swap finishes before the caret
      // is placed — otherwise the input can scroll its parent.
      requestAnimationFrame(function () { input.focus(); });
    }
    function close() {
      row.setAttribute("data-state", "idle");
      input.setAttribute("tabindex", "-1");
      input.value = "";
    }
    function submit() {
      var name = input.value.trim();
      if (!name) { close(); return; }
      send("create:" + name);
      // The Python handler calls mw.reset(); the deck list will refresh.
      close();
    }

    // Click on the row (outside the input/icon) opens it.
    row.addEventListener("click", function (e) {
      if (row.getAttribute("data-state") === "active") return;
      e.preventDefault();
      open();
    });
    // Keyboard activation when the row itself is focused (idle state).
    row.tabIndex = 0;
    row.addEventListener("keydown", function (e) {
      if (row.getAttribute("data-state") === "idle" &&
          (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        open();
      }
    });

    input.addEventListener("click", function (e) { e.stopPropagation(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    input.addEventListener("blur", function () {
      // Defer so other in-flight handlers (e.g. our own submit) run first.
      setTimeout(function () {
        if (document.activeElement !== input) close();
      }, 80);
    });

    // In active state the icon doubles as a submit affordance — clicking
    // it is equivalent to pressing Enter from the input. mousedown's
    // preventDefault keeps the input focused so the submit reads its
    // current value (and avoids the blur-then-close race).
    iconBtn.addEventListener("mousedown", function (e) {
      if (row.getAttribute("data-state") === "active") e.preventDefault();
    });
    iconBtn.addEventListener("click", function (e) {
      if (row.getAttribute("data-state") !== "active") return; // idle: let it bubble
      e.preventDefault();
      e.stopPropagation();
      submit();
    });

    // Public hook used by the Python handler when "ba:create" comes from a
    // keyboard shortcut or external trigger.
    window.__baFocusNewDeck = open;

    return row;
  }

  function build() {
    var aside = document.createElement("aside");
    aside.className = "ba-side";
    aside.innerHTML = ''
      // Wordmark — Anki Design lockup. Rendered as coded markup so the
      // two-typeface lockup (Helvetica anki + Architects Daughter DESIGN
      // with red period) scales from a single CSS variable.
      + '<div class="ba-side-head">'
      +   '<span class="ad-logo ba-side-mark" aria-label="Anki Design">'
      +     '<span class="ad-mark">anki<span class="ad-dot" aria-hidden="true"><span class="ad-pupil"></span></span></span>'
      +     '<span class="ad-design">'
      +       '<span class="ad-d">D</span>'
      +       '<span class="ad-e">E</span>'
      +       '<span class="ad-s">S</span>'
      +       '<span class="ad-i">I</span>'
      +       '<span class="ad-g">G</span>'
      +       '<span class="ad-n">N</span>'
      +     '</span>'
      +   '</span>'
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

    // Wordmark opens anki.design (in the user's default browser, via Python).
    var mark = aside.querySelector(".ba-side-mark");
    if (mark) {
      mark.setAttribute("role", "link");
      mark.setAttribute("tabindex", "0");
      mark.addEventListener("click", function (e) {
        e.preventDefault();
        send("website");
      });
      mark.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          send("website");
        }
      });

      // Googly period — on hover, the red dot grows an eyeball that tracks
      // the cursor. A ring of ink particles bursts outward around it just
      // as the sclera finishes scaling in (timing handled by the CSS
      // animation-delay on .ad-dot::after). Skipped under reduced-motion.
      var dot = mark.querySelector(".ad-dot");
      var pupil = dot ? dot.querySelector(".ad-pupil") : null;
      var reducedMotion = window.matchMedia
        && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (dot && pupil && !reducedMotion) {
        var trackPupil = function (e) {
          var rect = dot.getBoundingClientRect();
          var cx = rect.left + rect.width / 2;
          var cy = rect.top + rect.height / 2;
          var dx = e.clientX - cx;
          var dy = e.clientY - cy;
          var size = parseFloat(getComputedStyle(dot).fontSize) || 20;
          var maxPx = 0.18 * size;
          var len = Math.hypot(dx, dy);
          if (len > maxPx) {
            dx = (dx / len) * maxPx;
            dy = (dy / len) * maxPx;
          }
          pupil.style.setProperty("--ad-pupil-x", dx + "px");
          pupil.style.setProperty("--ad-pupil-y", dy + "px");
        };
        mark.addEventListener("mouseenter", function () {
          document.addEventListener("mousemove", trackPupil);
          mark.classList.add("is-burst");
        });
        mark.addEventListener("mouseleave", function () {
          document.removeEventListener("mousemove", trackPupil);
          pupil.style.setProperty("--ad-pupil-x", "0px");
          pupil.style.setProperty("--ad-pupil-y", "0px");
          mark.classList.remove("is-burst");
        });
      }
    }

    // Command-K palette launcher. Rendered as a button styled like a
    // search input so it reads as "click here to search anything", and
    // hints the ⌘K shortcut on the right. Actual palette UI is in
    // web/cmdk.js (injected on every themed page). Sending the pycmd
    // routes through Python so any open embed (AddCards/Browser/Stats/
    // Settings) is torn down before the palette opens.
    var cmdk = document.createElement("button");
    cmdk.type = "button";
    cmdk.className = "ba-side-cmdk";
    cmdk.setAttribute("aria-label", "Open command palette");
    // Mac users see ⌘K; everyone else sees Ctrl+K (both bindings fire).
    var modGlyph = /Mac|iPod|iPhone|iPad/i.test(navigator.platform || "")
      ? '<span class="ba-side-cmdk-key">⌘</span>'
      : '<span class="ba-side-cmdk-key ba-side-cmdk-key--w">Ctrl</span>';
    cmdk.innerHTML =
      '<svg class="ba-side-cmdk-ico" viewBox="0 0 24 24" width="14" height="14" ' +
        'fill="none" stroke="currentColor" stroke-width="1.7" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>' +
      '</svg>' +
      '<span class="ba-side-cmdk-l">Search anything…</span>' +
      '<span class="ba-side-cmdk-kbd">' +
        modGlyph +
        '<span class="ba-side-cmdk-key">K</span>' +
      '</span>';
    cmdk.addEventListener("click", function (e) {
      e.preventDefault();
      if (typeof window.__baCmdkOpen === "function") {
        // Same-webview: open immediately, no Python round-trip.
        window.__baCmdkOpen("");
      } else {
        send("cmdk-open");
      }
    });
    aside.appendChild(cmdk);

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
    quick.appendChild(makeNewDeckRow());
    quick.appendChild(makeRow({ cmd: "import", label: "Import file", cls: "ba-side-act" }));
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
  // The sync row drives a small state machine:
  //
  //   idle  ──click──▶  active  ──result(ok)──▶  reveal-ok   ──▶  idle
  //                          └──result(noop)──▶ reveal-noop ──▶  idle
  //                          └──result(error)─▶ reveal-err  ──▶  idle
  //
  // applySync() owns the standing class state (pending/full/active) and
  // the resting label. applySyncResult() owns the brief "Synced" reveal
  // — and during that reveal it locks the label so applySync() can't
  // overwrite it from a parallel `gui_hooks.sync_did_finish` refresh.
  var syncResultTimer = null;

  function applySync(state) {
    var el = document.querySelector('.ba-side-item[data-cmd="sync"]');
    if (!el) return;
    var revealing = el.hasAttribute("data-sync-result");
    var text = el.querySelector(".ba-side-l-text");
    el.classList.remove("ba-sync-pending", "ba-sync-full");
    // Keep the spin going while the reveal plays — it cross-fades into
    // the check, no abrupt stop.
    if (!revealing) el.classList.remove("ba-sync-active");
    if (state === "pending") el.classList.add("ba-sync-pending");
    else if (state === "full") el.classList.add("ba-sync-full");
    else if (state === "active") {
      el.classList.add("ba-sync-active");
      if (text && !revealing) text.textContent = "Syncing…";
    } else if (!revealing && text) {
      text.textContent = "Sync";
    }
  }

  function applySyncProgress(d) {
    // Anki's `progress.normal_sync.stage` is a localized full sentence
    // ("Checking…", "Uploading notes…") that would jitter the row width
    // if shown directly. We stash it on a data attr for inspection /
    // future use; the visible feedback is the spinning icon + "Syncing…"
    // label, which is enough to convey "work is in flight."
    if (!d) return;
    var el = document.querySelector('.ba-side-item[data-cmd="sync"]');
    if (!el) return;
    if (d.stage) el.setAttribute("data-sync-stage", d.stage);
    if (d.added) el.setAttribute("data-sync-added", d.added);
    if (d.removed) el.setAttribute("data-sync-removed", d.removed);
  }

  function applySyncResult(kind) {
    var el = document.querySelector('.ba-side-item[data-cmd="sync"]');
    if (!el) return;
    var text = el.querySelector(".ba-side-l-text");
    el.setAttribute("data-sync-result", kind);
    // Different reveals for "real changes happened" vs "heartbeat / no
    // changes" vs "error" — see styles below for the actual motion.
    if (kind === "ok" && text) text.textContent = "Synced";
    else if (kind === "error" && text) text.textContent = "Sync failed";
    // "noop" — keep the label as it was (usually "Syncing…"); we let it
    // fade back to "Sync" with the icon's settle bounce.

    var hold = (kind === "noop") ? 800 : 1800;
    clearTimeout(syncResultTimer);
    syncResultTimer = setTimeout(function () {
      el.removeAttribute("data-sync-result");
      el.classList.remove("ba-sync-active");
      el.removeAttribute("data-sync-stage");
      el.removeAttribute("data-sync-added");
      el.removeAttribute("data-sync-removed");
      var t = el.querySelector(".ba-side-l-text");
      if (t) t.textContent = "Sync";
    }, hold);
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
  window.__baSetSyncProgress = function (d) {
    applySyncProgress(d);
  };
  window.__baSetSyncResult = function (kind) {
    applySyncResult(kind);
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
