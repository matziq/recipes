"""Source-reviewed presentation normalization; never infer missing recipe quantities."""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup, Tag

PLAN_FILE = Path(__file__).with_name("recipe_structure_review.json")


def prepare_body(body: str) -> BeautifulSoup:
    soup = BeautifulSoup(body, "html.parser")
    for paragraph in list(soup.find_all("p")):
        if paragraph.find_parent("li") or not paragraph.find("br"):
            continue
        pieces = re.split(r"<br\s*/?>", paragraph.decode_contents(), flags=re.I)
        for piece in pieces:
            fragment = BeautifulSoup(f"<p>{piece}</p>", "html.parser").p
            if fragment.get_text(strip=True) or fragment.find("img"):
                paragraph.insert_before(fragment)
        paragraph.decompose()
    # Word exports frequently use nested, single-cell tables solely for layout.
    for table in list(soup.find_all(["table", "tbody", "thead", "tr", "td", "th"])):
        table.unwrap()
    return soup


def recipe_nodes(soup: BeautifulSoup) -> list[Tag]:
    return [tag for tag in soup.find_all(["p", "li", "h1", "h2", "h3", "h4"])
            if not tag.find_parent(["li", "aside", "section"])
            and "recipe-source" not in tag.get("class", [])
            and tag.get_text(strip=True)]


def text_of(node: Tag) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def load_plans(source: Path) -> dict:
    plans = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    for url, plan in plans.items():
        if not url.startswith("recipes/") or ".." in Path(url).parts:
            raise ValueError(f"Invalid structure review URL: {url}")
        for item in plan.get("sources", []):
            path = Path(item["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Invalid structure source: {path}")
            path = source / path
            if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"Recipe structure source changed; review required: {path}")
    return plans


def normalize_body(body: str, url: str, plans: dict) -> str:
    plan = plans.get(url)
    if plan is None:
        # New structured imports need no legacy review; unstructured additions do.
        if re.search(r"<h2>Ingredients</h2>.*?<ul\b", body, re.S) and "<h2>Instructions</h2>" in body:
            return body
        raise ValueError(f"Recipe needs a structure review: {url}")
    if plan.get("reference_summary_only"):
        body = '<p class="recipe-source">Source: Jamie Oliver, The Naked Chef 2, supplied cookbook. Original local source is unchanged.</p>'
    elif sha256(body.encode("utf-8")).hexdigest() != plan["body_sha256"]:
        raise ValueError(f"Recipe content changed; update its structure review: {url}")
    if plan.get("body_html"):
        return plan["body_html"]
    if plan.get("unchanged"):
        return body
    if plan.get("exception"):
        reason = escape(plan["exception"])
        return (
            f'<aside class="structure-note" role="note"><h2>Reference, not a standalone recipe</h2>'
            f'<p>{reason}</p></aside><h2>Ingredients</h2>'
            '<p>No standalone ingredient checklist is supplied by this reference.</p>'
            '<h2>Instructions</h2><p>Use this as reference material, not cooking instructions.</p>'
            f'{body}'
        )
    soup = prepare_body(body)
    nodes = recipe_nodes(soup)
    for index in plan.get("join_next", []):
        first, following = nodes[index], nodes[index + 1]
        first.append(" ")
        for child in list(following.contents):
            first.append(child.extract())
        following.decompose()
    old_items = soup.select("ul li, ol li")
    for index, item in enumerate(old_items):
        item["data-progress-index"] = str(index)
    new_index = len(old_items)
    ingredients = set(plan["ingredients"])
    instructions = set(plan["instructions"])
    if not ingredients:
        raise ValueError(f"No reviewed ingredient nodes: {url}")
    for index in sorted(ingredients | instructions):
        node = nodes[index]
        kind = "ingredient" if index in ingredients else "instruction"
        node["class"] = list(node.get("class", [])) + [f"recipe-{kind}"]
        if node.name == "li":
            continue
        wrapper = soup.new_tag("ul" if kind == "ingredient" else "ol")
        item = soup.new_tag("li")
        item["class"] = [f"recipe-{kind}"]
        item["data-progress-index"] = str(new_index)
        new_index += 1
        for child in list(node.contents):
            item.append(child.extract())
        wrapper.append(item)
        node.replace_with(wrapper)
    for index in plan.get("headings", []):
        node = nodes[index]
        if node.name != "li":
            node.name = "h3"
    # Keep original components in source order; do not merge alternate formulas.
    for kind, label in (("ingredient", "Ingredients"), ("instruction", "Instructions")):
        first = soup.select_one(f".recipe-{kind}")
        existing = soup.find(lambda tag: tag.name in {"h1", "h2", "h3", "h4", "p"}
                             and text_of(tag).rstrip(":").lower() in (
                                 ("ingredients",) if kind == "ingredient" else
                                 ("instructions", "directions", "method", "preparation")))
        if existing:
            existing.name = "h2"
            existing.clear()
            existing.append(label)
        elif first:
            heading = soup.new_tag("h2")
            heading.string = label
            container = first.find_parent(["ul", "ol"]) or first
            container.insert_before(heading)
        else:
            notice = BeautifulSoup(
                '<h2>Instructions</h2><p class="structure-note">The supplied source does not give '
                'a complete method. Missing instructions have not been invented.</p>', "html.parser")
            suggestion = soup.find("section", attrs={"aria-label": "Suggested completion"})
            if suggestion:
                for tag in list(notice.contents):
                    suggestion.insert_before(tag)
            else:
                soup.append(notice)
    # Adjacent generated single-item lists are one visual ingredient/step group.
    for listing in list(soup.find_all(["ul", "ol"])):
        following = listing.find_next_sibling()
        while following and following.name == listing.name and not following.attrs and not listing.attrs:
            for child in list(following.contents):
                listing.append(child.extract())
            following.decompose()
            following = listing.find_next_sibling()
    return str(soup)
