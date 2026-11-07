# Recipes

A static site for browsing my family recipe collection. Built from `d:\OneDrive\Recipes`.

🌐 **Live site:** <https://matziq.github.io/recipes/>

## Categories

22 categories, 404 recipes. `.docx` files are converted to HTML for inline browsing;
PDF pages are rendered as local images within recipe pages.

## Build

```powershell
python build.py
```

Requires `mammoth` (`pip install mammoth`).

## More Recipes reconciliation

`more_recipes_review.json` records the recursive review of
`D:\OneDrive\Recipes\More Recipes`: 170 files, with 30 complete missing recipes
or materially different variants added, 127 already represented, 7 incomplete
sources, and 6 breadmaker reference tables. Original files are not modified.
Alternate titles and photographed duplicates point to existing recipe URLs.
Incomplete cards and protected cookbook/reference collections are not published.

The build excludes that folder from automatic discovery and publishes only its
reviewed `added` entries in the existing categories. Single-recipe clippings with
adapted directions use `body_html`; personal scans retain their original content
and attribution. Every reviewed source has a SHA-256 fingerprint. A changed
source or inventory stops the build before it replaces generated output; review
the change and update the manifest deliberately rather than guessing missing
quantities or automatically importing a collection.
