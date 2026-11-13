(function () {
  "use strict";

  var regular = ["autumn", "winter", "spring", "summer", "ocean", "lavender", "terracotta", "forest"];
  var all = regular.concat("burger-arcade");
  var keys = { palette: "familyRecipesPalette", mode: "familyRecipesTheme", motion: "familyRecipesMotion" };
  var root = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  function read(key) {
    try { return JSON.parse(window.localStorage.getItem(key)); }
    catch (error) { return null; }
  }
  function write(key, value) {
    try { window.localStorage.setItem(key, JSON.stringify(value)); return true; }
    catch (error) { return false; }
  }
  function initialMode() {
    var query = new URLSearchParams(window.location.search).get("scoutTheme");
    if (query === "light" || query === "dark") return query;
    var saved = read(keys.mode);
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function chooseRandom(value, current) {
    if (!(value >= 0 && value < 1)) throw new RangeError("Random value must be in [0, 1)");
    var choices = regular.filter(function (name) { return name !== current; });
    if (current !== "burger-arcade" && value < 0.05) return "burger-arcade";
    var scaled = current === "burger-arcade" ? value : (value - 0.05) / 0.95;
    return choices[Math.min(Math.floor(scaled * choices.length), choices.length - 1)];
  }
  var palette = read(keys.palette);
  root.setAttribute("data-palette", all.includes(palette) ? palette : "autumn");
  root.setAttribute("data-theme", initialMode());
  var savedMotion = read(keys.motion);
  root.setAttribute("data-motion", savedMotion === false || (savedMotion !== true && reduced.matches) ? "off" : "on");

  function apply(attribute, key, value) {
    root.setAttribute(attribute, value);
    if (!write(key, value === "on" ? true : value === "off" ? false : value)) {
      window.RecipesApp.toast("Appearance changed for this page, but could not be saved.");
    }
    update();
  }
  function decoration() {
    var old = document.getElementById("appearance-decoration");
    if (old) old.remove();
    if (root.getAttribute("data-motion") !== "on" || reduced.matches) return;
    var selected = root.getAttribute("data-palette");
    var glyph = { autumn: "🍂", winter: "❄", spring: "✿", summer: "☀",
      ocean: "•", lavender: "✿", terracotta: "◆", forest: "🍃" }[selected];
    var layer = document.createElement("div");
    layer.id = "appearance-decoration";
    layer.className = "appearance-decoration";
    layer.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 16; i++) {
      var piece = document.createElement("span");
      piece.className = selected === "burger-arcade" ? "arcade-burger" : "appearance-particle";
      if (glyph) piece.textContent = glyph;
      piece.style.setProperty("--piece-x", (1 + (i + Math.random()) * 6) + "%");
      piece.style.setProperty("--piece-duration", (14 + Math.random() * 12) + "s");
      piece.style.setProperty("--piece-delay", (Math.random() * 8) + "s");
      piece.style.setProperty("--piece-size", (14 + Math.random() * 12) + "px");
      piece.style.setProperty("--piece-sway", (Math.random() * 60 - 30) + "px");
      layer.appendChild(piece);
    }
    document.body.appendChild(layer);
  }
  function update() {
    var select = document.querySelector("[data-palette-select]");
    var mode = document.querySelector("[data-theme-toggle]");
    var motion = document.querySelector("[data-motion-toggle]");
    var status = document.querySelector("[data-appearance-status]");
    var palette = root.getAttribute("data-palette");
    var dark = root.getAttribute("data-theme") === "dark";
    var enabled = root.getAttribute("data-motion") === "on";
    if (select) {
      var bonus = select.querySelector('option[value="burger-arcade"]');
      if (palette === "burger-arcade" && !bonus) {
        bonus = document.createElement("option");
        bonus.value = "burger-arcade";
        bonus.textContent = "Burger Arcade (unofficial homage)";
        select.appendChild(bonus);
      }
      select.value = palette;
    }
    if (mode) {
      mode.textContent = dark ? "Switch to light mode" : "Switch to dark mode";
      mode.setAttribute("aria-pressed", String(dark));
    }
    if (motion) {
      motion.setAttribute("aria-pressed", String(enabled));
      motion.textContent = enabled ? "Animations: on" : "Animations: off";
    }
    if (status) {
      var selectedLabel = select && select.selectedOptions.length
        ? select.selectedOptions[0].textContent : palette;
      status.textContent = "Current theme: " + selectedLabel + ". " +
        (palette === "burger-arcade" ? "An unofficial original homage, not affiliated with BurgerTime. " : "") +
        (reduced.matches && enabled ? "Animation is paused by your reduced-motion setting." : "");
    }
    decoration();
  }
  function init() {
    var select = document.querySelector("[data-palette-select]");
    var mode = document.querySelector("[data-theme-toggle]");
    var motion = document.querySelector("[data-motion-toggle]");
    var surprise = document.querySelector("[data-theme-surprise]");
    if (select) select.addEventListener("change", function () {
      if (all.includes(select.value)) apply("data-palette", keys.palette, select.value);
    });
    if (mode) mode.addEventListener("click", function () {
      apply("data-theme", keys.mode, root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
    if (motion) motion.addEventListener("click", function () {
      apply("data-motion", keys.motion, root.getAttribute("data-motion") === "on" ? "off" : "on");
    });
    if (surprise) surprise.addEventListener("click", function () {
      apply("data-palette", keys.palette, chooseRandom(Math.random(), root.getAttribute("data-palette")));
    });
    if (reduced.addEventListener) reduced.addEventListener("change", update);
    else if (reduced.addListener) reduced.addListener(update);
    update();
  }
  window.RecipesAppearance = { chooseRandom: chooseRandom, regular: regular.slice(), keys: keys };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
