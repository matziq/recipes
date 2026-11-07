# Recipes

A static site for browsing my family recipe collection. Built from `d:\OneDrive\Recipes`.

🌐 **Live site:** <https://matziq.github.io/recipes/>

## Categories

22 categories, 410 entries (including 5 explicitly incomplete recipes). `.docx` files are converted to HTML for inline browsing;
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
recipe entries, and 6 excluded breadmaker reference tables. Original files are not modified.
Alternate titles and photographed duplicates point to existing recipe URLs.
Incomplete entries have `(Incomplete)` in their indexed titles and a prominent
warning listing exactly what is missing before their factual content. Swig Sugar
Cookies' missing oil unit was recovered from the unequivocally identified
Mel's Kitchen Cafe original, with the supplied avocado-oil variant retained.
Mom's Dressing combines both cards. Basic Berliner uses only ingredient facts
and a short summary, not cookbook images or protected prose. Protected
cookbook/reference collections are not reproduced.

The build excludes that folder from automatic discovery and publishes only its
reviewed `added` entries and explicitly labeled factual `incomplete` entries
with a URL in the existing categories. Single-recipe clippings with
adapted directions use `body_html`; personal scans retain their original content
and attribution. Every reviewed source has a SHA-256 fingerprint. A changed
source or inventory stops the build before it replaces generated output; review
the change and update the manifest deliberately rather than guessing missing
quantities or automatically importing a collection.
