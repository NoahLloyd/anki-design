// Anki Design — reviewer progress bar + body cleanup + answer-reveal wrap
// + inline edit mode. Inline edit replaces Anki's EditCurrent dialog: the
// field spans (wrapped server-side with data-ba-field) become
// contenteditable in place, with a small floating toolbar at the bottom.
(function () {
  function cleanupBody() {
    if (!document.body) return;
    // Anki injects `background-position-y: -44px` inline — kill it so
    // we don't get a horizontal banding artifact.
    try {
      document.body.style.removeProperty("background-position-y");
      document.body.style.removeProperty("background-position");
      document.body.style.removeProperty("background-image");
    } catch (_) {}
  }

  function ensureBar() {
    cleanupBody();
    var bar = document.getElementById("reforge-progress");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "reforge-progress";
      bar.innerHTML = '<div id="reforge-progress-fill"></div>';
      document.body.appendChild(bar);

      var label = document.createElement("div");
      label.id = "reforge-progress-label";
      document.body.appendChild(label);
    }
  }

  // Wrap everything from the answer divider onward in a single .ba-rv-answer
  // element so CSS can fade it in without moving the question above it.
  function wrapAnswer() {
    var qa = document.getElementById("qa");
    if (!qa) return;
    var ease = document.querySelector(".ba-rv-ease");
    var hr = qa.querySelector("hr#answer");
    var hasAnswer = !!hr || !!qa.querySelector(".ba-rv-answer");
    if (ease) ease.hidden = !hasAnswer;
    if (qa.querySelector(".ba-rv-answer")) return;  // already wrapped
    if (!hr) return;
    var wrap = document.createElement("div");
    wrap.className = "ba-rv-answer";
    var parent = hr.parentNode;
    var nodes = [];
    var n = hr;
    while (n) {
      nodes.push(n);
      n = n.nextSibling;
    }
    nodes.forEach(function (node) { wrap.appendChild(node); });
    parent.appendChild(wrap);
  }

  // Receive {ease: interval_string} + defaultEase from Python and write
  // the interval strings into the ease chips, hiding chips with no
  // matching ease (i.e., 2/3-button new cards).
  window.__baSetEase = function (intervals, defaultEase) {
    var ease = document.querySelector(".ba-rv-ease");
    if (!ease) return;
    ease.querySelectorAll(".ba-rv-ease-key").forEach(function (btn) {
      var e = btn.getAttribute("data-ease");
      var label = intervals && intervals[e];
      var slot = btn.querySelector(".ba-rv-ease-int");
      if (label && slot) {
        slot.textContent = label;
        btn.hidden = false;
      } else {
        btn.hidden = true;
      }
      if (parseInt(e, 10) === parseInt(defaultEase, 10)) {
        btn.setAttribute("data-default", "");
      } else {
        btn.removeAttribute("data-default");
      }
    });
  };

  // Anki rewrites body.style on every card swap. We can't override its inline
  // styles permanently from CSS, so observe and re-strip when it reappears.
  function watchBody() {
    if (!document.body || !window.MutationObserver) return;
    var mo = new MutationObserver(function () {
      cleanupBody();
      wrapAnswer();
    });
    mo.observe(document.body, {
      attributes: true,
      attributeFilter: ["style"],
      childList: true,
      subtree: true,
    });
  }

  // Click-the-card to reveal: clicking anywhere on the card area while in
  // the question state triggers the same shortcut as Space. Avoid hijacking
  // clicks on actual links, inputs, or media inside the card body.
  function clickToReveal() {
    var qa = document.getElementById("qa");
    if (!qa) return;
    qa.addEventListener("click", function (e) {
      // Don't advance the card while the user is editing it.
      if (document.body.classList.contains("ba-editing")) return;
      if (qa.querySelector(".ba-rv-answer")) return;  // already answered
      var t = e.target;
      while (t && t !== qa) {
        var tag = (t.tagName || "").toLowerCase();
        if (tag === "a" || tag === "button" || tag === "input"
            || tag === "textarea" || tag === "select" || tag === "audio"
            || tag === "video" || t.isContentEditable) {
          return;  // let the user actually interact with that thing
        }
        t = t.parentNode;
      }
      try { pycmd && pycmd("ans"); } catch (_) {}
    }, { passive: true });
  }

  window.__reforgeProgress = function (pct, done, rem) {
    ensureBar();
    var fill = document.getElementById("reforge-progress-fill");
    var label = document.getElementById("reforge-progress-label");
    if (fill) fill.style.width = pct + "%";
    if (label) label.textContent = done + " / " + (done + rem);
  };

  // ---------- Inline edit mode ----------------------------------------- //
  // State held between enter / exit so Cancel can restore the original
  // HTML even after the user has typed.
  var editState = { active: false, originals: {}, triedReveal: false };

  function fieldSpans() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-ba-field]")
    );
  }

  function ensureEditToolbar() {
    var bar = document.getElementById("ba-edit-bar");
    if (bar) return bar;
    bar = document.createElement("div");
    bar.id = "ba-edit-bar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Edit card");
    // The toolbar lives outside the card so its buttons are reachable
    // even when the card content scrolls. Format buttons on the left,
    // primary actions on the right.
    bar.innerHTML =
        '<div class="ba-edit-fmt" role="group" aria-label="Formatting">'
      +   '<button type="button" data-cmd="bold"      title="Bold (⌘B)"      aria-label="Bold"><b>B</b></button>'
      +   '<button type="button" data-cmd="italic"    title="Italic (⌘I)"    aria-label="Italic"><i>I</i></button>'
      +   '<button type="button" data-cmd="underline" title="Underline (⌘U)" aria-label="Underline"><u>U</u></button>'
      + '</div>'
      + '<div class="ba-edit-actions">'
      +   '<button type="button" class="ba-edit-link" data-action="full" '
      +           'title="Open Anki\'s full editor">Open full editor</button>'
      +   '<button type="button" class="ba-edit-secondary" data-action="cancel" '
      +           'title="Cancel (Esc)">Cancel</button>'
      +   '<button type="button" class="ba-edit-primary" data-action="save" '
      +           'title="Save (⌘↩)">Save</button>'
      + '</div>';
    document.body.appendChild(bar);

    bar.addEventListener("mousedown", function (e) {
      // Don't let the toolbar steal focus from the field — that wipes the
      // selection before execCommand can act on it.
      e.preventDefault();
    });
    bar.addEventListener("click", function (e) {
      var t = e.target;
      while (t && t !== bar) {
        var cmd = t.getAttribute && t.getAttribute("data-cmd");
        if (cmd) {
          try { document.execCommand(cmd, false, null); } catch (_) {}
          return;
        }
        var act = t.getAttribute && t.getAttribute("data-action");
        if (act === "save") { exitEdit(true); return; }
        if (act === "cancel") { exitEdit(false); return; }
        if (act === "full") { openFullEditor(); return; }
        t = t.parentNode;
      }
    });
    return bar;
  }

  function focusFirstField(spans) {
    if (!spans || !spans.length) return;
    var first = spans[0];
    try {
      first.focus();
      var range = document.createRange();
      range.selectNodeContents(first);
      range.collapse(false);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (_) {}
  }

  function collectPayload() {
    var data = {};
    fieldSpans().forEach(function (sp) {
      var name = sp.getAttribute("data-ba-field");
      if (name == null) return;
      data[name] = sp.innerHTML;
    });
    return JSON.stringify(data);
  }

  function onEditKeydown(e) {
    if (!editState.active) return;
    var meta = e.metaKey || e.ctrlKey;
    if (e.key === "Escape") {
      e.preventDefault();
      exitEdit(false);
      return;
    }
    if (meta && (e.key === "Enter" || e.key === "Return"
                 || e.key === "s" || e.key === "S")) {
      e.preventDefault();
      exitEdit(true);
      return;
    }
    // Block answer-card shortcuts so a stray Space/1-4 doesn't grade the
    // card while the user is typing.
    if (e.key === " " || e.key === "1" || e.key === "2"
        || e.key === "3" || e.key === "4") {
      // Don't preventDefault — typing a space should still type a space.
      // We only need to stop the event from bubbling to Anki's shortcuts.
      e.stopPropagation();
    }
  }

  function hasAnswerRevealed() {
    var qa = document.getElementById("qa");
    if (!qa) return false;
    return !!(qa.querySelector(".ba-rv-answer")
              || qa.querySelector("hr#answer"));
  }

  window.__baEnterEdit = function () {
    if (editState.active) return;
    // Always edit with the back showing — front-only edits are confusing
    // when the user can't see what the back currently says. Anki's
    // question render doesn't contain the answer divider at all, so we
    // can't statically detect whether this card has a back; just try to
    // reveal, and short-circuit on the second pass if it didn't appear.
    if (!hasAnswerRevealed() && !editState.triedReveal) {
      editState.triedReveal = true;
      try { pycmd("ans"); } catch (_) {}
      var deadline = Date.now() + 2000;
      var poll = function () {
        if (hasAnswerRevealed() || Date.now() >= deadline) {
          window.__baEnterEdit();
        } else {
          setTimeout(poll, 40);
        }
      };
      setTimeout(poll, 40);
      return;
    }
    editState.triedReveal = false;
    var spans = fieldSpans();
    if (!spans.length) {
      // No editable fields detected — fall back to Anki's full editor.
      try { pycmd("ba:edit-full"); } catch (_) {}
      return;
    }
    editState.originals = {};
    spans.forEach(function (sp) {
      var name = sp.getAttribute("data-ba-field");
      editState.originals[name] = sp.innerHTML;
      sp.setAttribute("contenteditable", "true");
      sp.setAttribute("spellcheck", "true");
    });
    editState.active = true;
    document.body.classList.add("ba-editing");
    ensureEditToolbar().classList.add("ba-edit-bar--open");
    document.addEventListener("keydown", onEditKeydown, true);
    // Tell Python to disable the reviewer's Qt shortcuts so typing letters
    // and modifier+keys (⌘+Backspace, etc.) work as normal text editing
    // instead of triggering Anki's review-mode bindings.
    try { pycmd("ba:edit-state:on"); } catch (_) {}
    focusFirstField(spans);
  };

  window.__baExitEdit = function (save) {
    exitEdit(!!save);
  };

  function exitEdit(save) {
    if (!editState.active) return;
    var spans = fieldSpans();
    if (save) {
      var payload = collectPayload();
      try { pycmd("ba:edit-save:" + payload); } catch (_) {}
      // Python will re-render; we don't need to flip state ourselves —
      // the new render replaces the body and our editState is reset by
      // the watchBody MutationObserver picking up that ba-editing class
      // is no longer on the new body. Belt-and-braces: clear locally too.
    } else {
      // Discard: restore each field's original innerHTML.
      spans.forEach(function (sp) {
        var name = sp.getAttribute("data-ba-field");
        var orig = editState.originals[name];
        if (orig != null) sp.innerHTML = orig;
      });
    }
    spans.forEach(function (sp) {
      sp.removeAttribute("contenteditable");
      sp.removeAttribute("spellcheck");
    });
    editState.active = false;
    editState.originals = {};
    document.body.classList.remove("ba-editing");
    var bar = document.getElementById("ba-edit-bar");
    if (bar) bar.classList.remove("ba-edit-bar--open");
    document.removeEventListener("keydown", onEditKeydown, true);
    try { pycmd("ba:edit-state:off"); } catch (_) {}
  }

  function openFullEditor() {
    if (!editState.active) {
      try { pycmd("ba:edit-full:{}"); } catch (_) {}
      return;
    }
    // Send pending field text so the full editor opens with our edits
    // (Python applies the payload before opening EditCurrent).
    var payload = collectPayload();
    try { pycmd("ba:edit-full:" + payload); } catch (_) {}
    // Local cleanup — the full editor takes over from here.
    var spans = fieldSpans();
    spans.forEach(function (sp) {
      sp.removeAttribute("contenteditable");
      sp.removeAttribute("spellcheck");
    });
    editState.active = false;
    editState.originals = {};
    document.body.classList.remove("ba-editing");
    var bar = document.getElementById("ba-edit-bar");
    if (bar) bar.classList.remove("ba-edit-bar--open");
    document.removeEventListener("keydown", onEditKeydown, true);
    try { pycmd("ba:edit-state:off"); } catch (_) {}
  }

  function boot() {
    ensureBar();
    wrapAnswer();
    clickToReveal();
    watchBody();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
