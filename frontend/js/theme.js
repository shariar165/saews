// Applies the saved (or system) colour theme before first paint to avoid a flash. Classic script, loaded in <head>.
(function () {
  var t = null;
  try { t = localStorage.getItem("saews-theme"); } catch (e) { /* storage blocked */ }
  if (t !== "light" && t !== "dark") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", t);
})();
