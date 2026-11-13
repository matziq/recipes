import json
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

import recipe_presentation as presentation
import recipe_notes
from recipe_structure import text_of

ROOT = Path(__file__).parent
NO_METHOD = {
    "recipes/breads/sacrament-bread.html",
    "recipes/breakfast/red-door-skillet-incomplete.html",
    "recipes/desserts/basic-berliner-incomplete.html",
    "recipes/desserts/cakes/white-chocolate-raspberry-cake-incomplete.html",
    "recipes/snacks/finger-jello-incomplete.html",
    "recipes/sauces-dips/best-salsa-taquera-recipe-taqueria-style-salsa-roja-mexican-made-meatless.html",
}


class CollectionPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((ROOT / "recipes_index.json").read_text(encoding="utf-8"))
        cls.reviews = presentation.load_presentation_reviews()
        cls.pages = {r["url"]: BeautifulSoup((ROOT / r["url"]).read_text(encoding="utf-8"), "html.parser")
                     for r in cls.index}

    def test_all_reviewed_categories_and_urls_are_preserved(self):
        self.assertEqual(len(self.index), 425)
        self.assertEqual(len({r["category"] for r in self.index}), 23)
        self.assertTrue(set(self.reviews).issubset(self.pages))
        changes = {url: review["category"] for url, review in self.reviews.items() if "category" in review}
        self.assertEqual(len(changes), 38)
        for row in self.index:
            if row["url"] == "recipes/desserts/sophies-shepherds-pie.html":
                self.assertTrue(row.get("new"), "Reclassification must not lose NEW metadata")
            if row["url"] in changes:
                self.assertEqual(row["category"], changes[row["url"]])
            page = self.pages[row["url"]]
            self.assertEqual(page.body["data-recipe-category"], row["category"])
            for node in page.select('link[rel="stylesheet"], script[src], a.back-btn'):
                target = node.get("href", node.get("src", ""))
                if target and not target.startswith(("https:", "#")):
                    self.assertTrue((ROOT / row["url"]).parent.joinpath(target).resolve().exists(),
                                    (row["url"], target))

    def test_index_and_each_browse_group_are_alphabetical(self):
        self.assertEqual(self.index, sorted(self.index, key=presentation.recipe_sort_key))
        home = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        listings = home.select("#browse ul.recipes")
        self.assertTrue(listings)
        titles_by_url = {r["url"]: r["title"] for r in self.index}
        for listing in listings:
            titles = [titles_by_url[a["href"]] for a in listing.select("a")]
            self.assertEqual(titles, sorted(titles, key=presentation.sort_text))
        category_names = [r["category"] for r in self.index]
        unique = list(dict.fromkeys(category_names))
        self.assertEqual(unique, sorted(unique, key=presentation.sort_text))

    def test_all_cooking_facts_and_steps_have_distinct_checklist_semantics(self):
        references = 0
        missing_methods = set()
        for row in self.index:
            with self.subTest(url=row["url"]):
                page = self.pages[row["url"]]
                article = page.select_one(".recipe-content")
                ingredients = article.select("li.recipe-ingredient")
                steps = article.select("li.recipe-instruction")
                if article.find("h2", string="Reference, not a standalone recipe"):
                    references += 1
                    self.assertFalse(ingredients or steps)
                    self.assertIsNone(page.select_one(".shopping-list"))
                    self.assertEqual(page.body["data-food-family"], "reference")
                    continue
                self.assertTrue(ingredients)
                self.assertTrue(steps or article.select("[data-missing-method]"))
                if not steps:
                    missing_methods.add(row["url"])
                for item in ingredients + steps:
                    self.assertIsNotNone(item.find_parent(["ul", "ol"]))
                    self.assertFalse(item.find_parent(["aside", "section"]))
                    self.assertIn("data-progress-index", item.attrs)
                    self.assertTrue(text_of(item))
                shopping = page.select_one(".shopping-list")
                self.assertFalse(shopping.find_parent(class_="recipe-content"))
                self.assertLess(str(page).index('class="recipe-content"'),
                                str(page).index('class="shopping-list"'))
                self.assertEqual([text_of(li) for li in shopping.select("li")],
                                 [text_of(li) for li in ingredients])
                self.assertFalse(shopping.select("[data-progress-index], [role=checkbox], input"))
                self.assertIn("Planning reference only", text_of(shopping))
                self.assertFalse(article.select("aside li.recipe-ingredient, section li.recipe-instruction"))
        self.assertEqual(references, 10)
        self.assertEqual(missing_methods, NO_METHOD)

    def test_alternative_formulas_remain_separate_shopping_groups(self):
        for url in [
            "recipes/breakfast/moms-waffles.html",
            "recipes/breads/bread-machine-multigrain-bread-bread-dad.html",
            "recipes/breads/easy-bread-machine-bread-pj-hamel.html",
            "recipes/beef/burritos.html",
        ]:
            groups = self.pages[url].select(".shopping-group")
            self.assertGreaterEqual(len(groups), 2, url)
            self.assertTrue(all(g.find("h3").get_text(strip=True) for g in groups))
        burritos = self.pages["recipes/beef/burritos.html"]
        self.assertIn("1 package taco seasoning", text_of(burritos.select_one(".shopping-list")))
        self.assertIn("use refried beans instead", text_of(burritos.select_one(".shopping-list")))
        steak = self.pages["recipes/beef/best-at-home-steak.html"]
        self.assertTrue(any(text_of(li) == "Steak, cut and amount unspecified"
                            for li in steak.select(".shopping-list li")))

    def test_palette_has_explicit_labels_light_dark_mobile_and_print_support(self):
        css = (ROOT / "assets/site.css").read_text(encoding="utf-8")
        for row in self.index:
            family = self.pages[row["url"]].body["data-food-family"]
            self.assertIn(family, presentation.FAMILY_LABELS)
            self.assertIn(presentation.FAMILY_LABELS[family],
                          text_of(self.pages[row["url"]].select_one(".food-family-label")))
        for family in set(presentation.FAMILY_LABELS) - {"reference"}:
            self.assertIn(f'.recipe-page[data-food-family="{family}"]', css)
            self.assertIn(f'html[data-theme="dark"] .recipe-page[data-food-family="{family}"]', css)
        self.assertIn(".shopping-group ul { columns: 1; }", css)
        self.assertIn("@media print", css)

    def test_existing_list_slots_survive_new_fact_and_instruction_insertions(self):
        body = '<h2>Ingredients</h2><ul><li>Flour</li></ul><h2>Instructions</h2><ol><li>Bake.</li></ol><p>Cool.</p>'
        cooked, shopping = presentation.prepare_cooking_body(body, "recipes/test.html", {
            "recipes/test.html": {"additional_instructions": ["Cool."]}})
        items = BeautifulSoup(cooked, "html.parser").select("li")
        self.assertEqual([li["data-progress-index"] for li in items], ["0", "1", "2"])
        self.assertEqual([text_of(li) for li in items], ["Flour", "Bake.", "Cool."])
        self.assertNotIn("Cool.", shopping)
        with self.assertRaisesRegex(ValueError, "not found uniquely"):
            presentation.prepare_cooking_body(body, "recipes/test.html", {
                "recipes/test.html": {"additional_ingredients": ["Invented"]}})

    def test_all_disclosures_have_correct_defaults_and_preserve_cooking_items(self):
        prepared = 0
        references = 0
        for url, page in self.pages.items():
            with self.subTest(url=url):
                article = page.select_one(".recipe-content")
                if article.find("h2", string="Reference, not a standalone recipe"):
                    references += 1
                    self.assertFalse(page.select(".shopping-list, .dish-note, .cooking-section"))
                    continue
                prepared += 1
                for selector in (".shopping-list", ".dish-note"):
                    panel = page.select_one(selector)
                    self.assertEqual(panel.name, "details")
                    self.assertNotIn("open", panel.attrs)
                    self.assertEqual(panel.find(recursive=False).name, "summary")
                self.assertEqual(article.find_next_sibling("details")["class"], ["shopping-list"])
                self.assertEqual(page.select_one(".shopping-list").find_next_sibling("details")["class"],
                                 ["dish-note"])
                panels = article.select("details.cooking-section")
                self.assertTrue(panels)
                self.assertTrue(all("open" in panel.attrs for panel in panels))
                self.assertTrue(all(panel.select_one("summary") for panel in panels))
                for li in article.select("li.recipe-ingredient, li.recipe-instruction"):
                    panel = li.find_parent("details")
                    self.assertIsNotNone(panel)
                    expected = "ingredient" if "recipe-ingredient" in li["class"] else "instruction"
                    self.assertEqual(panel["data-cooking-kind"], expected)
                self.assertFalse(article.select("summary li, .cooking-section aside, .cooking-section section"))
        self.assertEqual((prepared, references), (415, 10))

    def test_food_notes_have_reviewed_citations_and_craft_is_not_food(self):
        foods = 0
        for url, page in self.pages.items():
            note = page.select_one(".dish-note")
            if not note:
                continue
            self.assertTrue(note.select_one("p").get_text(strip=True))
            self.assertFalse(note.select("li, [data-progress-index], img"))
            link = note.select_one(".note-source a")
            self.assertTrue(link)
            if note["data-note-topic"] == "craft":
                self.assertIn("play-dough", url)
                self.assertIn("nonfood", text_of(note))
                self.assertEqual(link["href"], "#main-content")
            else:
                foods += 1
                self.assertTrue(link["href"].startswith("https://"))
                self.assertIn("not a verified origin story", text_of(note))
        self.assertEqual(foods, 414)
        with self.assertRaisesRegex(ValueError, "No reviewed food-context fact"):
            recipe_notes.dish_note("Unidentified", '<ul><li class="recipe-ingredient">Unknown</li></ul>')

    def test_interleaved_components_keep_independent_panels_and_unchanged_slots(self):
        body = ('<h2>Ingredients</h2><h3>Dough</h3><ul>'
                '<li class="recipe-ingredient" data-progress-index="2">Flour</li></ul>'
                '<h2>Instructions</h2><ol><li class="recipe-instruction" data-progress-index="0">'
                'Mix.</li></ol><h3>Filling</h3><ul><li class="recipe-ingredient" '
                'data-progress-index="1">Apples</li></ul><ol><li class="recipe-instruction" '
                'data-progress-index="3">Fill.</li></ol><aside>Source warning</aside>')
        result = BeautifulSoup(presentation.collapsible_cooking_body(body), "html.parser")
        self.assertEqual([d["data-cooking-kind"] for d in result.select("details")],
                         ["ingredient", "instruction", "ingredient", "instruction"])
        self.assertEqual([li["data-progress-index"] for li in result.select("li")], ["2", "0", "1", "3"])
        self.assertIsNone(result.aside.find_parent("details"))

    def test_shared_appearance_is_available_before_styles_on_every_page(self):
        pages = list(self.pages.values()) + [
            BeautifulSoup((ROOT / name).read_text(encoding="utf-8"), "html.parser")
            for name in ("index.html", "new.html")
        ]
        for page in pages:
            scripts = page.select('head script[src$="assets/appearance.js"]')
            self.assertEqual(len(scripts), 1)
            self.assertFalse(scripts[0].has_attr("defer"))
            self.assertLess(str(page).index('assets/appearance.js'), str(page).index('assets/site.css'))
            for selector in ("[data-palette-select]", "[data-theme-toggle]",
                             "[data-motion-toggle]", "[data-theme-surprise]"):
                self.assertEqual(len(page.select(selector)), 1, selector)
        subprocess.run(["node", str(ROOT / "_test_appearance.js")], check=True)


if __name__ == "__main__":
    unittest.main()
