// Anki Design — reviewer progress bar + body cleanup + answer-reveal wrap.
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
