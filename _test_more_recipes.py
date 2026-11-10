import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

import build


class ReviewedRecipesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "More Recipes" / "Breads"
        source.mkdir(parents=True)
        self.file = source / "Recipe.docx"
        self.file.write_bytes(b"reviewed source")
        self.review = self.root / "review.json"
        self.entry = {
            "source": str(self.file.relative_to(self.root / "More Recipes")),
            "sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(),
            "status": "added",
        }
        self.write_review([self.entry])
        self.source_patch = patch.object(build, "SOURCE", self.root)
        self.review_patch = patch.object(build, "MORE_RECIPES_REVIEW", self.review)
        self.source_patch.start()
        self.review_patch.start()
        # These synthetic ingestion fixtures do not identify a real food.
        self.note_patch = patch("recipe_notes.dish_note", return_value="")
        self.note_patch.start()

    def tearDown(self):
        self.note_patch.stop()
        self.review_patch.stop()
        self.source_patch.stop()
        self.temporary.cleanup()

    def write_review(self, entries):
        self.review.write_text(json.dumps(entries), encoding="utf-8")

    def test_only_added_entries_are_published(self):
        self.assertEqual(build.load_reviewed_recipes(), [self.entry])
        for status in ("represented", "incomplete", "reference"):
            self.write_review([{**self.entry, "status": status}])
            self.assertEqual(build.load_reviewed_recipes(), [])

    def test_changed_source_requires_review(self):
        self.file.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            build.load_reviewed_recipes()

    def test_missing_manifest_stops_build(self):
        self.review.unlink()
        with self.assertRaises(FileNotFoundError):
            build.load_reviewed_recipes()

    def test_incomplete_entries_require_warning_data(self):
        self.write_review([{**self.entry, "status": "incomplete", "url": "recipes/incomplete.html",
                            "title": "Recipe"}])
        with self.assertRaisesRegex(ValueError, "Incomplete publication requires"):
            build.load_reviewed_recipes()

    def test_reviewed_incomplete_entry_is_published_with_warning(self):
        entry = {**self.entry, "status": "incomplete", "url": "recipes/incomplete.html",
                 "title": "Recipe (Incomplete)", "body_html": "<h2>Ingredients</h2><ul><li>Known ingredient facts.</li></ul><h2>Instructions</h2>",
                 "missing": "Baking directions are missing.", "category": "Breads", "sub": ""}
        self.write_review([entry])
        self.assertEqual(build.load_reviewed_recipes(), [entry])
        with patch.object(build, "OUT", self.root):
            result = build.render_reviewed_recipe(entry)
        page = (self.root / result["url"]).read_text(encoding="utf-8")
        self.assertIn("Incomplete recipe - not ready to cook", page)
        self.assertIn(entry["missing"], page)
        self.assertLess(page.index("Incomplete recipe - not ready to cook"), page.index("Known ingredient facts"))

    def test_unreviewed_file_requires_review(self):
        (self.file.parent / "New.docx").write_bytes(b"new")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            build.load_reviewed_recipes()

    def suggestion(self):
        return {"title": "Optional substitute", "source_url": "https://example.com/recipe",
                "attribution": "Independent author", "evidence": "Same ingredient family, different ratios.",
                "confidence": "Moderate; untested.", "body_html": "<p>Suggested ingredient facts.</p>"}

    def test_reference_requires_exception_label_and_suggestion(self):
        entry = {**self.entry, "status": "reference", "url": "recipes/exception.html",
                 "title": "Recipe (Exception)", "body_html": "<p>Manual subject only.</p>",
                 "missing": "Operating method absent.", "category": "Breads", "sub": ""}
        self.write_review([entry])
        with self.assertRaisesRegex(ValueError, "Reference publication requires"):
            build.load_reviewed_recipes()
        entry["suggestions"] = [self.suggestion()]
        self.write_review([entry])
        self.assertEqual(build.load_reviewed_recipes(), [entry])
        entry["title"] = "Recipe"
        self.write_review([entry])
        with self.assertRaisesRegex(ValueError, "Reference publication requires"):
            build.load_reviewed_recipes()

    def test_suggestion_requires_complete_evidence_and_https(self):
        suggestion = self.suggestion()
        del suggestion["confidence"]
        self.write_review([{**self.entry, "suggestions": [suggestion]}])
        with self.assertRaisesRegex(ValueError, "Incomplete suggestion evidence"):
            build.load_reviewed_recipes()
        suggestion = {**self.suggestion(), "source_url": "http://example.com"}
        self.write_review([{**self.entry, "suggestions": [suggestion]}])
        with self.assertRaisesRegex(ValueError, "Suggestion source must use HTTPS"):
            build.load_reviewed_recipes()

    def test_suggestion_is_separate_and_not_ingredient_indexed(self):
        entry = {**self.entry, "status": "incomplete", "url": "recipes/suggestion.html",
                 "title": "Recipe (Incomplete)", "body_html": "<h2>Ingredients</h2><ul><li>Original facts.</li></ul><h2>Instructions</h2>",
                 "missing": "Method absent.", "category": "Breads", "sub": "",
                 "suggestions": [self.suggestion()]}
        with patch.object(build, "OUT", self.root), patch.object(
                build, "extract_ingredients_from_html", return_value=[]) as extract:
            result = build.render_reviewed_recipe(entry)
        page = (self.root / result["url"]).read_text(encoding="utf-8")
        self.assertLess(page.index("Original facts"), page.index("Suggested completion -"))
        self.assertIn("not a recovered original or a tested completion", page)
        self.assertIn("https://example.com/recipe", page)
        self.assertNotIn("Suggested ingredient facts", extract.call_args.args[0])

    def test_duplicate_source_is_rejected(self):
        self.write_review([self.entry, self.entry])
        with self.assertRaisesRegex(ValueError, "Duplicate reviewed source"):
            build.load_reviewed_recipes()

    def test_path_traversal_is_rejected(self):
        self.write_review([{**self.entry, "source": str(Path("..") / "outside.docx")}])
        with self.assertRaisesRegex(ValueError, "Invalid reviewed source"):
            build.load_reviewed_recipes()

    def test_supplemental_sources_are_not_automatically_selected(self):
        self.assertEqual(build.select_best_files(False), [])

    def test_existing_page_is_not_overwritten(self):
        destination = self.root / "recipes" / "existing.html"
        destination.parent.mkdir()
        destination.write_text("keep", encoding="utf-8")
        with patch.object(build, "OUT", self.root):
            with self.assertRaisesRegex(ValueError, "overwrite"):
                build.render_reviewed_recipe({"source": self.entry["source"], "url": "recipes/existing.html"})
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep")

    def import_entry(self):
        return {"title": "Test Complete Recipe", "category": "Breads",
                "source_url": "https://example.com/recipe", "attribution": "Example author",
                "yield": "1 loaf", "ingredient_groups": [{"items": ["1 cup flour"]}],
                "instructions": ["Bake until done."]}

    def load_imports(self, entries):
        path = self.root / "imports.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        with patch.object(build, "IMPORTED_RECIPES", path):
            return build.load_imported_recipes()

    def test_import_requires_complete_fact_groups(self):
        for key in ("yield", "attribution", "ingredient_groups", "instructions"):
            entry = self.import_entry()
            del entry[key]
            with self.assertRaisesRegex(ValueError, "requires complete"):
                self.load_imports([entry])
        with self.assertRaisesRegex(ValueError, "must contain ingredient facts"):
            self.load_imports([{**self.import_entry(), "ingredient_groups": [{"items": []}]}])
        with self.assertRaisesRegex(ValueError, "must be lists"):
            self.load_imports([{**self.import_entry(), "instructions": "not steps"}])

    def test_import_duplicates_and_insecure_citations_fail(self):
        entry = self.import_entry()
        with self.assertRaisesRegex(ValueError, "Duplicate imported"):
            self.load_imports([entry, entry])
        with self.assertRaisesRegex(ValueError, "Duplicate imported"):
            self.load_imports([entry, {**entry, "source_url": "https://example.com/other"}])
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            self.load_imports([{**entry, "source_url": "http://example.com"}])

    def test_complete_import_has_lists_and_attribution_without_images(self):
        entry = self.load_imports([self.import_entry()])[0]
        with patch.object(build, "OUT", self.root):
            recipe = build.render_reviewed_recipe(entry)
        page = (self.root / recipe["url"]).read_text(encoding="utf-8")
        article = BeautifulSoup(page, "html.parser").select_one(".recipe-content")
        self.assertEqual(article.select_one("li.recipe-ingredient").get_text(), "1 cup flour")
        self.assertEqual(article.select_one("li.recipe-instruction").get_text(), "Bake until done.")
        self.assertIn("https://example.com/recipe", page)
        self.assertIn("Example author", page)
        self.assertIn("separate from the incomplete original", page)
        self.assertNotIn("<img", page)

    def test_internal_suggestion_link_preserves_original_list_order(self):
        original = "<h2>Ingredients</h2><ul><li>Original flour</li><li>Original sugar</li></ul><h2>Instructions</h2>"
        entry = {**self.entry, "status": "incomplete", "url": "recipes/breads/original.html",
                 "title": "Original (Incomplete)", "body_html": original, "missing": "Method absent.",
                 "category": "Breads", "sub": "", "suggestions": [{
                     **self.suggestion(), "recipe_url": "recipes/desserts/import.html",
                     "recipe_title": "Separate complete recipe"}]}
        target = self.root / entry["suggestions"][0]["recipe_url"]
        target.parent.mkdir(parents=True)
        target.write_text("complete", encoding="utf-8")
        with patch.object(build, "OUT", self.root):
            recipe = build.render_reviewed_recipe(entry)
        page = (self.root / recipe["url"]).read_text(encoding="utf-8")
        self.assertIn('href="../desserts/import.html"', page)
        article = BeautifulSoup(page, "html.parser").select_one(".recipe-content")
        self.assertEqual([li.get_text() for li in article.select("li")], ["Original flour", "Original sugar"])
        self.assertFalse(article.select('[aria-label="Suggested completion"] li'))

    def test_internal_suggestion_requires_safe_destination(self):
        for url in ("../outside.html", "recipes/../../outside.html", "https://example.com", "recipes/missing.txt"):
            self.write_review([{**self.entry, "suggestions": [{
                **self.suggestion(), "recipe_url": url, "recipe_title": "Complete"}]}])
            with self.assertRaisesRegex(ValueError, "Invalid suggested internal"):
                build.load_reviewed_recipes()

    def test_missing_imported_target_fails_explicitly(self):
        entry = {**self.entry, "status": "incomplete", "url": "recipes/original.html",
                 "title": "Original (Incomplete)", "body_html": "<h2>Ingredients</h2><ul><li>Known facts.</li></ul><h2>Instructions</h2>",
                 "missing": "Method absent.", "category": "Breads", "sub": "",
                 "suggestions": [{**self.suggestion(), "recipe_url": "recipes/missing.html",
                                  "recipe_title": "Missing complete recipe"}]}
        with patch.object(build, "OUT", self.root):
            with self.assertRaisesRegex(ValueError, "does not exist"):
                build.render_reviewed_recipe(entry)


if __name__ == "__main__":
    unittest.main()
