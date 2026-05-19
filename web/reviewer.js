// BetterAnki — reviewer progress bar. Python pushes values via window.__reforgeProgress.
(function () {
  function ensureBar() {
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

  window.__reforgeProgress = function (pct, done, rem) {
    ensureBar();
    var fill = document.getElementById("reforge-progress-fill");
    var label = document.getElementById("reforge-progress-label");
    if (fill) fill.style.width = pct + "%";
    if (label) label.textContent = done + " / " + (done + rem);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureBar);
  } else {
    ensureBar();
  }
})();
