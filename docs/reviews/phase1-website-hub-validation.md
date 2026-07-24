# Phase 1 Website Hub Validation

## Evidence-backed cohort

| Product | Website ID | Imported units | Identity |
| --- | ---: | ---: | --- |
| Mailman Duck | 1770148417697 | 1,120 | Website + Etsy mapped |
| EMT Duck | 36 | 266 | Website + Etsy mapped |
| Firefighter Duck | 1770148069202 | 260 | Website + Etsy mapped |
| 911 Dispatcher Duck | 9 | 168 | Website + Etsy mapped |
| Police Duck | 15 | 129 | Website + Etsy mapped |
| Mailwoman Duck | 1770148911584 | 61 | Website + Etsy mapped |

Counts were recomputed read-only on 2026-07-24 from `product_sales.quantity`;
the latest source import in the selected rows is 2026-06-20. Sales are verified
imported Etsy history, not Pinterest/Search demand proof. `Everyday Heroes`,
`mail carrier gifts`, and `first responder gifts` are bounded hypotheses until
Pinterest and Search Console evidence arrives. Weak traffic is not a negative
product-demand signal.

## Website checks

| Check | Result |
| --- | --- |
| `npm run build` | Passed |
| Generated application pages | 137 |
| Canonical product static paths | 61 |
| Legacy product route | HTTP 308 to current canonical slug |
| Canonical product route | HTTP 200 |
| Collection route | Built and rendered |
| Two guide routes | Built and rendered |
| `2:3` visual slot | Present |
| Dedicated route metadata images | 3 images, PNG 1000×1500 |
| Metadata image visual review | Passed for collection and both guides |
| All inventoried application Etsy exits tracked | AST enforcement passed for link, anchor, router, window, and location bypasses |
| Sitemap lifecycle | Corrected from `postBuild` to npm `postbuild` |
| Sitemap canonical hub/product URLs | Present |
| Sitemap broken static product dependency | Removed |
| Robots exclusions | `/api`, `/cart`, `/store`, `/thank-you` preserved |
| Product structured data | Canonical URL and verified optional facts only |

## Contract checks

- v1 agent routes remain available.
- v2 product and draft routes compile in the Next.js production build.
- OpenAPI version and v2 paths are published by the existing agent OpenAPI endpoint.
- Nine Marketing OS adapter contract tests pass.
- Twenty-seven website contract/privacy/security tests pass.
- Concurrent identical blog requests return two successes and one stored draft
  in the injected DynamoDB route test.
- Same-key/different-payload and different-key/same-slug tests return 409.
- Equivalent concurrent/conflict tests pass for typed editorial drafts.
- v2 blog and typed editorial draft writes require a 16–128 character
  idempotency key and persist only draft/preview results.
- Malformed product snapshots preserve the adapter’s last valid revision.
- Product revisions cover the normalized public contract and ignore ordering.
- Loopback scope smoke: read-on-write 403; write-on-read 403; authorized invalid
  draft payload 400 before any database write.
- Measurement scope smoke: catalog-read-on-measurement 403;
  measurement-on-catalog 403; valid measurement credential reaches the
  intentionally unconfigured local receiver and returns 503 without a write.
- Same-origin approved receiver route test persists the bounded payload and
  returns 202; cross-origin requests return 403 before persistence.
- Receiver normalization tests prove 400-day TTL, Etsy-only destinations,
  invalid identifier/path removal, and exclusion of unapproved fields.
- Attribution merge tests prove identifiers survive same-session navigation,
  preserve the current touch’s landing pathname across untagged navigation, and
  reject unapproved/malformed query fields.
- A second tagged landing atomically replaces the whole prior tuple and landing
  path, preventing mixed-touch attribution.
- Receiver tests prove replay deduplication, 4 KiB enforcement without trusting
  `Content-Length`, same-origin rejection, transaction-based address/global
  quotas, and deterministic client event keys.
- The measurement read-route test proves cursor pagination and removal of raw
  table-only or accidental fields; the Marketing OS adapter rejects unknown
  response fields.
- Terraform formatting and configuration validation pass for the dedicated
  growth-event table.
- No live draft or public website write was performed during validation.

## Deployment gate

The code is not deployed. Human preview/approval of the first collection and
guide page type, normal website branch review, and the existing website
deployment/rollback process remain required before these routes become public.
The first-party receiver, exact payload, and 400-day retention were explicitly
approved on 2026-07-24. Production Terraform apply, three scoped production key
rotations, branch review, and initial page publication remain deployment/release
gates rather than unfinished implementation.

Final independent review passed on 2026-07-24 with no Phase 1 implementation
blockers. The website implementation is committed as `3166790`.
