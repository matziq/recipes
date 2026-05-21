"""Build static recipes site from d:/OneDrive/Recipes.

- Converts .docx -> .html via mammoth
- Copies .pdf, .jpg, .png as-is
- Generates per-category pages, a recipe viewer, and a search index
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import stat
import time
from collections import Counter
from html import escape
from pathlib import Path

import fitz  # PyMuPDF
import mammoth

SOURCE = Path(r"d:/OneDrive/Recipes")
OUT = Path(__file__).parent
RECIPES_OUT = OUT / "recipes"
NEW_RECIPES_JSON = OUT / "new_recipes.json"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
DOCX_EXT = {".docx"}
PDF_EXT = {".pdf"}
SKIP_EXT = {".psd", ".doc"}  # cannot easily render
PDF_DPI = 130  # render resolution for PDF page images
ICONS = {
    "Appetizers": "🥟", "Baby Food": "🍼", "Beef": "🥩", "Breads": "🍞",
    "Breakfast": "🍳", "Chicken": "🍗", "Desserts": "🍰", "Drinks": "🥤",
    "Fruit": "🍓", "Luau": "🌺", "Pasta": "🍝", "Pork": "🥓",
    "Salads": "🥗", "Sandwiches": "🥪", "Sauces  & Dips": "🥫",
    "Seafood": "🦐", "Sides": "🍚", "Snacks": "🍿", "Soups": "🍲",
    "Turkey": "🦃", "Vegetarian (Tofu)": "🥦",
    "Cakes": "🎂", "Candies": "🍬", "Cookies": "🍪", "Pies": "🥧",
    "Other": "📄",
}


def slugify(text: str) -> str:
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch.lower())
        elif ch in (" ", "-", "_"):
            out.append("-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "x"


def convert_docx(src: Path, dst_html: Path) -> str:
    with open(src, "rb") as f:
        result = mammoth.convert_to_html(f)
    return result.value or "<p><em>(empty document)</em></p>"


def convert_pdf_pages(src: Path, out_dir: Path, slug: str) -> str:
    """Render each PDF page to a JPEG and return HTML body that displays them."""
    images_dir = out_dir / f"{slug}_pages"
    images_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    zoom = PDF_DPI / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(src) as doc:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img_path = images_dir / f"page-{i:03d}.jpg"
            pix.pil_save(img_path, format="JPEG", quality=82, optimize=True)
            rel = f"{slug}_pages/{img_path.name}"
            parts.append(
                f'<img class="pdf-page" loading="lazy" src="{rel}" alt="Page {i}">'
            )
    if not parts:
        return "<p><em>(empty PDF)</em></p>"
    return '<div class="pdf-pages">' + "\n".join(parts) + "</div>"


# ---------- Ingredient extraction ----------

# Measurement units (singular + abbreviations); plural forms generated below.
# Single-letter abbreviations like 'c', 't', 'l', 'g' are intentionally
# excluded because they cause too many false positives in free-form text.
_UNIT_WORDS = {
    "cup", "tablespoon", "tbsp", "tbs", "tb", "teaspoon", "tsp", "ts",
    "ounce", "oz", "pound", "lb", "lbs", "gram", "grams", "kilogram", "kg",
    "milliliter", "ml", "liter", "liters", "pint", "pt", "quart", "qt",
    "gallon", "gal", "package", "pkg", "can", "bottle", "jar", "box",
    "bag", "slice", "piece", "clove", "sprig", "bunch", "dash", "pinch",
    "drop", "stick", "head", "stalk", "envelope", "packet", "rib",
    "inch", "fluid", "tsp.", "tbsp.",
}
UNITS = set(_UNIT_WORDS) | {w + "s" for w in _UNIT_WORDS if not w.endswith(".")}

# Article/filler words to strip when they appear at the front of a phrase.
_FILLER = {"of", "a", "an", "the", "some"}

# Equipment/cookware words that, if seen as the final noun, mean the line is
# an instruction ("in a large skillet") rather than an ingredient.
_EQUIPMENT = {
    "skillet", "pan", "saucepan", "pot", "bowl", "dish", "plate",
    "baking-dish", "sheet", "oven", "grill", "stove", "burner",
    "refrigerator", "freezer", "microwave", "blender", "processor",
    "mixer", "whisk", "spoon", "fork", "knife", "spatula", "colander",
    "strainer", "thermometer", "timer", "foil", "wrap", "towel",
}

# Hand-curated singularizations for common food plurals where naive rules fail.
_SINGULAR_OVERRIDES = {
    "tomatoes": "tomato",
    "potatoes": "potato",
    "chilies": "chili",
    "chilis": "chili",
    "chillies": "chili",
    "berries": "berry",
    "cherries": "cherry",
    "strawberries": "strawberry",
    "blueberries": "blueberry",
    "raspberries": "raspberry",
    "blackberries": "blackberry",
    "cranberries": "cranberry",
    "anchovies": "anchovy",
    "loaves": "loaf",
    "leaves": "leaf",
    "knives": "knife",
    "halves": "half",
    "calves": "calf",
    "wolves": "wolf",
    "shelves": "shelf",
    "chives": "chives",  # always plural in recipes
    "oats": "oats",
    "greens": "greens",
    "sprouts": "sprouts",
    "grits": "grits",
    "peas": "peas",
    "beans": "beans",
    "noodles": "noodles",
    "oysters": "oyster",
    "shrimp": "shrimp",
    "shrimps": "shrimp",
    "scallops": "scallop",
}

# Adjectives/prep words to drop from the start/end of an ingredient name.
DESCRIPTORS = {
    "large", "small", "medium", "jumbo", "mini", "whole", "half", "quarter",
    "fresh", "frozen", "dried", "dry", "canned", "raw", "cooked", "cold",
    "warm", "hot", "softened", "melted", "chilled", "room-temperature",
    "room", "temperature", "ripe", "unripe", "organic", "wild", "unsalted",
    "salted", "unsweetened", "sweetened", "low-fat", "nonfat", "non-fat",
    "fat-free", "lean", "skinless", "boneless", "extra-virgin", "extra",
    "virgin", "pure", "plain", "chopped", "minced", "diced", "sliced",
    "crushed", "grated", "shredded", "peeled", "pitted", "cored", "drained",
    "rinsed", "thawed", "squeezed", "ground", "fine", "finely", "coarse",
    "coarsely", "pressed", "mashed", "beaten", "whipped", "cubed", "halved",
    "quartered", "julienned", "shaved", "roasted", "toasted", "blanched",
    "crumbled", "smoked", "cured", "uncooked", "lightly", "thinly",
    "thickly", "freshly", "preferably", "optional", "about", "approximately",
    "good", "good-quality", "quality", "low-sodium", "reduced-fat",
    "all-purpose", "all", "purpose", "self-rising", "hot-cooked",
}

# Words that, if they appear AS THE FINAL TOKEN, indicate the line is not
# really a food noun (it's a description/instruction/measurement leftover).
_BAD_FINAL_TOKENS = {
    "taste", "needed", "garnish", "serving", "desired", "wanted",
    "minute", "minutes", "hour", "hours", "second", "seconds",
    "degree", "degrees", "people", "person", "serving", "servings",
    "use", "needed", "side", "sides", "top", "topping", "thick", "thin",
    "long", "wide", "deep", "diameter", "size", "sized", "color", "colored",
}

# Unicode fractions for line-start detection and quantity stripping.
_FRACTION_CHARS = "¼½¾⅓⅔⅛⅜⅝⅞"

_QTY_PREFIX = re.compile(
    r"^[\d" + _FRACTION_CHARS + r"\s/\-–.,xX×]+"
)
_PAREN = re.compile(r"\([^()]*\)")
_NON_ALPHA = re.compile(r"[^a-z\-' ]+")

# Phrases that indicate the rest of the line is prep, not ingredient.
_TRAILING_PHRASES = (
    " to taste",
    " for serving",
    " for garnish",
    " for the ",
    " as needed",
    " if desired",
    " or to taste",
    " plus more",
    " plus extra",
)


def _looks_like_ingredient(line: str) -> bool:
    """Heuristic: a non-empty line that starts with a digit, fraction, or unit."""
    if not line or len(line) > 200:
        return False
    s = line.lstrip()
    if not s:
        return False
    if s[0].isdigit() or s[0] in _FRACTION_CHARS:
        return True
    first = re.split(r"\s+", s, maxsplit=1)[0].lower().rstrip(".,:;")
    if first in UNITS:
        return True
    return False


def _clean_phrase(s: str) -> str:
    """Strip a single ingredient candidate down to its core noun phrase."""
    s = s.strip().strip(",.;:!?-–")
    if not s:
        return ""

    # Drop parentheticals like "(10 ounce)" or "(optional)".
    s = _PAREN.sub(" ", s)

    # Anything after the first comma is usually preparation: "garlic, minced".
    if "," in s:
        s = s.split(",", 1)[0]

    # Strip well-known trailing phrases.
    low = s.lower()
    for phrase in _TRAILING_PHRASES:
        idx = low.find(phrase)
        if idx >= 0:
            s = s[:idx]
            low = s.lower()

    # Strip leading quantity (numbers, fractions, ranges).
    s = _QTY_PREFIX.sub("", s).strip()

    # Lowercase, keep only a-z/-/'/space, collapse whitespace.
    s = s.lower()
    s = _NON_ALPHA.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""

    tokens = s.split()

    # Strip leading filler/unit/descriptor tokens, repeatedly, in any order.
    # Handles things like "2 large cloves garlic" -> "garlic" by peeling
    # 'large' (descriptor), then 'cloves' (unit) off the front.
    while tokens:
        first = tokens[0]
        if first in _FILLER or first in UNITS or first in DESCRIPTORS:
            tokens.pop(0)
            continue
        break

    # Strip trailing descriptors ("cheese softened" -> "cheese").
    while tokens and tokens[-1] in DESCRIPTORS:
        tokens.pop()
    if not tokens:
        return ""

    # Reject if the only remaining token is a unit/stop word/equipment.
    if all(t in UNITS or t in _BAD_FINAL_TOKENS or t in _EQUIPMENT for t in tokens):
        return ""
    if tokens[-1] in _BAD_FINAL_TOKENS or tokens[-1] in _EQUIPMENT:
        return ""

    # Cap length to first 4 tokens (ingredient names are usually 1-3 words).
    if len(tokens) > 4:
        tokens = tokens[:4]

    # Singularize the last token. Prefer the override table; fall back to
    # simple suffix rules.
    last = tokens[-1]
    if last in _SINGULAR_OVERRIDES:
        tokens[-1] = _SINGULAR_OVERRIDES[last]
    elif len(last) > 4 and last.endswith("ies"):
        tokens[-1] = last[:-3] + "y"
    elif len(last) > 3 and last.endswith("ses"):
        tokens[-1] = last[:-2]
    elif len(last) > 3 and last.endswith("es") and last[-3] in "shxz":
        tokens[-1] = last[:-2]
    elif (
        len(last) > 3
        and last.endswith("s")
        and not last.endswith("ss")
        and not last.endswith("us")
        and not last.endswith("is")
    ):
        tokens[-1] = last[:-1]

    out = " ".join(tokens).strip("-' ")
    if len(out) < 2 or len(out) > 40:
        return ""
    # Must contain at least one vowel/letter pair to look like a real word.
    if not re.search(r"[a-z]{2,}", out):
        return ""
    return out


def normalize_ingredient_line(line: str) -> list[str]:
    """Return one or more normalized ingredient names from a single line."""
    line = line.strip()
    if not line:
        return []

    # Split on "substitute" so both halves are added as alternates.
    parts = [line]
    sub_match = re.search(r"\bsubstitute[sd]?\b", line, re.IGNORECASE)
    if sub_match:
        before = line[: sub_match.start()].rstrip(" ,.-")
        after = line[sub_match.end():].lstrip(" ,.-")
        parts = [p for p in (before, after) if p]

    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _clean_phrase(part)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


# Match an explicit "Ingredients" heading and capture text until the next heading.
_INGREDIENTS_SECTION = re.compile(
    r"<h[1-6][^>]*>\s*(?:<[^>]+>\s*)*ingredients\b[^<]*</h[1-6]>(.*?)(?=<h[1-6]\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_LI_OR_P = re.compile(r"<(?:li|p|td)[^>]*>(.*?)</(?:li|p|td)>", re.DOTALL | re.IGNORECASE)
_BR_SPLIT = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_DATA_URI = re.compile(r'src="data:[^"]+"', re.IGNORECASE)


def extract_ingredients_from_html(body_html: str) -> list[str]:
    """Pull a deduplicated list of normalized ingredient names from a recipe body."""
    if not body_html:
        return []

    # Strip embedded base64 image payloads — they bloat the text and contain no info.
    body_html = _DATA_URI.sub('src=""', body_html)

    # Phase 1: try the explicit "Ingredients" section if present.
    section_match = _INGREDIENTS_SECTION.search(body_html)
    raw_lines: list[str] = []

    def _harvest(scope: str, require_filter: bool) -> None:
        for tag_match in _LI_OR_P.finditer(scope):
            inner = tag_match.group(1)
            for piece in _BR_SPLIT.split(inner):
                txt = _TAGS.sub(" ", piece)
                txt = html_lib.unescape(txt)
                txt = re.sub(r"\s+", " ", txt).strip()
                if not txt:
                    continue
                if require_filter and not _looks_like_ingredient(txt):
                    continue
                raw_lines.append(txt)

    if section_match:
        _harvest(section_match.group(1), require_filter=False)

    # Phase 2: only fall back to whole-document scanning when no explicit
    # Ingredients section yielded content. Otherwise we risk pulling in
    # instruction lines and table-of-contents noise.
    if not raw_lines:
        _harvest(body_html, require_filter=True)

    ingredients: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        for ing in normalize_ingredient_line(line):
            if ing not in seen:
                seen.add(ing)
                ingredients.append(ing)
    return ingredients



def category_for(rel: Path) -> tuple[str, str]:
    """Return (top_category, sub_category_or_empty)."""
    parts = rel.parts
    if len(parts) <= 1:
        return ("Other", "")
    top = parts[0]
    sub = parts[1] if len(parts) >= 3 else ""
    return (top, sub)


_DEDUP_TITLE_RE = re.compile(r"-desktop-[a-z0-9]+|\(\d+\)", re.IGNORECASE)


def normalize_title(title: str) -> str:
    """Normalize a title for duplicate detection."""
    t = _DEDUP_TITLE_RE.sub("", title)
    t = re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return t


# Format priority: docx is preferred (cleanest text), then pdf, then images
_FORMAT_RANK = {".docx": 0, ".pdf": 1, ".jpg": 2, ".jpeg": 2, ".png": 2, ".gif": 2, ".webp": 2}


def _is_sync_conflict(name: str) -> bool:
    n = name.lower()
    return "-desktop-" in n or re.search(r"\(\d+\)$", name) is not None


def _docx_text_and_images(path: Path) -> tuple[str, bool]:
    """Return (normalized_text, has_images) for a docx file."""
    try:
        with open(path, "rb") as f:
            html = mammoth.convert_to_html(f).value or ""
    except Exception:
        return ("", False)
    has_images = "<img" in html
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return (text, has_images)


def _pdf_text_and_images(path: Path) -> tuple[str, bool]:
    """Return (normalized_text, has_images) for a pdf file."""
    try:
        with fitz.open(path) as doc:
            text_parts = []
            has_images = False
            for page in doc:
                text_parts.append(page.get_text("text"))
                if not has_images and page.get_images(full=False):
                    has_images = True
            text = re.sub(r"\s+", " ", " ".join(text_parts)).strip().lower()
            return (text, has_images)
    except Exception:
        return ("", False)


def _text_similarity(a: str, b: str) -> float:
    """Word-set Jaccard similarity (0..1). Cheap and order-independent."""
    if not a or not b:
        return 0.0
    wa = set(re.findall(r"\w+", a))
    wb = set(re.findall(r"\w+", b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


# Threshold above which two recipes are considered the same content
SIMILARITY_THRESHOLD = 0.75


def _smart_pick(files: list[Path], log: list[str]) -> list[Path]:
    """For a duplicate group, choose which file(s) to keep based on content.

    Rules:
      1. Drop sync-conflict copies if any clean copy exists.
      2. If a docx and pdf cover the same recipe (text similarity high):
           - Keep the one with images if only one has images.
           - Otherwise keep the docx (cleaner conversion).
      3. If text differs significantly, keep both (return both files).
    """
    if len(files) == 1:
        return files

    # Drop sync-conflict copies when a clean version exists
    clean = [p for p in files if not _is_sync_conflict(p.stem)]
    if clean and len(clean) < len(files):
        dropped = [p.name for p in files if _is_sync_conflict(p.stem)]
        log.append(f"  dropped sync-conflict copies: {dropped}")
        files = clean

    if len(files) == 1:
        return files

    # Analyze content
    info: list[tuple[Path, str, bool]] = []
    for p in files:
        ext = p.suffix.lower()
        if ext in DOCX_EXT:
            txt, imgs = _docx_text_and_images(p)
        elif ext in PDF_EXT:
            txt, imgs = _pdf_text_and_images(p)
        else:
            txt, imgs = ("", False)
        info.append((p, txt, imgs))

    # Pairwise: if every pair is similar enough, treat as one recipe
    paths = [i[0] for i in info]
    all_similar = True
    for i in range(len(info)):
        for j in range(i + 1, len(info)):
            sim = _text_similarity(info[i][1], info[j][1])
            if sim < SIMILARITY_THRESHOLD:
                all_similar = False
                break
        if not all_similar:
            break

    if not all_similar:
        log.append(f"  content differs -> keeping all {len(files)}: {[p.name for p in paths]}")
        return files

    # Same content: prefer image-bearing version if only some have images
    with_images = [t for t in info if t[2]]
    without_images = [t for t in info if not t[2]]
    if with_images and without_images:
        # Prefer pdf-with-images > docx-with-images > anything else
        with_images.sort(key=lambda t: _FORMAT_RANK.get(t[0].suffix.lower(), 99))
        # Actually prefer .pdf if it's the one with images, since user wants
        # to preserve embedded images — but if docx also has images, it wins.
        pdf_with = next((t for t in with_images if t[0].suffix.lower() == ".pdf"), None)
        docx_with = next((t for t in with_images if t[0].suffix.lower() == ".docx"), None)
        winner = (docx_with or pdf_with or with_images[0])[0]
        log.append(f"  same content; kept {winner.name} (has images)")
        return [winner]

    # Either all have images or none do; pick by format rank (docx wins)
    info.sort(key=lambda t: _FORMAT_RANK.get(t[0].suffix.lower(), 99))
    winner = info[0][0]
    log.append(f"  same content; kept {winner.name} (preferred format)")
    return [winner]


def select_best_files(verbose: bool = True) -> list[Path]:
    """Walk SOURCE and pick the best file(s) for each recipe group.

    Uses content-aware deduplication: compares text and image presence
    between docx/pdf siblings to keep the version with the most info.
    """
    candidates: dict[tuple[str, str, str], list[Path]] = {}
    for src in SOURCE.rglob("*"):
        if not src.is_file():
            continue
        ext = src.suffix.lower()
        if ext in SKIP_EXT:
            continue
        if ext not in IMAGE_EXT and ext not in DOCX_EXT and ext not in PDF_EXT:
            continue
        rel = src.relative_to(SOURCE)
        category, sub = category_for(rel)
        key = (category, sub, normalize_title(src.stem))
        candidates.setdefault(key, []).append(src)

    chosen: list[Path] = []
    decision_log: list[str] = []
    for key, files in candidates.items():
        if len(files) > 1:
            decision_log.append(f"[{key[0]}{('/'+key[1]) if key[1] else ''}] {key[2]!r}")
        picked = _smart_pick(files, decision_log)
        chosen.extend(picked)

    if verbose and decision_log:
        print("Deduplication decisions:")
        print("\n".join(decision_log))
        print()

    chosen.sort()
    return chosen


def _force_rm(func, path, exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        time.sleep(0.2)
        try:
            func(path)
        except Exception:
            pass


def main() -> None:
    if RECIPES_OUT.exists():
        shutil.rmtree(RECIPES_OUT, onerror=_force_rm)
    RECIPES_OUT.mkdir(parents=True, exist_ok=True)

    recipes = []  # list of dicts: {title, category, sub, path, type}

    for src in select_best_files():
        rel = src.relative_to(SOURCE)
        ext = src.suffix.lower()

        category, sub = category_for(rel)
        cat_dir_parts = [slugify(category)]
        if sub:
            cat_dir_parts.append(slugify(sub))
        out_dir = RECIPES_OUT.joinpath(*cat_dir_parts)
        out_dir.mkdir(parents=True, exist_ok=True)

        title = src.stem
        slug = slugify(title)

        if ext in DOCX_EXT or ext in PDF_EXT:
            out_file = out_dir / f"{slug}.html"
            n = 2
            slug_used = slug
            while out_file.exists():
                slug_used = f"{slug}-{n}"
                out_file = out_dir / f"{slug_used}.html"
                n += 1
            try:
                if ext in DOCX_EXT:
                    body = convert_docx(src, out_file)
                else:
                    body = convert_pdf_pages(src, out_dir, slug_used)
            except Exception as e:
                body = f"<p>Could not convert: {escape(str(e))}</p>"
            page = render_recipe_page(title, category, sub, body)
            out_file.write_text(page, encoding="utf-8")
            rel_url = out_file.relative_to(OUT).as_posix()
            # Only docx-derived pages have parseable ingredient text; PDF pages
            # are rendered as images and yield nothing useful.
            ingredients = extract_ingredients_from_html(body) if ext in DOCX_EXT else []
            recipes.append({
                "title": title, "category": category, "sub": sub,
                "url": rel_url, "type": "html",
                "ingredients": ingredients,
            })
        else:
            out_file = out_dir / f"{slug}{ext}"
            n = 2
            while out_file.exists():
                out_file = out_dir / f"{slug}-{n}{ext}"
                n += 1
            shutil.copy2(src, out_file)
            rel_url = out_file.relative_to(OUT).as_posix()
            recipes.append({
                "title": title, "category": category, "sub": sub,
                "url": rel_url, "type": ext.lstrip("."),
                "ingredients": [],
            })

    recipes.sort(key=lambda r: (r["category"], r["sub"], r["title"].lower()))

    # Apply NEW flag from new_recipes.json (case-insensitive match on category + title)
    new_keys: set[tuple[str, str]] = set()
    if NEW_RECIPES_JSON.exists():
        try:
            entries = json.loads(NEW_RECIPES_JSON.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                for e in entries:
                    cat = (e.get("category") or "").strip().lower()
                    title = (e.get("title") or "").strip().lower()
                    if cat and title:
                        new_keys.add((cat, title))
        except Exception as exc:
            print(f"Warning: could not read {NEW_RECIPES_JSON.name}: {exc}")
    if new_keys:
        matched = 0
        for r in recipes:
            if (r["category"].strip().lower(), r["title"].strip().lower()) in new_keys:
                r["new"] = True
                matched += 1
        print(f"Flagged {matched} recipe(s) as NEW from {NEW_RECIPES_JSON.name}.")

    new_count = sum(1 for r in recipes if r.get("new"))

    # Write search index
    (OUT / "recipes_index.json").write_text(
        json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build master ingredient list sorted by frequency (most common first)
    ing_counter: Counter[str] = Counter()
    for r in recipes:
        for ing in r.get("ingredients", []):
            ing_counter[ing] += 1
    master = [
        {"name": name, "count": count}
        for name, count in sorted(
            ing_counter.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]
    (OUT / "ingredients_master.json").write_text(
        json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Extracted {sum(ing_counter.values())} ingredient mentions "
        f"({len(master)} unique) from {sum(1 for r in recipes if r.get('ingredients'))} recipes."
    )

    # Build category tree
    tree: dict[str, dict[str, list[dict]]] = {}
    for r in recipes:
        tree.setdefault(r["category"], {}).setdefault(r["sub"], []).append(r)

    (OUT / "index.html").write_text(render_index(tree, len(recipes), new_count), encoding="utf-8")
    new_html_path = OUT / "new.html"
    if new_count:
        new_html_path.write_text(render_new_page(recipes, new_count), encoding="utf-8")
    elif new_html_path.exists():
        new_html_path.unlink()
    print(f"Built {len(recipes)} recipes across {len(tree)} categories.")


# ---------- HTML templates ----------

BASE_CSS = """
:root{
  --bg:#fff8f1; --card:#fff; --ink:#3b2a1a; --muted:#7a6a55;
  --accent:#c2410c; --accent2:#f59e0b; --line:#f1e4d2;
}
*{box-sizing:border-box}
body{margin:0;font-family:Georgia,'Iowan Old Style',serif;background:var(--bg);color:var(--ink);line-height:1.55}
header{position:sticky;top:0;z-index:10;background:linear-gradient(180deg,#fff7ec,#fff8f1);
  border-bottom:1px solid var(--line);padding:12px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header h1{margin:0;font-size:1.4rem;color:var(--accent)}
header h1 a{color:inherit;text-decoration:none}
.search{flex:1;min-width:240px}
.search input{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:999px;font-size:1rem;background:#fff}
.container{max-width:1100px;margin:0 auto;padding:24px 20px}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
.cat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;text-align:center;
  text-decoration:none;color:var(--ink);transition:transform .15s,box-shadow .15s}
.cat:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(194,65,12,.12)}
.cat .ic{font-size:2.2rem;display:block}
.cat .name{font-weight:bold;margin-top:6px;display:block}
.cat .count{color:var(--muted);font-size:.9rem;display:block;margin-top:2px}
h2.cat-title{color:var(--accent);border-bottom:2px solid var(--line);padding-bottom:6px}
.recipes{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.recipes li{background:var(--card);border:1px solid var(--line);border-radius:10px}
.recipes a{display:block;padding:12px 14px;color:var(--ink);text-decoration:none}
.recipes a:hover{background:#fff3e2}
.tag{font-size:.7rem;background:var(--accent2);color:#fff;padding:2px 6px;border-radius:6px;margin-left:6px;vertical-align:middle}
.tag.pdf{background:#ef4444}
.tag.html{background:#16a34a}
.tag.jpg,.tag.jpeg,.tag.png{background:#3b82f6}
.tag.new{background:#dc2626;font-weight:bold;letter-spacing:.5px;animation:pulse-new 1.6s ease-in-out infinite}
@keyframes pulse-new{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.7;transform:scale(1.05)}}
.new-banner{display:flex;align-items:center;gap:12px;background:linear-gradient(90deg,#fff1f0,#fff8f1);border:1px solid #fecaca;border-left:6px solid #dc2626;border-radius:12px;padding:14px 18px;margin:0 0 22px;text-decoration:none;color:var(--ink);box-shadow:0 1px 4px rgba(220,38,38,.08);transition:transform .12s ease, box-shadow .12s ease}
.new-banner:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(220,38,38,.15)}
.new-banner-tag{background:#dc2626;color:#fff;font-weight:bold;letter-spacing:.5px;font-size:.78rem;padding:3px 8px;border-radius:6px;animation:pulse-new 1.6s ease-in-out infinite}
.new-banner-text{font-weight:600;flex:1}
.new-banner-arrow{color:#dc2626;font-size:1.2rem;font-weight:bold}
.new-page-intro{color:var(--muted);margin:6px 0 22px}
.crumbs{color:var(--muted);font-size:.95rem;margin-bottom:14px}
.crumbs a{color:var(--accent);text-decoration:none}
.recipe-content{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px}
.recipe-content img{display:block;max-width:min(220px,100%);height:auto;margin:10px 0;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.08);cursor:zoom-in;transition:max-width .18s ease,box-shadow .18s ease,transform .18s ease}
.recipe-content img:hover{box-shadow:0 6px 22px rgba(194,65,12,.18);transform:translateY(-1px)}
.recipe-content img.image-expanded{max-width:100%;cursor:zoom-out;box-shadow:0 8px 28px rgba(0,0,0,.14)}
.recipe-content img:focus{outline:3px solid rgba(245,158,11,.5);outline-offset:3px}
.recipe-content table{border-collapse:collapse;margin:12px 0}
.recipe-content td,.recipe-content th{border:1px solid var(--line);padding:6px 10px}
.pdf-pages{display:flex;flex-direction:column;gap:14px;align-items:center}
.pdf-page{background:#fff}
footer{text-align:center;color:var(--muted);padding:30px 20px;font-size:.85rem}
.search-results{display:none}
.search-results.active{display:block}
.search-results ul{list-style:none;padding:0;margin:0}
.search-results li{padding:10px;border-bottom:1px solid var(--line)}
.search-results a{color:var(--accent);text-decoration:none;font-weight:bold}
.search-results .meta{color:var(--muted);font-size:.85rem}
.empty{color:var(--muted);font-style:italic;padding:20px}
.all-caught-up{text-align:center;color:var(--muted);font-size:1.1rem;margin:40px 0;padding:30px;background:var(--card);border:1px dashed var(--line);border-radius:14px}

/* "What do you have?" panel */
.wdyh{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 22px;overflow:hidden}
.wdyh-head{display:flex;align-items:center;gap:10px;width:100%;padding:14px 18px;background:linear-gradient(90deg,#fff7ec,#fff3e2);border:0;border-bottom:1px solid var(--line);font-family:inherit;font-size:1.05rem;color:var(--accent);font-weight:bold;cursor:pointer;text-align:left}
.wdyh-head:hover{background:linear-gradient(90deg,#fff3e2,#ffe9ce)}
.wdyh-head .wdyh-icon{font-size:1.4rem}
.wdyh-head .wdyh-chev{margin-left:auto;transition:transform .2s ease;color:var(--accent2)}
.wdyh[data-open="true"] .wdyh-head .wdyh-chev{transform:rotate(180deg)}
.wdyh[data-open="true"] .wdyh-head{border-bottom-color:var(--line)}
.wdyh-body{display:none;padding:16px 18px 18px}
.wdyh[data-open="true"] .wdyh-body{display:block}
.wdyh-hint{color:var(--muted);font-size:.9rem;margin:0 0 10px}
.wdyh-input-wrap{position:relative}
.wdyh-input{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:999px;font-size:1rem;background:#fff;font-family:inherit}
.wdyh-input:disabled{background:#faf2e6;color:var(--muted);cursor:not-allowed}
.wdyh-suggest{position:absolute;left:0;right:0;top:calc(100% + 4px);background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.08);max-height:280px;overflow-y:auto;z-index:20;display:none}
.wdyh-suggest.active{display:block}
.wdyh-suggest button{display:flex;align-items:center;gap:8px;width:100%;padding:8px 14px;background:transparent;border:0;text-align:left;font-family:inherit;font-size:.95rem;color:var(--ink);cursor:pointer}
.wdyh-suggest button:hover,.wdyh-suggest button.active{background:#fff3e2}
.wdyh-suggest .wdyh-count{margin-left:auto;color:var(--muted);font-size:.8rem}
.wdyh-suggest .wdyh-empty{padding:10px 14px;color:var(--muted);font-style:italic}
.wdyh-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;min-height:0}
.wdyh-chip{display:inline-flex;align-items:center;gap:6px;background:#fff3e2;border:1px solid #fbd9b3;color:var(--accent);padding:4px 6px 4px 12px;border-radius:999px;font-size:.9rem}
.wdyh-chip button{background:transparent;border:0;color:var(--accent);font-size:1rem;line-height:1;padding:2px 6px;cursor:pointer;border-radius:999px}
.wdyh-chip button:hover{background:rgba(194,65,12,.12)}
.wdyh-actions{display:flex;align-items:center;gap:14px;margin-top:10px;font-size:.85rem;color:var(--muted)}
.wdyh-actions button{background:transparent;border:0;color:var(--accent);cursor:pointer;font-size:.85rem;font-family:inherit;text-decoration:underline}
.wdyh-actions button:hover{color:#9a3209}
.wdyh-matches{margin-top:18px}
.wdyh-matches h3{margin:0 0 10px;color:var(--accent);font-size:1.05rem}
.wdyh-match{display:flex;flex-direction:column;gap:4px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:8px;text-decoration:none;color:var(--ink)}
.wdyh-match:hover{background:#fff3e2}
.wdyh-match-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.wdyh-match-title{font-weight:bold}
.wdyh-match-cat{color:var(--muted);font-size:.85rem}
.wdyh-match-score{margin-left:auto;background:var(--accent);color:#fff;border-radius:999px;padding:2px 10px;font-size:.8rem;font-weight:bold}
.wdyh-match-score.partial{background:var(--accent2)}
.wdyh-match-need{color:var(--muted);font-size:.85rem}
.wdyh-match-need .have{color:#16a34a;font-weight:bold}
.wdyh-match-need .miss{color:#b45309}
.wdyh-empty-state{color:var(--muted);font-style:italic;padding:14px;background:#fff;border:1px dashed var(--line);border-radius:10px;text-align:center}
"""


# Client-side JS: hide NEW badges per-user once a recipe is viewed.
# Stores viewed recipe URLs in localStorage under "recipesViewedNew".
VIEWED_NEW_JS = r"""
(function(){
  var KEY = 'recipesViewedNew';
  function load(){
    try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); }
    catch(e){ return new Set(); }
  }
  function save(s){
    try { localStorage.setItem(KEY, JSON.stringify(Array.from(s))); } catch(e){}
  }
  var viewed = load();
  var isNewPage = document.body.classList.contains('new-page');

  // Hide NEW badges (and on new.html the whole <li>) for already-viewed links.
  var anchors = document.querySelectorAll('a');
  for (var i = 0; i < anchors.length; i++) {
    var a = anchors[i];
    var badge = a.querySelector('.tag.new');
    if (!badge) continue;
    var href = a.getAttribute('href');
    if (href && viewed.has(href)) {
      badge.remove();
      if (isNewPage) {
        var li = a.closest('li');
        if (li) li.remove();
      }
    }
  }

  // Index page: update banner count or hide it.
  var banner = document.querySelector('.new-banner');
  if (banner) {
    var remaining = document.querySelectorAll('a .tag.new').length;
    if (remaining === 0) {
      banner.style.display = 'none';
    } else {
      var text = banner.querySelector('.new-banner-text');
      if (text) {
        text.textContent = 'See the ' + remaining + ' newest recipe' + (remaining === 1 ? '' : 's');
      }
    }
  }

  // New page: drop empty sections and show "all caught up" if everything viewed.
  if (isNewPage) {
    var sections = document.querySelectorAll('section');
    for (var j = 0; j < sections.length; j++) {
      if (sections[j].querySelectorAll('li').length === 0) sections[j].remove();
    }
    if (document.querySelectorAll('section').length === 0) {
      var main = document.querySelector('main');
      if (main) {
        var msg = document.createElement('p');
        msg.className = 'all-caught-up';
        msg.innerHTML = "\u2728 You're all caught up! No new recipes to view.";
        main.appendChild(msg);
      }
      var headline = document.querySelector('main h1');
      if (headline) headline.style.display = 'none';
      var intro = document.querySelector('.new-page-intro');
      if (intro) intro.style.display = 'none';
    } else {
      // Update headline count too
      var leftCount = document.querySelectorAll('a .tag.new').length;
      var headlineEl = document.querySelector('main h1');
      if (headlineEl) {
        headlineEl.textContent = '\ud83c\udd95 ' + leftCount + ' New Recipe' + (leftCount === 1 ? '' : 's');
      }
    }
  }

  // Mark as viewed on click of any link that currently shows a NEW badge.
  document.addEventListener('click', function(e){
    var t = e.target;
    while (t && t !== document.body) {
      if (t.tagName === 'A') {
        var b = t.querySelector('.tag.new');
        if (b) {
          var h = t.getAttribute('href');
          if (h) {
            viewed.add(h);
            save(viewed);
          }
        }
        break;
      }
      t = t.parentNode;
    }
  });
})();
"""


# Client-side JS: make every recipe image a clickable/focusable thumbnail
# that toggles between compact and full-width display.
IMAGE_TOGGLE_JS = r"""
(function(){
    var images = document.querySelectorAll('.recipe-content img');
    function toggle(img){
        var expanded = img.classList.toggle('image-expanded');
        img.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        img.title = expanded ? 'Click to shrink image' : 'Click to enlarge image';
    }
    for (var i = 0; i < images.length; i++) {
        var img = images[i];
        img.setAttribute('role', 'button');
        img.setAttribute('tabindex', '0');
        img.setAttribute('aria-expanded', 'false');
        img.title = 'Click to enlarge image';
        img.addEventListener('click', function(){ toggle(this); });
        img.addEventListener('keydown', function(e){
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggle(this);
            }
        });
    }
})();
"""


WDYH_JS = r"""
(function(){
  var RECIPES = [];
  var INGREDIENTS = [];
  var selected = [];
  var MAX_SELECTED = 10;
  var activeSuggestIdx = -1;

  var panel = document.getElementById('wdyh');
  var head = document.getElementById('wdyh-head');
  var body = document.getElementById('wdyh-body');
  var input = document.getElementById('wdyh-input');
  var suggest = document.getElementById('wdyh-suggest');
  var chips = document.getElementById('wdyh-chips');
  var matches = document.getElementById('wdyh-matches');
  var clearBtn = document.getElementById('wdyh-clear');
  var count = document.getElementById('wdyh-count');

  if (!panel) return;

  // Collapsible
  head.addEventListener('click', function(){
    var open = panel.getAttribute('data-open') === 'true';
    panel.setAttribute('data-open', open ? 'false' : 'true');
  });

  function loadData(){
    return Promise.all([
      fetch('recipes_index.json').then(function(r){return r.json();}),
      fetch('ingredients_master.json').then(function(r){return r.json();})
    ]).then(function(arr){
      RECIPES = arr[0];
      INGREDIENTS = arr[1];
      input.disabled = false;
      input.placeholder = 'Type an ingredient (e.g. chicken, eggs, flour)...';
    }).catch(function(){
      input.placeholder = 'Could not load ingredient data';
    });
  }
  loadData();

  function updateCount(){
    if (count) count.textContent = selected.length + ' / ' + MAX_SELECTED;
    if (input) {
      input.disabled = selected.length >= MAX_SELECTED;
      if (input.disabled) input.placeholder = 'Maximum ' + MAX_SELECTED + ' ingredients selected';
    }
  }

  function renderChips(){
    chips.innerHTML = '';
    selected.forEach(function(name, i){
      var chip = document.createElement('span');
      chip.className = 'wdyh-chip';
      chip.textContent = name;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('aria-label', 'Remove ' + name);
      btn.innerHTML = '&times;';
      btn.addEventListener('click', function(){
        selected.splice(i, 1);
        renderChips();
        renderMatches();
        updateCount();
      });
      chip.appendChild(btn);
      chips.appendChild(chip);
    });
  }

  function renderSuggest(){
    var q = input.value.trim().toLowerCase();
    suggest.innerHTML = '';
    activeSuggestIdx = -1;
    if (!q || selected.length >= MAX_SELECTED){
      suggest.classList.remove('active');
      return;
    }
    var pool = INGREDIENTS
      .filter(function(x){ return x.name.indexOf(q) !== -1 && selected.indexOf(x.name) === -1; })
      .slice(0, 12);
    if (!pool.length){
      var empty = document.createElement('div');
      empty.className = 'wdyh-empty';
      empty.textContent = 'No matching ingredients';
      suggest.appendChild(empty);
      suggest.classList.add('active');
      return;
    }
    pool.forEach(function(x, i){
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('data-name', x.name);
      b.innerHTML = '<span>' + x.name + '</span><span class="wdyh-count">' + x.count + '</span>';
      b.addEventListener('click', function(){ addIngredient(x.name); });
      suggest.appendChild(b);
    });
    suggest.classList.add('active');
  }

  function addIngredient(name){
    if (selected.length >= MAX_SELECTED) return;
    if (selected.indexOf(name) !== -1) return;
    selected.push(name);
    input.value = '';
    renderChips();
    renderSuggest();
    renderMatches();
    updateCount();
    input.focus();
  }

  function renderMatches(){
    if (!selected.length){
      matches.innerHTML = '<div class="wdyh-empty-state">Pick some ingredients above to see what you can make!</div>';
      return;
    }
    var sel = new Set(selected);
    var scored = RECIPES.map(function(r){
      var ings = r.ingredients || [];
      if (!ings.length) return null;
      var have = 0, miss = [];
      ings.forEach(function(ing){
        if (sel.has(ing)) have++; else miss.push(ing);
      });
      return { r: r, have: have, miss: miss, total: ings.length, ratio: have / ings.length };
    }).filter(function(x){ return x && x.have > 0; });

    scored.sort(function(a, b){
      if (b.ratio !== a.ratio) return b.ratio - a.ratio;
      if (a.miss.length !== b.miss.length) return a.miss.length - b.miss.length;
      return a.r.title.localeCompare(b.r.title);
    });

    var full = scored.filter(function(x){ return x.miss.length === 0; });
    var partial = scored.filter(function(x){ return x.miss.length > 0; }).slice(0, 20);

    var html = '';
    if (full.length){
      html += '<h3>You can make these now (' + full.length + ')</h3>';
      full.forEach(function(x){ html += matchCard(x, true); });
    }
    if (partial.length){
      html += '<h3>Close — missing a few ingredients</h3>';
      partial.forEach(function(x){ html += matchCard(x, false); });
    }
    if (!html){
      html = '<div class="wdyh-empty-state">No recipes match those ingredients yet. Try adding more!</div>';
    }
    matches.innerHTML = html;
  }

  function matchCard(x, full){
    var pct = Math.round(x.ratio * 100);
    var need = '';
    if (!full){
      var preview = x.miss.slice(0, 5).map(function(m){ return '<span class="miss">' + escapeHtml(m) + '</span>'; }).join(', ');
      var more = x.miss.length > 5 ? ' (+' + (x.miss.length - 5) + ' more)' : '';
      need = '<div class="wdyh-match-need">Need: ' + preview + more + '</div>';
    } else {
      need = '<div class="wdyh-match-need"><span class="have">All ' + x.total + ' ingredients ✓</span></div>';
    }
    return '<a class="wdyh-match" href="' + x.r.url + '">'
      + '<div class="wdyh-match-top">'
        + '<span class="wdyh-match-title">' + escapeHtml(x.r.title) + '</span>'
        + '<span class="wdyh-match-cat">' + escapeHtml(x.r.category) + '</span>'
        + '<span class="wdyh-match-score' + (full ? '' : ' partial') + '">' + pct + '%</span>'
      + '</div>'
      + need
      + '</a>';
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"']/g, function(c){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }

  input.addEventListener('input', renderSuggest);
  input.addEventListener('keydown', function(e){
    var btns = suggest.querySelectorAll('button');
    if (e.key === 'ArrowDown'){
      e.preventDefault();
      activeSuggestIdx = Math.min(activeSuggestIdx + 1, btns.length - 1);
      btns.forEach(function(b, i){ b.classList.toggle('active', i === activeSuggestIdx); });
    } else if (e.key === 'ArrowUp'){
      e.preventDefault();
      activeSuggestIdx = Math.max(activeSuggestIdx - 1, 0);
      btns.forEach(function(b, i){ b.classList.toggle('active', i === activeSuggestIdx); });
    } else if (e.key === 'Enter'){
      e.preventDefault();
      var pick = activeSuggestIdx >= 0 ? btns[activeSuggestIdx] : btns[0];
      if (pick) addIngredient(pick.getAttribute('data-name'));
    } else if (e.key === 'Escape'){
      suggest.classList.remove('active');
    } else if (e.key === 'Backspace' && !input.value && selected.length){
      selected.pop();
      renderChips();
      renderMatches();
      updateCount();
    }
  });

  document.addEventListener('click', function(e){
    if (!panel.contains(e.target)) suggest.classList.remove('active');
  });

  if (clearBtn){
    clearBtn.addEventListener('click', function(){
      selected = [];
      input.value = '';
      renderChips();
      renderSuggest();
      renderMatches();
      updateCount();
    });
  }

  renderChips();
  renderMatches();
  updateCount();
})();
"""


def render_index(tree: dict[str, dict[str, list[dict]]], total: int, new_count: int = 0) -> str:
    sections = []
    cat_cards = []
    for cat in sorted(tree.keys()):
        sub_map = tree[cat]
        count = sum(len(v) for v in sub_map.values())
        anchor = slugify(cat)
        icon = ICONS.get(cat, "\U0001F4C4")
        cat_cards.append(
            f'<a class="cat" href="#cat-{anchor}"><span class="ic">{icon}</span>'
            f'<span class="name">{escape(cat)}</span><span class="count">{count} recipes</span></a>'
        )
        items_html = []
        has_subs = any(s for s in sub_map.keys())
        if has_subs:
            for sub in sorted(sub_map.keys()):
                if sub:
                    items_html.append(f'<h3 style="color:var(--muted);margin-top:18px">{ICONS.get(sub,"")} {escape(sub)}</h3>')
                items_html.append('<ul class="recipes">')
                for r in sub_map[sub]:
                    items_html.append(_recipe_li(r))
                items_html.append("</ul>")
        else:
            items_html.append('<ul class="recipes">')
            for sub in sub_map:
                for r in sub_map[sub]:
                    items_html.append(_recipe_li(r))
            items_html.append("</ul>")
        sections.append(
            f'<section id="cat-{anchor}"><h2 class="cat-title">{icon} {escape(cat)}</h2>'
            + "\n".join(items_html) + "</section>"
        )

    new_banner = ""
    if new_count:
        plural = "" if new_count == 1 else "s"
        new_banner = (
            f'<a class="new-banner" href="new.html">'
            f'<span class="new-banner-tag">NEW</span>'
            f'<span class="new-banner-text">See the {new_count} newest recipe{plural}</span>'
            f'<span class="new-banner-arrow">&rarr;</span>'
            f'</a>'
        )

    wdyh_panel = (
        '<div class="wdyh" id="wdyh" data-open="true">'
          '<button type="button" class="wdyh-head" id="wdyh-head" aria-expanded="true">'
            '<span class="wdyh-icon">\U0001F9FA</span>'
            '<span>What do you have?</span>'
            '<span class="wdyh-chev">\u25BC</span>'
          '</button>'
          '<div class="wdyh-body" id="wdyh-body">'
            '<p class="wdyh-hint">Add ingredients you have on hand (up to 10) and we\'ll show you recipes you can make.</p>'
            '<div class="wdyh-input-wrap">'
              '<input id="wdyh-input" class="wdyh-input" type="text" placeholder="Loading ingredients..." autocomplete="off" spellcheck="false" disabled>'
              '<div id="wdyh-suggest" class="wdyh-suggest" role="listbox"></div>'
            '</div>'
            '<div id="wdyh-chips" class="wdyh-chips"></div>'
            '<div class="wdyh-actions">'
              '<span id="wdyh-count">0 / 10</span>'
              '<button type="button" id="wdyh-clear">Clear all</button>'
            '</div>'
            '<div id="wdyh-matches" class="wdyh-matches"></div>'
          '</div>'
        '</div>'
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recipes</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='80' font-size='80'>\U0001F374</text></svg>">
<style>{BASE_CSS}</style>
</head><body>
<header>
  <h1><a href="./">\U0001F374 Recipes</a></h1>
  <div class="search"><input id="q" type="search" placeholder="Search {total} recipes..." autocomplete="off"></div>
</header>
<main class="container">
  {new_banner}
  {wdyh_panel}
  <div id="results" class="search-results"><ul id="results-list"></ul></div>
  <div id="browse">
    <div class="cats">{"".join(cat_cards)}</div>
    {"".join(sections)}
  </div>
</main>
<footer>Built from OneDrive/Recipes \u2022 {total} recipes</footer>
<script>
let RECIPES = [];
fetch('recipes_index.json').then(r=>r.json()).then(d=>{{RECIPES=d}});
const q = document.getElementById('q');
const browse = document.getElementById('browse');
const results = document.getElementById('results');
const list = document.getElementById('results-list');
function render(items){{
  if(!items.length){{ list.innerHTML='<li class="empty">No matches.</li>'; return;}}
  list.innerHTML = items.slice(0,200).map(r=>{{
    const sub = r.sub ? ' \u203A '+r.sub : '';
    const newBadge = r.new ? ' <span class="tag new">NEW</span>' : '';
    return `<li><a href="${{r.url}}">${{r.title}}</a> <span class="tag ${{r.type}}">${{r.type}}</span>${{newBadge}}<div class="meta">${{r.category}}${{sub}}</div></li>`;
  }}).join('');
}}
q.addEventListener('input', () => {{
  const term = q.value.trim().toLowerCase();
  if(!term){{ results.classList.remove('active'); browse.style.display=''; return;}}
  const matches = RECIPES.filter(r =>
    r.title.toLowerCase().includes(term) ||
    r.category.toLowerCase().includes(term) ||
    (r.sub||'').toLowerCase().includes(term)
  );
  render(matches);
  results.classList.add('active');
  browse.style.display='none';
}});
</script>
<script>{WDYH_JS}</script>
<script>{VIEWED_NEW_JS}</script>
</body></html>
"""


def _OLD_render_index_unused(tree, total, new_count=0):
    # placeholder so the broken code below this point doesn't run
    def esc(s):
        return s.replace('{', '{{').replace('}', '}}')

    js_block = r'''
let RECIPES = [];
let INGREDIENTS = [];
fetch('recipes_index.json').then(r=>r.json()).then(d=>{RECIPES=d;});
fetch('ingredients_master.json').then(r=>r.json()).then(d=>{INGREDIENTS=d;});
const q = document.getElementById('q');
const browse = document.getElementById('browse');
const results = document.getElementById('results');
const list = document.getElementById('results-list');

// --- What Do You Have Panel Logic ---
const wdyhInput = document.getElementById('wdyh-input');
const wdyhSuggest = document.getElementById('wdyh-suggest');
const wdyhChips = document.getElementById('wdyh-chips');
const wdyhMatches = document.getElementById('wdyh-matches');
let wdyhSelected = [];
let wdyhSuggestList = [];

function renderWdyhChips() {
    wdyhChips.innerHTML = wdyhSelected.map((name, i) =>
        `<span class="wdyh-chip">${name}<button type="button" class="wdyh-chip-x" data-idx="${i}" aria-label="Remove">&times;</button></span>`
    ).join('');
}




function renderWdyhSuggest() {
    const val = wdyhInput.value.trim().toLowerCase();
    if (!val) { wdyhSuggest.innerHTML = ''; wdyhSuggestList = []; return; }
    const matches = INGREDIENTS.filter(x => x.name.includes(val) && !wdyhSelected.includes(x.name)).slice(0, 10);
    wdyhSuggestList = matches;
    wdyhSuggest.innerHTML = matches.length ?
        '<ul>' + matches.map((x, i) => `<li data-idx="${i}">${x.name} <span class="wdyh-suggest-count">(${x.count})</span></li>`).join('') + '</ul>' : '';
}

function renderWdyhMatches() {
    if (!wdyhSelected.length) {
        wdyhMatches.innerHTML = '<div class="wdyh-empty-state">Pick some ingredients to see matching recipes!</div>';
        return;
    }
    // Find recipes where every ingredient is in wdyhSelected
    const matches = RECIPES.filter(r => {
        if (!r.ingredients || !r.ingredients.length) return false;
        return r.ingredients.every(ing => wdyhSelected.includes(ing));
    });
    if (!matches.length) {
        wdyhMatches.innerHTML = '<div class="wdyh-empty-state">No recipes use only those ingredients. Try adding or removing some!</div>';
        return;
    }
    wdyhMatches.innerHTML = '<ul class="wdyh-match-list">' + matches.map(r =>
        `<li><a href="${r.url}">${r.title}</a> <span class="tag">${r.category}</span></li>`
    ).join('') + '</ul>';
}

wdyhInput.addEventListener('input', renderWdyhSuggest);
wdyhInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && wdyhSuggestList.length) {
        // Add first suggestion
        if (wdyhSelected.length < 10) {
            wdyhSelected.push(wdyhSuggestList[0].name);
            wdyhInput.value = '';
            renderWdyhChips();
            renderWdyhSuggest();
            renderWdyhMatches();
        }
        e.preventDefault();
    }
});
wdyhSuggest.addEventListener('click', function(e) {
    const li = e.target.closest('li[data-idx]');
    if (!li) return;
    const idx = +li.getAttribute('data-idx');
    if (wdyhSelected.length < 10) {
        wdyhSelected.push(wdyhSuggestList[idx].name);
        wdyhInput.value = '';
        renderWdyhChips();
        renderWdyhSuggest();
        renderWdyhMatches();
    }
});
    }
    const btn = e.target.closest('button[data-idx]');
    if (!btn) return;
    const idx = +btn.getAttribute('data-idx');
    wdyhSelected.splice(idx, 1);
    renderWdyhChips();
    renderWdyhSuggest();
    renderWdyhMatches();
});

// Initial render
setTimeout(() => {
    renderWdyhChips();
    renderWdyhSuggest();
    renderWdyhMatches();
}, 400);

// --- Existing search logic ---
function render(items){
    if(!items.length){ list.innerHTML='<li class="empty">No matches.</li>'; return;}
    list.innerHTML = items.slice(0,200).map(r=>{
        const sub = r.sub ? ' › '+r.sub : '';
        const newBadge = r.new ? ' <span class="tag new">NEW</span>' : '';
        return `<li><a href="${r.url}">${r.title}</a> <span class="tag ${r.type}">${r.type}</span>${newBadge}<div class="meta">${r.category}${sub}</div></li>`;
    }).join('');
}
q.addEventListener('input', () => {
    const term = q.value.trim().toLowerCase();
    if(!term){ results.classList.remove('active'); browse.style.display=''; return;}
    const matches = RECIPES.filter(r =>
        r.title.toLowerCase().includes(term) ||
        r.category.toLowerCase().includes(term) ||
        (r.sub||'').toLowerCase().includes(term)
    );
    render(matches);
'''
    html = '''<!doctype html>
    <html lang='en'><head>
    <meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Recipes</title>
    <link rel='icon' href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='80' font-size='80'>&#127860;</text></svg>">
    <style>{BASE_CSS}</style>
    </head><body>
    <header>
        <h1><a href='./'>&#127860; Recipes</a></h1>
        <div class='search'><input id='q' type='search' placeholder='Search {total} recipes...' autocomplete='off'></div>
    </header>
    <main class='container'>
        <!-- What Do You Have Panel -->
        <section class='wdyh-panel' id='wdyh-panel'>
            <h2 class='wdyh-title'>What do you have?</h2>
            <div class='wdyh-desc'>Pick up to 10 ingredients you have on hand. We\'ll show you every recipe you can make!</div>
            <div class='wdyh-input-row'>
                <input id='wdyh-input' class='wdyh-input' type='text' placeholder='Type an ingredient...' autocomplete='off' spellcheck='false'>
                <div id='wdyh-suggest' class='wdyh-suggest'></div>
            </div>
            <div id='wdyh-chips' class='wdyh-chips'></div>
            <div id='wdyh-matches' class='wdyh-matches'></div>
        </section>
        {new_banner}
        <div id='results' class='search-results'><ul id='results-list'></ul></div>
        <div id='browse'>
            <div class='cats'>{cat_cards}</div>
            {sections}
        </div>
    </main>
    <footer>Built from OneDrive/Recipes • {total} recipes</footer>
    <script>
    {js}
    </script>
    <script>{viewed_new_js}</script>
    </body></html>
    '''.format(
        BASE_CSS=BASE_CSS,
        total=total,
        new_banner=new_banner,
        cat_cards="".join(cat_cards),
        sections="".join(sections),
        js=esc(js_block),
        viewed_new_js=VIEWED_NEW_JS
    )
    return html

def _recipe_li(r: dict) -> str:
    t = r["type"]
    new_badge = ' <span class="tag new">NEW</span>' if r.get("new") else ''
    return (
        f'<li><a href="{escape(r["url"])}">{escape(r["title"])}'
        f'<span class="tag {t}">{t}</span>{new_badge}</a></li>'
    )


def render_new_page(recipes: list[dict], new_count: int) -> str:
    """Build a dedicated page listing every recipe currently flagged NEW."""
    by_cat: dict[str, list[dict]] = {}
    for r in recipes:
        if r.get("new"):
            by_cat.setdefault(r["category"], []).append(r)
    sections = []
    for cat in sorted(by_cat.keys()):
        icon = ICONS.get(cat, "\U0001F4C4")
        items = "\n".join(_recipe_li(r) for r in sorted(by_cat[cat], key=lambda x: x["title"].lower()))
        sections.append(
            f'<section><h2 class="cat-title">{icon} {escape(cat)}</h2>'
            f'<ul class="recipes">{items}</ul></section>'
        )
    plural = "" if new_count == 1 else "s"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>New Recipes \u2022 Recipes</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='80' font-size='80'>\U0001F374</text></svg>">
<style>{BASE_CSS}</style>
</head><body class="new-page">
<header><h1><a href="index.html">\U0001F374 Recipes</a></h1></header>
<main class="container">
  <div class="crumbs"><a href="index.html">Recipes</a> \u203A <span class="tag new">NEW</span></div>
  <h1 style="color:var(--accent);margin-top:0">\U0001F195 {new_count} New Recipe{plural}</h1>
  <p class="new-page-intro">Click any recipe and the NEW badge disappears for you. (We remember your views in this browser.)</p>
  {"".join(sections)}
</main>
<footer><a href="index.html">\u2190 Back to all recipes</a></footer>
<script>""" + VIEWED_NEW_JS + """</script>
</body></html>
"""


def render_recipe_page(title: str, category: str, sub: str, body: str) -> str:
    # Compute path back to root from /recipes/<cat>[/<sub>]/file.html
    depth = 2 + (1 if sub else 0)
    root = "../" * depth
    crumbs = f'<a href="{root}index.html">Recipes</a> › <a href="{root}index.html#cat-{slugify(category)}">{escape(category)}</a>'
    if sub:
        crumbs += f' › {escape(sub)}'
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} • Recipes</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='80' font-size='80'>🍴</text></svg>">
<style>{BASE_CSS}</style>
</head><body>
<header><h1><a href="{root}index.html">🍴 Recipes</a></h1></header>
<main class="container">
  <div class="crumbs">{crumbs}</div>
  <h1 style="color:var(--accent);margin-top:0">{escape(title)}</h1>
  <article class="recipe-content">{body}</article>
</main>
<footer><a href="{root}index.html">← Back to all recipes</a></footer>
<script>""" + IMAGE_TOGGLE_JS + """</script>
</body></html>
"""


if __name__ == "__main__":
    main()
