# Asset Workshop (Marketing OS primary goal)

## Status
- Status: ready for review
- Owner: Matthew / Codex
- Branch: codex/gallery-bulk-needs-review
- PR: (open with this change)
- Last updated: 2026-09-29 (Gallery bulk needs-review approve/reject)

Allowed statuses: planned, in progress, blocked, needs human validation, ready for review, completed, abandoned.

## Summary
- Lock **asset workshop** as the active product goal for Marketing OS.
- Why: humans and agents need one place to **find** product truth + reference photos and **make** social-ready assets for review. Brand Lab / grok desks own posting (pins, IG/FB/X drafts). This app owns catalog ↔ files ↔ generate ↔ review.
- Out of scope for this plan file: deploy, Brand Lab, video, background Etsy, mattmademe.com site desk. Earlier build-order items shipped in #11–#18; this PR adds Gallery bulk needs-review.

## Job (for now)
Marketing OS is the **asset workshop**:
- Find product truth and reference photos.
- Make social-ready assets for human/agent review.
- Boundary: not the public site desk; not Brand Lab posting desks. Pinterest growth remains historical/parked for day-to-day primary focus (see park list).

## Two loops

### 1. Find
Product → default refs → gallery/library → Etsy remote source photos → prior generated assets by platform / ratio / review state.

Etsy sync is **supporting infra** for find (product + https refs), not the product.

### 2. Make
Product + refs + platform/aspect → queue → Magnific worker drain → outputs → needs review → approve/reject.

## Actors
- **Human UI:** products, gallery, art studio (social images / video surfaces).
- **Agents via APIs:** `/api/assets`, `/api/art-studio/jobs`, `POST /api/art-studio/social-images/queue`, `POST /api/assets/<id>/review`, `POST /api/assets/review` (bulk), product APIs.
- **Worker:** `art_studio.social_image.generate` when `MAGNIFIC_API_KEY` is set (hosted REST drain on Sheldon).
- Agents must **not** invent parallel filesystem truth; use Marketing OS catalog + asset records.

## Asset states
1. Remote Etsy reference
2. Local source (`file_exists`)
3. Queued / generating
4. Imported / needs review
5. Approved / rejected

Default reference assets lock generation inputs.

## Park / demote (do not delete)
Keep code and old plans; demote as primary day-to-day focus:
- Coverage intelligence — **demoted from primary nav** into More tools; routes/APIs remain; **parked for primary investment**
- Pinterest Shadow — **demoted from primary nav** into More tools; routes/APIs remain; **parked for primary investment**
- Live Pinterest publish
- Website-as-product source of truth
- Weekly planner / metrics as primary nav

Old plan kept and marked parked for primary focus:
- `docs/exec-plans/active/pinterest-first-autonomous-brand-growth.md`

## Build order
1. **Done:** Magnific API drain (live on Sheldon). Per-platform aspect ratios (#11).
2. **Done:** Findability — Gallery filters + agent asset list APIs (PR #12).
3. **Done:** Make UX — multi-platform queue progress on Products/Art Studio; Gallery needs-review social grouping (#13).
4. **Done:** Local refs → Magnific-reachable (Upload Files API staging) (#14).
5. **Done (this PR):** Nav focus — Coverage / Pinterest Shadow moved under More tools so Products, Gallery, Art Studio dominate primary chrome.
6. **Later:** background Etsy sync; video on same pattern; Magnific webhook verify.
7. **Done (this PR):** Agent make-loop JSON APIs — `POST /api/art-studio/social-images/queue` + `POST /api/assets/<id>/review` (write Bearer); HTML forms unchanged.

**Primary build-order loop (items 1–5) complete.** Item 7 (agent make-loop APIs) shipped in #17. **Follow-on (this PR):** Gallery bulk needs-review on #13 groups — multi-select + group Approve all / Reject all (`POST /assets/review/bulk`) and optional agent `POST /api/assets/review`. Remaining parked track is item 6+.

## Success
An agent or human can: resolve product → list refs → enqueue e.g. IG 4:5 + Stories 9:16 → wait for reviewable files → approve — without leaving Marketing OS and without a bot babysitting Magnific.

## Boundary
- Not mattmademe.com site desk.
- Not Brand Lab content desks (pins, IG/FB/X drafts/posting).
- Pinterest growth plan is **not** the primary active goal for day-to-day product work.

## Work State
- Planned: later items (background Etsy sync; video pattern; Magnific webhook verify).
- In progress: none.
- Ready for review: Gallery bulk needs-review (`codex/gallery-bulk-needs-review`).
- Completed earlier: products find parity (#18); agent make-loop JSON APIs (#17); nav focus (#15); strategy lock; Magnific REST drain; per-platform aspect ratios (#11); findability (#12); make UX (#13); local refs staging (#14).
- Blocked: none.
- Needs human validation: on Gallery after deploy — open needs-review strip, multi-select Approve/Reject selected, and group Approve all / Reject all.
- Completed: Magnific REST social-image drain on Sheldon (`art_studio.social_image.generate`); primary build-order items 1–5.

## Decisions
- Asset workshop is the active strategy source in `docs/PROJECT_CONTEXT.md`.
- Pinterest-first plan stays in `active/` but is parked/superseded for primary focus.
- Hosted worker uses Magnific **REST** (`MAGNIFIC_API_KEY`); Magnific **MCP** remains the interactive assistant path — do not conflate.
- Production hostname: `mmm.digicolony.net`.

## Implementation
### Gallery bulk needs-review (this PR)
- Gallery make-loop strip (#13 groups): checkboxes + Approve/Reject selected; per-group Approve all / Reject all.
- `POST /assets/review/bulk` wraps `review_assets` → `review_asset` (CSRF on secure browser forms).
- Optional agent bulk: `POST /api/assets/review` (`asset_ids` + `review_state`) matching #17 review shape.
- Tests: `tests/test_gallery_bulk_needs_review.py`.
- Docs: `docs/AUTOMATIONS.md`, `docs/operating-guides/local-web-console.md`, this plan.

### Agent make-loop APIs (follow-on)
- `POST /api/art-studio/social-images/queue` wraps `enqueue_product_social_image_jobs` / `enqueue_social_image_generation` (product default refs × platforms × option_count).
- `POST /api/assets/<id>/review` wraps `review_asset`.
- Auth: write-scoped Bearer service credential on secure app; CSRF skipped for service auth.
- Docs: `docs/AUTOMATIONS.md`, `docs/operating-guides/local-web-console.md`.
- Tests: `tests/test_agent_make_loop_apis.py`.

Nav focus (prior PR):
- `marketing_os/templates/base.html` — remove Coverage and Pinterest Shadow from primary Workflow list; place them first under More tools; auto-open overflow when `active` is coverage/shadow
- Routes/blueprints unchanged (`/coverage`, `/shadow-campaigns`, APIs)
- `tests/test_nav_focus.py` — asserts primary chrome excludes those labels and overflow still links them; routes return 200
- Docs: this plan (item 5 done; primary loop 1–5 complete; Coverage/Shadow remain parked for primary investment)

Out of scope: deleting Coverage/Shadow code, deploy, Brand Lab, video, background Etsy.

## Validation
- `python -m unittest tests.test_nav_focus`
- `scripts/check-current-state.sh --remote` before PR
- Date checked: 2026-09-25

## Human Validation
- Owner: Matthew
- Exact steps: After merge/deploy, open Marketing OS chrome — confirm Coverage and Pinterest Shadow are only under More tools; Products/Gallery/Art Studio remain primary; deep links `/coverage` and `/shadow-campaigns` still work.
- Expected evidence: PR merged; chrome matches intent on hosted app.
- Evidence location: this plan + PR.
- Blocks merge: No (template demotion + unit test; routes preserved).

## Documentation
- Same-change updates listed under Implementation.
- After later implementation phases complete, move or split follow-on plans; keep this file as the durable strategy lock until superseded.

## Open questions
- (Resolved) Agent list filters: `GET /api/assets` query params + optional `GET /api/products/<id>/assets`.
- (Resolved) Products find parity: `/products` `q`+`tag` (Gallery-style) + `GET /api/products` catalog (`id`, `name`, `sync_status`, `default_ref_count`, `tags`; `q`/`tag`/`page`/`sort`).
- (Resolved) Local-ref Magnific reachability: Magnific Upload Files API (`POST /v1/ai/uploads/request-url` → PUT → `asset_url`). Persist `file_id`+checksum in `SyncMetadata` (`magnific_upload_asset_<id>`); refresh via `GET /v1/ai/uploads` on retry. Etsy https refs unchanged.
- When (if ever) to resume Pinterest growth as a primary track after asset-workshop loops are solid.

## Closeout
- Final status: TBD until merge of nav-focus PR.
- Follow-up: later items only (background Etsy sync; video; Magnific webhook verify) — separate PRs. Coverage/Shadow stay parked for primary investment.
