(function () {
  "use strict";

  var recipes = [];
  var searchTimer;
  var q = document.getElementById("q");
  var browse = document.getElementById("browse");
  var results = document.getElementById("results");
  var list = document.getElementById("results-list");
  var status = document.getElementById("search-status");
  var collection = document.getElementById("collection-view");
  var collectionTitle = document.getElementById("collection-title");
  var collectionGrid = document.getElementById("collection-grid");

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[character];
    });
  }

  function normalize(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function recipeByUrl(url) {
    var normalized = window.RecipesApp.normalizeUrl(url);
    return recipes.find(function (recipe) {
      return window.RecipesApp.normalizeUrl(recipe.url) === normalized;
    });
  }

  function matchRecipe(recipe, query) {
    var tokens = normalize(query).split(/\s+/).filter(Boolean);
    var title = normalize(recipe.title);
    var category = normalize(recipe.category + " " + (recipe.sub || ""));
    var ingredients = normalize((recipe.ingredients || []).join(" "));
    var all = title + " " + category + " " + ingredients;
    if (!tokens.every(function (token) { return all.includes(token); })) return -1;
    return tokens.reduce(function (score, token) {
      if (title === token) return score + 20;
      if (title.startsWith(token)) return score + 12;
      if (title.includes(token)) return score + 8;
      if (category.includes(token)) return score + 4;
      if (ingredients.includes(token)) return score + 2;
      return score;
    }, 0);
  }

  function cardMarkup(recipe) {
    var sub = recipe.sub ? " &rsaquo; " + escapeHtml(recipe.sub) : "";
    var badge = recipe.new ? '<span class="tag new">New</span>' : "";
    return '<li><a href="' + escapeHtml(recipe.url) + '">' +
      '<span>' + escapeHtml(recipe.title) + "</span> " + badge +
      '<div class="meta">' + escapeHtml(recipe.category) + sub + "</div>" +
      "</a></li>";
  }

  function showBrowse() {
    results.classList.remove("active");
    collection.classList.remove("active");
    browse.hidden = false;
    status.textContent = "";
    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.classList.remove("is-active");
    });
  }

  function renderSearch() {
    var query = q.value.trim();
    if (!query) {
      showBrowse();
      return;
    }
    var matches = recipes.map(function (recipe) {
      return { recipe: recipe, score: matchRecipe(recipe, query) };
    }).filter(function (item) {
      return item.score >= 0;
    }).sort(function (a, b) {
      return b.score - a.score || a.recipe.title.localeCompare(b.recipe.title);
    }).slice(0, 120).map(function (item) {
      return item.recipe;
    });

    list.innerHTML = matches.length
      ? matches.map(cardMarkup).join("")
      : '<li class="empty">No recipes matched. Try a category, ingredient, or shorter phrase.</li>';
    browse.hidden = true;
    collection.classList.remove("active");
    results.classList.add("active");
    status.textContent = matches.length + (matches.length === 1 ? " recipe found" : " recipes found");
  }

  function scheduleSearch() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(renderSearch, 70);
  }

  function renderCollection(kind) {
    var items = [];
    var title = "";
    if (kind === "favorites") {
      title = "Your favorites";
      items = window.RecipesApp.favorites().map(function (item) {
        return recipeByUrl(typeof item === "string" ? item : item.url) || item;
      }).filter(Boolean);
    } else {
      title = "Recently viewed";
      items = window.RecipesApp.read(window.RecipesApp.keys.recent, []).map(function (item) {
        return recipeByUrl(item.url) || item;
      }).filter(Boolean);
    }

    collectionTitle.textContent = title;
    collectionGrid.innerHTML = items.length
      ? items.map(function (recipe) {
        return '<article class="collection-card"><a href="' + escapeHtml(recipe.url) + '">' +
          escapeHtml(recipe.title) +
          '<div class="collection-meta">' + escapeHtml(recipe.category || "") + "</div>" +
          "</a></article>";
      }).join("")
      : '<div class="empty-state">' +
        (kind === "favorites"
          ? "No favorites yet. Open a recipe and tap the heart to save it here."
          : "Recipes you open will appear here for quick access.") +
        "</div>";
    q.value = "";
    results.classList.remove("active");
    browse.hidden = true;
    collection.classList.add("active");
    status.textContent = "";
    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.classList.toggle("is-active", button.getAttribute("data-view") === kind);
    });
  }

  function updateFavoriteCount() {
    var count = window.RecipesApp.favorites().length;
    document.querySelectorAll("[data-favorite-count]").forEach(function (node) {
      node.textContent = String(count);
    });
  }

  function initEvents() {
    q.addEventListener("input", scheduleSearch);
    q.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        q.value = "";
        showBrowse();
        q.blur();
      } else if (event.key === "ArrowDown") {
        var first = results.querySelector("a");
        if (first) {
          event.preventDefault();
          first.focus();
        }
      }
    });

    var clear = document.querySelector("[data-search-clear]");
    if (clear) clear.addEventListener("click", function () {
      q.value = "";
      showBrowse();
      q.focus();
    });

    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.addEventListener("click", function () {
        var kind = button.getAttribute("data-view");
        if (button.classList.contains("is-active")) {
          showBrowse();
        } else {
          renderCollection(kind);
        }
      });
    });

    document.querySelectorAll("[data-surprise]").forEach(function (button) {
      button.addEventListener("click", function () {
        if (!recipes.length) return;
        var recipe = recipes[Math.floor(Math.random() * recipes.length)];
        window.location.href = recipe.url;
      });
    });

    document.querySelectorAll(".cat").forEach(function (link) {
      link.addEventListener("click", function () {
        var target = document.querySelector(link.getAttribute("href"));
        if (target && target.tagName === "DETAILS") target.open = true;
      });
    });

    document.addEventListener("recipes:favorites", updateFavoriteCount);
    updateFavoriteCount();
  }

  function openSectionFromHash() {
    if (!window.location.hash) return;
    try {
      var target = document.querySelector(window.location.hash);
      if (target && target.tagName === "DETAILS") {
        target.open = true;
        window.setTimeout(function () {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 30);
      }
    } catch (error) {
      return;
    }
  }

  fetch("recipes_index.json")
    .then(function (response) {
      if (!response.ok) throw new Error("Could not load recipes");
      return response.json();
    })
    .then(function (data) {
      recipes = data;
      initEvents();
      openSectionFromHash();
    })
    .catch(function () {
      status.textContent = "Recipe search is temporarily unavailable.";
      initEvents();
    });

  window.addEventListener("hashchange", openSectionFromHash);
})();
