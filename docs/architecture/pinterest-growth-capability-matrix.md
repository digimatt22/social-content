# Pinterest Growth Capability Matrix

## Status

Phase -1 evidence captured 2026-07-24. `Unknown` means account/environment capability was not proven; it does not mean the provider lacks the feature.

| Capability | State | Evidence | Limitation or risk | Safe fallback / next gate |
| --- | --- | --- | --- | --- |
| Etsy active listing read | Available | Configured live read returned 74 active listings | Current adapter uses app key, not private transaction OAuth | Continue catalog sync |
| Etsy reviews read | Available in code/config | Existing read-only adapter and configured shop | Not separately exercised in this gate | Exercise with bounded fixture/live count in Phase 0 |
| Etsy orders, receipts, revenue | Unavailable in current integration | No OAuth transaction token/config or receipt adapter | Existing sales CSV is delayed/manual | Keep idempotent CSV import; add `transactions_r` OAuth only after seller authorization |
| Etsy near-real-time order events | Provider capability available; account setup unknown | Official Etsy webhook docs include paid/cancelled/shipped/delivered events | Requires OAuth and public callback | Poll/CSV fallback; do not claim real-time attribution |
| MattMadeMe website agent authentication | Available | Configured bearer credential; live authenticated reads succeeded | Single static bearer token, no scoped identity/rotation UI | Preserve temporarily; replace with scoped service identity |
| MattMadeMe public product read | Available | Live authenticated API returned 61 products | API is v1 and numeric-ID based | Contract fixtures and versioning in Phase 0/1 |
| MattMadeMe published blog read | Available | Live authenticated API returned 6 posts | Only published metadata is returned | Preserve |
| MattMadeMe blog draft write | Available in code; live write not tested | Authenticated draft endpoint and OpenAPI contract | A live write would create production draft state | Test against fixture/preview before production use |
| MattMadeMe product/collection/editorial write | Unavailable | No agent write endpoints beyond blog drafts | Blocks autonomous website enrichment | Draft/export fallback until Phase 1 |
| Website analytics collection | Partially available | GA tag, Vercel Analytics, and Ahrefs client instrumentation exist | Reporting API credentials and event contract absent | Establish baseline through available dashboards; add GA4 API credentials/events in Phase 0 |
| GA4 reporting API | Unknown/unconfigured | No property ID or Google API credential in Marketing OS environment | Cannot automate reports | Manual dashboard/export fallback |
| Google Search Console | Unknown/unconfigured | No site/API configuration found | Search query/index evidence unavailable | Use labeled hypotheses and observed page/Pin data; fixed exploration allocation |
| Pinterest public profile | Available publicly | Website links to `MattMadeMe` Pinterest profile | Business-account and claimed-domain status not proven | Human/account check before analytics assumptions |
| Pinterest app and OAuth | Unconfigured | No app ID, secret, access token, or refresh token configured | Cannot call Pinterest API | Shadow/export only |
| Pinterest board/Pin reads | Provider capability available; account access unknown | Official API supports `boards:read` and `pins:read` | Requires approved app/token | Fixture adapter until OAuth is configured |
| Pinterest public Pin create | Provider capability available; access tier unknown | Official API supports `pins:write`; Trial-created Pins are creator-only | Standard access is required for normal public production behavior | Shadow/export or creator-only sandbox tests |
| Pinterest refresh-token continuity | Provider capability available; unconfigured | Official OAuth docs define continuous refresh flow | Requires registered app and secure token storage/refresh | No unattended publishing |
| Pinterest organic analytics | Provider capability available; account access unknown | Official API supports account and Pin analytics, including detailed and rolling metrics | Business account/claimed website improve coverage; 90-day/lifetime caveats | Manual analytics export until access is proven |
| Pinterest Trends API | Likely unavailable until eligibility proven | Official Trends API targets agencies, Enterprise clients, and partner platforms | Cannot treat strategy keywords as measured Pinterest demand | Search Console/observed performance plus labeled hypotheses and exploration |
| Pinterest native scheduling | Not proven | Organic creation docs show immediate Create Pin; no schedule field was evidenced | Scheduling ownership cannot be delegated to an assumed provider feature | Marketing OS durable scheduler issues Create Pin at due time |
| Magnific MCP | Unavailable in this Codex session | No Magnific tool detected; repo handoff workflow exists | Cannot execute current provider from this environment | Preserve provider manifests; use approved image fallback/manual execution |
| Repository skills | Partially verified | Seven skill directories exist; two script-level tests pass | No clean-device/provider smoke coverage for every skill | Preserve repo skills; add capability manifest/check in Phase 0 |
| Digi-CTO plugin | Available | Version 0.3.0 installed/enabled | None for planning | Keep version recorded |
| Always-on Sheldon host | Available for initial internal service | SSH preflight: Linux, rootless Docker, Caddy, protected secrets | Development server; no HA claim | Use for bounded vertical slice with backups and rollback |
| PostgreSQL server on Sheldon | Not currently running | `postgresql` service inactive and no Postgres container observed | Database must be provisioned and backed up | App-owned rootless PostgreSQL 17 container in Phase 0/4 |
| PostgreSQL durable leasing | Available/proven locally | Concurrent PostgreSQL 17 test skipped locked job `1` and claimed job `2` | Full worker recovery not implemented | Implement and test in Phase 0 |
| Hosted Flask authentication | Unavailable | Current app is trusted-local-network only | Cannot expose permanent console | Implement application auth in Phase 0; no hosted operator access before pass |
| Cloudflare/Caddy route | Partially available | Hostname selected: `mmm.digicolony.net` (Matthew, 2026-09-25); Caddy active on Sheldon; Cloudflare route not yet configured | Access/route policy still open | Loopback/LAN-only until Cloudflare route is configured |
| Alert delivery | Unconfigured | No alert webhook/email provider configuration found | Unattended failures could go unseen | Persist exceptions; no unattended external writes until alert proof |
| Off-host PostgreSQL backup | Unconfigured | No Marketing OS database deployment exists | Restore objective unproven | Phase 0 selects destination and runs restore proof |
| Source-control remote/PR | Unavailable in Marketing OS repo | No `origin` remote configured | Local phase commits cannot be pushed/reviewed | Create scoped local commits; remote setup remains a delivery follow-up |

## Provider Facts Used

Checked against official documentation on 2026-07-24:

- [Pinterest access tiers](https://developers.pinterest.com/docs/key-concepts/access-tiers/)
- [Pinterest authentication and authorization](https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/)
- [Pinterest boards and Pins](https://developers.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/)
- [Pinterest organic reporting](https://developers.pinterest.com/docs/analytics-and-reports/organic-reporting/)
- [Pinterest Trends](https://developers.pinterest.com/docs/analytics-and-reports/trends/)
- [Etsy Open API v3](https://developers.etsy.com/)
- [Etsy authentication](https://developers.etsy.com/documentation/essentials/authentication/)
- [Etsy webhooks](https://developers.etsy.com/documentation/essentials/webhooks/)
- [Google Search Console Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics)
- [Google Analytics Data API](https://developers.google.com/analytics/devguides/reporting/data/v1)

## Gate Result

- Phase 0 internal foundation work may proceed.
- Phase 1 website draft/preview work may proceed after Phase 0 contracts pass.
- Public Pinterest publishing remains blocked until app access, OAuth scopes/token refresh, board IDs, access tier, reconciliation, alert delivery, and pause/cost policies are proven.
- Automated Etsy order attribution remains blocked until `transactions_r` OAuth or an accepted import fallback is operational.
- Automated Search Console/GA4 optimization remains blocked until reporting credentials and data contracts are proven; labeled hypotheses remain safe for exploration.
