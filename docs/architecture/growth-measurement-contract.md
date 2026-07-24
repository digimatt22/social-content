# Growth Identity And Measurement Contract

## Purpose

This contract connects Pinterest demand, MattMadeMe landing activity, Etsy exits, and later orders without treating delayed or missing data as poor performance.

## Durable identifiers

Every publishable content unit must carry:

| Identifier | Meaning | Persistence |
| --- | --- | --- |
| `campaign_id` | Stable strategic campaign/cohort | Job payload, destination URL, event |
| `content_id` | Stable creative/content candidate | Job payload, destination URL, event |
| `publication_id` | Platform publication or shadow-export attempt | Job result, destination URL, event |
| `product_id` | Marketing OS product ID | Product identity map and event |
| `event_id` | Source event deduplication key | Unique `growth_events.event_id` |

Pinterest landing URLs use `utm_source=pinterest`, `utm_medium=organic_social`, `utm_campaign=<campaign_id>`, `utm_content=<content_id>`, and `publication_id=<publication_id>`. Missing durable IDs are a validation failure, not an invitation to publish with partial attribution.

## Product identity

`product_identities` maps a Marketing OS product to its website ID/route and Etsy listing ID. Automated publication may reference only `mapping_state=mapped` products. Every other active product appears in an exception report with a reason.

The Etsy listing ID is the cross-system match key during Phase 0. Names are not authoritative because titles and presentation copy change independently.

## Events

`growth_events` stores deduplicated events with both `source_timestamp` and `ingested_at`.

Initial event types:

- `landing_view`;
- `etsy_outbound_click`;
- `etsy_order_attributed`;
- `pin_impression`;
- `pin_engagement`;
- `pin_save`;
- `pin_outbound_click`.

`attribution_quality` is required for interpretation and uses `utm_complete`, `platform_only`, `time_window_inferred`, or `unknown`. Late events are accepted idempotently and recompute their cohort; they do not rewrite immutable source facts.

## Demand evidence

`demand_evidence` distinguishes observed provider/customer evidence from human hypotheses. Manual topics enter with `evidence_state=hypothesis` until a verified source supports them. Evidence carries a deduplication key, source time, ingestion time, confidence, and raw source payload.

Evidence older than its source-specific freshness window becomes `stale`. Undated evidence becomes `insufficient_evidence`. Neither state is a negative demand signal.

## Feedback timing

- Queue health and dead-letter/quarantine counts: operational check at least every five minutes.
- Website event delivery and broken-destination synthetic checks: target detection within 15 minutes once a production receiver is connected.
- Pinterest and Etsy metrics: evaluated according to provider availability; incomplete windows remain provisional.
- Strategy optimization: no automatic winner/loser decision unless tracking coverage and sample thresholds pass.

The `marketing-os-status` command exposes machine-readable queue lag, exception states, and evidence freshness. The `pinterest_publish` capability profile remains non-ready until Pinterest authorization, alert delivery, cost ceiling, and explicit publish authority are all configured.

## Ownership

- Marketing OS PostgreSQL owns job/run/audit, identity map, demand evidence, and normalized growth events.
- MattMadeMe.com owns public product pages and emits Etsy outbound-click analytics.
- Etsy owns listing/order source facts.
- Pinterest owns Pin and audience source metrics.
- Human-entered hypotheses are never relabeled as verified provider evidence.
