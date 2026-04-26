"""Find likely duplicate recipes from recipes_index.json."""
import json
import re
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent
data = json.loads((OUT / "recipes_index.json").read_text(encoding="utf-8"))


def normalize(title: str) -> str:
    t = title.lower()
    # strip common suffixes
    t = re.sub(r"-desktop-[a-z0-9]+", "", t)
    t = re.sub(r"\(\d+\)", "", t)
    t = re.sub(r"\s+half(\s+batch)?$", "", t)
    t = re.sub(r"\s+\d+$", "", t)
    # remove punctuation
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
for r in data:
    key = (r["category"], normalize(r["title"]))
    groups[key].append(r)

dupes = {k: v for k, v in groups.items() if len(v) > 1}
print(f"Total recipes: {len(data)}")
print(f"Duplicate groups: {len(dupes)}")
print(f"Total duplicate files: {sum(len(v) for v in dupes.values())}")
print()
for (cat, norm), items in sorted(dupes.items()):
    print(f"[{cat}] {norm!r}")
    for it in items:
        print(f"   - {it['title']}  ->  {it['url']}")
    print()
