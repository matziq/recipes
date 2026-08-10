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
  var surpriseDialog = document.getElementById("surprise-dialog");
  var surpriseChoices = document.getElementById("surprise-choices");
  var surpriseResult = document.getElementById("surprise-result");
  var lastSurpriseChoice = "smart";

  var MEALS = {
    breakfast: ["breakfast"],
    lunch: ["salads", "sandwiches", "soups", "pasta", "seafood", "vegetarian tofu"],
    dinner: ["beef", "chicken", "luau", "pasta", "pork", "seafood", "sides", "soups", "turkey", "vegetarian tofu"],
    dessert: ["desserts"],
    snack: ["appetizers", "breads", "drinks", "fruit", "sauces dips", "snacks"]
  };

  var MEAL_LABELS = {
    breakfast: "Breakfast",
    lunch: "Lunch",
    dinner: "Dinner",
    dessert: "Dessert",
    snack: "Snack or drink"
  };

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

  function seasonFor(date) {
    var month = date.getMonth();
    if (month >= 2 && month <= 4) return "spring";
    if (month >= 5 && month <= 7) return "summer";
    if (month >= 8 && month <= 10) return "fall";
    return "winter";
  }

  function mealForTime(date) {
    var hour = date.getHours();
    if (hour >= 5 && hour < 11) return "breakfast";
    if (hour >= 11 && hour < 15) return "lunch";
    if (hour >= 15 && hour < 17) return "snack";
    if (hour >= 17 && hour < 23) return "dinner";
    return "snack";
  }

  function isSummerHeatRecipe(recipe) {
    var text = normalize(recipe.category + " " + recipe.title);
    return normalize(recipe.category) === "soups" ||
      /\b(soup|stew|chili|chowder|bisque|hot chocolate)\b/.test(text);
  }

  function seasonalScore(recipe, season) {
    var text = normalize(recipe.category + " " + recipe.title + " " + (recipe.ingredients || []).join(" "));
    var score = 1;
    if (season === "summer") {
      if (/\b(salad|grill|fresh|berry|lemon|lime|mango|avocado|cold|no bake|ice cream|smoothie)\b/.test(text)) score += 5;
      if (/salads|drinks|fruit|sandwiches|seafood/.test(normalize(recipe.category))) score += 3;
    } else if (season === "fall") {
      if (/\b(apple|pumpkin|squash|cider|maple|cranberry|pecan|roast|soup|stew|chili)\b/.test(text)) score += 5;
      if (/breads|soups|desserts/.test(normalize(recipe.category))) score += 2;
    } else if (season === "winter") {
      if (/\b(soup|stew|chili|bake|roast|potato|chocolate|cinnamon)\b/.test(text)) score += 5;
      if (/soups|breads|beef|desserts/.test(normalize(recipe.category))) score += 2;
    } else {
      if (/\b(salad|lemon|berry|asparagus|pea|fresh|herb|strawberry)\b/.test(text)) score += 5;
      if (/salads|fruit|vegetarian/.test(normalize(recipe.category))) score += 2;
    }
    return score;
  }

  function mealMatches(recipe, meal) {
    var category = normalize(recipe.category).replace(/[^a-z ]/g, "").replace(/\s+/g, " ").trim();
    return MEALS[meal].includes(category);
  }

  function chooseSurprise(choice, date, random) {
    var now = date || new Date();
    var season = seasonFor(now);
    var meal = choice === "smart" ? mealForTime(now) : choice;
    var candidates = recipes.filter(function (recipe) {
      return mealMatches(recipe, meal);
    });
    if (season === "summer") {
      var summerCandidates = candidates.filter(function (recipe) {
        return !isSummerHeatRecipe(recipe);
      });
      if (summerCandidates.length) candidates = summerCandidates;
    }
    if (!candidates.length) candidates = recipes.slice();
    var roll = random || Math.random;
    var ranked = candidates.map(function (recipe) {
      return { recipe: recipe, score: seasonalScore(recipe, season) + roll() * 4 };
    }).sort(function (a, b) {
      return b.score - a.score;
    });
    var shortlist = ranked.slice(0, Math.max(1, Math.ceil(ranked.length / 3)));
    var picked = shortlist[Math.floor(roll() * shortlist.length)].recipe;
    return {
      recipe: picked,
      meal: meal,
      season: season,
      context: MEAL_LABELS[meal] + " for a " + season + " " +
        (now.getHours() < 12 ? "morning" : now.getHours() < 17 ? "afternoon" : "evening")
    };
  }

  function renderSurprise(choice) {
    if (!recipes.length) {
      window.RecipesApp.toast("Recipes are still loading");
      return;
    }
    lastSurpriseChoice = choice;
    var pick = chooseSurprise(choice);
    document.getElementById("surprise-recipe-title").textContent = pick.recipe.title;
    document.getElementById("surprise-recipe-meta").textContent =
      pick.context + " \u2022 " + pick.recipe.category;
    document.getElementById("surprise-open").href = pick.recipe.url;
    surpriseChoices.hidden = true;
    surpriseResult.hidden = false;
  }

  function openSurprise() {
    if (!surpriseDialog) return;
    surpriseChoices.hidden = false;
    surpriseResult.hidden = true;
    var now = new Date();
    document.getElementById("surprise-context").textContent =
      "It is " + seasonFor(now) + " where you are. Smart pick will suggest " +
      MEAL_LABELS[mealForTime(now)].toLowerCase() + " for this time of day.";
    surpriseDialog.showModal();
  }

  function initLeaves() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    try {
      if (window.sessionStorage.getItem("familyRecipesLeavesShown")) return;
      window.sessionStorage.setItem("familyRecipesLeavesShown", "1");
    } catch (error) {
      return;
    }
    var shower = document.createElement("div");
    shower.className = "leaf-shower";
    shower.setAttribute("aria-hidden", "true");
    for (var index = 0; index < 14; index += 1) {
      var leaf = document.createElement("span");
      leaf.className = "falling-leaf";
      leaf.textContent = index % 2 ? "\ud83c\udf42" : "\ud83c\udf41";
      leaf.style.setProperty("--leaf-x", (3 + index * 7) + "vw");
      leaf.style.setProperty("--leaf-drift", ((index % 3 - 1) * 55) + "px");
      leaf.style.setProperty("--leaf-delay", (index * 0.16) + "s");
      leaf.style.setProperty("--leaf-duration", (3.8 + index % 4 * 0.45) + "s");
      shower.appendChild(leaf);
    }
    document.body.appendChild(shower);
    window.setTimeout(function () { shower.remove(); }, 6500);
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
      button.addEventListener("click", openSurprise);
    });

    document.querySelectorAll("[data-surprise-choice]").forEach(function (button) {
      button.addEventListener("click", function () {
        renderSurprise(button.getAttribute("data-surprise-choice"));
      });
    });
    document.querySelector("[data-surprise-again]")?.addEventListener("click", function () {
      renderSurprise(lastSurpriseChoice);
    });
    document.querySelector("[data-surprise-back]")?.addEventListener("click", function () {
      surpriseResult.hidden = true;
      surpriseChoices.hidden = false;
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
      initLeaves();
      openSectionFromHash();
    })
    .catch(function () {
      status.textContent = "Recipe search is temporarily unavailable.";
      initEvents();
    });

  window.addEventListener("hashchange", openSectionFromHash);
  window.RecipeSurprise = {
    choose: chooseSurprise,
    isSummerHeatRecipe: isSummerHeatRecipe,
    mealForTime: mealForTime,
    seasonFor: seasonFor
  };
})();
