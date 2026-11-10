# Recipes

A static site for browsing my family recipe collection. Built from `d:\OneDrive\Recipes`.

🌐 **Live site:** <https://matziq.github.io/recipes/>

## Categories

23 categories, 425 entries (including 5 explicitly incomplete recipes and
10 intentional reference pages). Actual recipes have standard Ingredients and
Instructions sections with ingredient and cooking-step checklists. Reviewed scan recipes include
searchable ingredient facts and concise methods; unresolved source gaps remain
disclosed rather than guessed. Protected cookbook and breadmaker collections
are reference summaries, not reproduced collections.

## Build

```powershell
python build.py
```

Dependencies are listed in `requirements.txt`.

```powershell
python -m unittest discover -p "_test_*.py" -v
```

## Recipe presentation and saved progress

`recipe_structure_review.json` binds reviewed presentation changes to source
SHA-256 fingerprints and the converter's original HTML. `recipe_structure.py`
turns reviewed paragraph, line-break, and layout-table ingredients into semantic
lists; scan transcriptions live in that same manifest. The build stops explicitly
when a reviewed source or converter body changes. Update the review deliberately;
do not infer amounts or methods from recipe names.

Existing list items retain their original progress slots. Newly added ingredient
and instruction items use subsequent slots even when displayed earlier, preserving
the existing URL-based saved-progress keys. Citation links remain usable without
toggling checklist items. Tests inventory every indexed page, verify legacy item
fingerprints and progress-slot uniqueness, and exercise keyboard/link behavior.

`recipe_presentation_review.json` records content-reviewed browse-category corrections
with rationales, food-family exceptions, and the few ingredient facts originally
misformatted as headings or embedded in methods. `recipe_presentation.py` gives all
cooking items explicit semantics, keeps non-cooking notes/references out of checklists,
and produces static, grouped shopping lists above the recipe. Shopping lists copy
ingredient facts without aggregating quantities, combining alternate sizes/formulas,
or sharing cooking-progress state. Missing amounts/methods remain disclosed; six
ingredient-only sources intentionally have no invented step checklist.

All existing recipe URLs stay unchanged even when their browse category changes;
navigation/asset paths are based on the URL, not the category label. Category,
subcategory, and title sorting use accent/punctuation-normalized alphabetical keys,
with the same title comparison in client-side search. Broad food-family backgrounds
have visible text labels, light/dark palettes, mobile layouts, and neutral print styles.
Saved progress retains inactive legacy slots as well as active cooking slots.
Native keyboard-accessible disclosures keep Shopping list and About this dish /
Did you know? closed by default, with Ingredients and Instructions independently
open by default, including interleaved components. Cook mode opens cooking sections.
Printing opens all meaningful disclosures and restores their screen states afterward.
Images start as small aspect-ratio-preserving previews; click, Enter or Space toggles
full-width viewing and back, with an accessible expanded-state label.

`recipe_notes.py` supplies independently worded, cited history or did-you-know
paragraphs for all 414 food preparations. Facts describe an identified dish family
or an ingredient actually present, not invented origins for individual family recipes.
Related variants may share context. The play-dough preparation instead has an
explicitly nonfood craft note grounded in its source; the ten reference pages do
not receive invented dish histories. Missing fact coverage stops the build.
The inventory tests cover all 425 entries, exact shopping-list fact coverage and
alternative grouping, 38 reviewed category corrections, and every published
legacy item fingerprint and storage slot.

The six breadmaker exceptions, first-tastes ideas, quick dinner ideas, healthy
snack ideas, and the supplied full cookbook are explicitly identified as reference
material, not standalone recipes. They have section explanations instead of invented
ingredient checklists or cooking instructions.

## More Recipes reconciliation

`more_recipes_review.json` records the recursive review of
`D:\OneDrive\Recipes\More Recipes`: 170 files, with 31 complete missing recipes
or materially different variants added, 128 represented files (including the
back of an incomplete card combined with its front), 5 explicitly incomplete
recipe entries, and 6 breadmaker reference tables represented by exception suggestion pages
(the protected tables and images remain excluded). Original files are not modified.
Alternate titles and photographed duplicates point to existing recipe URLs.
Incomplete entries have `(Incomplete)` in their indexed titles and a prominent
warning listing exactly what is missing before their factual content. Swig Sugar
Cookies' missing oil unit was recovered from the unequivocally identified
Mel's Kitchen Cafe original, with the supplied avocado-oil variant retained.
Mom's Dressing combines both cards. Basic Berliner uses only ingredient facts
and a short summary, not cookbook images or protected prose. Protected
cookbook/reference collections are not reproduced.

All 11 remaining exceptions have a visually separate **Suggested completion** section.
Each names and links an independent source, gives evidence/rating information where
verified, explains differences and confidence, and distinguishes an optional adaptation
from a recovered original. Suggestions do not overwrite source facts or change the
incomplete classification. Reference titles end in `(Exception)` and retain warnings;
their pages summarize the subject without copying manual tables or images. No
substitute is advertised as a tested completion of the original. Suggested ingredient
quantities are excluded from original-recipe ingredient indexing. Mom's Dressing
retains its 165 F food-safety requirement.

The nine distinct complete substitute/comparison recipes are stored in
`imported_recipes.json` and generated with the same reviewed recipe renderer.
Every exception's primary substitute link stays within this collection; external
links remain as author/source citations. Shared sources are imported once, and
materially different formulas are not conflated with existing family recipes.
Ingredient facts and cooking details are retained with independently worded
directions; no protected prose or photos are imported. Complete substitutes are
not untested hybrid completions of the original. Bread-machine size alternatives
are labeled as separate batches, and machine-specific cycle/capacity limitations
remain explicit. The manufacturer finger-gelatin page supplies an actual complete
recipe with envelope weights, not a guessed tablespoon conversion.

The build excludes that folder from automatic discovery and publishes only its
reviewed `added` entries and explicitly labeled factual `incomplete` entries
or `reference` exception suggestions with a URL in the existing categories. Single-recipe clippings with
adapted directions use `body_html`; personal scans retain their original content
and attribution. Every reviewed source has a SHA-256 fingerprint. A changed
source or inventory stops the build before it replaces generated output; review
the change and update the manifest deliberately rather than guessing missing
quantities or automatically importing a collection.
