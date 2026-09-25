# Asset Workshop (Marketing OS primary goal)

## Status
- Status: in progress
- Owner: Matthew / Codex
- Branch: docs/asset-workshop-strategy
- PR: https://github.com/digimatt22/social-content/pull/10
- Last updated: 2026-09-25 (findability shipped in PR)

Allowed statuses: planned, in progress, blocked, needs human validation, ready for review, completed, abandoned.

## Summary
- Lock **asset workshop** as the active product goal for Marketing OS.
- Why: humans and agents need one place to **find** product truth + reference photos and **make** social-ready assets for review. Brand Lab / grok desks own posting (pins, IG/FB/X drafts). This app owns catalog ↔ files ↔ generate ↔ review.
- Out of scope for this plan file: code, deploy, aspect-ratio implementation (separate PR), nav-hide code, mattmademe.com site desk, Brand Lab content desks.

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
- **Agents via APIs:** `/api/assets`, `/api/art-studio/jobs`, product APIs, queue endpoints.
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
- Coverage intelligence surfaces as primary nav
- Pinterest Shadow as primary nav
- Live Pinterest publish
- Website-as-product source of truth
- Weekly planner / metrics as primary nav

Old plan kept and marked parked for primary focus:
- `docs/exec-plans/active/pinterest-first-autonomous-brand-growth.md`

## Build order
1. **Done:** Magnific API drain (live on Sheldon). **In flight:** per-platform aspect ratios.
2. **Done (this PR):** Findability — Gallery filters (product, type, review, platform, aspect, name search); `GET /api/assets` + `GET /api/products/<id>/assets` query params (`product_id`, `asset_type`, `review_state`, `platform`, `aspect_ratio`, `q`); stable agent JSON includes id/product_id/name/asset_type/review_state/source_path/canonical_url/file_exists/platform/aspect_ratio when known from linked generation jobs.
3. **Make UX:** multi-platform queue; worker progress visible.
4. **Local refs:** make local files Magnific-reachable (https/upload).
5. **Nav focus:** image-asset primary; park coverage/shadow behind more.
6. **Later:** background Etsy sync; video on same pattern; Magnific webhook verify.

## Success
An agent or human can: resolve product → list refs → enqueue e.g. IG 4:5 + Stories 9:16 → wait for reviewable files → approve — without leaving Marketing OS and without a bot babysitting Magnific.

## Boundary
- Not mattmademe.com site desk.
- Not Brand Lab content desks (pins, IG/FB/X drafts/posting).
- Pinterest growth plan is **not** the primary active goal for day-to-day product work.

## Work State
- Planned: make UX, local refs, nav focus, later items above.
- In progress: none for findability (PR opened).
- Completed earlier: strategy lock; per-platform aspect ratios (#11); findability filters + agent list API (this PR).
- Blocked: none.
- Needs human validation: smoke Gallery filters on hosted/local; confirm agent list shape.
- Ready for review: findability PR.
- Completed: Magnific REST social-image drain on Sheldon (`art_studio.social_image.generate`).

## Decisions
- Asset workshop is the active strategy source in `docs/PROJECT_CONTEXT.md`.
- Pinterest-first plan stays in `active/` but is parked/superseded for primary focus.
- Hosted worker uses Magnific **REST** (`MAGNIFIC_API_KEY`); Magnific **MCP** remains the interactive assistant path — do not conflate.
- Production hostname: `mmm.digicolony.net`.

## Implementation
Docs-only in this change:
- NEW `docs/exec-plans/active/asset-workshop.md`
- UPDATE `docs/PROJECT_CONTEXT.md` strategy + Magnific capability line
- Park note on pinterest-first plan header
- Light README Current Scope pointer

No code, deploy, aspect-ratio, or nav-hide work in this PR.

## Validation
- Docs-only; `scripts/check-current-state.sh --remote` before PR.
- Link sanity for new strategy path from PROJECT_CONTEXT / README.
- Date checked: 2026-09-25

## Human Validation
- Owner: Matthew
- Exact steps: Confirm strategy wording matches approved chat; merge docs PR.
- Expected evidence: PR merged; PROJECT_CONTEXT Strategy source points at this plan.
- Evidence location: this plan + PR.
- Blocks merge: No (Matthew already approved writing strategy into docs).

## Documentation
- Same-change updates listed under Implementation.
- After later implementation phases complete, move or split follow-on plans; keep this file as the durable strategy lock until superseded.

## Open questions
- (Resolved) Agent list filters: `GET /api/assets` query params + optional `GET /api/products/<id>/assets`.
- Preferred path for local-ref Magnific reachability (upload vs temporary https).
- When (if ever) to resume Pinterest growth as a primary track after asset-workshop loops are solid.

## Closeout
- Final status: TBD until merge.
- Follow-up: make UX → local refs → nav focus → later items (separate PRs).
