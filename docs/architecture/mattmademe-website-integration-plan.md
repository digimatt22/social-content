# MattMadeMe Website Integration Plan

This document is a Phase 4 reference for adding MattMadeMe.com as an authenticated product, image, published blog, and draft blog source for the MattMadeMe Marketing OS.

## Goal

Use the MattMadeMe website API to reduce manual product upkeep and let the Marketing OS create CMS-reviewable draft blog posts without publishing directly.

The integration should answer:

- What products are currently available on MattMadeMe.com?
- Which product descriptions, tags, categories, sizes, and marketing notes are safe to use for planning?
- Which product photos and lifestyle images are already available from the website?
- Which product URLs should tasks, blog ideas, and metrics refer to?
- Which published blog posts already exist, so new content does not duplicate prior work?
- Which draft blog posts has the Marketing OS created for human CMS review?

The first implementation should import or sync website product and blog data into local SQLite and make it visible in the operator/admin UI. Blog draft creation is allowed only as an explicit human-triggered action that creates a draft for CMS review. It must not publish, update, delete, or otherwise mutate public website content.

## Write Boundary

Treat MattMadeMe.com as a trusted source of product and published blog truth, plus a narrow draft target.

Allowed:

- `GET` requests for products and published blog posts.
- `POST` requests only to create draft blog posts at the documented draft endpoint.
- Storing external IDs, URLs, timestamps, image metadata, related product IDs, draft slugs, and sync status locally.
- Showing imported data in Data Health, Products, Assets, Tasks, Blog Ideas, and Metrics Due workflows.
- Creating a draft blog post only after an operator reviews the generated headline, excerpt, body, tags, CTA, sources, and related products.

Not allowed:

- `PUT`, `PATCH`, or `DELETE` requests to MattMadeMe.com.
- Automated publication of blog posts.
- Automated edits to existing published posts or drafts.
- Treating a created draft as approved, published, or ready to promote.
- Using imported website data to overwrite local human edits without showing review/override state.
- Storing, logging, printing, or committing the API token.

Code-level guardrails should make unsafe operations hard to add accidentally. The website adapter should expose read methods plus one clearly named draft creation method, tests should assert that only the documented methods and endpoints are used, and draft creation should require an explicit service call from an operator-facing review flow.

## Credentials And Local Configuration

MattMadeMe.com uses bearer-token authentication for the agent API. Local credentials should live in `.env`, which is ignored by git. The repository should keep `.env.example` with empty variable names only.

Initial variables:

```text
MARKETING_AGENT_API_KEY=
MATTMADEME_AGENT_API_BASE_URL=https://mattmademe.com
```

The API token is sensitive. Do not print it in terminal output, write it to logs, include it in exceptions, save it to generated docs, or share it in chat. Error messages should say the token is missing or invalid without echoing any token value.

## Website API Surface

The API manifest is available at:

```text
https://mattmademe.com/.well-known/ai-plugin.json
```

The OpenAPI document is available at:

```text
https://mattmademe.com/api/agent/openapi
```

Useful endpoints:

| Purpose | Endpoint | Operation | Auth |
| --- | --- | --- | --- |
| Read marketing-safe products | `GET /api/agent/products` | `listMarketingProducts` | Bearer token |
| Read one marketing-safe product | `GET /api/agent/products/{id}` | `getMarketingProduct` | Bearer token |
| Read published blog posts | `GET /api/agent/blog` | `listPublishedBlogPosts` | Bearer token |
| Create a CMS-review draft blog post | `POST /api/agent/blog-drafts` | `createBlogDraft` | Bearer token |

Recommended first pass:

1. Load `MARKETING_AGENT_API_KEY` from local environment configuration.
2. Fetch products through `listMarketingProducts`.
3. Fetch published blog posts through `listPublishedBlogPosts`.
4. Store products, product images, product URLs, published blog metadata, and sync state locally.
5. Show imported website records in Data Health before planner output depends on them.
6. Add draft creation only after the local review UI exists.

## Data We Want

Product identity:

- website product ID
- product name
- subtitle
- product URL
- Etsy URL
- MakerWorld URL
- status
- category

Planning and merchandising:

- description
- why/story field
- material
- tags
- perfect-for audiences or occasions
- sizes
- size dimensions
- product status

Images and assets:

- hero image URL
- image URLs
- lifestyle image URL
- local external asset record linkage
- local thumbnail/cache path if downloaded later
- image freshness and availability state

Published blog context:

- website blog post ID
- slug
- headline
- excerpt
- published date
- updated date
- author
- category
- tags
- reading time
- SEO description
- cover image
- canonical URL

Draft blog output:

- local draft request ID
- generated headline
- slug returned by website
- preview admin URL returned by website
- related product IDs
- CTA label and URL
- sources
- created timestamp
- review state
- sync or submit status
- submission error, if any

Freshness:

- local `last_synced_at`
- local `sync_status`
- local `sync_error`
- remote `updatedAt` for blog posts when present
- product/image stale state when imported data disappears or changes

## How To Make It Useful

Products:

- Match website products to local product records by website product ID first, then product URL, then normalized product name as a review-only suggestion.
- Show website URL, category, tags, status, and last website sync on product/admin screens.
- Flag local products that do not appear in the website product feed.
- Flag website products that have no local product mapping.
- Prefer website product descriptions and image URLs over manually stale docs only after human review confirms the mapping.

Tasks:

- Add canonical website product URLs to website, blog, and cross-channel promotion tasks.
- Use website product names, descriptions, audiences, and image availability as planning inputs.
- Surface status warnings before an operator promotes a stale, unmapped, or unavailable product.
- Use product tags and perfect-for fields as planning hints, not mandatory copy.

Assets:

- Create external asset records for website product images.
- Show website thumbnails in asset inventory and task pages.
- Keep remote image URL and local cache status separate.
- Treat website images as source/reference assets unless a human marks them ready for a specific marketing use.

Blog planning:

- Use published blog posts to avoid duplicate article ideas.
- Suggest internal links to existing relevant blog posts when drafting new posts.
- Track which products already have related blog coverage.
- Keep draft blog requests and website-returned preview URLs visible in a review queue.

Metrics and data health:

- Show `last_synced_at` and stale status in Data Health.
- Warn when website sync fails or credentials are missing.
- Keep daily operator workflows usable when website sync is unavailable.
- Track post URLs and blog draft preview URLs separately from published URLs.

Creative generation:

- Allow approved website product images to become source images for generated social graphics.
- Preserve source product ID and image URL in generated asset metadata.
- Never assume generated assets are approved just because their source image came from the website.

## Suggested Local Data Model

Add or reuse fields that support any external source, with MattMadeMe.com as another adapter:

- `external_source` such as `mattmademe_website`
- `external_id` such as product ID, blog post ID, or draft slug
- `external_parent_id` for image-to-product relationships
- `external_url`
- `external_state`
- `external_updated_at`
- `last_synced_at`
- `sync_status`
- `sync_error`
- `manual_override`
- `review_state`
- `raw_external_data` for selected JSON snapshots if useful

For website-specific records, keep the local model useful without hard-coding every API field into first-class columns. Promote only the fields the UI and planner need frequently.

Blog draft submissions may also need:

- `draft_preview_admin_url`
- `draft_slug`
- `draft_submitted_at`
- `draft_submission_status`
- `draft_submission_error`
- `draft_related_product_ids`

## Adapter Shape

Create a MattMadeMe website adapter behind a service boundary:

```text
marketing_os/integrations/mattmademe_website.py
```

Suggested methods:

- `list_products()`
- `get_product(product_id)`
- `list_published_blog_posts()`
- `create_blog_draft(draft_request)`

Suggested services:

```text
marketing_os/services/mattmademe_website_import.py
marketing_os/services/blog_draft_submission.py
```

Import service responsibilities:

- read environment configuration
- call website read endpoints
- normalize API responses into local DTOs
- upsert import records without overwriting manual overrides
- create/update external asset records for images
- record sync status and errors
- expose summaries for Data Health

Draft submission service responsibilities:

- accept only locally reviewed draft data
- validate required `headline` and `body`
- include related product IDs, tags, CTA, cover image, SEO description, and sources when available
- submit to `createBlogDraft`
- store the returned slug and preview admin URL
- keep submitted drafts in a review/pending state until a human marks them published or discarded

Routes and templates should call services, not the raw adapter.

## Phased Implementation

### Phase A - Authenticated Read Import

- Add configuration loading for `MARKETING_AGENT_API_KEY` and optional `MATTMADEME_AGENT_API_BASE_URL`.
- Implement bearer-token `GET` adapter methods.
- Import products via `listMarketingProducts`.
- Import published blog metadata via `listPublishedBlogPosts`.
- Store external IDs, URLs, image metadata, blog metadata, and sync state.
- Show imported website records in Data Health.

### Phase B - Product And Asset Mapping

- Add admin review UI to match website products to local products.
- Suggest matches by website product ID, URL, and normalized name but require human confirmation.
- Show website product URLs and thumbnails on tasks.
- Warn when a task references an unmapped or stale product.

### Phase C - Blog Context And Draft Review

- Use published blog metadata to inform blog idea generation.
- Show related existing posts when creating a new blog idea.
- Add a local draft review screen with headline, excerpt, body, tags, CTA, sources, cover image, and related products.
- Keep draft creation disabled until the operator explicitly submits a reviewed draft.

### Phase D - CMS Draft Submission

- Implement `createBlogDraft` as the only allowed website write action.
- Store the returned slug and preview admin URL.
- Mark submitted drafts as awaiting CMS review.
- Do not mark drafts as published until a human records the published URL or a later read endpoint confirms publication.

## Failure States

Handle these as normal, visible states:

- missing `MARKETING_AGENT_API_KEY`
- invalid bearer token
- network timeout
- API manifest unavailable
- OpenAPI document unavailable
- product removed or unavailable
- image URL unavailable
- published blog feed unavailable
- draft payload rejected
- draft submission succeeds but returned preview URL is missing
- local mapping conflict
- local manual override blocks an automatic update

Failures should not block Today, This Week, existing tasks, local planning, or manual blog drafting.

## Acceptance Criteria

- Real credentials are kept out of git, logs, terminal output, and chat.
- The adapter exposes read methods plus only one clearly named draft creation method.
- Product and published blog sync can run with the bearer token from local environment configuration.
- Every imported record has source, external ID, external URL where available, and last sync status.
- Imported data is visible in Data Health before it influences planner output.
- Product matching requires review before overwriting local assumptions.
- Tasks can display canonical website URLs and thumbnails from imported records.
- Blog draft creation requires explicit human review and submit action.
- Created draft responses store slug and preview admin URL without treating the draft as published.
- Unsafe HTTP methods are absent from configuration, tests, and adapter code.
