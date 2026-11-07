# Recipes

A static site for browsing my family recipe collection. Built from `d:\OneDrive\Recipes`.

🌐 **Live site:** <https://matziq.github.io/recipes/>

## Categories

22 categories, 425 entries (including 5 explicitly incomplete recipes and 6 reference exceptions). `.docx` files are converted to HTML for inline browsing;
PDF pages are rendered as local images within recipe pages.

## Build

```powershell
python build.py
```

Requires `mammoth` (`pip install mammoth`).

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
