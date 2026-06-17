# Etsy Read-Only Integration Plan

This document is a Phase 4 reference for adding Etsy as a read-only product, listing, and asset source for the MattMadeMe Marketing OS.

## Goal

Use Etsy data to reduce manual upkeep without letting the Marketing OS edit the Etsy store.

The integration should answer:

- What products/listings are currently active?
- Which listing URLs should tasks and metrics refer to?
- Which product photos are already available from Etsy?
- Which products appear stale, missing, sold out, expired, or out of sync?
- Which Etsy facts are useful for planning social posts, website tasks, and creative asset work?

The first implementation should import or sync data into local SQLite and make it visible in the operator/admin UI. It must not publish, update, renew, delete, or otherwise mutate Etsy listings.

## Read-Only Policy

Treat Etsy as a source of truth, not as a target system.

Allowed:

- `GET` requests only.
- Reading public shop/listing data with the Etsy app key header.
- Reading shop-owned listing data only with the minimum read scopes needed.
- Storing external IDs, URLs, timestamps, image metadata, and sync status locally.
- Showing imported data in Data Health, Assets, Products, Tasks, and Metrics Due workflows.

Not allowed:

- `POST`, `PUT`, `PATCH`, or `DELETE` requests to Etsy.
- OAuth scopes ending in `_w` or `_d`.
- Automated publishing, listing creation, listing edits, listing activation, renewals, inventory changes, or receipt/order updates.
- Using imported Etsy data to overwrite local human edits without showing review/override state.

Code-level guardrails should make write operations hard to add accidentally. The Etsy adapter should expose read methods only, tests should assert that only `GET` requests are made, and configuration should request read scopes only.

## Credentials And Local Configuration

Etsy requires an API key header on every Open API v3 request:

```text
x-api-key: <keystring>:<shared_secret>
```

Local credentials should live in `.env`, which is ignored by git. The repository should keep `.env.example` with empty variable names only.

Initial variables:

```text
ETSY_KEYSTRING=
ETSY_SHARED_SECRET=
ETSY_SHOP_ID=
ETSY_SHOP_NAME=
```

If a later phase needs OAuth for private or owner-only listing fields, add local-only token variables or a token store outside git:

```text
ETSY_OAUTH_ACCESS_TOKEN=
ETSY_OAUTH_REFRESH_TOKEN=
ETSY_OAUTH_EXPIRES_AT=
```

OAuth should request `listings_r` only for listing reads that require owner authorization. Do not request `listings_w`, `listings_d`, `shops_w`, or `transactions_w`.

## Etsy API Surface

The Etsy MCP server identifies these useful read endpoints:

| Purpose | Endpoint | Operation | Auth |
| --- | --- | --- | --- |
| Search for shop ID by name | `GET /v3/application/shops?shop_name=...` | `findShops` | API key |
| Read shop profile/status | `GET /v3/application/shops/{shop_id}` | `getShop` | API key |
| Read active public shop listings | `GET /v3/application/shops/{shop_id}/listings/active` | `findAllActiveListingsByShop` | API key |
| Read shop listings with state filter and associations | `GET /v3/application/shops/{shop_id}/listings` | `getListingsByShop` | API key + OAuth `listings_r` |
| Read one listing | `GET /v3/application/listings/{listing_id}` | `getListing` | API key |
| Read listing images | `GET /v3/application/listings/{listing_id}/images` | `getListingImages` | API key |
| Read listing inventory/SKUs/offerings | `GET /v3/application/listings/{listing_id}/inventory` | `getListingInventory` | API key + OAuth `listings_r` |

Recommended first pass:

1. Use `findShops` once if `ETSY_SHOP_ID` is not known.
2. Store `ETSY_SHOP_ID` locally after verification.
3. Use `findAllActiveListingsByShop` for the first safe import.
4. Use `getListingImages` per imported listing to create external asset records.
5. Defer `getListingsByShop` and `getListingInventory` until OAuth is implemented with `listings_r`.

## Data We Want

Listing identity:

- Etsy `listing_id`
- Etsy `shop_id`
- listing title
- listing URL
- listing state
- listing type
- shop section ID
- taxonomy ID

Planning and merchandising:

- description
- tags
- materials
- price amount, divisor, and currency
- quantity
- personalization/customization flags
- processing min/max when available
- active/sold out/expired/inactive state where accessible
- favorite count
- listing view count when returned

Freshness:

- created timestamp
- updated/last modified timestamp
- ending timestamp
- state timestamp
- local `last_synced_at`
- local `sync_status`
- local `sync_error`

Images and assets:

- listing image ID
- image rank
- thumbnail URLs
- full image URL
- width and height
- average color/hex code
- alt text
- local asset record linkage
- local thumbnail/cache path if downloaded later

Inventory, if OAuth is added:

- product IDs
- SKUs
- offerings
- variation/property values
- offering-level quantity
- offering-level price
- enabled/deleted flags

## How To Make It Useful

Products:

- Match imported Etsy listings to local product records by external ID first, then URL, then normalized title as a review-only suggestion.
- Show Etsy URL, state, price, quantity, and last Etsy update on product/admin screens.
- Flag local products that do not appear in active Etsy listings.
- Flag active Etsy listings that have no local product mapping.

Tasks:

- Add canonical Etsy listing URLs to Etsy promotion tasks.
- Prefer real listing titles and URLs over manually typed references.
- Surface listing status warnings before an operator promotes a stale, inactive, sold out, or unmapped item.
- Use tags/materials as planning inputs, not as copy that must be repeated verbatim.

Assets:

- Create external asset records for Etsy listing images.
- Show Etsy thumbnails in asset inventory and task pages.
- Keep remote image URL and local cache status separate.
- Treat Etsy images as source/reference assets unless a human marks them ready for a specific marketing use.

Metrics and data health:

- Track Etsy listing favorite count and view count as imported metrics when present.
- Show `last_synced_at` and stale status in Data Health.
- Warn when Etsy import fails, credentials are missing, or OAuth is required for requested data.
- Keep daily operator workflows usable when Etsy sync is unavailable.

Creative generation:

- Allow approved Etsy listing images to become source images for generated social graphics.
- Preserve source listing ID and image ID in generated asset metadata.
- Never assume generated assets are approved just because their source image came from Etsy.

## Suggested Local Data Model

Add or reuse fields that support any external source, with Etsy as the first adapter:

- `external_source` such as `etsy`
- `external_id` such as listing ID or image ID
- `external_parent_id` for image-to-listing relationships
- `external_url`
- `external_state`
- `external_updated_at`
- `last_synced_at`
- `sync_status`
- `sync_error`
- `manual_override`
- `review_state`
- `raw_external_data` for selected JSON snapshots if useful

For Etsy-specific records, keep the local model useful without hard-coding every Etsy field into first-class columns. Promote only the fields the UI and planner need frequently.

## Adapter Shape

Create a read-only Etsy adapter behind a service boundary:

```text
marketing_os/integrations/etsy.py
```

Suggested methods:

- `find_shop_by_name(shop_name)`
- `get_shop(shop_id)`
- `list_active_shop_listings(shop_id, limit, offset)`
- `get_listing(listing_id)`
- `get_listing_images(listing_id)`
- `get_listing_inventory(listing_id)` only after OAuth `listings_r`

Suggested service:

```text
marketing_os/services/etsy_import.py
```

Responsibilities:

- read environment configuration
- page through listing results
- normalize Etsy API responses into local DTOs
- upsert import records without overwriting manual overrides
- create/update external asset records for images
- record sync status and errors
- expose summaries for Data Health

Routes and templates should call the service, not the raw adapter.

## Phased Implementation

### Phase A - Public Read Import

- Add configuration loading for `ETSY_KEYSTRING`, `ETSY_SHARED_SECRET`, `ETSY_SHOP_ID`, and `ETSY_SHOP_NAME`.
- Implement API-key-only `GET` adapter.
- Import active listings via `findAllActiveListingsByShop`.
- Import listing images via `getListingImages`.
- Store external IDs, URLs, image metadata, and sync state.
- Show imported Etsy records in Data Health.

### Phase B - Product And Asset Mapping

- Add admin review UI to match Etsy listings to local products.
- Suggest matches by URL/title but require human confirmation.
- Show Etsy listing URLs and thumbnails on tasks.
- Warn when a task references an unmapped or stale listing.

### Phase C - OAuth Read Expansion

- Add OAuth 2.0 PKCE setup only if owner-only listing states, inactive listings, SKUs, or inventory are needed.
- Request `listings_r` only.
- Import non-active listing states through `getListingsByShop`.
- Import SKU/variation/offering data through `getListingInventory`.
- Continue enforcing `GET`-only adapter behavior.

## Failure States

Handle these as normal, visible states:

- missing `.env` values
- invalid keystring/shared secret
- missing or unknown shop ID
- Etsy rate limit response
- network timeout
- OAuth required for a requested field
- listing removed or unavailable
- image URL unavailable
- local mapping conflict
- local manual override blocks an automatic update

Failures should not block Today, This Week, existing tasks, or local planning.

## Acceptance Criteria

- Real credentials are kept out of git.
- The Etsy adapter exposes read methods only.
- The first sync can import active listings and listing images without OAuth.
- Every imported record has source, external ID, external URL where available, and last sync status.
- Imported data is visible in Data Health before it influences planner output.
- Product/listing matching requires review before overwriting local assumptions.
- Tasks can display canonical Etsy URLs and thumbnails from imported records.
- Write scopes and write HTTP methods are absent from configuration, tests, and adapter code.
