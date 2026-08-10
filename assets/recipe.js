(function () {
  "use strict";

  var body = document.body;
  var content = document.querySelector(".recipe-content");
  if (!content || !window.RecipesApp) return;

  var recipe = {
    title: body.getAttribute("data-recipe-title") || document.title.replace(/\s*\u2022\s*Recipes.*$/, ""),
    category: body.getAttribute("data-recipe-category") || "",
    url: body.getAttribute("data-recipe-url") || window.location.pathname
  };
  var root = body.getAttribute("data-root") || "../../";
  var progressKey = "familyRecipesProgress:" + window.RecipesApp.normalizeUrl(recipe.url);
  var textSizes = ["1rem", "1.15rem", "1.3rem"];
  var textSizeIndex = 0;
  var wakeLock = null;

  window.RecipesApp.addRecent(recipe);

  function checkableItems() {
    return Array.from(content.querySelectorAll("li.checkable"));
  }

  function updateProgress() {
    var items = checkableItems();
    var done = items.filter(function (item) { return item.classList.contains("is-done"); }).length;
    var ratio = items.length ? done / items.length : 0;
    var bar = document.querySelector("[data-progress-bar]");
    var label = document.querySelector("[data-progress-label]");
    if (bar) bar.style.transform = "scaleX(" + ratio + ")";
    if (label) label.textContent = items.length ? done + " / " + items.length : "Ready";
    window.RecipesApp.write(progressKey, items.map(function (item) {
      return item.classList.contains("is-done");
    }));
  }

  function initChecklists() {
    var saved = window.RecipesApp.read(progressKey, []);
    Array.from(content.querySelectorAll("ul li, ol li")).forEach(function (item, index) {
      item.classList.add("checkable");
      item.setAttribute("role", "checkbox");
      item.setAttribute("tabindex", "0");
      item.setAttribute("aria-checked", String(Boolean(saved[index])));
      item.classList.toggle("is-done", Boolean(saved[index]));
      function toggle() {
        var done = !item.classList.contains("is-done");
        item.classList.toggle("is-done", done);
        item.setAttribute("aria-checked", String(done));
        updateProgress();
      }
      item.addEventListener("click", toggle);
      item.addEventListener("keydown", function (event) {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          toggle();
        }
      });
    });
    updateProgress();
  }

  async function shareRecipe() {
    var data = {
      title: recipe.title,
      text: "Try this recipe: " + recipe.title,
      url: window.location.href
    };
    if (navigator.share) {
      try {
        await navigator.share(data);
        return;
      } catch (error) {
        if (error.name === "AbortError") return;
      }
    }
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(window.location.href);
        window.RecipesApp.toast("Recipe link copied");
        return;
      } catch (error) {
        window.RecipesApp.toast("Could not copy the link");
        return;
      }
    }
    window.RecipesApp.toast("Use your browser menu to share this recipe");
  }

  async function setCookMode(enabled) {
    body.classList.toggle("cook-mode", enabled);
    var button = document.querySelector("[data-cook-mode]");
    if (button) {
      button.classList.toggle("is-active", enabled);
      button.setAttribute("aria-pressed", String(enabled));
    }
    if (enabled && "wakeLock" in navigator) {
      try {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", function () { wakeLock = null; });
      } catch (error) {
        window.RecipesApp.toast("Cook mode is on, but screen wake lock is unavailable");
      }
    } else if (!enabled && wakeLock) {
      await wakeLock.release();
      wakeLock = null;
    }
  }

  function initImages() {
    content.querySelectorAll("img").forEach(function (image) {
      image.setAttribute("tabindex", "0");
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", "Expand recipe image");
      function toggle() {
        var expanded = image.classList.toggle("image-expanded");
        image.setAttribute("aria-label", expanded ? "Shrink recipe image" : "Expand recipe image");
      }
      image.addEventListener("click", toggle);
      image.addEventListener("keydown", function (event) {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          toggle();
        }
      });
    });
  }

  function renderRelated() {
    fetch(root + "recipes_index.json")
      .then(function (response) {
        if (!response.ok) throw new Error("Related recipes unavailable");
        return response.json();
      })
      .then(function (allRecipes) {
        var current = window.RecipesApp.normalizeUrl(recipe.url);
        var sameCategory = allRecipes.filter(function (item) {
          return item.category === recipe.category &&
            window.RecipesApp.normalizeUrl(item.url) !== current;
        });
        for (var index = sameCategory.length - 1; index > 0; index -= 1) {
          var random = Math.floor(Math.random() * (index + 1));
          var temporary = sameCategory[index];
          sameCategory[index] = sameCategory[random];
          sameCategory[random] = temporary;
        }
        var related = sameCategory.slice(0, 3);
        var grid = document.querySelector("[data-related-grid]");
        var section = document.querySelector("[data-related]");
        if (!grid || !section || !related.length) return;
        grid.innerHTML = related.map(function (item) {
          return '<a class="related-card" href="' + root + item.url + '">' +
            item.title.replace(/[&<>"']/g, function (character) {
              return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
            }) +
            "<small>" + item.category + "</small></a>";
        }).join("");
        section.hidden = false;
      })
      .catch(function () {
        var section = document.querySelector("[data-related]");
        if (section) section.hidden = true;
      });
  }

  document.querySelector("[data-print]")?.addEventListener("click", function () {
    window.print();
  });
  document.querySelector("[data-share]")?.addEventListener("click", shareRecipe);
  document.querySelector("[data-cook-mode]")?.addEventListener("click", function (event) {
    setCookMode(!event.currentTarget.classList.contains("is-active"));
  });
  document.querySelector("[data-text-size]")?.addEventListener("click", function () {
    textSizeIndex = (textSizeIndex + 1) % textSizes.length;
    content.style.setProperty("--recipe-font-size", textSizes[textSizeIndex]);
    window.RecipesApp.toast(textSizeIndex === 0 ? "Standard text size" : "Larger text size");
  });
  document.querySelector("[data-reset-progress]")?.addEventListener("click", function () {
    checkableItems().forEach(function (item) {
      item.classList.remove("is-done");
      item.setAttribute("aria-checked", "false");
    });
    updateProgress();
    window.RecipesApp.toast("Recipe checklist reset");
  });

  var backToTop = document.querySelector("[data-back-to-top]");
  if (backToTop) {
    window.addEventListener("scroll", function () {
      backToTop.classList.toggle("visible", window.scrollY > 600);
    }, { passive: true });
    backToTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && body.classList.contains("cook-mode") && !wakeLock) {
      setCookMode(true);
    }
  });

  initChecklists();
  initImages();
  renderRelated();
})();
