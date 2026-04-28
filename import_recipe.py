"""Import a recipe from a URL (uses JSON-LD schema.org/Recipe) into OneDrive/Recipes as a .docx.

Usage:
    python import_recipe.py <url> [--category Breads] [--title "Override Title"]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import requests
from docx import Document

ONEDRIVE_RECIPES = Path(r"d:/OneDrive/Recipes")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return unescape(s).strip()


def find_recipe(data):
    """Recursively search JSON-LD for a Recipe object."""
    if isinstance(data, dict):
        t = data.get("@type")
        if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
            return data
        for v in data.values():
            r = find_recipe(v)
            if r:
                return r
    elif isinstance(data, list):
        for v in data:
            r = find_recipe(v)
            if r:
                return r
    return None


def fetch_recipe(url: str) -> dict:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    html = resp.text
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        recipe = find_recipe(data)
        if recipe:
            return recipe
    raise SystemExit("No JSON-LD Recipe schema found on the page.")


def safe_filename(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", title).strip()


def parse_iso_duration(s: str) -> str:
    """Convert PT1H45M -> '1 hr 45 min'."""
    if not s:
        return ""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", s)
    if not m:
        return s
    h, mn = m.groups()
    parts = []
    if h:
        parts.append(f"{h} hr")
    if mn:
        parts.append(f"{mn} min")
    return " ".join(parts)


def build_docx(recipe: dict, source_url: str, out_path: Path) -> None:
    doc = Document()
    title = strip_html(recipe.get("name", "Untitled Recipe"))
    doc.add_heading(title, level=1)

    desc = strip_html(recipe.get("description", ""))
    if desc:
        doc.add_paragraph(desc)

    # Meta
    meta_bits = []
    yield_v = recipe.get("recipeYield")
    if isinstance(yield_v, list):
        yield_v = yield_v[-1] if yield_v else ""
    if yield_v:
        meta_bits.append(f"Yield: {yield_v}")
    prep = parse_iso_duration(recipe.get("prepTime", ""))
    cook = parse_iso_duration(recipe.get("cookTime", ""))
    total = parse_iso_duration(recipe.get("totalTime", ""))
    if prep:
        meta_bits.append(f"Prep: {prep}")
    if cook:
        meta_bits.append(f"Cook: {cook}")
    if total:
        meta_bits.append(f"Total: {total}")
    if meta_bits:
        p = doc.add_paragraph()
        p.add_run(" • ".join(meta_bits)).italic = True

    # Ingredients
    ings = recipe.get("recipeIngredient") or []
    if ings:
        doc.add_heading("Ingredients", level=2)
        for ing in ings:
            doc.add_paragraph(strip_html(str(ing)), style="List Bullet")

    # Instructions
    instrs = recipe.get("recipeInstructions") or []
    if instrs:
        doc.add_heading("Instructions", level=2)
        steps: list[str] = []
        for it in instrs:
            if isinstance(it, str):
                steps.append(strip_html(it))
            elif isinstance(it, dict):
                if it.get("@type") == "HowToSection":
                    sect = strip_html(it.get("name", ""))
                    if sect:
                        steps.append(f"[{sect}]")
                    for sub in it.get("itemListElement", []) or []:
                        if isinstance(sub, dict):
                            steps.append(strip_html(sub.get("text", "")))
                else:
                    steps.append(strip_html(it.get("text", "")))
        for step in steps:
            if step:
                doc.add_paragraph(step, style="List Number")

    # Source
    doc.add_paragraph()
    p = doc.add_paragraph()
    r = p.add_run(f"Source: {source_url}")
    r.italic = True

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--category", default="Breads")
    ap.add_argument("--title", default=None, help="Override title for filename")
    args = ap.parse_args()

    recipe = fetch_recipe(args.url)
    title = args.title or strip_html(recipe.get("name", "Untitled"))
    out = ONEDRIVE_RECIPES / args.category / f"{safe_filename(title)}.docx"
    if out.exists():
        print(f"Already exists: {out}")
        sys.exit(0)
    build_docx(recipe, args.url, out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
