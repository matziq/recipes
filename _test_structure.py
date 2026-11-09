import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

import recipe_structure
from build import extract_ingredients_from_html

ROOT = Path(__file__).parent


class WholeSiteStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = json.loads(recipe_structure.PLAN_FILE.read_text(encoding="utf-8"))
        cls.index = json.loads((ROOT / "recipes_index.json").read_text(encoding="utf-8"))

    def test_every_indexed_recipe_has_sections_and_ingredient_checklists(self):
        self.assertTrue(self.index)
        self.assertTrue(set(self.plans).issubset({row["url"] for row in self.index}))
        for row in self.index:
            with self.subTest(url=row["url"]):
                article = BeautifulSoup((ROOT / row["url"]).read_text(encoding="utf-8"), "html.parser").select_one(".recipe-content")
                self.assertIsNotNone(article)
                headings = [h.get_text(strip=True) for h in article.find_all("h2")]
                self.assertIn("Ingredients", headings)
                self.assertIn("Instructions", headings)
                plan = self.plans.get(row["url"], {})
                if plan.get("exception"):
                    self.assertIn("Reference, not a standalone recipe", headings)
                    self.assertEqual(len(article.select('[aria-label="Suggested completion"] li')), 0)
                    continue
                ingredient_heading = article.find("h2", string="Ingredients")
                ingredient_list = ingredient_heading.find_next("ul")
                self.assertIsNotNone(ingredient_list)
                self.assertTrue(ingredient_list.find_all("li"))
                self.assertTrue(all(li.get_text(strip=True) for li in article.find_all("li")))
                self.assertFalse(article.select('[aria-label="Suggested completion"] li'))
                if "incomplete" in row["url"]:
                    self.assertIn("Incomplete recipe - not ready to cook", article.get_text())

    def test_existing_saved_slots_remain_bound_to_the_same_item_text(self):
        for row in self.index:
            plan = self.plans.get(row["url"], {})
            with self.subTest(url=row["url"]):
                article = BeautifulSoup((ROOT / row["url"]).read_text(encoding="utf-8"), "html.parser").select_one(".recipe-content")
                items = article.select("ul li, ol li")
                slots = [int(li.get("data-progress-index", i)) for i, li in enumerate(items)]
                self.assertEqual(len(slots), len(set(slots)))
                self.assertEqual(set(slots), set(range(len(slots))))
                by_slot = dict(zip(slots, items))
                for slot, expected in enumerate(plan.get("legacy_items", [])):
                    text = recipe_structure.text_of(by_slot[slot])
                    self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), expected)

    def test_protected_cookbook_is_only_a_reference_summary(self):
        article = BeautifulSoup((ROOT / "recipes/other/jamie-oliver-the-naked-chef-2.html").read_text(encoding="utf-8"), "html.parser").select_one(".recipe-content")
        self.assertFalse(article.find_all("img"))
        self.assertLess(len(article.get_text()), 1000)
        for row in self.index:
            if self.plans.get(row["url"], {}).get("body_html"):
                page = ROOT / row["url"]
                self.assertFalse(page.with_name(page.stem + "_pages").exists(),
                                 f"Reviewed transcription must not republish unused scans: {row['url']}")

    def test_javascript_saved_state_and_link_behavior(self):
        subprocess.run(["node", str(ROOT / "_test_checklists.js")], check=True)

    def test_changed_body_requires_explicit_review(self):
        body = "<p>1 cup flour</p><p>Mix.</p>"
        plan = {"body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "ingredients": [0], "instructions": [1]}
        with self.assertRaisesRegex(ValueError, "content changed"):
            recipe_structure.normalize_body(body + "<p>Changed</p>", "recipes/test.html", {"recipes/test.html": plan})

    def test_missing_source_review_fails_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Recipe.txt"
            source.write_text("original", encoding="utf-8")
            path = root / "plans.json"
            path.write_text(json.dumps({"recipes/test.html": {
                "sources": [{"path": "Recipe.txt", "sha256": "0" * 64}]}}), encoding="utf-8")
            with patch.object(recipe_structure, "PLAN_FILE", path):
                with self.assertRaisesRegex(ValueError, "source changed"):
                    recipe_structure.load_plans(root)

    def test_source_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plans.json"
            path.write_text(json.dumps({"recipes/test.html": {
                "sources": [{"path": "../outside", "sha256": "0" * 64}]}}), encoding="utf-8")
            with patch.object(recipe_structure, "PLAN_FILE", path):
                with self.assertRaisesRegex(ValueError, "Invalid structure source"):
                    recipe_structure.load_plans(Path(directory))

    def test_new_ingredient_lists_do_not_shift_existing_instruction_slots(self):
        body = ("<p>Ingredients</p><p>1 cup flour<br>1 egg</p>"
                "<h2>Instructions</h2><ol><li>Mix.</li><li>Bake.</li></ol>")
        plan = {"body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "ingredients": [1, 2], "instructions": [4, 5]}
        normalized = BeautifulSoup(recipe_structure.normalize_body(
            body, "recipes/test.html", {"recipes/test.html": plan}), "html.parser")
        self.assertEqual([li["data-progress-index"] for li in normalized.select("li")], ["2", "3", "0", "1"])
        self.assertEqual([h.get_text() for h in normalized.find_all("h2")], ["Ingredients", "Instructions"])

    def test_component_ingredients_are_indexed_without_methods_or_suggestions(self):
        body = ('<h2>Ingredients</h2><ul><li class="recipe-ingredient">1 cup flour</li></ul>'
                '<h2>Instructions</h2><ol><li class="recipe-instruction">Bake.</li></ol>'
                '<h3>Frosting</h3><ul><li class="recipe-ingredient">1 cup sugar</li></ul>'
                '<section><p>2 cups salt</p></section>')
        self.assertEqual(extract_ingredients_from_html(body), ["flour", "sugar"])
        self.assertEqual(extract_ingredients_from_html(
            '<h2>Reference, not a standalone recipe</h2><h2>Ingredients</h2><p>No ingredient list.</p>'), [])


if __name__ == "__main__":
    unittest.main()
