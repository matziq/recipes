"use strict";
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "assets", "appearance.js"), "utf8");

function setup(initial = {}, options = {}) {
  const store = { ...initial }, attrs = {}, handlers = {}, nodes = {};
  const media = { matches: !!options.reduced, addEventListener(type, cb) { this.change = cb; } };
  function node() {
    return {
      attributes: {}, handlers: {}, children: [], textContent: "", value: "",
      selectedOptions: [],
      style: { values: {}, setProperty(k, v) { this.values[k] = v; } },
      setAttribute(k, v) { this.attributes[k] = v; },
      addEventListener(k, cb) { this.handlers[k] = cb; },
      appendChild(child) { this.children.push(child); if (child.id) nodes[child.id] = child; },
      querySelector(selector) { return selector.includes("burger-arcade") ? this.children.find(c => c.value === "burger-arcade") : null; },
      remove() { delete nodes[this.id]; }
    };
  }
  const select = node(), mode = node(), motion = node(), surprise = node(), status = node();
  const document = {
    readyState: "loading",
    documentElement: { setAttribute: (k, v) => { attrs[k] = v; }, getAttribute: k => attrs[k] },
    body: node(), createElement: node, getElementById: id => nodes[id] || null,
    querySelector: selector => ({
      "[data-palette-select]": select, "[data-theme-toggle]": mode,
      "[data-motion-toggle]": motion, "[data-theme-surprise]": surprise,
      "[data-appearance-status]": status
    })[selector] || null,
    addEventListener: (type, cb) => { handlers[type] = cb; }
  };
  const localStorage = {
    getItem: key => store[key] ?? null,
    setItem: (key, value) => { if (options.blocked) throw Error("blocked"); store[key] = value; }
  };
  const notices = [];
  const window = { localStorage, location: { search: options.search || "" },
    matchMedia: query => query.includes("reduced-motion") ? media : { matches: !!options.systemDark },
    RecipesApp: { toast: message => notices.push(message) } };
  const context = { window, document, URLSearchParams, Math, RangeError };
  vm.runInNewContext(source, context);
  return { window, document, attrs, handlers, store, select, mode, motion, surprise, status, media, nodes, notices };
}
const themes = ["autumn", "winter", "spring", "summer", "ocean", "lavender", "terracotta", "forest", "burger-arcade"];
for (const theme of themes) for (const mode of ["light", "dark"]) {
  const t = setup({ familyRecipesPalette: JSON.stringify(theme), familyRecipesTheme: JSON.stringify(mode), familyRecipesMotion: "false" });
  assert.equal(t.attrs["data-palette"], theme, "Palette must be set before DOM ready");
  assert.equal(t.attrs["data-theme"], mode, "Mode must be set before DOM ready");
  t.handlers.DOMContentLoaded();
  assert.equal(t.select.value, theme);
  assert.equal(t.motion.attributes["aria-pressed"], "false");
  assert.equal(t.nodes["appearance-decoration"], undefined);
}
const random = setup().window.RecipesAppearance.chooseRandom;
assert.equal(random(0, "autumn"), "burger-arcade");
assert.equal(random(0.049999999, "autumn"), "burger-arcade");
assert.notEqual(random(0.05, "autumn"), "burger-arcade");
assert.throws(() => random(1, "winter"), /Random value/);
for (const theme of themes) for (const value of [0, .049999, .05, .2, .5, .999999]) {
  assert.notEqual(random(value, theme), theme);
  assert.ok(themes.includes(random(value, theme)));
}
const migrated = setup({ familyRecipesTheme: '"dark"' });
assert.equal(migrated.attrs["data-theme"], "dark");
assert.equal(migrated.attrs["data-palette"], "autumn");
assert.equal(setup({ familyRecipesTheme: '"dark"' }, { search: "?scoutTheme=light" }).attrs["data-theme"], "light");
assert.equal(setup({ familyRecipesTheme: '"bad"', familyRecipesPalette: '"bad"' }, { systemDark: true }).attrs["data-theme"], "dark");
const t = setup({}, { reduced: true });
assert.equal(t.attrs["data-motion"], "off");
t.handlers.DOMContentLoaded();
t.motion.handlers.click();
assert.equal(t.attrs["data-motion"], "on");
assert.equal(t.nodes["appearance-decoration"], undefined, "Reduced motion takes precedence over preference");
t.media.matches = false; t.media.change();
const layer = t.nodes["appearance-decoration"];
assert.equal(layer.children.length, 16);
assert.equal(layer.attributes["aria-hidden"], "true");
const xs = [], delays = new Set(), durations = new Set(), sways = new Set(), sizes = new Set();
layer.children.forEach((piece, i) => {
  const props = piece.style.values;
  const x = parseFloat(props["--piece-x"]);
  xs.push(x);
  assert.ok(x >= 1 + i * 6 && x < 1 + (i + 1) * 6);
  assert.ok(parseFloat(props["--piece-duration"]) >= 14 && parseFloat(props["--piece-duration"]) < 26);
  assert.ok(parseFloat(props["--piece-delay"]) >= 0 && parseFloat(props["--piece-delay"]) < 8);
  assert.ok(parseFloat(props["--piece-size"]) >= 14 && parseFloat(props["--piece-size"]) < 26);
  assert.ok(parseFloat(props["--piece-sway"]) >= -30 && parseFloat(props["--piece-sway"]) < 30);
  durations.add(props["--piece-duration"]); delays.add(props["--piece-delay"]);
  sizes.add(props["--piece-size"]); sways.add(props["--piece-sway"]);
});
assert.ok(xs[0] < 7 && xs[15] > 91);
assert.ok(durations.size > 1 && delays.size > 1 && sizes.size > 1 && sways.size > 1);
const css = fs.readFileSync(path.join(__dirname, "assets", "site.css"), "utf8");
assert.match(css, /\.appearance-decoration\s*\{[^}]*inset:\s*0;[^}]*pointer-events:\s*none/s);
assert.match(css, /\.appearance-decoration span\s*\{[^}]*top:\s*-10vh;[^}]*left:\s*var\(--piece-x\)/s);
assert.match(css, /@keyframes appearance-drift\s*\{[\s\S]*?120vh/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)\s*\{\s*\.appearance-decoration\s*\{\s*display:\s*none/);
assert.match(css, /@media print\s*\{\s*\.appearance-decoration\s*\{\s*display:\s*none/);
t.motion.handlers.click();
assert.equal(t.nodes["appearance-decoration"], undefined, "Off removes the animated layer");
assert.equal(t.store.familyRecipesMotion, "false");
t.select.value = "ocean"; t.select.handlers.change();
assert.equal(t.store.familyRecipesPalette, '"ocean"');
t.mode.handlers.click();
assert.equal(t.store.familyRecipesTheme, '"dark"');
const restored = setup(t.store); restored.handlers.DOMContentLoaded();
assert.equal(restored.select.value, "ocean");
assert.equal(restored.attrs["data-theme"], "dark");
assert.equal(restored.attrs["data-motion"], "off");
const blocked = setup({}, { blocked: true }); blocked.handlers.DOMContentLoaded(); blocked.mode.handlers.click();
assert.match(blocked.notices[0], /could not be saved/);
console.log("Appearance prepaint, all palettes/modes, RNG boundaries, migration, persistence and reduced motion pass.");
