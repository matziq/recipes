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

    def test_unreviewed_file_requires_review(self):
        (self.file.parent / "New.docx").write_bytes(b"new")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            build.load_reviewed_recipes()

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
