"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function run(slots, previous) {
  const writes = [], messages = [];
  function element(attributes = {}) {
    const classes = new Set();
    const handlers = {};
    return {
      attributes, handlers,
      getAttribute: key => attributes[key] ?? null,
      setAttribute: (key, value) => { attributes[key] = value; },
      classList: {
        add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name),
        toggle: (name, enabled = !classes.has(name)) => {
          if (enabled) classes.add(name); else classes.delete(name);
          return enabled;
        }
      },
      addEventListener: (type, handler) => { handlers[type] = handler; }
    };
  }
  const items = slots.map(slot => element(slot === null ? {} : { "data-progress-index": String(slot) }));
  const disclosure = { attributes: {}, open: true }, shopping = { attributes: {}, open: false };
  const note = { open: false }, instruction = { open: true };
  const image = element(), cookButton = element(), printButton = element();
  const events = {};
  const content = {
    querySelectorAll: selector => {
      if (selector === "img") return [image];
      if (selector === "details.cooking-section") return [disclosure, instruction];
      if (selector === "li.checkable") return items.filter(item => item.classList.contains("checkable"));
      assert.equal(selector, "li.recipe-ingredient, li.recipe-instruction",
        "Only cooking items may become checkboxes, not disclosures or shopping lists");
      return items;
    }
  };
  const body = {
    getAttribute: key => ({ "data-recipe-title": "Test", "data-recipe-category": "Breads" })[key] ?? null,
    classList: element().classList
  };
  const context = {
    Set, Number, Array, String, Boolean, navigator: {}, console: { error() {} },
    document: {
      body, querySelector: selector => ({
        ".recipe-content": content, "[data-cook-mode]": cookButton, "[data-print]": printButton
      })[selector] ?? null,
      querySelectorAll: selector => {
        assert.equal(selector, ".shopping-list, .dish-note, details.cooking-section");
        return [shopping, note, disclosure, instruction];
      },
      addEventListener() {}
    },
    window: {
      addEventListener: (type, handler) => { events[type] = handler; },
      print() { events.beforeprint(); },
      location: { pathname: "/recipes/recipes/breads/test.html" },
      RecipesApp: {
        normalizeUrl: value => value.replace("/recipes/", ""),
        addRecent() {}, read: () => previous,
        write: (key, value) => writes.push([key, Array.from(value)]),
        toast: message => messages.push(message)
      }
    },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "assets", "recipe.js"), "utf8"), context);
  return { items, writes, messages, disclosure, shopping, note, instruction, image,
    cookButton, printButton, events };
}

// New ingredients precede legacy instructions visually, but are appended in storage.
const migrated = run([2, 3, 0, 1], [true, false]);
assert.equal(migrated.items[0].attributes["aria-checked"], "false");
assert.equal(migrated.items[2].attributes["aria-checked"], "true");
assert.deepEqual(migrated.writes[0], [
  "familyRecipesProgress:recipes/breads/test.html", [true, false, false, false]
]);
const item = migrated.items[0];
item.handlers.click({ target: { closest: selector => selector === "li.checkable" ? item : null } });
assert.deepEqual(migrated.writes.at(-1)[1], [true, false, true, false]);
const count = migrated.writes.length;
item.handlers.click({ target: { closest: () => ({ tagName: "A" }) } });
item.handlers.keydown({ key: "Enter", target: { tagName: "A" } });
assert.equal(migrated.writes.length, count, "Following a citation must not toggle a checkbox");
item.handlers.click({
  target: { closest: selector => selector === "li.checkable" ? migrated.items[1] : null }
});
assert.equal(migrated.writes.length, count, "Nested checklist clicks must not toggle their parent");
let prevented = false;
item.handlers.keydown({ key: " ", target: item, preventDefault() { prevented = true; } });
assert.equal(prevented, true);
assert.deepEqual(migrated.writes.at(-1)[1], [true, false, false, false]);
const unchanged = run([null, null], [false, true]);
assert.deepEqual(unchanged.writes[0][1], [false, true]);
const invalid = run([0, 0], [true]);
assert.equal(invalid.writes.length, 0);
assert.equal(invalid.messages.length, 1);
const malformed = run(["invalid"], [true]);
assert.equal(malformed.writes.length, 0);
const retained = run([0, 2], [false, true, true]);
assert.deepEqual(retained.writes[0][1], [false, true, true]);
retained.items[0].handlers.keydown({
  key: "Enter", target: retained.items[0], preventDefault() {}
});
assert.deepEqual(retained.writes.at(-1)[1], [true, true, true],
  "Inactive legacy slots must survive subsequent cooking progress writes");
assert.equal(retained.disclosure.attributes.role, undefined);
assert.equal(retained.shopping.attributes.role, undefined);
assert.equal(run([], []).writes.length, 0, "Reference pages have no cooking checkboxes");
const controls = run([0], [true]);
assert.equal(controls.image.attributes["aria-expanded"], "false");
controls.image.handlers.click();
assert.equal(controls.image.attributes["aria-expanded"], "true");
assert.equal(controls.image.attributes["aria-label"], "Shrink recipe image");
let imagePrevented = false;
controls.image.handlers.keydown({ key: " ", preventDefault() { imagePrevented = true; } });
assert.equal(imagePrevented, true);
assert.equal(controls.image.attributes["aria-expanded"], "false");
controls.image.handlers.keydown({ key: "Enter", preventDefault() {} });
assert.equal(controls.image.attributes["aria-expanded"], "true");
controls.disclosure.open = false;
controls.printButton.handlers.click();
assert.ok([controls.disclosure, controls.instruction, controls.shopping, controls.note].every(d => d.open));
controls.events.beforeprint(); // Repeated native event must not replace the original snapshot.
controls.events.afterprint();
assert.deepEqual([controls.disclosure.open, controls.instruction.open, controls.shopping.open, controls.note.open],
  [false, true, false, false]);
controls.events.beforeprint(); // Browser-menu printing uses the same path.
controls.events.afterprint();
controls.instruction.open = false;
controls.cookButton.handlers.click({ currentTarget: controls.cookButton });
assert.equal(controls.disclosure.open, true);
assert.equal(controls.instruction.open, true);
assert.equal(controls.shopping.open, false);
assert.equal(controls.note.open, false);
assert.equal(controls.items[0].attributes["aria-checked"], "true");
const site = { window: {}, document: { readyState: "loading", addEventListener() {} } };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "assets", "site.js"), "utf8"), site);
assert.deepEqual(["Zebra", "Éclair", "apples", "Apple's cake"].sort(site.window.RecipesApp.compareTitles),
  ["apples", "Apple's cake", "Éclair", "Zebra"]);
console.log("Cooking-only checkboxes, stable slots, isolation, keyboard/links, sorting, images, print restoration and cook-mode disclosures pass.");
