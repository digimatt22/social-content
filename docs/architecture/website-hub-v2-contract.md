# Website Hub And Agent API v2 Contract

## Cohort

Phase 1 uses one bounded `Everyday Heroes` cohort. Products require a public website record and verified Etsy identity mapping. Delivery Duck remains excluded because its public website record has no Etsy destination.

## Canonical public routes

- Product: `/products/<name-slug>-<website-id>`
- Legacy product: `/product/<website-id>` returns a permanent redirect
- Collection: `/collections/everyday-heroes`
- Guides:
  - `/guides/mail-carrier-gifts`
  - `/guides/first-responder-gifts`

The numeric suffix keeps product resolution stable when names change. A stale name slug permanently redirects to the current canonical path.

## Page facts and tracking

Pages render only current public product fields. Changing purchase facts remain on Etsy. Product schema omits unknown price, availability, validity, material, or size rather than inventing fallbacks.

Every currently inventoried Etsy exit in application components uses
`TrackedLink` and emits
`etsy_outbound_click` with destination and placement source; product exits also
include product ID. Automated AST coverage rejects raw anchors, normal/self-closing
`Link` elements, router navigation, `window.open`, and location assignment when
their destination is recognizably Etsy-derived. Code review remains responsible
for unusually indirect or newly named navigation abstractions.

Campaign/content/publication/Pin identifiers are retained in session storage and
treated as an atomic last-touch tuple: a later tagged landing replaces the
entire prior tuple and its landing path, preventing cross-campaign mixing. The
tuple is delivered only to the explicitly approved same-origin growth receiver. GA
receives pathname-only pageviews, and Vercel/GA do not receive the retained
identifiers.

Every collection/guide page contains a `2:3` visual slot, verified product
links, tracked Etsy exits, related editorial links, canonical metadata, and
CollectionPage/Article structured data. Each route also generates a dedicated
1000×1500 Open Graph/Pinterest image with meaningful route-specific alt text.

## Agent API compatibility

Existing v1 paths remain:

- `GET /api/agent/products`
- `POST /api/agent/blog-drafts`

Phase 1 adds:

- `GET /api/agent/v2/products`
  - response `contractVersion=v2`;
  - SHA-256 content revision;
  - canonical product URL/path;
  - published/public products only.
- `POST /api/agent/v2/blog-drafts`
  - requires a 16–128 character `Idempotency-Key`;
  - creates `status=draft` only;
  - returns the existing result for the same key and canonical request;
  - rejects one key reused with different content;
  - returns the admin preview location;
  - has no publish operation.
- `POST /api/agent/v2/editorial-drafts`
  - accepts typed `collection` or `guide` records;
  - creates or optimistically updates a draft;
  - returns a specific admin-only preview URL and content revision;
  - uses the same transactional idempotency rules;
  - has no publish operation.
- `GET /api/agent/v2/growth-events`
  - requires the separate `measurement:read` credential;
  - returns ordered, cursor-based Etsy-exit events;
  - exposes only the approved non-PII record;
  - is the sole Marketing OS interface to the website event table.

Blog idempotency uses an atomic DynamoDB transaction for the public slug and a
separate marker record. Collision reads are strongly consistent. Simultaneous
identical requests therefore return one stored draft and two HTTP 200 results;
same-key/different-payload and different-key/same-slug requests return 409.

## Credentials

- Catalog reads use `MARKETING_AGENT_READ_API_KEYS`.
- Draft writes, including the compatibility v1 route, use
  `MARKETING_AGENT_DRAFT_API_KEYS`.
- Measurement reads use `MARKETING_AGENT_MEASUREMENT_API_KEYS`.
- Read credentials receive 403 on draft routes and draft credentials receive
  403 on read routes.
- Either environment variable can carry current and next comma-separated keys
  during a rotation overlap.
- The old shared key is honored only when neither scoped variable exists.

Draft credentials do not authorize publish or CMS/admin operations. Measurement
credentials cannot read catalog data or create drafts.

## First-party measurement record

Same-origin `POST /api/growth-events` accepts only `etsy_outbound_click` events
whose destination hostname is Etsy. It persists campaign/content/publication/Pin
identifiers, UTM campaign/content, landing and click pathnames, product ID,
placement source, Etsy hostname, client occurrence time, and server ingestion
time. Full queries, cookies, personal information, and full destination URLs are
not accepted or stored. DynamoDB TTL removes records after 400 days.

Admission requires an edge-owned, overwritten client-address header and a
server-side hashing secret; the raw address is never stored. Each event carries
a UUID and bounded client timestamp used as a durable replay key. One DynamoDB
transaction enforces the replay condition, a 250-event per-address daily limit,
and a 10,000-event global daily limit. Requests are capped at 4 KiB independent
of `Content-Length`, and the table has a 100 read/write request-unit on-demand
ceiling.

The measurement read route serializes an explicit approved-field allowlist
rather than returning raw DynamoDB items. Marketing OS independently rejects any
unknown field or malformed ID/timestamp/key relationship.

Marketing OS integrates through `MattMadeMeAgentApiAdapter`; it never reads or writes DynamoDB directly.

## Authority

Code review and build completion do not authorize production deployment or publication. The first collection/guide page type and any generated draft require human preview before deployment/publish.
