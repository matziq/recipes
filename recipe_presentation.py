"""Shared cooking semantics, shopping groups, and reviewed browse categories."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
import unicodedata

from bs4 import BeautifulSoup

from recipe_structure import text_of

REVIEW_FILE = Path(__file__).with_name("recipe_presentation_review.json")
FAMILIES = {
    "Appetizers": "snacks", "Baby Food": "baby", "Beef": "mains",
    "Breads": "breads", "Breakfast": "breakfast", "Chicken": "mains",
    "Desserts": "desserts", "Drinks": "drinks", "Fruit": "sides",
    "Luau": "mains", "Main Dishes": "mains", "Other": "reference",
    "Pasta": "mains", "Pork": "mains", "Salads": "sides",
    "Sandwiches": "mains", "Sauces  & Dips": "sauces", "Seafood": "mains",
    "Sides": "sides", "Snacks": "snacks", "Soups": "soups",
    "Turkey": "mains", "Vegetarian (Tofu)": "mains",
}
FAMILY_LABELS = {
    "snacks": "Appetizers & snacks", "baby": "Baby food", "mains": "Main dishes",
    "breads": "Breads", "breakfast": "Breakfast", "desserts": "Desserts",
    "drinks": "Drinks", "sides": "Sides, fruit & salads", "reference": "Other & reference",
    "sauces": "Sauces & dips", "soups": "Soups",
}


def sort_text(value: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFD", value)
                    if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", value)).strip()


def recipe_sort_key(recipe: dict) -> tuple:
    return tuple(sort_text(recipe.get(key, "")) for key in ("category", "sub", "title")) + (recipe["url"],)


def load_presentation_reviews() -> dict:
    reviews = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    allowed = {"category", "sub", "reason", "family", "shopping_labels",
               "additional_ingredients", "additional_instructions", "split_ingredient_headings",
               "method_ingredient_facts"}
    for url, review in reviews.items():
        if not url.startswith("recipes/") or ".." in url.split("/") or set(review) - allowed:
            raise ValueError(f"Invalid presentation review: {url}")
        if "category" in review and (review["category"] not in FAMILIES or not review.get("reason")):
            raise ValueError(f"Category correction needs a known category and rationale: {url}")
        if "family" in review and review["family"] not in FAMILY_LABELS:
            raise ValueError(f"Unknown food family: {url}")
    return reviews


def browse_category(url: str, category: str, sub: str, reviews: dict) -> tuple[str, str]:
    review = reviews.get(url, {})
    category = review.get("category", category)
    if category not in FAMILIES:
        raise ValueError(f"Unreviewed recipe category: {category}")
    return category, review.get("sub", "" if "category" in review else sub)


def _excluded(node) -> bool:
    return bool(node.find_parent(["aside", "section"]) or
                node.find_parent(class_="recipe-source"))


def prepare_cooking_body(body: str, url: str, reviews: dict) -> tuple[str, str]:
    """Keep legacy slots even when a non-cooking list item is no longer interactive."""
    soup = BeautifulSoup(body, "html.parser")
    review = reviews.get(url, {})
    items = soup.select("ul li, ol li")
    for index, item in enumerate(items):
        if not item.has_attr("data-progress-index"):
            item["data-progress-index"] = str(index)
    next_slot = max((int(item["data-progress-index"]) for item in items), default=-1) + 1
    reference = soup.find("h2", string="Reference, not a standalone recipe")
    if reference:
        for item in items:
            item["class"] = [c for c in item.get("class", [])
                             if c not in {"recipe-ingredient", "recipe-instruction"}]
        return str(soup), ""

    # Canonical imports already have Ingredients/Instructions sections; older reviewed
    # conversions carry explicit classes, including interleaved components.
    explicit = bool(soup.select(".recipe-ingredient"))
    kind = None
    for node in soup.find_all(["h2", "li"]):
        if _excluded(node):
            continue
        if node.name == "h2":
            label = text_of(node).lower()
            kind = {"ingredients": "ingredient", "instructions": "instruction"}.get(label)
        elif not explicit and kind and not node.find_parent("li"):
            node["class"] = list(node.get("class", [])) + [f"recipe-{kind}"]

    for kind in ("ingredient", "instruction"):
        for text in review.get(f"additional_{kind}s", []):
            matches = [node for node in soup.find_all(["p", "h3", "h4"])
                       if not _excluded(node) and text_of(node) == text]
            if len(matches) != 1:
                raise ValueError(f"Reviewed {kind} not found uniquely: {url}: {text}")
            node = matches[0]
            listing = soup.new_tag("ul" if kind == "ingredient" else "ol")
            item = soup.new_tag("li", attrs={"class": [f"recipe-{kind}"],
                                           "data-progress-index": str(next_slot)})
            next_slot += 1
            for child in list(node.contents):
                item.append(child.extract())
            listing.append(item)
            node.replace_with(listing)

    for text, split in review.get("split_ingredient_headings", {}).items():
        node = soup.find(lambda tag: tag.name in {"h3", "h4"} and text_of(tag) == text)
        if node is None:
            raise ValueError(f"Reviewed ingredient heading missing: {url}")
        listing = soup.new_tag("ul")
        for text in split["items"]:
            item = soup.new_tag("li", attrs={"class": ["recipe-ingredient"],
                                           "data-progress-index": str(next_slot)})
            next_slot += 1
            item.string = text
            listing.append(item)
        node.insert_before(listing)
        node.clear()
        node.string = split["heading"]

    for group in review.get("method_ingredient_facts", []):
        if group["evidence"] not in soup.get_text(" ", strip=True):
            raise ValueError(f"Reviewed method ingredient evidence missing: {url}")
        heading = soup.new_tag("h3")
        heading.string = group["title"]
        listing = soup.new_tag("ul")
        for text in group["items"]:
            item = soup.new_tag("li", attrs={"class": ["recipe-ingredient"],
                                           "data-progress-index": str(next_slot)})
            next_slot += 1
            item.string = text
            listing.append(item)
        instructions = soup.find("h2", string="Instructions")
        instructions.insert_before(heading)
        instructions.insert_before(listing)

    for item in soup.select("li.recipe-ingredient, li.recipe-instruction"):
        if _excluded(item):
            raise ValueError(f"Non-cooking disclosure entered a checklist: {url}")
    if not soup.select("li.recipe-ingredient"):
        raise ValueError(f"Missing ingredient facts: {url}")
    if not soup.select("li.recipe-instruction"):
        notice = soup.find(lambda tag: tag.name == "p" and (
            "no complete method" in text_of(tag) or "does not give a complete method" in text_of(tag)))
        if notice is None:
            notice = soup.new_tag("p", attrs={"class": "structure-note"})
            notice.string = ("No cooking-step checklist: the original source supplies no method. "
                             "Missing steps have not been invented; use a separately linked complete "
                             "substitute where one is available.")
            soup.find("h2", string="Instructions").insert_after(notice)
        notice["data-missing-method"] = ""

    groups = []
    heading = "Ingredients"
    for node in soup.find_all(["h2", "h3", "h4", "li"]):
        if _excluded(node):
            continue
        if node.name in {"h2", "h3", "h4"}:
            label = text_of(node)
            if label != "Instructions":
                heading = label
        elif "recipe-ingredient" in node.get("class", []):
            if not groups or groups[-1]["title"] != heading:
                groups.append({"title": heading, "items": []})
            groups[-1]["items"].append(text_of(node))
    for number, label in enumerate(review.get("shopping_labels", [])):
        if number >= len(groups):
            raise ValueError(f"Shopping group review no longer matches: {url}")
        groups[number]["title"] = label
    shopping = (
        '<details class="shopping-list">'
        '<summary><h2>Shopping list</h2></summary>'
        '<p class="shopping-hint">Planning reference only; cooking checkboxes are below. '
        'Amounts and alternatives are copied from this recipe, not added together. '
        'Choose one labeled formula or size where alternatives are given; include only '
        'the components you intend to make. Check source limitations before cooking.</p>'
    )
    warning = soup.find("aside", attrs={"aria-label": "Incomplete recipe"})
    if warning or soup.select("[data-missing-method]") or "Source limitation / note:" in soup.get_text():
        label = "Incomplete recipe - not ready to cook." if warning else "Original-source limitations apply."
        reason = escape(text_of(warning.find("p"))) + " " if warning else ""
        shopping += (f'<p class="shopping-warning" role="note"><strong>{label}</strong> {reason}'
                     'This planning copy does not recover missing amounts or steps. '
                     'Read the original recipe warnings and source notes below.</p>')
    for group in groups:
        shopping += f'<div class="shopping-group"><h3>{escape(group["title"])}</h3><ul>'
        shopping += "".join(f"<li>{escape(text)}</li>" for text in group["items"])
        shopping += "</ul></div>"
    shopping += "</details>"
    return str(soup), shopping


def collapsible_cooking_body(body: str) -> str:
    """Group adjacent cooking components without changing any progress slots."""
    soup = BeautifulSoup(body, "html.parser")
    if soup.find("h2", string="Reference, not a standalone recipe"):
        return body
    result = BeautifulSoup("", "html.parser")
    active = None
    current_kind = None
    for node in list(soup.contents):
        if not getattr(node, "name", None):
            (active if active is not None else result).append(node.extract())
            continue
        canonical = text_of(node).lower() if node.name == "h2" else ""
        kind = {"ingredients": "ingredient", "instructions": "instruction"}.get(canonical)
        if node.name in {"h3", "h4"}:
            following = node.find_next_sibling()
            while following and following.name not in {"ul", "ol", "h2", "aside", "section"}:
                following = following.find_next_sibling()
            if following and following.name in {"ul", "ol"}:
                item = following.select_one(".recipe-ingredient, .recipe-instruction")
                if item:
                    kind = "ingredient" if "recipe-ingredient" in item.get("class", []) else "instruction"
        elif node.name in {"ul", "ol"}:
            item = node.select_one(".recipe-ingredient, .recipe-instruction")
            if item:
                kind = "ingredient" if "recipe-ingredient" in item.get("class", []) else "instruction"
        if node.name in {"aside", "section"} or "recipe-source" in node.get("class", []):
            active = None
            current_kind = None
        if kind and (kind != current_kind or canonical):
            active = result.new_tag("details", attrs={
                "class": ["cooking-section"], "data-cooking-kind": kind, "open": ""})
            summary = result.new_tag("summary")
            if canonical:
                summary.append(node.extract())
            else:
                label = result.new_tag("h3")
                label.string = "Ingredients" if kind == "ingredient" else "Instructions"
                summary.append(label)
            active.append(summary)
            result.append(active)
            current_kind = kind
            if canonical:
                continue
        (active if active is not None else result).append(node.extract())
    return str(result)
