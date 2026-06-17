# Local Web Console Guide

Use the web console when the weekly plan needs to be executed by someone who does not want to work from Terminal or Markdown files.

## Daily Workflow

1. Open the local web app.
2. Start on the Today page.
3. Use the recommended next action at the top of the page.
4. Open the task with `Start task`.
5. Work through the task sections:
   - `Prepare`: check product, asset, caption, CTA, and hashtags.
   - `Post`: follow the platform steps, preview checklist, and common mistake warning.
   - `Finish`: mark posted, scheduled, needs help, or skipped.
   - `Metrics later`: record results only when they are due.
6. Use the copy buttons instead of manually selecting caption, CTA, or hashtags.
7. Return through `Metrics Due` when a posted task needs results recorded.
8. Use `Completed` to review finished or skipped work later.

## Roles

- `Matt`: Etsy, website, product, business, or owner-review work.
- `social operator`: Instagram and Facebook posting work.
- `either`: simple work that either person can complete.
- `blocked until owner input`: cannot move until Matt supplies the missing decision or account detail.

## Templates

Template source files live in:

- `docs/templates/platform`
- `docs/templates/copy`
- `docs/templates/graphics`

Restart the web app after editing template files so the database sync can refresh them.

Use `Posting Guides` for operator-facing platform help. It shows the same platform template knowledge in beginner language without source paths or JSON.

## Assets

Use Assets to review local product photos and generated graphics.

- Put local product photos under `assets/products`.
- Use `Scan local assets` to import image files.
- Use `Upload source photo` to copy a product photo into the local inventory without managing folders by hand.
- If a product photo is somewhere else on this computer, use `Register Source Photo` and paste the local file path.
- Each asset shows which tasks currently use it.
- Missing files and unreviewed assets appear in the asset list and Data Health.
- Readiness states should describe what the operator needs to know before using an asset.
- File checks track existence, modified time, and checksum so replaced files can be detected later.

Generated graphics should stay in `needs review` until a human approves them.

Set `MARKETING_OS_ASSETS_ROOT` before startup if the local product photo inventory should live somewhere other than `assets/products`.

## Creative Assets

Use Creative Assets after a real product source photo exists and has been approved.

The workflow is:

1. Add a product photo under `assets/products`.
2. Use Assets to scan local files.
3. Approve the source photo after checking product accuracy.
4. Open Creative Assets.
5. Review the planned outputs for:
   - Square Product Card
   - Reel Cover
   - Carousel Slide
6. Use `Prepare generation run` to create `needs review` asset records and a JSON manifest under `outputs/graphics/manifests`.
7. Use the manifest in the image-generation pass, or manually place image files at the planned output paths.
8. Return to Assets and approve only outputs that exist on disk and preserve product shape, color, printed details, and proportions.

Generated assets should not be used in normal tasks until approved.

After approval, open the relevant task, use `Change asset` in the `Prepare` section, and assign the approved file-backed asset.

## Metrics Due

Metrics are follow-up work. A task should not feel like it requires metrics before it has been posted.

Use `Metrics Due` to find posted tasks that need reach, likes, comments, shares, saves, Etsy visits/orders, email signup notes, or lessons learned.

Metrics Due separates `Post URL needed` from `Metrics needed`. Add the published post URL first when it is missing, then record the platform numbers.

## Data Health

Use Data Health to see upkeep work that can make the planner less trustworthy:

- stale imported products
- missing asset files
- unreviewed source or generated assets
- manual overrides that protect local edits from imports
- posted tasks waiting for metrics

## API Boundary

Phase 4 keeps the Flask/Jinja app, but the main operator workflows also expose JSON endpoints so a future frontend can reuse the same service logic:

- `GET /api/today`
- `GET /api/week`
- `GET /api/tasks/<task_id>`
- `GET /api/metrics-due`
- `GET /api/assets`
- `GET /api/data-health`
- `GET /api/creative-assets`
- `POST /api/tasks/<task_id>/finish`
- `POST /api/tasks/<task_id>/metrics`
- `POST /api/tasks/<task_id>/asset`

These endpoints are local-first and unauthenticated, like the rest of the app. Do not expose them to the public internet.

## Etsy CSV Import

Use Settings to import a local Etsy listing CSV export.

The CSV import is read-only/import-only. It can import listing title, listing ID, listing URL, and listing status into product records with sync metadata. It does not publish anything or change Etsy.

If a product has `manual_override_state` set to `locked` or `override`, imports keep the local product status and record a sync note instead of overwriting the local choice.

Useful CSV headers include:

- `Title`
- `Listing ID`
- `Listing URL`
- `Status`

## Backup And Export

Use Settings to create a timestamped SQLite backup under:

```text
data/backups
```

Use `Export JSON` to download a readable snapshot of products, plans, tasks, assets, metrics, templates, and sync metadata. Use the SQLite backup for full local recovery; use JSON export for review, portability, and future integration work.

The app remains local-first. Do not expose it to the public internet.
