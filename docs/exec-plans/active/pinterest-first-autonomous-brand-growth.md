# Pinterest-First Autonomous Brand Growth Reframe

## Status

- Status: in progress; Phases -1 through 2 completed, Phase 3 next, and live external capabilities remain gated by the capability matrix
- Owner: Matthew / Codex
- Branch: main (planning artifact only; implementation must use a new `codex/` branch)
- PR: Not applicable to this planning pass because this repository has no `origin` remote configured. Configure a remote before implementation and use PR review.
- Last updated: 2026-07-24
- Planning framework: Digi-CTO plugin `0.3.0`

## Outcome

Reframe Marketing OS from an operator-led social-post planner into the private control plane for a coverage-driven growth system:

```text
Catalog and market signals
        ↓
Opportunity and coverage graph
        ↓
Website content + Magnific assets + Pinterest campaigns
        ↓
MattMadeMe.com discovery and internal navigation
        ↓
Attributed Etsy clicks and sales
        ↓
Performance learning and next-best-action scoring
```

MattMadeMe.com becomes the public brand and content source of truth. Marketing OS remains the private orchestration, decision, audit, and review system. Etsy remains the fulfillment destination until a separate decision changes that boundary.

The first independently executable vertical slice should cover a deliberately bounded product cohort, one collection, two evergreen guides, approved Pinterest boards, hosted reconciliation and publishing, Pinterest/website/Etsy measurement, and a weekly exception digest. The cohort bounds validation risk; it is not a publishing quota. Expansion must follow evidence, not a fixed content count.

The permanent service keeps the existing Python/Flask control plane, moves production persistence from SQLite to PostgreSQL, executes schedules and integrations through durable background jobs, and requires authenticated operator or service access. The public Next.js website remains a separate deployment.

## Source Inputs

- Supplied `MattMadeMe Autonomous Brand Growth Strategy`, version 2.0
- Current `social-content` application, tests, skills, operating guides, and active execution plan
- Current MattMadeMe website at `/Users/mwood/Documents/Digicolony/websites/mattmade_me`
- Digi-CTO `0.3.0` readiness and handoff standards
- Skill/plugin inspection performed 2026-07-24

## Current-State Findings

### Useful foundations to preserve

- Flask, SQLAlchemy, and SQLite already provide a local control plane with products, plans, tasks, assets, generated candidates, creative jobs, metrics, and review states.
- Etsy integrations already import active listings, images, reviews, and idempotent sales CSV signals.
- Existing website adapters can read published blog metadata and create authenticated blog drafts.
- Content automation already exports deterministic copy/image handoffs and registers generated candidates.
- Magnific-oriented art direction and product-identity guardrails already exist.
- The website already has DynamoDB-backed products and blog content, authenticated agent read APIs, a blog-draft write API, product pages, metadata, basic Product schema, analytics hooks, and Etsy links.
- Seven repository-local skill directories are present:
  - `copywriter`
  - `social-media-strategist`
  - `social-media-copywriter`
  - `social-media-copy-chief`
  - `social-media-art-director`
  - `video-content-planner`
  - `video-editor`
- Digi-CTO `0.3.0` is installed and enabled through the `digicolony-team` marketplace.
- `python -m unittest tests.test_skills` passes two script-level tests covering `copywriter` and `social-media-art-director`. It does not yet prove that all seven skills, manifests, provider dependencies, or clean-device restoration work.

### Gaps against the strategy

- Planning is schedule/post oriented, not based on a durable product × intent × season × format × landing-page coverage model.
- No catalog monitor turns new, changed, or retired products into idempotent marketing jobs.
- Search demand, keyword opportunity, content coverage, and duplication are not first-class records.
- Website product writes, collections, gift guides, brand stories, and educational-content workflows are incomplete.
- Pinterest board management, scheduling, publication, deduplication, and performance ingestion are absent.
- Website analytics exist, but pin → landing page → internal navigation → Etsy click → order attribution is not a coherent contract.
- The current insights loop learns from manually entered task metrics; it cannot continuously score campaigns or landing pages.
- The weekly Codex workflow and manual Etsy sales CSV are useful scaffolding but do not satisfy the long-term low-touch autonomy requirement.
- The local-only runner depends on a powered-on Mac and has no durable queue, dead-letter handling, centralized alerting, or unattended recovery.
- The Flask console is currently designed for a trusted local network and cannot be exposed as a permanent hosted service until authentication, authorization, session/CSRF protection, and security logging are implemented.
- Several harness system-of-record docs still describe a generic starter instead of the implemented Marketing OS.
- The website Product JSON-LD includes hard-coded price, availability, size, and an expired `priceValidUntil`; these must come from verified product data or be omitted.
- Product URLs use numeric IDs. Stable slugs, redirects, canonical URLs, richer image/FAQ data, and collection/content relationships are needed for an SEO hub.

## Product and Architecture Decisions

1. **Coverage, not quota, drives work.** Do not generate or publish merely to hit a daily count.
2. **Separate public truth from private operations.** MattMadeMe.com owns published product/content truth; Marketing OS owns opportunities, jobs, evidence, experiments, and decisions.
3. **Use one canonical product identity.** Maintain stable `product_id`, website slug, Etsy listing ID, and source references; do not match by title once IDs are known.
4. **Treat website content as typed content.** Product pages, collections, gift guides, educational articles, and brand stories share reusable blocks and relationships but retain distinct page types and schema.
5. **Reuse Magnific.** Keep image generation behind the existing modular provider/job boundary and preserve product-identity QA.
6. **Progressive autonomy.** Start in shadow/draft mode, then enable auto-publishing per low-risk policy only after evidence gates pass.
7. **Every automated decision is explainable.** Persist inputs, score components, selected action, rejected alternatives, repository/skill/prompt/provider revisions, plugin version when applicable, and resulting outcome.
8. **Optimize for qualified traffic and conversion.** Followers are diagnostic only; primary measures are search coverage, outbound clicks, engaged website sessions, Etsy click-through, attributed orders/revenue, and marginal lift.
9. **Use event-driven triggers plus bounded sweeps.** Catalog changes enqueue work; daily and weekly sweeps repair missed events, refresh seasonal priorities, and learn from mature results.
10. **Never let optimization silently rewrite brand truth.** Product facts, pricing, claims, safety details, major brand changes, and new integrations retain explicit authority boundaries.
11. **Prove capabilities before committing architecture.** Pinterest access tiers/scopes, analytics/trend availability, Etsy attribution, website deployment, and the always-on runtime must pass an explicit discovery gate with fallbacks.
12. **Deliver a narrow vertical slice before broad domain or plugin extraction.** Prove one end-to-end cohort, then generalize.
13. **Keep Python/Flask for the private control plane.** Do not rewrite Marketing OS in Node merely to host it permanently; the Next.js website and Flask automation service remain separate systems with versioned contracts.
14. **Use PostgreSQL for hosted production persistence.** SQLite remains acceptable for lightweight local development and fixtures, but it is not the production source of truth after cutover.
15. **Run asynchronous work as durable jobs.** Schedules and external integrations must use persisted jobs with leasing, heartbeats, idempotency, bounded retries, dead-letter handling, and restart recovery; web requests must not own long-running work.
16. **Authenticate every privileged surface.** Except for a minimal health endpoint, hosted UI/API access requires an authenticated human or scoped service identity, explicit authorization, and an audit trail.

## Permanent Service Foundation

### Runtime topology

Deploy independently scalable processes from the same Python application package:

- `web`: Flask operator UI and authenticated API served by a production WSGI server;
- `worker`: claims and executes durable integration, generation, analytics, and maintenance jobs;
- `scheduler`: creates due jobs using leader election/advisory locking so only one schedule instance emits a job;
- `PostgreSQL`: production system of record for domain data, job state, leases, audit events, and schema versions;
- object storage: generated assets, manifests, and large immutable artifacts that do not belong in database rows.

The first slice should prefer a PostgreSQL-backed job implementation to avoid adding another stateful service. Phase -1 must select a maintained Python job library or approve an explicit SQLAlchemy job/lease contract. Add Redis or another broker only when measured concurrency, latency, or operational needs justify it.

### PostgreSQL migration contract

- Introduce Alembic or an equivalent reviewed migration system; production startup must not silently mutate schemas.
- Make connection configuration environment-based and require TLS for nonlocal database connections.
- Test supported behavior against PostgreSQL in integration/CI; SQLite-only tests cannot validate production locking, JSON, transaction, or concurrency behavior.
- Build an idempotent SQLite → PostgreSQL migration command with dry-run, preflight, row-count and relationship validation, deterministic ID preservation, and a migration report.
- Take and verify a restorable SQLite backup immediately before cutover.
- Stop writes during final migration unless an approved dual-write/reconciliation design exists.
- Retain the SQLite backup read-only through the rollback window; define the point after which PostgreSQL becomes authoritative.
- Document backup cadence, point-in-time recovery where supported, restore tests, retention, encryption, and database owner.

### Durable job contract

Every job records type, schema version, payload reference, priority, state, scheduled time, attempt count, maximum attempts, idempotency key, lease owner/expiry, heartbeat, correlation ID, result reference, last error, next retry, and created/updated/completed times.

Required behavior:

- atomic claim using a PostgreSQL-safe lease/locking mechanism;
- heartbeat and recovery of abandoned leases after worker termination;
- exponential backoff with jitter for transient failures;
- no automatic retry for validation, authorization, unsupported-operation, or policy failures;
- deterministic idempotency at both internal and external side-effect boundaries;
- `publish_unknown`/quarantine for ambiguous external writes;
- dead-letter inspection, replay, cancel, and resume operations with actor/reason audit;
- per-job timeouts, concurrency limits, provider rate limits, and cost guards;
- scheduler catch-up policy for restarts, time zones, daylight-saving changes, and expired seasonal work;
- graceful worker shutdown without losing or double-executing claimed work.

### Authentication and authorization contract

- Use a reviewed identity provider and OIDC/OAuth-based login or an equivalently strong private-access layer; do not build password storage unless an explicit decision requires it.
- Do not provide public self-registration.
- Define at least `viewer`, `operator`, `admin`, and `service` roles. Publishing-policy changes, secret/configuration changes, destructive operations, user/service management, and dead-letter replay require elevated permission.
- Use server-side sessions or short-lived signed tokens with secure, HTTP-only, same-site cookies where applicable, CSRF protection for state-changing browser requests, session expiry/revocation, and reauthentication for high-risk changes.
- Service-to-service credentials are scoped, separately revocable, rotated, stored in the approved secret manager, and never shared with browser sessions.
- Rate-limit login and sensitive API operations; record successful/failed authentication, authorization denial, policy change, external write, destructive action, and credential lifecycle events.
- Return minimal information from the unauthenticated health endpoint; place detailed health, queue, and dependency status behind authentication.
- Define account recovery, emergency access, access review, and incident revocation procedures before production.

## Target Domain Model

Add the following durable concepts, initially in Marketing OS:

| Entity | Purpose | Key lifecycle notes |
| --- | --- | --- |
| `ProductIdentity` | Maps Marketing OS, website, Etsy, and asset IDs | One active canonical mapping; redirects/history retained |
| `CatalogChange` | Records new, changed, retired, and failed-sync events | Idempotent by source revision/hash |
| `DemandEvidence` | Records query evidence, source, locale, scale, confidence, licensing, collected time, and expiry | Manual ideas are labeled hypotheses, never reported as measured demand |
| `SearchIntent` | Normalized query, audience, occasion, locale, season, and evidence | Version evidence and last-checked time |
| `LandingPage` | Product, collection, guide, article, or story target | Draft → approved → published → refresh/retired |
| `CoverageCell` | Sparse, observed/planned product/topic × intent × season × format × page × channel combination | Missing, planned, produced, published, stale, suppressed; expire/prune impossible or obsolete combinations |
| `PageOpportunity` | A scored need to create or improve a landing page | Can rank highly even when no page exists |
| `PublicationOpportunity` | A scored chance to publish or refresh channel content | Ineligible until the destination page passes readiness |
| `Campaign` | Groups related pages, assets, pins, boards, dates, and objective | Evergreen or bounded seasonal window |
| `CreativeVariant` | Product-safe image/copy variant with provenance and QA | Immutable source lineage; new revisions supersede |
| `Publication` | Exact Pinterest pin/board/URL/UTM/publish state | Idempotency key prevents duplicate publishing |
| `PerformanceSnapshot` | Time-windowed Pinterest, web, Etsy, and attribution metrics | Append-only snapshots at defined maturity windows |
| `Experiment` | Hypothesis, variants, allocation, guardrails, and result | No conclusion before minimum data/confidence rule |
| `DecisionRun` | Inputs, scoring, chosen actions, versions, and explanation | Append-only audit log |
| `AutomationJob` | Durable payload, schedule, priority, idempotency, lease, heartbeat, attempts, result/error, and retry state | Queued → leased/running → succeeded/failed/dead-letter/quarantined/cancelled |
| `AutomationRun` | Correlates one trigger/sweep with its child jobs, counts, cost, and outcome | Append-only operational summary |
| `Principal` | Human or service identity and authorized role bindings | Provisioned → active → revoked; no shared identities |
| `AuditEvent` | Authentication, authorization, policy, external-write, replay, destructive-action, and credential events | Append-only with actor, target, correlation ID, and timestamp |
| `PolicyException` | Human approval or override for higher-risk actions | Actor, reason, scope, expiry, and audit record required |

### Demand evidence ladder

Rank opportunity evidence in this order, subject to confirmed access and terms:

1. Eligible Pinterest query/trend evidence.
2. Pinterest Pin, board, audience, and outbound-click performance.
3. Google Search Console query, impression, click, position, and index data.
4. Privacy-safe website search/navigation and landing-page behavior.
5. Etsy listing/search evidence, reviews, sales, and recipient/use patterns.
6. Explicitly labeled manual hypotheses from strategy, product facts, or operator input.

Each evidence record includes source, query, locale, collection time, absolute or relative scale, confidence, permitted use, freshness/expiry, and raw-source reference. Low-confidence hypotheses may receive a bounded exploration allocation, but cannot silently outrank observed demand.

### Initial opportunity scoring contracts

Use an inspectable weighted score, calibrated later:

```text
page_opportunity =
  weighted(
    business_relevance,
    demand_evidence,
    seasonal_urgency,
    performance_prior,
    coverage_gap,
    internal_link_value
  )
  - duplication_penalty
  - data_quality_penalty

publication_opportunity =
  weighted(
    business_relevance,
    demand_evidence,
    seasonal_urgency,
    performance_prior,
    coverage_gap
  )
  - duplication_penalty
  - creative_fatigue
  - data_quality_penalty
```

Normalize all inputs to documented ranges, define missing-data defaults, confidence adjustment, score bounds, tie-breakers, and versioned weights. Page readiness is a hard publication eligibility gate, not a multiplier that suppresses missing-page creation. Seasonal opportunities include a target-ready date 60–90 days before the event where appropriate. The first release may use transparent proxies, but must not present them as exact search volume. Weight changes require versioning, historical replay, and bounded per-release change.

### Field-level truth ownership

Confirm this recommended matrix during Phase -1. Marketing OS stores provenance and operational copies but is not authoritative for published product truth.

| Field | Recommended authority | Conflict behavior |
| --- | --- | --- |
| Stable product ID and website slug | Website CMS mapping | Pause affected automation on ambiguity |
| Brand product name, description, material, dimensions, imagery | Human-approved website CMS | Website wins after revision validation |
| Etsy listing ID, price, availability, and fulfillment URL | Etsy read model | Mark stale/unknown; do not invent or retain expired claims |
| Product active/retired state | Human-approved website state reconciled with Etsy | Pause publication when sources materially disagree |
| SEO title/description, gift contexts, FAQs, collections, related content | Published website CMS | Marketing OS may propose revisions, not overwrite unseen edits |
| Brand, safety, popularity, and product-performance claims | Human-approved claim/policy record | Block when provenance or approval is absent |

The public website is the published projection, not automatically the origin of every field.

## Autonomous Control Loop

### Fast loop: event and failure response

- Trigger on catalog revisions, page publication, pin publication, API failures, and policy violations.
- Enqueue only affected coverage cells.
- Service targets after production graduation: ingest detectable events within 5 minutes, identify broken published destinations/tracking within 15 minutes, and pause the affected policy class immediately on identity, claim, duplicate-risk, or permission failure.
- Retry transient failures with exponential backoff and jitter.
- Stop in dead-letter state after a bounded attempt count and alert Matthew with the exact failed object and recovery action.
- Never retry validation, authentication, permission, or unsupported-content failures indefinitely.

### Daily loop: coverage and freshness

- Reconcile website and Etsy catalog identity.
- Detect missing or stale assets/pages/pins.
- Re-score high-urgency seasonal and catalog-change opportunities.
- Prepare or publish only work allowed by the current autonomy policy.
- Confirm published URLs, canonical tags, image availability, Pinterest IDs, and UTM contracts.

### Weekly learning loop

- Ingest Pinterest, website, and Etsy/attribution snapshots.
- Ingest Google Search Console index/query performance, branded-search evidence where available, privacy-safe new/returning traffic, and assisted Etsy-click cohorts.
- Compare performance by intent, page type, creative type, product, board, season, and cohort.
- Promote strong patterns while reserving a configurable exploration share for new intents and creative variants.
- Generate targeted refresh actions, not generic “make more content” tasks.
- Produce a one-screen exception and learning digest; do not require routine item-by-item approval.

### Performance maturity windows

- `1 hour`: publication/URL/asset health only
- `24 hours`: delivery and obvious tracking failures
- `7 days`: early diagnostics for saves, outbound clicks, engaged sessions; no evergreen suppression
- `30 days`: bounded copy/image/landing experiments when minimum evidence is met
- `90 days`: expand/suppress recommendations using documented uncertainty and seasonal context

Do not kill evergreen content based on early low volume. Separate technical failure, weak delivery, weak click-through, weak landing-page engagement, and weak Etsy conversion so the optimizer changes the correct layer.

### Experiment and optimizer safeguards

- Define the assignment unit before launch: Pin, creative variant, landing-page revision, or eligible audience/time cohort.
- Change one major factor per controlled experiment.
- Persist a control/holdout when the provider and traffic allow it; otherwise label results observational and do not claim causal lift.
- Define minimum impressions/clicks/conversions, fixed evaluation windows, late-data/backfill behavior, stop rules, seasonality treatment, cannibalization checks, and multiple-comparison handling per experiment class.
- Keep a fixed exploration share so early winners do not permanently crowd out new search coverage.
- Cap automatic score-weight movement per cycle and require replay/backtest before promoting a weight set.
- Never auto-delete Pins/pages, rewrite product truth, or promote a low-confidence hypothesis outside its exploration allocation.
- If required evidence is missing or delayed, retain the current policy and record `insufficient_evidence`; do not convert absence of data into a negative result.

## Authority and Human Involvement

| Action | Initial authority | Target authority after evidence |
| --- | --- | --- |
| Detect catalog/coverage gaps | Automatic | Automatic |
| Score and queue opportunities | Automatic | Automatic |
| Draft routine copy, images, metadata, and website pages | Automatic, review queue | Automatic within policy |
| Publish a routine pin to an approved board and existing page | Shadow mode, then sampled approval | Automatic |
| Refresh title/description/image variant | Draft-only until experiment safeguards pass | Automatic within bounded variants |
| Refresh metadata on an existing approved page | Draft-only | Automatic after a separate website-policy graduation |
| Refresh body copy on an existing approved page | Human approval | Sampled approval, then bounded automatic revisions |
| Draft a new page in an approved page type | Automatic draft | Automatic draft |
| Publish a new collection/guide in an approved page type/template | Human approval | Automatic within the graduated policy, with ongoing sampled QA |
| Publish a new product page/launch | Human approval | Human approval |
| Introduce a new page type | Human approval | Human approval |
| Change product facts, price, safety, claims, or brand positioning | Human approval | Human approval |
| Create a new integration, board taxonomy, page type, or campaign policy | Human approval | Human approval |
| Recover from repeated failure/dead-letter | Human attention | Human attention |
| Retire products/pages or delete assets | Human approval | Human approval |

Autonomy graduation criteria for a workflow:

- at least 20 successful shadow/draft runs or a human-approved smaller threshold;
- zero product-identity, unsupported-claim, broken-link, or duplicate-publication incidents in the evaluation window;
- idempotency/retry tests pass;
- rollback or unpublish procedure is documented and smoke-tested;
- sampled human QA meets the agreed pass rate;
- tracking completeness is at least 95% for required identifiers;
- Matthew explicitly enables that policy class.

Graduation is separate for Pin publication, metadata refresh, existing-page copy refresh, and approved-type collection/guide publication. Success in one class grants no authority in another.

Initial measurable operating targets, to confirm in Phase -1:

- at least 95% of happy-path runs complete without intervention;
- median routine human work below 30 minutes per week for the initial cohort;
- zero identity, unsupported-claim, broken-destination, or duplicate-publication incidents during the graduation window;
- at least 95% required tracking-ID completeness;
- routine queue age below 24 hours and seasonal-ready dates met;
- at least 95% sampled content/creative QA pass rate;
- actionable critical alerts delivered within 5 minutes and acknowledged within the agreed on-call window;
- generation/provider spend stays below the approved per-week and per-campaign ceilings;
- automatic pause on threshold breach, with the exact policy class and reason recorded.

## Website Workstream

Work in `/Users/mwood/Documents/Digicolony/websites/mattmade_me` on its own branch and PR. Do not couple deploys to Marketing OS releases.

### Content and URL foundation

- Add stable product slugs while retaining numeric-ID redirects.
- Define canonical URL, redirect, sitemap, and retirement rules.
- Expand the product contract for verified dimensions, materials, print information, FAQ, `why`, gift contexts, related collections/content, Pinterest assets, SEO title/description, availability, and source revision.
- Replace hard-coded Product JSON-LD values with verified fields; omit unknown values.
- Add valid Product, BreadcrumbList, CollectionPage, Article, and FAQPage schema where page content supports it.
- Add typed collection and editorial content models for gift guides, educational articles, and brand stories.
- Build collection, guide, article/story, and index templates with internal linking and Etsy conversion paths.

### Agent API foundation

- Version the agent API.
- Preserve current authenticated product/blog reads and blog-draft creation.
- Add least-privilege draft/upsert endpoints for product enrichment, collections, editorial pages, media attachments, and publish requests.
- Require revision tokens/idempotency keys to prevent overwrites and duplicates.
- Return validation errors, preview URLs, revision IDs, and publish state.
- Keep publishing separate from drafting; record actor and source provenance.
- Expand the OpenAPI document and add contract tests shared with Marketing OS.

### Analytics and attribution

- Generate one campaign/content/publication ID across pin URLs and website events.
- Use UTMs consistently and retain Pinterest pin/board IDs.
- Track landing, internal-navigation, collection/product views, and Etsy outbound clicks.
- Prefer a first-party Etsy outbound redirect/event endpoint so the click is logged before redirect.
- Define a privacy-safe order-attribution method using available Etsy order exports/API capabilities; mark unmatched orders explicitly.
- Add data-quality dashboards for missing IDs, bot traffic, duplicate events, and delayed imports.

## Marketing OS Workstream

### Control-plane refactor

- Add coverage, opportunity, campaign, publication, experiment, decision-run, and automation-run services without removing current plans/tasks until migration is proven.
- Make “Coverage” and “Exceptions” the primary operator surfaces; keep Today as a fallback queue.
- Replace fixed weekly platform mix logic with the opportunity scorer.
- Retain existing generated candidate review records as the first creative-variant implementation, then migrate deliberately.
- Add catalog reconciliation against website agent APIs and Etsy IDs.
- Add durable locks, idempotency keys, bounded retries, dead-letter records, and resumable checkpoints.

### Pinterest connector

- Implement provider interfaces for boards, pin create/update/read, scheduling, and analytics.
- Store external IDs and payload hashes before/after writes.
- Enforce fresh-image and duplicate-content rules through coverage/publication history.
- Support dry-run, shadow, sampled approval, and automatic policy modes.
- Validate destination URL, canonical page, image dimensions, alt text, board eligibility, and campaign timing before publish.
- Respect API rate limits and terms; exact credentials, account permissions, and API capabilities are blocking discovery items.
- Treat an ambiguous timeout/partial response as `publish_unknown`, not failed. Use a deterministic publication fingerprint, pre-write reconciliation, post-write lookup when supported, and quarantine/manual reconciliation when provider state cannot be proven.
- Confirm whether Pinterest or Marketing OS owns delayed publishing. If Marketing OS owns it, the hosted scheduler owns time zone/DST conversion, token freshness, missed/late-job policy, seasonal cutoff, and restart catch-up.

### Optimization

- Extend insights from task metrics to time-windowed cross-system snapshots.
- Report funnel stages separately: impression → save/outbound click → engaged landing → internal browse → Etsy click → order.
- Add controlled experiments for title, image, description, landing page, board, and timing; vary one major factor per experiment.
- Use confidence/minimum-data rules and persistent holdouts where feasible.
- Version score weights, prompts, templates, skills, and model/provider metadata.
- Provide “why this action” and “what would change the decision” on each opportunity.
- Report brand/search compounding separately: Search Console impressions/clicks/position/index coverage, branded queries when available, direct/return traffic where privacy-safe, and assisted Etsy-click cohorts. Keep follower counts diagnostic only.

## Skills and Private Marketplace Plan

### Audit result

- Seven expected repository skill directories and their instruction files are present.
- Two current script-level skill tests passed on 2026-07-24; full manifest, invocation, provider, and restore coverage is still required.
- The current skills are discoverable only because this repo is open; that is adequate for project-local work but weak for reuse, version pinning, and cross-device restoration.
- The strategy introduces capabilities that have never existed here; they should be built and tested, not described as restored.

### Recommended plugin boundary

After the bounded vertical slice proves the generic boundaries, create a versioned private-marketplace plugin tentatively named `digi-marketing`:

- Move/refactor generic parts of `copywriter`, the three social-copy skills, `social-media-art-director`, and the video skills into the plugin.
- Add reusable skills:
  - `content-coverage-planner`
  - `pinterest-search-strategist`
  - `pinterest-publisher`
  - `seo-content-architect`
  - `growth-analyst`
  - `experiment-optimizer`
  - `marketing-automation-operator`
- Keep MattMadeMe product facts, brand voice, banned claims, account IDs, URLs, policies, and business thresholds in this repo as a thin brand adapter/context pack.
- Keep provider-specific secrets and runtime credentials outside both repo and plugin.
- Use semantic versions, changelog, manifest validation, skill unit tests, clean-workspace smoke tests, and a reviewed marketplace snapshot before promotion.

Do not create a separate plugin for every skill. Split a future `digi-creative-studio` plugin only if Magnific image/video workflows develop an independent release cadence or serve non-marketing products.

### Machine restoration contract

Add during implementation:

- `config/required-capabilities.json` containing plugin name, minimum/approved version, required skill names, and whether repo fallback is allowed.
- `scripts/check-capabilities.sh` that exits non-zero for missing/invalid/incompatible skills and prints the reviewed restoration command.
- An installation/upgrade runbook for the DigiColony private marketplace.
- CI/automation preflight using the same capability check.
- A migration period where repo-local skills remain available until plugin parity and clean-machine validation pass.
- Manifest/schema validation, one invocation smoke test per required skill, separate Magnific/provider capability checks, and a clean-device install/restore test.

Never auto-upgrade production automation to an unreviewed plugin version. “Restore” may reinstall the pinned approved version automatically; “upgrade” requires review.

## Delivery Phases

### Phase -1 — Capability and authority gate

**Goal:** establish whether the required external contracts exist before committing the Phase 1+ architecture.

Discovery tests:

- Confirm Pinterest account/app access tier, OAuth/scopes, refresh-token behavior, approved boards, public Pin creation, read-after-write/reconciliation behavior, organic analytics fields/granularity/retention/lag, scheduling behavior, rate limits, and trend/query-data eligibility.
- Run non-destructive read tests and provider-approved sandbox/test writes; do not publish publicly from this phase unless Matthew explicitly approves the exact test.
- Confirm Etsy catalog/order/revenue/attribution paths, permissible uses, identifiers, and import delay.
- Confirm Google Search Console, website analytics, index coverage, event export, and retention access.
- Document website deployment, preview, secrets, DynamoDB backup/restore, rollback, and agent API ownership.
- Select and approve the always-on Python/Flask runtime, managed PostgreSQL service/version, PostgreSQL-backed job implementation, WSGI server, identity provider/private-access layer, alert destination, secret manager, cost ceilings, database backup/restore, and recovery model.
- Confirm database/network TLS, inbound access, service identity, deployment migration, worker scaling, and operational ownership constraints.
- Approve the field-level truth matrix, initial product cohort, one collection, two evergreen guides, boards, and human/autonomy policies.

Pass criteria:

- A capability matrix records `available`, `unavailable`, or `unknown` with evidence date, owner, tested operation, limitation, and fallback.
- A service-foundation ADR records the chosen hosting, PostgreSQL, durable-job, authentication/authorization, secret, backup, alert, and rollback contracts.
- Each unavailable capability has an explicit degraded mode:
  - no public Pin write → shadow/export workflow only;
  - no query/trend source → observed performance/Search Console plus labeled hypotheses and fixed exploration;
  - no Etsy order attribution → optimize verified upstream funnel stages and report order attribution as unknown;
  - no always-on runtime → do not enable unattended external writes;
  - no reliable reconciliation after ambiguous writes → keep publishing approval/manual reconciliation gated.
- Architecture decisions and cost/authority thresholds are updated from evidence.
- Phase 1+ remains blocked for any capability without a safe fallback.

Validation:

- Redacted capability test log and provider response fixtures
- Credential/permission failure tests
- PostgreSQL connectivity/locking proof, job lease/recovery spike, and identity-provider login/logout/revocation proof in a nonproduction environment
- Human approval of capability matrix and fallbacks

### Phase 0 — Baseline, contracts, and measurement

**Goal:** make current truth, IDs, authority, and metrics reliable before adding autonomy.

Implementation:

- Update `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/AUTOMATIONS.md`, `docs/VALIDATION.md`, and `docs/REPO_MAP.md` to match the actual Marketing OS.
- Configure an `origin` remote and create implementation branches/PRs.
- Add reviewed PostgreSQL configuration and schema migrations while preserving a local SQLite development/fixture path.
- Add the idempotent SQLite → PostgreSQL dry-run/migrate/verify/rollback workflow and record the production authority cutover rule.
- Add durable job, worker, scheduler, lease, heartbeat, retry, quarantine, dead-letter, replay, and graceful-shutdown foundations.
- Add authenticated Flask sessions/API access, role-based authorization, CSRF protection, service identities, audit events, session revocation, and security headers. Protect all routes except minimal liveness/readiness endpoints.
- Inventory website/Etsy/Marketing OS product IDs and repair ambiguous mappings.
- Define funnel events, campaign/content/publication IDs, UTM rules, metric windows, and baseline dashboard.
- Add the `DemandEvidence` contract and ingest at least one verified source; label manual topics as hypotheses.
- Capture the initial cohort baseline: current search/coverage inventory, Pinterest presence, website sessions/engagement, Etsy outbound CTR, attributable orders when available, and data-quality confidence.
- Repair website structured data and add tracked Etsy outbound clicks.
- Record Pinterest API/account access, analytics access, website deployment, secrets, and rollback facts.
- Add the required-capability manifest/check; preserve working repo skills.

Acceptance criteria:

- Every active product has an unambiguous identity mapping or a named exception.
- PostgreSQL migrations apply from empty and current schemas, migration dry-run/verification passes against a representative SQLite copy, rollback evidence exists, and production locking/concurrency tests run on PostgreSQL.
- A worker-kill/restart test recovers an abandoned lease without losing a job or creating a duplicate side effect; invalid/auth/policy failures do not retry; dead-letter replay is permissioned and audited.
- Anonymous users cannot access operator data or state-changing routes; each role/service identity can perform only its allowed actions; logout/revocation and CSRF tests pass.
- Required website and publication events have documented schemas and test fixtures.
- No invalid/hard-coded Product schema claim remains.
- The capability check passes on this machine and fails clearly in a clean missing-plugin fixture.
- Current-state docs no longer present the repo as a generic harness.

Validation:

- Marketing OS full unit suite and skill tests
- PostgreSQL migration, transaction, concurrency, backup/restore, and connection-failure integration tests
- Durable job claim/lease/heartbeat/retry/dead-letter/quarantine/replay/restart tests
- Authentication, role authorization, CSRF, session expiry/revocation, rate-limit, audit, and service-credential tests
- Website lint/typecheck/build and structured-data inspection
- Contract fixture tests for product and analytics IDs
- Human review of baseline funnel and source-of-truth decisions

### Phase 1 — Website hub MVP

**Goal:** make the bounded vertical-slice cohort a credible destination for initial Pinterest traffic.

Implementation:

- Add product slugs/canonical redirects and enriched product fields.
- Add collection and editorial content types/templates.
- Launch the one approved collection and two approved evergreen guides for the initial cohort.
- Add internal related-content/product links and Pinterest-ready `2:3` asset slots.
- Version and extend agent draft APIs with preview/publish separation.

Acceptance criteria:

- Selected pages answer buyer intent, expose verified product facts, link internally, and offer a tracked Etsy path.
- Sitemaps, canonical URLs, metadata, schema, OG/Pinterest images, and redirects validate.
- Marketing OS can read published revisions and create idempotent drafts without direct database access.
- Human approval remains required for the initial pages and page-type launch.

### Phase 2 — Coverage intelligence and catalog monitor

**Goal:** replace calendar-first planning with sparse, evidence-labeled next-best search opportunity planning for the initial cohort.

Implementation:

- Add the domain records and migrations.
- Seed a reviewed intent taxonomy from `DemandEvidence`, products, audiences, reviews, sales, collections, and labeled strategy hypotheses.
- Build catalog diff and coverage materialization jobs.
- Implement transparent opportunity scoring, freshness, suppression, and explanation.
- Add Coverage and Exceptions UI/API.

Acceptance criteria:

- New/updated/retired catalog fixtures create the correct idempotent jobs.
- A product coverage view shows what exists, what is missing, why it matters, and the next action.
- Duplicate or already-covered opportunities are penalized/suppressed.
- Page creation can rank when no page exists; publication cannot rank as eligible until page readiness passes.
- Seasonal fixtures honor the documented 60–90-day ready/publish lead window.
- Re-running unchanged inputs produces no duplicate jobs.

### Phase 3 — Pinterest production in shadow mode

**Goal:** produce complete, reviewable Pinterest campaigns without external writes.

Implementation:

- Generate page draft, pin title/description, board recommendation, UTM URL, and product-safe image variants from an opportunity.
- Extend Magnific manifests with coverage/campaign/publication provenance.
- Add policy and QA gates for identity, claims, crop, destination, duplication, season, and board.
- Generate a weekly exception/learning digest.

Acceptance criteria:

- At least 20 representative opportunities complete end to end in shadow mode.
- Every output traces to source facts, coverage cell, page revision, asset lineage, repository revision, skill/prompt/provider version, and decision run. Add plugin version after marketplace extraction.
- QA blocks unsupported claims, broken destinations, duplicate payloads, and identity drift.
- Human review time is measured and materially lower than the current item-by-item creation workflow.

### Phase 4 — Hosted, controlled Pinterest vertical slice

**Goal:** safely deliver the first low-touch end-to-end cohort before broad expansion.

Implementation:

- Deploy the authenticated Flask web process, PostgreSQL database, durable scheduler/workers, scoped service identities, secret handling, database backup/recovery, action-oriented alerts, and weekly exception digest before enabling unattended writes.
- Add authenticated Pinterest connector, rate-limit handling, idempotent publishing, reconciliation, and dead-letter recovery.
- Run sampled-approval mode, then graduate approved policy classes.
- Add publication health checks and rollback/unpublish runbook.
- Ingest Pinterest delivery/click metrics, website engagement/internal/Etsy-click events, Search Console signals, and the available Etsy attribution feed.
- Operate the initial cohort, one collection, two guides, and approved boards through the full loop.

Acceptance criteria:

- No duplicate is created in tested timeout, partial-response, restart, and retry scenarios using the confirmed provider contract; ambiguous state quarantines instead of retrying blindly.
- External IDs, payloads, URLs, and state reconcile after partial failure.
- Authenticated role boundaries, service credentials, audit events, PostgreSQL recovery, worker restart, scheduler leader locking, and dead-letter operations pass production-like smoke tests.
- Failed credentials/permissions stop safely and alert; transient failures retry boundedly.
- Autonomy graduation criteria pass and Matthew explicitly enables the first automatic policy.
- At least 95% happy-path runs complete without intervention, median routine human work is below the confirmed weekly target, tracking completeness is at least 95%, and cost/queue/QA/incident thresholds pass.
- Compare the cohort with its Phase 0 baseline and record coverage gained, qualified outbound clicks, engaged sessions, Etsy click-through, attributable outcomes when available, and what was learned about demand/creative/page performance.
- If the always-on runtime or safe publish reconciliation is unavailable, this phase remains shadow/sampled and cannot claim low-touch autonomy.

### Phase 5 — Closed-loop optimization and coverage expansion

**Goal:** let observed outcomes continually improve prioritization and variants.

Implementation:

- Ingest website and Etsy attribution snapshots.
- Add funnel diagnostics, experiments, exploration allocation, confidence rules, and weight versioning.
- Generate refresh/expand/suppress actions from mature evidence.
- Keep Marketing OS as the audit/operator console while the approved hosted workers execute jobs.
- Expand beyond the initial cohort only when Phase 4 operating targets pass and the business-learning gate shows either useful qualified-traffic/engagement/Etsy-click evidence or a documented `insufficient_evidence—continue bounded exploration` decision. A reliable but ineffective system does not scale automatically, and low-volume absence of conversions is not treated as failure.
- Extract and validate `digi-marketing` only after the vertical slice proves the generic/brand boundary.

Acceptance criteria:

- A pin/campaign can be followed through all observable funnel stages with explicit attribution quality.
- The optimizer can distinguish delivery, creative, landing-page, and conversion problems.
- A historical replay shows how changed weights would alter decisions.
- Routine successful runs require no review; humans receive only exceptions, strategic choices, new launches/integrations, and sampled QA.
- Recovery, rollback, alert ownership, secret rotation, backup, and restore are tested.
- Experiment results are causal only when assignment/control rules pass; otherwise they are explicitly observational.

### Phase 6 — Channel expansion

**Goal:** reuse the content/coverage ecosystem without redesigning it.

- Add channels one at a time through the same campaign, asset, publication, experiment, and performance contracts.
- Facebook/Instagram are likely next, but channel priority must be based on the measured opportunity and current business decision.
- Do not clone Pinterest cadence or copy shapes into feed-based channels.

## Phase Kickoff Prompts

Use only after the previous phase gate passes. Each phase gets its own execution plan, branch, PR, validation evidence, and human decisions.

### Phase -1

> Start Phase -1 of `docs/exec-plans/active/pinterest-first-autonomous-brand-growth.md`. Perform capability and authority discovery only. Use non-destructive reads and provider-approved test operations; do not make a public Pin or production content write without Matthew’s explicit approval. Produce the evidence-backed capability matrix, field-ownership decision, and service-foundation ADR covering hosted Flask, PostgreSQL, durable jobs, authentication/authorization, secrets, backup/recovery, alerts, costs, and fallbacks. Preserve unknowns.

### Phase 0

> Start Phase 0 only after the Phase -1 gate is approved. Implement and validate the permanent service foundation: PostgreSQL migrations and SQLite cutover tooling, durable workers/scheduler and recovery semantics, authenticated Flask UI/API, role/service authorization, CSRF/session security, and audit events. Then baseline IDs, contracts, measurement, capabilities, and system-of-record docs. Do not implement autonomous publishing.

### Phase 1

> Start Phase 1 for only the approved product cohort, one collection, and two evergreen guides. Implement stable URLs, typed website content, internal links, verified metadata/schema, tracked Etsy paths, and versioned draft APIs with preview/publish separation. Keep launch and initial publication human-approved.

### Phase 2

> Start Phase 2 for the approved cohort. Implement sparse coverage, `DemandEvidence`, catalog diffs, page/publication opportunities, explainable versioned scoring, seasonal lead times, and Coverage/Exceptions views. Use fake adapters and idempotency tests. Do not publish externally.

### Phase 3

> Start Phase 3 in shadow mode. Generate complete Pinterest campaign candidates with page revision, pin copy, approved-board recommendation, UTM URL, and product-safe Magnific assets. Persist provenance and QA decisions. Complete representative shadow runs and measure review effort; do not write to Pinterest.

### Phase 4

> Start Phase 4 only with the authenticated Flask service, PostgreSQL, durable scheduler/workers, service identities, secrets, backup/restore, alerts, provider contract, and reconciliation evidence approved. Implement the bounded hosted vertical slice in sampled mode, test ambiguous-response quarantine, worker/database recovery, and rollback, then request explicit graduation for the first Pin policy class. Do not infer authority from technical success.

### Phase 5

> Start Phase 5 after Phase 4 operating targets pass. Add evidence-maturity rules, safe experiments, replay/backtesting, bounded optimizer actions, and cohort expansion. Report causal versus observational findings accurately. Extract `digi-marketing` only after clean-machine plugin parity is proven.

### Phase 6

> Start Phase 6 only after Pinterest produces a stable measured loop and Matthew approves the next channel. Reuse canonical content, campaign, publication, experiment, and performance contracts while implementing channel-native strategy and authority rules.

## Files to Read First for Implementation

### Marketing OS

- `AGENTS.md`
- `README.md`
- `marketing_os/config.py`
- `marketing_os/db.py`
- `marketing_os/db_models.py`
- `marketing_os/web_app.py`
- `marketing_os/integrations.py`
- `marketing_os/services/content_briefs.py`
- `marketing_os/services/weekly_social_planner.py`
- `marketing_os/services/insights.py`
- `marketing_os/jobs/content_automation.py`
- `marketing_os/services/skill_adapters.py`
- `docs/operating-guides/codex-content-automation.md`
- `.agents/skills/`
- `tests/test_phase3.py`
- `tests/test_skills.py`

### MattMadeMe website

- `README.md`
- `lib/products.ts`
- `lib/blog.ts`
- `lib/agent.ts`
- `lib/analytics.ts`
- `app/product/[id]/page.tsx`
- `app/blog/[slug]/page.tsx`
- `app/api/agent/openapi/route.ts`
- `app/api/agent/products/`
- `app/api/agent/blog/`
- `app/components/TrackedLink.tsx`
- `next-sitemap.config.js`
- `infra/terraform/`

## Cross-Repository Delivery Rules

- Use one execution plan and PR per bounded phase/repository; link dependent PRs.
- Define API fixtures/contracts before either side implements an integration.
- Deploy backward-compatible website reads before Marketing OS depends on them.
- Add new write authority in draft-only mode before enabling publish.
- Preserve current `/art-studio` internal route contracts and existing candidate records until migrations are proven.
- Back up and verify SQLite and DynamoDB data before migrations; preserve the SQLite backup read-only through the PostgreSQL rollback window.
- Never commit credentials, customer/order exports, or raw analytics identifiers.

## Observability and Operations

Each automation run must expose:

- trigger and correlation ID;
- input revisions and data freshness;
- queued/started/succeeded/failed/dead-letter counts;
- duration and provider/API cost when available;
- retries and rate-limit state;
- PostgreSQL connection/pool/migration/replication or backup health as supported;
- worker/scheduler liveness, active/expired leases, queue age, dead letters, and job throughput;
- authentication failures, authorization denials, active/revoked sessions or service credentials, and privileged audit events;
- coverage cells changed;
- external writes and idempotency keys;
- policy/QA failures;
- tracking completeness;
- next retry or human action.

Alert only on actionable conditions: repeated failure, dead letter, credential/permission failure, broken published destination, tracking loss, duplicate-risk detection, material data drift, or policy violation. Summarize routine success weekly.

Before production, define the alert destination and named owner, severity and automatic policy-pause rules, deduplication window, delivery/acknowledgement targets, escalation after missed acknowledgement, quiet-hour behavior for noncritical alerts, and remediation/resume/incident-close evidence.

## Validation Strategy

### Automated

- Unit tests for normalization, scoring, coverage materialization, state transitions, and attribution.
- Property/idempotency tests for catalog events, job retries, publication retries, and draft upserts.
- Contract tests using versioned Marketing OS ↔ website and provider fixtures.
- Integration tests with fake Pinterest, website, analytics, and Etsy adapters.
- Historical replay/backtest for score and optimizer changes.
- Skill/plugin manifest, schema, prompt-contract, and clean-machine installation tests.
- One invocation smoke test for every required skill and separate provider/tool availability checks.
- Website lint, typecheck, build, sitemap, metadata, redirect, accessibility, and structured-data tests.
- Security tests for agent auth, replay, least privilege, secret absence, and write audit.
- Production-like authenticated Flask/PostgreSQL/worker/scheduler smoke tests after deployment.

### Human/live

- Owner: Matthew
- Validate Pinterest developer/account permissions and permitted analytics/publishing behavior.
- Approve canonical product/website ownership rules, initial keyword taxonomy, board taxonomy, and autonomy thresholds.
- Review the initial website page types and first campaigns.
- Enable each autonomy policy after reviewing shadow/sampled evidence.
- Expected evidence: linked dashboard/report, sampled outputs, incident count, tracking completeness, and signed policy decision in the phase plan/PR.
- Blocks merge: yes for live publishing, new page-type launch, new integration, and autonomy graduation; no for local fixtures and shadow-mode development.

## Blocking Questions

These block Phase 1+, not Phase -1 discovery:

1. What Pinterest business account/app access tier, OAuth/scopes, boards, analytics, query/trend data, reconciliation, scheduling, and public publishing capabilities are confirmed by tests?
2. Where is MattMadeMe.com deployed, and what are its CI, staging/preview, DynamoDB backup, and rollback procedures?
3. Does Matthew approve the proposed field-level authority matrix, including conflict-pause behavior?
4. What privacy/consent policy applies to analytics, email, click IDs, and order attribution?
5. Which Etsy data path can legally and reliably provide order-level attribution, and at what delay?
6. Which hosting environment, managed PostgreSQL service/version, Python durable-job implementation, WSGI server, identity provider/private-access layer, secret manager, and alert destination are approved?
7. What spend/API-cost limits should automatically pause generation or publishing?
8. What weekly human-time target, QA pass rate, recovery target, and incident-free window should confirm the proposed autonomy defaults?
9. Which products, collection, guides, and Pinterest boards form the initial vertical-slice cohort?

## Non-Blocking Questions

- Initial scoring weights and exploration percentage
- First collections/gift guides after baseline data review
- Exact dashboard visual design
- Whether creative/video skills eventually split into their own plugin
- Which post-Pinterest channel comes next

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Content volume outruns quality or search value | Coverage score, duplicate/fatigue penalties, page-readiness gate |
| Incorrect product likeness | Existing identity locks, source lineage, automated checks, sampled human QA |
| Bad AI claims or SEO spam | Source-backed fields, claim policy, page quality gate, no quota |
| Pinterest/API drift | Provider adapter, contract fixtures, capability discovery, bounded failure |
| Broken or duplicate external writes | Idempotency keys, reconciliation, payload hashes, dead-letter handling |
| False optimization from sparse data | Maturity windows, minimum data, uncertainty, exploration, holdouts |
| “Search opportunity” is only a plausible idea | `DemandEvidence` source ladder, confidence/expiry, fixed exploration, no unlabeled proxies |
| Etsy attribution remains incomplete | Track confidence and unmatched orders; optimize upstream metrics separately |
| Local Mac prevents reliable autonomy | Prove workflow locally, then require the approved always-on worker before unattended external writes |
| SQLite-to-PostgreSQL migration loses or changes data | Dry-run migration, deterministic IDs, row/relationship validation, verified backup, controlled write stop, rollback window |
| Worker crash duplicates or loses external work | Durable leases/heartbeats, internal and provider idempotency, ambiguous-write quarantine, restart tests |
| Hosted console exposes privileged data/actions | OIDC/private access, role/service authorization, secure sessions, CSRF, rate limits, audit, minimal public health |
| Plugin update breaks automation | Pinned approved versions, preflight, clean-machine tests, rollback |
| Cross-repo schema drift | Versioned API/OpenAPI and shared fixtures before dependent deployment |
| Existing dirty worktree causes accidental overwrite | New branches, narrow PRs, preserve unrelated changes, back up data |

## Definition of Done for the Full Reframe

- Coverage gaps, not arbitrary calendar quotas, drive routine work.
- New/changed products automatically enter the coverage lifecycle.
- MattMadeMe.com has reliable product, collection, guide, story/article, SEO, schema, internal-link, and tracked Etsy conversion contracts.
- Approved routine Pinterest campaigns can be created, published, reconciled, measured, and refreshed without item-by-item human labor.
- The feedback loop uses Pinterest, website, and Etsy evidence at appropriate maturity windows and records why it changed a decision.
- Humans handle strategy, launches, new integrations, major brand/product truth, dead letters, and sampled QA—not routine happy paths.
- Required skills/plugins are versioned, machine-checkable, restorable on a clean device, and distributed through the DigiColony private marketplace.
- Production state is stored in backed-up PostgreSQL with tested migrations and restore; SQLite is not the hosted production authority.
- Schedules and long-running integrations execute through durable, restart-safe jobs with inspected dead-letter and quarantine workflows.
- Hosted Flask UI/API surfaces require authenticated, least-privilege human or service identities with revocation and audit evidence.
- Automation, security, rollback, observability, cost limits, and human authority are documented and tested.
- Both repositories’ system-of-record docs match deployed behavior.

## Planning-Pass Validation Log

- `scripts/check-current-state.sh` — reported no `origin` remote; 2026-07-24.
- `python -m unittest tests.test_skills` — 2 script-level tests passed; this is not full seven-skill/provider validation; 2026-07-24.
- `codex plugin list` — Digi-CTO `0.3.0` installed/enabled; repository skills are locally discoverable; 2026-07-24.
- Read-only review of Marketing OS features, service boundaries, jobs, database records, automation guides, and current reviews; 2026-07-24.
- Read-only review of MattMadeMe website product/blog models, agent APIs, analytics hooks, sitemap surface, metadata, schema, and Git state; 2026-07-24.
- Sub-agent challenge round 1 — `FAIL`; strategy fit 8/10, low-touch automation 5/10, feedback/safe adaptation 5/10. P0/P1 revisions incorporated; 2026-07-24.
- Sub-agent challenge round 2 — `FAIL`; strategy fit 9/10, low-touch automation 8/10, feedback/safe adaptation 8.5/10. Remaining business-learning, website-autonomy, and pre-plugin provenance findings incorporated; 2026-07-24.
- Sub-agent challenge round 3 — `PASS`; strategy fit 9.5/10, low-touch automation 9/10, feedback/safe adaptation 9/10; no remaining P0/P1 blockers; 2026-07-24.
- Permanent-service decision added: retain Flask, move hosted production persistence to PostgreSQL, add durable jobs, and require authenticated/authorized access; 2026-07-24.
- Phase -1 completed: service-foundation ADR accepted, capability matrix recorded, live Etsy/website reads passed, Sheldon preflight passed, and PostgreSQL durable-job locking proved; 2026-07-24.
- Phase 0 completed: frozen PostgreSQL/Alembic schema, controlled SQLite cutover, durable scheduler/workers, hosted auth/authz, service identities, audit, container/backup operations, product identity and feedback contracts, baseline evidence, website Etsy-click tracking/structured-data repair, and current-state docs; 2026-07-24.
- Phase 1 completed: canonical product routes, one
  collection and two guides, typed idempotent editorial/blog drafts,
  content-complete catalog revisions, scoped read/write credentials, dedicated
  portrait metadata images, sitemap coverage, and automated Etsy-exit
  enforcement, plus an approved privacy-bounded attribution receiver and
  measurement-read contract; website commit `3166790`; 2026-07-24.
- Phase 1 final independent review — `PASS`; atomic attribution semantics,
  streamed payload limits, replay protection, bounded quotas, least-privilege
  credentials, strict serialization, and Marketing OS validation passed with no
  implementation blockers; 2026-07-24.
- Phase 2 completed: complete paginated website catalog and typed editorial
  reads; versioned coverage policy/taxonomy; PostgreSQL coverage, opportunity,
  decision, checkpoint, and outcome records; atomic catalog/outbox and
  measurement/cursor flows; identity transition repair; exact seasonal gates;
  ranked Coverage/Exceptions read surfaces; and 24-hour, 7-day, and 30-day
  observational feedback. Final independent review `PASS` at 9.5/10 for
  strategy, automation/idempotency, and feedback with no P0/P1 blockers;
  2026-07-24.

## Closeout

- Final planning status: implementation in progress.
- Phases -1 through 2 are complete; Phase 3 Pinterest production in shadow mode
  is next.
- Phase 0 website changes were committed separately as `fb92e37` on `codex/pinterest-growth-phase-0`.
- Phase 1 website changes were committed separately as `3166790` on
  `codex/pinterest-growth-phase-1`.
- Phase 2 uses separate scoped website and Marketing OS commits on
  `codex/pinterest-growth-phase-2`.
- lifeOS context was unavailable and did not inform the plan; no durable lifeOS update was identified.
