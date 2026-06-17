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

## Planning Intent

Use Planning when Matt or the social operator knows what marketing should happen but does not want to write final copy during planning.

The Planning page saves lightweight calendar intent:

- destination such as Facebook, Instagram, Pinterest, blog post, Etsy, website, or email
- goal such as sales growth, repeat customers, followers, product awareness, email signup, blog traffic, seasonal launch, or engagement
- one or more product focuses
- optional audience, occasion, promotion, and notes

Planned items start as `planned`. Use `Prepare candidates` to create review-only copy and image-prompt candidates immediately, or let the content-production job process them later.

Generated candidates start in `needs_review`. They are not posted automatically.

## Content Production Job

The first Phase 5 content-production job is scriptable and idempotent:

```bash
python -m marketing_os.jobs.content_production --limit 10
```

Useful test options:

```bash
python -m marketing_os.jobs.content_production --dry-run --limit 10
python -m marketing_os.jobs.content_production --planned-item-id 1
python -m marketing_os.jobs.content_production --channel facebook
```

The job finds planned items, builds structured briefs from business/product context, creates review candidates, and writes them back to Marketing OS. Rerunning the job does not duplicate existing candidates unless `--force` is used.

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

Phase 5 is expected to move the durable asset source to the external-drive asset library described in `docs/architecture/local-asset-library-agent-access-plan.md`. Until that is implemented, keep repo-local product photos treated as working data and out of git.

## Local Asset Library

Set `MARKETING_OS_ASSET_ROOT` to the stable external-drive or local asset-library root, such as `/Volumes/MarketingAssets`.

Use Settings -> `Scan asset library` to index files under that root. The scanner:

- indexes product, brand, campaign, video, template, and generated asset files
- stores relative path, role, MIME type, file size, dimensions, rights, brand-safety review state, and indexed timestamp
- generates image thumbnails under `_index/thumbnails`
- writes `_index/assets-manifest.json`
- keeps original files out of git

If the configured root is missing, Data Health shows `Local Asset Library` as needing attention.

## Creative Assets

Use Creative Assets after a real product source photo exists and has been approved.

The current workflow is:

1. Add a product photo under `assets/products`.
2. Use Assets to scan local files.
3. Approve the source photo after checking product accuracy.
4. Open Creative Assets.
5. Review the planned outputs for:
   - Square Product Card
   - Reel Cover
   - Carousel Slide
6. Use `Prepare generation run` to create `needs review` asset records and a JSON manifest under `outputs/graphics/manifests`.
7. Use the manifest in a higher-quality image-generation pass, or manually place image files at the planned output paths.
8. Return to Assets and approve only outputs that exist on disk and preserve product shape, color, printed details, and proportions.

Generated assets should not be used in normal tasks until approved. The first Phase 4 generated images did not meet the product-quality bar; use the Freepik/Magnific plan before treating this workflow as production-ready.

After approval, open the relevant task, use `Change asset` in the `Prepare` section, and assign the approved file-backed asset.

Use `Import Magnific / MCP Output` after generating or upscaling an image outside the app. The source asset must already be approved, the output file must exist locally, and the imported generated candidate starts in `needs review`. Review and approve it from Assets before assigning it to a task.

## Metrics Due

Metrics are follow-up work. A task should not feel like it requires metrics before it has been posted.

Use `Metrics Due` to find posted tasks that need reach, likes, comments, shares, saves, Etsy visits/orders, email signup notes, or lessons learned.

Metrics Due separates `Post URL needed` from `Metrics needed`. Add the published post URL first when it is missing, then record the platform numbers.

## Data Health

Use Data Health to see upkeep work that can make the planner less trustworthy:

- stale imported products
- Etsy and website sync status
- local asset-library mount/index status
- missing asset files
- unreviewed source or generated assets
- Magnific/MCP generation jobs waiting for review
- manual overrides that protect local edits from imports
- posted tasks waiting for metrics

## Phase 5 Readiness

Use Phase 5 Readiness to check the two final human-proof items before calling Phase 5 complete:

- Matt-approved Facebook copy with reviewer evidence
- Matt-approved generated creative with reviewer evidence and a file-backed candidate asset

The page can record the final copy and creative review directly, and it links to the underlying Planning and Creative Assets records for deeper inspection. When no generated creative job exists yet, it shows a recommended approved source asset and Magnific/MCP prompt handoff for the next generation pass, and it can open Creative Assets with the import form prefilled. It can export either a full Markdown approval packet or a focused creative handoff file.

The same check can run from the command line:

```bash
python -m marketing_os.jobs.phase5_readiness --export-markdown
python -m marketing_os.jobs.phase5_readiness --export-creative-handoff
```

Add `--fail-on-incomplete` only when using the command as a strict final gate.

## API Boundary

Phase 4 keeps the Flask/Jinja app, but the main operator workflows also expose JSON endpoints so a future frontend can reuse the same service logic:

- `GET /api/today`
- `GET /api/week`
- `GET /api/tasks/<task_id>`
- `GET /api/metrics-due`
- `GET /api/assets`
- `GET /api/data-health`
- `GET /api/phase5-readiness`
- `GET /api/phase5-approval-packet`
- `GET /api/creative-assets`
- `GET /api/planned-content`
- `POST /api/creative-assets/manual-import`
- `POST /api/tasks/<task_id>/finish`
- `POST /api/tasks/<task_id>/metrics`
- `POST /api/tasks/<task_id>/asset`
- `POST /api/planned-content`
- `POST /api/planned-content/<item_id>/produce`
- `POST /api/integrations/etsy/sync`
- `POST /api/integrations/website/sync`
- `POST /api/assets/library/scan`

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

## Read-Only API Syncs

Settings includes read-only sync actions for Etsy and MattMadeMe.com.

Etsy API sync imports active listings and listing images as external records. It requires local `.env` values for `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`, and `ETSY_SHOP_ID`.

MattMadeMe Website Sync imports website products, product images, and published blog metadata. It requires `MARKETING_AGENT_API_KEY`.

Both syncs are safe to run without credentials. Missing credentials are recorded in Data Health rather than blocking normal daily work.

## Backup And Export

Use Settings to create a timestamped SQLite backup under:

```text
data/backups
```

Use `Export JSON` to download a readable snapshot of products, plans, tasks, assets, metrics, templates, and sync metadata. Use the SQLite backup for full local recovery; use JSON export for review, portability, and future integration work.

The app remains local-first. Do not expose it to the public internet.
