# Recipe editor

The browser editor at <https://memconfigmgr.org/recipes/admin/> publishes recipe
changes directly to the `main` branch of `matziq/recipes` through GitHub's Git
Data API.

## Granting access

1. In the repository, open **Settings > Collaborators > Add people**.
2. Invite the editor's GitHub account and have them accept the invitation.
3. The editor creates a classic personal access token:
   - Scope: **public_repo**
   - Expiration: 90 days or another short period
4. Open the recipe editor, add or select a recipe, and paste the token only when
   publishing.

Fine-grained tokens cannot target a repository owned by another personal
account, so a collaborator must use the classic `public_repo` scope. The token
remains in the active browser tab. The page does not save it in cookies, local
storage, or repository files.

## Publishing behavior

Each publish creates one atomic commit on `main` containing the recipe page and
updated recipe, ingredient, category, and new-recipe indexes. GitHub Pages then
publishes the commit automatically.
