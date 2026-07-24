# Phase 0 Product Identity And Measurement Baseline

Measured 2026-07-24 using read-only MattMadeMe agent API data and a disposable copy of the local Marketing OS database.

## Product identity

| Measure | Result |
| --- | ---: |
| Marketing OS products | 72 |
| Public website products returned | 61 |
| Etsy-ID mappings | 58 |
| Mapping coverage | 80.6% |
| Explicit exceptions | 14 |

Exceptions are currently `no_website_product_with_matching_etsy_listing`:

- Product 2 — Captain Duck;
- Product 3 — Firefighter Duck Limited Edition;
- Product 13 — Room Steward Duck;
- Product 14 — Duck Keychain;
- Product 17 — Delivery Duck;
- Product 19 — Elks Lodge Duck;
- Product 22 — Florida Duck;
- Product 25 — Pennsylvania Duck;
- Product 26 — New York Duck;
- Product 34 — Texas Duck;
- Product 35 — Georgia Duck;
- Product 50 — Hatchling Duck;
- Product 52 — Delivery Duck (Blue Edition);
- Product 68 — Firefighter Duck.

These exceptions are safe exclusions. They are not automatically merged by similar name.

## Demand and funnel baseline

| Signal | Coverage/result | Confidence |
| --- | --- | --- |
| Verified Etsy sales rows | 3,182 rows; 4,738 units | High for imported source data |
| Etsy sales date range | 2025-03-14 through 2026-06-20 | High |
| Manual topic list | Available only as hypotheses | Low until provider/customer evidence |
| Website sessions | Not available to Marketing OS | Unknown |
| Website engagement | Not available to Marketing OS | Unknown |
| Etsy outbound CTR | Newly instrumented; no historical baseline | Unknown |
| Published-task metrics | 0 metric rows; 0 tasks with a published URL | No baseline |
| Pinterest organic analytics | Authorization unavailable | Unknown |
| End-to-end order attribution | Not implemented | Unknown |

## Interpretation

The Etsy sales import is a verified demand source and may rank already-known products, but it does not prove Pinterest search demand. The initial content and topic catalog remains hypothesis data until Pinterest Trends/search or another verified source is ingested.

The website now emits an `etsy_outbound_click` event from product-detail purchases with product ID and destination properties. Historical CTR cannot be reconstructed from this change. GA4 reporting credentials/property and a Marketing OS event receiver remain unavailable, so Phase 1 should use the event contract in shadow fixtures until those capabilities are authorized.

No automated growth decision may interpret missing sessions, CTR, Pinterest metrics, or delayed Etsy outcomes as zero performance.
