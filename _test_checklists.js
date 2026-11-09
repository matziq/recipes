"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function run(slots, previous) {
  const writes = [], messages = [];
  const items = slots.map(slot => {
    const attributes = slot === null ? {} : { "data-progress-index": String(slot) };
    const classes = new Set();
    const handlers = {};
    return {
      attributes, handlers,
      getAttribute: key => attributes[key] ?? null,
      setAttribute: (key, value) => { attributes[key] = value; },
      classList: {
        add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name),
        toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name)
      },
      addEventListener: (type, handler) => { handlers[type] = handler; }
    };
  });
  const content = {
    querySelectorAll: selector => selector === "img" ? [] :
      selector === "li.checkable" ? items.filter(item => item.classList.contains("checkable")) : items
  };
  const body = {
    getAttribute: key => ({ "data-recipe-title": "Test", "data-recipe-category": "Breads" })[key] ?? null
  };
  const context = {
    Set, Number, Array, String, Boolean, console: { error() {} },
    document: {
      body, querySelector: selector => selector === ".recipe-content" ? content : null,
      addEventListener() {}
    },
    window: {
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
  return { items, writes, messages };
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
console.log("Checklist migration, legacy fallback, keyboard/link handling and invalid-state guards pass.");
