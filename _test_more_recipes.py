import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def tearDown(self):
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
                 "title": "Recipe (Incomplete)", "body_html": "<p>Known ingredient facts.</p>",
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
                 "title": "Recipe (Incomplete)", "body_html": "<p>Original facts.</p>",
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


if __name__ == "__main__":
    unittest.main()
