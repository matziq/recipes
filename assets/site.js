(function () {
  "use strict";

  var KEYS = {
    favorites: "familyRecipesFavorites",
    recent: "familyRecipesRecent",
    theme: "familyRecipesTheme"
  };

  function read(key, fallback) {
    try {
      var value = window.localStorage.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (error) {
      return false;
    }
  }

  function normalizeUrl(url) {
    var raw = String(url || "").replace(/^\.\//, "");
    if (/^recipes\//.test(raw)) return raw;
    try {
      var pathname = new URL(raw, window.location.href).pathname;
      var marker = pathname.lastIndexOf("/recipes/");
      return marker >= 0 ? pathname.slice(marker + 1) : pathname.replace(/^\//, "");
    } catch (error) {
      return raw.replace(/^\.\.\//g, "");
    }
  }

  function favorites() {
    return read(KEYS.favorites, []);
  }

  function isFavorite(url) {
    var normalized = normalizeUrl(url);
    return favorites().some(function (item) {
      return normalizeUrl(typeof item === "string" ? item : item.url) === normalized;
    });
  }

  function toggleFavorite(recipe) {
    var list = favorites();
    var normalized = normalizeUrl(recipe.url);
    var index = list.findIndex(function (item) {
      return normalizeUrl(typeof item === "string" ? item : item.url) === normalized;
    });
    var added = index < 0;
    if (added) {
      list.unshift({
        title: recipe.title || document.title.replace(/\s*[\u2022|-]\s*Recipes.*$/, ""),
        category: recipe.category || "",
        url: normalized
      });
    } else {
      list.splice(index, 1);
    }
    write(KEYS.favorites, list);
    document.dispatchEvent(new CustomEvent("recipes:favorites", {
      detail: { added: added, recipe: recipe, favorites: list }
    }));
    return added;
  }

  function addRecent(recipe) {
    var list = read(KEYS.recent, []);
    var normalized = normalizeUrl(recipe.url);
    list = list.filter(function (item) {
      return normalizeUrl(item.url) !== normalized;
    });
    list.unshift({
      title: recipe.title,
      category: recipe.category || "",
      url: normalized,
      viewedAt: Date.now()
    });
    write(KEYS.recent, list.slice(0, 12));
  }

  var toastTimer;
  function toast(message) {
    var node = document.getElementById("site-toast");
    if (!node) {
      node = document.createElement("div");
      node.id = "site-toast";
      node.className = "toast";
      node.setAttribute("role", "status");
      node.setAttribute("aria-live", "polite");
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      node.classList.remove("visible");
    }, 2600);
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    write(KEYS.theme, theme);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var isDark = theme === "dark";
      button.setAttribute("aria-label", isDark ? "Use light theme" : "Use dark theme");
      button.setAttribute("title", isDark ? "Use light theme" : "Use dark theme");
      var icon = button.querySelector("[data-theme-icon]");
      if (icon) icon.textContent = isDark ? "\u2600" : "\u263E";
    });
  }

  function updateFavoriteButtons() {
    document.querySelectorAll("[data-favorite]").forEach(function (button) {
      var active = isFavorite(button.getAttribute("data-url") || window.location.pathname);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("title", active ? "Remove from favorites" : "Save to favorites");
      var icon = button.querySelector("[data-favorite-icon]");
      if (icon) icon.textContent = active ? "\u2665" : "\u2661";
      var label = button.querySelector("[data-favorite-label]");
      if (label) label.textContent = active ? "Saved" : "Save";
    });
  }

  function init() {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        setTheme(next);
      });
    });

    document.querySelectorAll("[data-favorite]").forEach(function (button) {
      button.addEventListener("click", function () {
        var added = toggleFavorite({
          title: button.getAttribute("data-title") || "",
          category: button.getAttribute("data-category") || "",
          url: button.getAttribute("data-url") || window.location.pathname
        });
        toast(added ? "Saved to favorites" : "Removed from favorites");
      });
    });

    document.addEventListener("recipes:favorites", updateFavoriteButtons);
    updateFavoriteButtons();
    setTheme(read(KEYS.theme, null) || document.documentElement.getAttribute("data-theme") || "light");
  }

  window.RecipesApp = {
    addRecent: addRecent,
    favorites: favorites,
    isFavorite: isFavorite,
    normalizeUrl: normalizeUrl,
    read: read,
    toast: toast,
    toggleFavorite: toggleFavorite,
    write: write,
    keys: KEYS
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
