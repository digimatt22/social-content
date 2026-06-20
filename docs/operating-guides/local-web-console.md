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

Generated candidates start in `needs_review`. They are not posted automatically. For Facebook post candidates, review the generated draft, edit the post copy if needed, then approve, reject, or request a rewrite. Approved edited copy is what flows into the posting task.

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
python -m marketing_os.jobs.content_production --days-ahead 14
python -m marketing_os.jobs.content_production --export-briefs-dir data/exports/content-briefs
```

The job finds planned items, builds structured briefs from business/product context, creates review candidates, and writes them back to Marketing OS. Use `--export-briefs-dir` when Codex or another model-assisted worker needs a file handoff before or during generation. Brief filenames are stable by planned item ID, so rerunning the job updates the handoff instead of creating duplicate files. Rerunning the job does not duplicate existing candidates unless `--force` is used. Candidates marked `rewrite_requested` are picked up by the normal job and refreshed back into `needs_review`; exported briefs include the rewrite notes and prior copy so the next pass can address the critique.

For a local manual or Codex-managed run, use the wrapper script:

```bash
./scripts/run-content-production.sh
```

The wrapper writes structured briefs to `data/exports/content-briefs`, appends job output to `data/logs/content-production.log`, and defaults to planned items due within the next 14 days. Override the window with `MARKETING_OS_CONTENT_DAYS_AHEAD`. If a Codex automation runs this flow, keep generated copy and creative in `needs_review`; the automation should never approve, post, or mark Phase 5 complete.

## Assets

Use Assets to review local product photos and generated graphics.

- Managed product image files live under `assets/products/` by default. Generated and planning image outputs live under `outputs/`.
- Use `Upload source photo` to copy a product photo into the managed image library.
- Use `Scan local assets` to rescan managed image files.
- Remote listing images selected in Planning are downloaded into the managed image library before generation.
- Each asset shows which tasks currently use it.
- Missing files and unreviewed assets appear in the asset list and Data Health.
- Readiness states should describe what the operator needs to know before using an asset.
- File checks track existence, modified time, and checksum so replaced files can be detected later.

Generated graphics should stay in `needs review` until a human approves them.

Override `MARKETING_OS_ASSETS_ROOT`, `MARKETING_OS_GENERATED_OUTPUT_ROOT`, or `MARKETING_OS_PLANNING_UPLOAD_ROOT` only if the managed image folders should live somewhere other than the repo-local ignored folders.

Phase 5 added the local asset-library index. The original implementation plan is archived at `docs/archive/2026-06-17-phase5-implementation/architecture/local-asset-library-agent-access-plan.md`; use the Local Asset Library workflow below as the active operator guidance.

## Local Asset Library

Set `MARKETING_OS_ASSET_ROOT` to the local asset-library root, usually `assets`.

Use Settings -> `Scan asset library` to index files under that root. The scanner:

- indexes product, brand, campaign, video, template, and generated asset files
- stores relative path, role, MIME type, file size, dimensions, rights, brand-safety review state, and indexed timestamp
- generates image thumbnails under `_index/thumbnails`
- writes `_index/assets-manifest.json`
- keeps original files out of git

If the configured root is missing, Data Health shows `Local Asset Library` as needing attention.

## Assets And Planning Images

Use Assets to manage local image records. Use Planning to choose which product images should support a specific post or image-generation job.

The current workflow is:

1. Upload a product source photo in Assets.
2. Use Assets to scan managed local files when needed.
3. Approve the source photo after checking product accuracy.
4. Open Planning when creating a post.
5. Select at least one source image for the planned post.
6. If the selected image is a remote Etsy or website reference, Planning downloads it into the managed image library before queueing generation.
7. Keep generated options attached to the planned post until Matt reviews the final choice.

Generated assets should not be used in normal tasks until approved. When reviewing generated creative, compare the source and generated previews side by side. Approve only if product shape, colors, printed details, and proportions match the source, no new markings/logos/text/packaging were invented, the composition fits the target format, and the local output file is usable.

## Metrics Due

Metrics are follow-up work. A task should not feel like it requires metrics before it has been posted.

Use `Metrics Due` to find posted tasks that need reach, likes, comments, shares, saves, Etsy visits/orders, email signup notes, or lessons learned.

Metrics Due separates `Post URL needed` from `Metrics needed`. Add the published post URL first when it is missing, then record the platform numbers.

## Data Health

Use Data Health to see upkeep work that can make the planner less trustworthy:

- stale imported products
- Etsy sync status
- local asset-library mount/index status
- missing asset files
- unreviewed source or generated assets
- Magnific/MCP generation jobs waiting for review
- manual overrides that protect local edits from imports
- posted tasks waiting for metrics

## Phase 5 Status

Phase 5 is closed as historical implementation work. Use Planning and Products as the current starting points for the next operating goal and plan.

## API Boundary

Phase 4 keeps the Flask/Jinja app, but the main operator workflows also expose JSON endpoints so a future frontend can reuse the same service logic:

- `GET /api/today`
- `GET /api/week`
- `GET /api/tasks/<task_id>`
- `GET /api/metrics-due`
- `GET /api/assets`
- `GET /api/data-health`
- `GET /api/planned-content`
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

The CSV import is read-only/import-only. It can import listing title, listing ID, and listing URL into product records with sync metadata. It does not publish anything or change Etsy.

Useful CSV headers include:

- `Title`
- `Listing ID`
- `Listing URL`

## Read-Only API Syncs

Settings includes read-only sync actions for Etsy and MattMadeMe.com.

Etsy API sync imports active listings and listing images as external records. It requires local `.env` values for `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`, and `ETSY_SHOP_ID`.

MattMadeMe website product import is intentionally disabled. Etsy is the product source of truth. The website adapter is reserved for reviewed blog draft publishing and published blog metadata.

Both syncs are safe to run without credentials. Missing credentials are recorded in Data Health rather than blocking normal daily work.

## Planning Image Generation

Planning queues image generation until real files exist. See `docs/operating-guides/codex-image-generation.md` for the adapter contract, and `docs/operating-guides/codex-content-automation.md` for the scheduled Codex automation setup.

## Export

Use Settings to download a readable JSON export. Choose a scope such as full snapshot, products and images, plans and tasks, metrics and insights, or templates.

The app remains local-first. Do not expose it to the public internet.
