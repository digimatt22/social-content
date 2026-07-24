# Phase -1 Capability Test Log

## Scope

Read-only or disposable tests only. Secret values, product content, customer information, and order data were not printed or stored in this artifact.

## Results

| Date | Test | Result |
| --- | --- | --- |
| 2026-07-24 | Marketing OS current-state gate | No `origin` remote configured |
| 2026-07-24 | Local configuration presence | Etsy and website agent credentials configured; Pinterest, Google reporting, PostgreSQL, OIDC, and alert configuration absent |
| 2026-07-24 | Etsy live catalog read | Passed; 74 active listings returned |
| 2026-07-24 | MattMadeMe authenticated product read | Passed; 61 public products returned |
| 2026-07-24 | MattMadeMe authenticated blog read | Passed; 6 published posts returned |
| 2026-07-24 | Website deployment/auth source review | Next.js uses AWS DynamoDB/S3, Credentials-based NextAuth for CMS users, and a static bearer token for agent APIs; production hosting/rollback contract not found |
| 2026-07-24 | Website local secret hygiene | `.env.local` is ignored by Git, not tracked, and mode `0700`/owner-only executable-readable on this Mac; hosted deployment must rotate static AWS credentials rather than copy them |
| 2026-07-24 | Sheldon read-only preflight | Linux, Docker 29.6.2, PostgreSQL 17 client, active Caddy, rootless Docker context, `0700` secrets directory, and `0600` existing app secret files |
| 2026-07-24 | Sheldon PostgreSQL inventory | No active system PostgreSQL service or rootless PostgreSQL container found |
| 2026-07-24 | Disposable PostgreSQL 17 startup | Passed locally; server accepted connections |
| 2026-07-24 | Concurrent durable-job claim | Passed; worker A locked job `1`, worker B using `FOR UPDATE SKIP LOCKED` claimed job `2` |
| 2026-07-24 | Disposable test cleanup | PostgreSQL test container stopped and removed |
| 2026-07-24 | Magnific tool discovery | No Magnific tool available in the current Codex session |

## Not Performed

- No Pinterest login, OAuth, app registration, board read, Pin create, or analytics request: credentials/app configuration are absent.
- No Etsy private receipt/order request: `transactions_r` OAuth is absent.
- No website production write: Phase -1 avoids creating drafts or content.
- No Google Search Console or GA4 reporting request: service/user credentials and property contracts are absent.
- No Cloudflare route or access-policy mutation.
- No persistent PostgreSQL deployment or database migration.
- No authentication implementation or live login test; this belongs to Phase 0 after ADR-001.

## Security Note

The website development environment contains ignored local secret material with restrictive permissions. Values were not copied into project docs. Phase 0/4 must use new deployment-scoped credentials and rotate any long-lived development credentials used by the hosted service.

## Conclusion

The internal service foundation is feasible and has safe fallbacks. Phase 0 can proceed without external publishing authority. Public Pinterest writes, automated private Etsy attribution, automated Google reporting, and unattended operation remain explicitly gated.
