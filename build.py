"""Build static recipes site from d:/OneDrive/Recipes.

- Converts .docx -> .html via mammoth
- Copies .pdf, .jpg, .png as-is
- Generates per-category pages, a recipe viewer, and a search index
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
from html import escape
from pathlib import Path

import fitz  # PyMuPDF
import mammoth

SOURCE = Path(r"d:/OneDrive/Recipes")
OUT = Path(__file__).parent
RECIPES_OUT = OUT / "recipes"

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
            recipes.append({
                "title": title, "category": category, "sub": sub,
                "url": rel_url, "type": "html",
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
            })

    recipes.sort(key=lambda r: (r["category"], r["sub"], r["title"].lower()))

    # Write search index
    (OUT / "recipes_index.json").write_text(
        json.dumps(recipes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build category tree
    tree: dict[str, dict[str, list[dict]]] = {}
    for r in recipes:
        tree.setdefault(r["category"], {}).setdefault(r["sub"], []).append(r)

    (OUT / "index.html").write_text(render_index(tree, len(recipes)), encoding="utf-8")
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
.crumbs{color:var(--muted);font-size:.95rem;margin-bottom:14px}
.crumbs a{color:var(--accent);text-decoration:none}
.recipe-content{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:28px}
.recipe-content img{max-width:100%;height:auto}
.recipe-content table{border-collapse:collapse;margin:12px 0}
.recipe-content td,.recipe-content th{border:1px solid var(--line);padding:6px 10px}
.pdf-pages{display:flex;flex-direction:column;gap:14px;align-items:center}
.pdf-page{max-width:100%;height:auto;box-shadow:0 2px 12px rgba(0,0,0,.08);border-radius:6px;background:#fff}
footer{text-align:center;color:var(--muted);padding:30px 20px;font-size:.85rem}
.search-results{display:none}
.search-results.active{display:block}
.search-results ul{list-style:none;padding:0;margin:0}
.search-results li{padding:10px;border-bottom:1px solid var(--line)}
.search-results a{color:var(--accent);text-decoration:none;font-weight:bold}
.search-results .meta{color:var(--muted);font-size:.85rem}
.empty{color:var(--muted);font-style:italic;padding:20px}
"""


def render_index(tree: dict[str, dict[str, list[dict]]], total: int) -> str:
    sections = []
    cat_cards = []
    for cat in sorted(tree.keys()):
        sub_map = tree[cat]
        count = sum(len(v) for v in sub_map.values())
        anchor = slugify(cat)
        icon = ICONS.get(cat, "📄")
        cat_cards.append(
            f'<a class="cat" href="#cat-{anchor}"><span class="ic">{icon}</span>'
            f'<span class="name">{escape(cat)}</span><span class="count">{count} recipes</span></a>'
        )
        items_html = []
        # If has subcategories, group; else flat list
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

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recipes</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='80' font-size='80'>🍴</text></svg>">
<style>{BASE_CSS}</style>
</head><body>
<header>
  <h1><a href="./">🍴 Recipes</a></h1>
  <div class="search"><input id="q" type="search" placeholder="Search {total} recipes..." autocomplete="off"></div>
</header>
<main class="container">
  <div id="results" class="search-results"><ul id="results-list"></ul></div>
  <div id="browse">
    <div class="cats">{"".join(cat_cards)}</div>
    {"".join(sections)}
  </div>
</main>
<footer>Built from OneDrive/Recipes • {total} recipes</footer>
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
    const sub = r.sub ? ' › '+r.sub : '';
    return `<li><a href="${{r.url}}">${{r.title}}</a> <span class="tag ${{r.type}}">${{r.type}}</span><div class="meta">${{r.category}}${{sub}}</div></li>`;
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
</body></html>
"""


def _recipe_li(r: dict) -> str:
    t = r["type"]
    return (
        f'<li><a href="{escape(r["url"])}">{escape(r["title"])}'
        f'<span class="tag {t}">{t}</span></a></li>'
    )


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
</body></html>
"""


if __name__ == "__main__":
    main()
