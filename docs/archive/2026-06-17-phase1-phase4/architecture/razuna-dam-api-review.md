# Razuna DAM API Review

Date: 2026-06-17

## Recommendation

Razuna is a promising fit for Marketing OS as a remote DAM for product photos, company logos, videos, design files, and generated marketing assets, especially if the goal is to give the app and AI workflows access to approved assets without storing full binary copies locally.

The recommended path is a small read-first pilot:

1. Use Razuna as the source of truth for original assets.
2. Store only asset metadata, IDs, remote URLs, approval status, and sync timestamps in Marketing OS.
3. Use remote thumbnails/previews in the UI where possible.
4. Add optional short-lived local thumbnail caching later only if performance requires it.
5. Defer write operations such as upload, metadata mutation, moving, deletion, and rendition generation until read/search behavior is proven.

The main caveat is documentation clarity. Razuna now markets a modern REST API and MCP server, but the public detailed REST docs still expose an older API2 style. Before building deeply against it, we should verify the current paid-plan OpenAPI/Swagger documentation inside a real Razuna account.

## Fit For Marketing OS

Razuna matches the Marketing OS asset problem well:

- It is designed for images, videos, audio, documents, design files, brand assets, metadata, search, sharing, permissions, and AI-assisted discovery.
- It supports semantic search, full-text search, similar-image search, automatic metadata extraction, custom fields, auto-tagging, versioning, renditions, share links, and role-based permissions.
- It has an MCP server intended for AI assistants, which is directly relevant to giving Codex or other agent workflows access to assets without local copies.
- Paid plans include API access, MCP server access, SSO/SAML, custom fields, versioning, renditions, advanced AI, and unlimited users.
- Pricing is storage-based rather than per-seat, which helps if Marketing OS becomes useful to operators, contractors, agencies, or collaborators.

For Marketing OS, Razuna should be treated as an external asset source similar to Etsy, not as an internal file store. Local records should point to Razuna assets and capture the subset of metadata needed for planning, task execution, creative selection, and data health checks.

## Relevant API Surfaces

### Current MCP Server

Razuna documents a remote MCP server at:

```text
https://mcp.razuna.com/sse
```

Authentication uses an access token, preferably:

```text
Authorization: Bearer YOUR_TOKEN
```

The MCP server is the most interesting surface for Codex-style workflows. It exposes 67 tools across asset operations, including:

- Search and browse files across workspaces.
- Upload, move, delete, tag, and organize assets.
- Find visually similar images.
- Manage tags, collections, custom metadata, notes, and memories.
- Generate share links.
- Analyze file content with AI.
- Track file usage analytics.

Useful MCP tools listed in the public docs include:

| Area | Useful tools |
| --- | --- |
| Files | `search_files`, `get_file`, `upload_file`, `update_file_metadata`, `list_folder_files`, `transform_image`, `add_tag_to_files`, `move_file`, `bulk_move_files` |
| Folders | `get_folder_tree`, `create_folder` |
| Collections and sharing | `create_collection`, `create_share_link` |
| Custom metadata | `get_custom_fields`, `get_file_custom_fields`, `set_file_custom_fields` |
| AI | `find_similar_images`, `analyze_file_content` |
| Usage | `get_file_usage_stats` |

For Marketing OS, this is excellent for operator/agent workflows, but less ideal as the only app integration layer unless we want Marketing OS itself to be MCP-aware. The production app should still prefer direct REST calls once the current OpenAPI documentation is verified.

### Modern REST API

Razuna announced a newer API with SwaggerJS/JSDoc documentation, interactive endpoint testing, and core API coverage. Public marketing and FAQ pages say API access is available on paid plans and covers file management, metadata, users, bulk extraction, automation, and custom workflows.

Open item: the public search results and docs do not expose a complete current OpenAPI spec. Before implementation, we should create a test Razuna account or use a paid trial and export/inspect the actual Swagger/OpenAPI contract.

### Legacy/Public API2 Docs

The public API2 docs are old but useful for understanding core primitives. API2 is REST-style, uses a per-user API key, and returns JSON by default, with JSONP and XML/WDDX options.

Important API2 sections:

| Section | Capabilities |
| --- | --- |
| Search | `searchassets`, `searchIndex`; filters include asset type, folder ID, creation/change dates, pagination, sort, and rendition inclusion. |
| Asset | `getasset`, `getrenditions`, `getmetadata`, `setmetadata`, `remove`, `move`, `createrenditions`. |
| Folder | `getfolders`, `getassets`, `getfolder`, `setfolder`, `removefolder`, `setFolderPermissions`. |
| Custom fields | `getall`, `setfield`, `getfieldsofasset`, `setfieldvaluebulk`, `setfieldvalue`. |
| Upload | multipart upload through the tenant endpoint with `fa=c.apiupload`, `api_key`, `destfolderid`, and file field `filedata`. |

The older REST shape is not as clean as a modern resource API. It uses `.cfc?method=...` endpoints, query/form parameters, row-oriented record-set JSON, and in some cases serialized JSON structures embedded in URL parameters. That is workable for an adapter, but we should not model Marketing OS around this shape if a newer OpenAPI surface is available.

## Marketing OS Integration Shape

Add a DAM adapter behind a source-agnostic asset service:

```text
marketing_os/integrations/razuna.py
```

Suggested read-first methods:

```text
list_workspaces()
list_folders(workspace_id)
list_folder_assets(folder_id, cursor=None)
search_assets(query, asset_type=None, tags=None, workspace_id=None, folder_id=None, limit=25, cursor=None)
get_asset(asset_id)
get_asset_custom_fields(asset_id)
get_asset_usage(asset_id)
get_asset_download_or_preview_url(asset_id, rendition=None)
```

Suggested later write methods:

```text
upload_asset(folder_id, file, metadata)
update_asset_metadata(asset_id, metadata)
set_asset_custom_fields(asset_id, fields)
create_share_link(asset_id_or_folder_id, expires_at=None, password=None)
create_rendition(asset_id, format, width=None, height=None)
```

Keep the first production adapter read-only unless there is a specific operator workflow that needs writes.

## Local Data Model

Marketing OS should store references, not full DAM files.

Recommended fields:

- `external_source`: `razuna`
- `external_id`: Razuna file/asset ID
- `external_parent_id`: folder, collection, workspace, or source product ID when useful
- `external_url`: stable Razuna file/detail/share URL if provided
- `preview_url`: remote preview or thumbnail URL
- `download_url`: remote original/rendition URL if safe to expose
- `asset_type`: image, video, audio, document, design, logo, other
- `mime_type`
- `filename`
- `width`
- `height`
- `duration_seconds`
- `size_bytes`
- `tags`
- `description`
- `custom_fields`
- `approval_state`: draft, approved, archived, restricted, unknown
- `rights_notes`
- `product_slug` or local product link
- `campaign`
- `source_updated_at`
- `last_synced_at`
- `sync_status`
- `sync_error`
- `raw_external_data` for selected JSON snapshots, not binary data

Optional local cache fields:

- `local_thumbnail_path`
- `thumbnail_cached_at`
- `cache_expires_at`

Do not cache original photos or videos by default.

## Asset Taxonomy For MattMadeMe

Start with a small metadata schema that Marketing OS can use immediately:

| Field | Purpose |
| --- | --- |
| `asset_status` | approved, draft, needs_review, archived |
| `asset_role` | product_photo, logo, lifestyle, packaging, process, video, template, generated_output |
| `product_slug` | Maps assets to local product records. |
| `platform_fit` | instagram_feed, instagram_reel, facebook, etsy, website, email |
| `orientation` | square, portrait, landscape, transparent, logo_lockup |
| `rights` | owned, licensed, restricted, unknown |
| `brand_safe` | yes, no, review |
| `source_system` | razuna, etsy, generated, local_import |
| `campaign` | Optional campaign or seasonal grouping. |

This keeps creative selection practical without requiring a large enterprise taxonomy on day one.

## Workflow Uses

Product planning:

- Find approved product photos by `product_slug`.
- Select best remote thumbnail/preview for weekly plan cards.
- Warn when a product has no approved image.
- Prefer approved assets over generated drafts.

Creative asset generation:

- Pull source image URLs from Razuna.
- Record Razuna asset IDs on generated outputs.
- Upload approved generated outputs back to Razuna in a later phase.
- Keep generated files in a review state until explicitly approved.

Brand governance:

- Retrieve current logos and brand files from Razuna rather than local folders.
- Prevent stale logo use by filtering on `asset_status=approved`.
- Use custom fields for rights and usage restrictions.

Data health:

- Show missing product images, stale assets, sync failures, restricted assets, and unmapped assets.
- Track whether Marketing OS can still reach Razuna.
- Use webhook notifications later to trigger incremental syncs.

## Security And Access

Credentials should live in `.env`, never in git:

```text
RAZUNA_BASE_URL=
RAZUNA_ACCESS_TOKEN=
RAZUNA_WORKSPACE_ID=
RAZUNA_DEFAULT_FOLDER_ID=
```

If using the legacy API2 surface:

```text
RAZUNA_API_KEY=
RAZUNA_HOST=
```

Security guardrails:

- Use a least-privilege Razuna user/token for Marketing OS.
- Start read-only if Razuna supports token scopes or role-limited users.
- Do not expose original download URLs in pages where a preview is enough.
- Treat share-link creation as a privileged action.
- Log metadata sync events but avoid logging access tokens or signed URLs.
- Keep tenant isolation in mind: MCP requests are scoped to the authenticated user, and Razuna says server-side tenant isolation is enforced.

## No-Local-Copy Strategy

The integration should avoid storing original files locally.

Allowed locally:

- IDs, URLs, metadata, tags, dimensions, rights state.
- Small generated thumbnails only if needed for UI performance.
- Temporary files during upload or transformation, deleted after completion.

Not allowed by default:

- Full-resolution product photos.
- Original videos.
- Logo master files.
- Bulk-exported DAM libraries.

For generated Marketing OS assets, decide per workflow:

- Draft generated outputs can live locally until reviewed.
- Approved generated outputs should be pushed to Razuna and then referenced by Razuna ID.
- Once pushed and verified, local generated originals can be archived or deleted according to the chosen retention policy.

## Risks And Questions

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Current public REST contract is unclear | We may build against legacy docs when a newer API exists | Verify paid-plan Swagger/OpenAPI docs before coding. |
| MCP is strong for agents but not necessarily app-native | Marketing OS may need direct API calls for reliable UI sync | Use MCP for Codex/operator workflows, REST for app backend. |
| Remote preview/download URL stability is unknown | UI links may expire or break | Store asset IDs as canonical references; refresh URLs on demand. |
| Rate limits are not clear from public docs | Sync jobs could fail at scale | Ask Razuna for limits; implement pagination, backoff, and incremental sync. |
| Webhook payload shape is not public in detail | Hard to design incremental sync yet | Start with scheduled sync; add webhooks after pilot. |
| Permissions can hide assets from the integration user | Marketing OS may report false missing assets | Use a dedicated integration user with documented workspace access. |
| AI auto-tags may be noisy | Creative selection may pick wrong assets | Treat AI tags as suggestions; use explicit approval/status fields. |

## Pilot Plan

1. Create a Razuna workspace for Marketing OS pilot assets.
2. Add a small but realistic set of product photos, logos, and one or two videos.
3. Define the custom fields in the taxonomy above.
4. Create a dedicated integration token or user.
5. Verify the current REST/OpenAPI docs and capture endpoint details.
6. Build a read-only adapter that can search, list, and fetch asset metadata.
7. Add a local sync table for remote asset references.
8. Display remote previews in the Marketing OS asset inventory.
9. Add Data Health checks for missing credentials, failed sync, unmapped product images, and stale records.
10. Decide whether to add MCP access for Codex once token handling is settled.

## Decision

Razuna is a good candidate for a Marketing OS DAM, with a cautious `yes` for pilot adoption.

Use it first as a remote source of truth for approved assets, not as a local file mirror. The strongest immediate value is asset discovery, metadata, remote previews, custom fields, and AI-agent access through MCP. The biggest implementation dependency is confirming the modern REST/OpenAPI contract from an actual account before writing production code.

## Sources

- [Razuna home/features overview](https://razuna.com/)
- [Razuna feature page](https://razuna.com/features/)
- [Razuna AI page](https://razuna.com/ai/)
- [Razuna pricing](https://razuna.com/pricing/)
- [Razuna MCP server documentation](https://help.razuna.com/p/mcp-server)
- [Create an access token](https://help.razuna.com/p/create-an-access-token)
- [Razuna API announcement](https://razuna.com/blog/the-razuna-api-is-here/)
- [Legacy/API2 overview](https://razuna-documentation.readthedocs.io/en/1.8/api/)
- [Legacy/API2 Search API](https://razuna-documentation.readthedocs.io/en/1.8/api/Search%20API2/)
- [Legacy/API2 Asset API](https://razuna-documentation.readthedocs.io/en/1.8/api/Asset%20API2/)
- [Legacy/API2 Folder API](https://razuna-documentation.readthedocs.io/en/1.8/api/Folder%20API2/)
- [Legacy/API2 Custom Fields API](https://razuna-documentation.readthedocs.io/en/1.8/api/Custom%20Fields%20API2/)
- [Legacy/API2 Upload API](https://razuna-documentation.readthedocs.io/en/1.8/api/Upload%20API2/)
- [S3 browser and import documentation](https://help.razuna.com/p/browse-your-s3-and-compatible-storage)
