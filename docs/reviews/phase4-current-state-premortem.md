# Phase 4 Current-State Premortem

Date: 2026-06-17

## Bottom Line

Phase 4 improved the app mechanics and the operator workflow, but it should not be treated as fully product-complete.

The UI/UX work is directionally complete enough to build on: Today, task detail, This Week, Metrics Due, Assets, Data Health, and JSON service boundaries now exist. The risky parts are adoption, data upkeep, and creative quality. The generated images proved the workflow boundary, but the output quality was not good enough. Future implementation should keep the current Python stack for now, add integrations through adapters, and avoid a rewrite until real usage shows that Flask/Jinja is blocking velocity or experience.

## Was Phase 4 Complete?

Mechanically, mostly yes:

- Operator-first Today page exists.
- Task pages are guided into prepare/post/finish/metrics sections.
- Navigation separates daily work from admin/setup.
- Metrics Due and Completed views exist.
- Asset inventory can upload, scan, register, preview, review, and assign file-backed assets.
- Data Health, backup, export, and JSON API boundaries exist.
- Integration-ready fields and CSV/import foundations exist.

Product-value-wise, no:

- Creative output quality is below the bar.
- The system still needs manual data upkeep.
- No real Etsy API sync exists yet.
- No MattMadeMe website API sync exists yet.
- Local asset library access is still only a repo-local asset folder, not the planned external-drive index.
- The UI has not yet been validated by a real operator session after the Phase 4 changes.

## Tech Stack Review

Keep Python/Flask/SQLAlchemy/SQLite for Phase 5.

Reasons:

- The system is local-first and workflow-heavy, not yet a public SaaS app.
- The planning logic, data model, tests, and local persistence are already in Python.
- Phase 4 added service/view-model boundaries and JSON endpoints that reduce future migration risk.
- The next bottleneck is not frontend technology; it is trustworthy data and production-quality assets.

Do not rewrite in Next.js yet.

Reasons:

- A rewrite would delay Etsy, website, asset-library, and creative-provider integration.
- The current app can support the next validation pass with less risk.
- A future Next.js frontend can consume the JSON endpoints if richer interactivity becomes necessary.

Triggers that would justify Next.js later:

- The operator UI needs complex client-side state, drag/drop planning, or rich asset review interactions that become awkward in Jinja.
- The app needs authenticated multi-user remote access.
- The JSON API becomes stable and the Flask templates become the main source of UX drag.
- UI iteration speed becomes materially slower than backend/integration work.

## How The System Fails From Here

### 1. Manual Data Upkeep Makes The App Feel Like Chores

Failure mode:

The planner keeps asking the operator to update products, URLs, asset paths, and metrics by hand. After a few missed updates, the app feels stale and stops being trusted.

Mitigation:

- Implement read-only Etsy sync.
- Implement MattMadeMe website product/blog sync.
- Add Data Health alerts that point to one action, not a vague maintenance list.
- Keep manual overrides visible so imports do not erase local decisions.

Useful connections:

- Etsy listings and images.
- MattMadeMe products, product images, and published blog posts.
- MattMadeMe draft blog creation after review.
- Local asset library scan/index.
- Freepik/Magnific generated-output import.
- Later: Instagram/Facebook metrics, Google Analytics, Google Search Console, email platform, MakerWorld, backup status.

### 2. Creative Output Is Technically Valid But Not Usable

Failure mode:

The app can make image files, but they look amateur or distort the product. Operators learn not to trust the creative workflow.

Mitigation:

- Treat Phase 4 generation as a proof of workflow only.
- Use Freepik/Magnific as the next creative backend.
- Start with manual/MCP generation import if REST API work is slower.
- Require source asset approval and generated output review.
- Add rejection reasons and keep rejected outputs out of ready states.

### 3. Asset Storage Drifts Between Repo, Local Folders, And Generated Outputs

Failure mode:

Photos end up scattered across the repo, downloads, platform exports, and generated folders. The app shows paths that no longer exist or files no one should use.

Mitigation:

- Move to the external-drive asset-library plan.
- Keep original files out of git.
- Index the asset root and generate thumbnails.
- Add Data Health checks for missing asset root, stale index, missing approved product image, duplicate hashes, and generated outputs without sources.

### 4. Integrations Become One-Offs

Failure mode:

Etsy, website, assets, and Magnific each get custom code paths, making later changes hard and increasing rewrite pressure.

Mitigation:

- Use adapter/service boundaries.
- Normalize external records into source-agnostic fields.
- Keep raw provider responses as metadata, not planner assumptions.
- Write tests that assert read-only/write-boundary behavior.

### 5. UI Improvements Do Not Convert Into Habit

Failure mode:

The app is better organized, but still not faster than memory, platform apps, and ad hoc notes.

Mitigation:

- Run one real operator walkthrough.
- Watch for the first place the operator hesitates.
- Reduce setup/admin noise on daily pages.
- Make Data Health actionable and batched.
- Improve copy buttons, asset previews, and missing-data warnings where observed.

### 6. Local-First Safety Is Incomplete

Failure mode:

The app works until the local database or asset drive fails, then trust collapses.

Mitigation:

- Keep SQLite backup/export.
- Add external asset backup guidance to Data Health.
- Keep generated outputs and source photos out of git.
- Document restore expectations.

## Current Non-Use Friction List

- Product truth must still be maintained manually.
- Etsy listing URLs and states are not automatically synced.
- Website product/image/blog data is not automatically synced.
- Metrics are still manually entered.
- Asset approval requires local file organization discipline.
- Generated image quality is not good enough.
- Data Health can become a guilt wall if it is not tied to specific actions.
- Setup/admin pages can still distract from daily execution.
- Local network app has no auth and should not be exposed publicly.

## Next Goal Input

Phase 5 should focus on integration and creative quality:

- Etsy read-only sync.
- MattMadeMe website product/blog sync and reviewed draft creation path.
- Local external-drive asset library and index.
- Freepik/Magnific creative generation/upscale path with human review.
- UI/UX validation against real operator use.
- Cleanup of executed phase docs so future work reads the current goal first.

