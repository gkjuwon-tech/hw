# `edge_api/` — Cloudflare Workers edge cache

This Worker fronts the **read-only** slice of the FastAPI control plane
(`backend/`) so the Tactile Edge appliance and the public marketing
site see <50 ms p99 globally, even when `api.conet.studio` is hosted in
a single Seoul region.

It is intentionally **not** a full reverse proxy: only the catalog,
pricing-quote, and kiosk-config endpoints get rewritten + cached.
Everything else (auth-bearing endpoints, write paths,
`/v1/lines/.../inspect`, heartbeats, store checkout) falls through to
the origin untouched.

| Worker path                    | Origin path                            | Cache         |
| ------------------------------ | -------------------------------------- | ------------- |
| `GET /catalog`                 | `GET /v1/store/catalog`                | 5 min + SWR   |
| `GET /pricing/quote?lines=...` | `GET /v1/pricing/quote?lines=...`      | 1 min + SWR   |
| `GET /kiosk/config/{edge_id}`  | `GET /v1/kiosk/{edge_id}/config`       | no cache      |
| `GET /healthz`                 | `GET /healthz`                         | no cache      |
| anything else                  | identity (no rewrite, no cache)        | no cache      |

The Worker strips `Authorization` / `Cookie` headers before forwarding
cacheable requests so we never accidentally cache per-tenant responses.

## Local dev

```bash
cd edge_api
npm install
npm run typecheck
npm test
npm run dev   # wrangler dev — proxies against ORIGIN_URL
```

## Deploy

`wrangler deploy` (or `wrangler deploy --env preview`). Production
points at `https://api.conet.studio`; the `preview` env points at
`https://api.staging.conet.studio` with shorter TTLs.
