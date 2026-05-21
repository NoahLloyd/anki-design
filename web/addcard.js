// BetterAnki — Add Card editor webview script.
//
// Tags <html> so addcard.css can scope its overrides to the editor when it's
// being shown in the AddCards window (not Browser, not Edit-Current). Anki's
// CSP blocks inline scripts on the editor page, so this work happens in a
// loaded JS file rather than a <script> in the page head.
//
// Also moves the gear/options button to the end of the toolbar (visual
// order). CSS `order:` should do this but Anki's Svelte adds extra wrappers
// that defeat the flex-order on some builds; a one-shot DOM reorder is
// reliable and runs once on first paint plus once after Anki's async
// editor ready.
(function () {
  "use strict";
  try {
    document.documentElement.dataset.baEditor = "add";
    var theme = document.querySelector('meta[name="ba-theme"]');
    if (theme && theme.content) {
      document.documentElement.dataset.rfTheme = theme.content;
    }
  } catch (_) {}

  function reorderToolbar() {
    var toolbar = document.querySelector(".button-toolbar.btn-toolbar");
    var settings = document.getElementById("settings");
    if (!toolbar || !settings) return false;
    // Walk up to find the closest sibling-set container.
    var parent = settings.parentElement;
    if (!parent) return false;
    // Move to last position in its parent (the dynamically-slottable wrapper).
    if (parent.lastElementChild !== settings) {
      parent.appendChild(settings);
    }
    return true;
  }

  // Try immediately, then a few delayed tries to catch the async editor
  // ready.
  reorderToolbar();
  var attempts = 0;
  var iv = setInterval(function () {
    attempts += 1;
    if (reorderToolbar() || attempts > 30) clearInterval(iv);
  }, 200);
})();
