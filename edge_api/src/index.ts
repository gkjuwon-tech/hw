/**
 * Conet Tactile — edge_api Cloudflare Worker.
 *
 * This Worker fronts the *read-only* slice of the FastAPI control
 * plane so the Tactile Edge appliance and the marketing site see
 * <50 ms p99 globally even when api.conet.studio is in a single
 * Seoul region. Three routes are handled here:
 *
 *   GET  /catalog            → /v1/store/catalog          (5 min cache)
 *   GET  /pricing/quote      → /v1/pricing/quote          (60 s cache)
 *   GET  /kiosk/config/:id   → /v1/kiosk/{edge_id}/config (no cache)
 *
 * Everything else falls through to the origin transparently so we
 * can roll endpoints onto the edge one at a time. The Worker never
 * inspects bodies of POST requests and never caches auth-bearing
 * responses.
 */

export interface Env {
  ORIGIN_URL: string;
  CACHE_TTL_CATALOG_S: string;
  CACHE_TTL_PRICING_S: string;
}

type CacheHint = {
  ttlSeconds: number;
  staleWhileRevalidateSeconds: number;
};

const CACHE_RULES: Record<string, (env: Env) => CacheHint> = {
  "/catalog": (env) => ({
    ttlSeconds: parseIntDefault(env.CACHE_TTL_CATALOG_S, 300),
    staleWhileRevalidateSeconds: 24 * 60 * 60,
  }),
  "/pricing/quote": (env) => ({
    ttlSeconds: parseIntDefault(env.CACHE_TTL_PRICING_S, 60),
    staleWhileRevalidateSeconds: 10 * 60,
  }),
};

function parseIntDefault(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const n = Number.parseInt(value, 10);
  return Number.isFinite(n) && n >= 0 ? n : fallback;
}

/**
 * Translate the Worker request path into the FastAPI control-plane
 * path. Returns ``null`` if the path is not one we handle.
 */
export function rewritePath(pathname: string): string | null {
  if (pathname === "/" || pathname === "/healthz") {
    return "/healthz";
  }
  if (pathname === "/catalog") {
    return "/v1/store/catalog";
  }
  if (pathname === "/pricing/quote") {
    return "/v1/pricing/quote";
  }
  if (pathname.startsWith("/kiosk/config/")) {
    const id = pathname.slice("/kiosk/config/".length);
    if (!id || id.includes("/")) return null;
    return `/v1/kiosk/${encodeURIComponent(id)}/config`;
  }
  return null;
}

export function cacheHintFor(pathname: string, env: Env): CacheHint | null {
  const rule = CACHE_RULES[pathname];
  return rule ? rule(env) : null;
}

function buildCacheControl(hint: CacheHint | null): string {
  if (!hint) return "no-store";
  return [
    "public",
    `max-age=${hint.ttlSeconds}`,
    `s-maxage=${hint.ttlSeconds}`,
    `stale-while-revalidate=${hint.staleWhileRevalidateSeconds}`,
  ].join(", ");
}

async function proxy(
  request: Request,
  env: Env,
  upstreamPath: string,
  hint: CacheHint | null,
): Promise<Response> {
  const upstream = new URL(env.ORIGIN_URL);
  upstream.pathname = upstreamPath;

  // Forward the query string verbatim — pricing/quote needs the
  // ``lines`` and ``care_tier`` params to make sense.
  const requestUrl = new URL(request.url);
  upstream.search = requestUrl.search;

  // Strip hop-by-hop headers; Cloudflare drops Connection / TE for us
  // but we explicitly remove the Authorization header for cacheable
  // routes so we don't accidentally cache per-tenant responses.
  const upstreamHeaders = new Headers(request.headers);
  if (hint) {
    upstreamHeaders.delete("Authorization");
    upstreamHeaders.delete("Cookie");
  }
  upstreamHeaders.set("Host", upstream.host);

  const upstreamRequest = new Request(upstream.toString(), {
    method: request.method,
    headers: upstreamHeaders,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
    redirect: "manual",
  });

  const upstreamResponse = await fetch(upstreamRequest);
  const responseHeaders = new Headers(upstreamResponse.headers);
  responseHeaders.set("Cache-Control", buildCacheControl(hint));
  responseHeaders.set("X-Edge-Worker", "conet-edge-api");
  if (hint) {
    responseHeaders.set("X-Edge-Cached", "shortlived");
  }
  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const upstreamPath = rewritePath(url.pathname);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age": "600",
        },
      });
    }

    if (upstreamPath === null) {
      // Unknown path → fall through to origin without any caching so
      // the migration can happen one endpoint at a time.
      return proxy(request, env, url.pathname, null);
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed", {
        status: 405,
        headers: { "Cache-Control": "no-store" },
      });
    }

    const hint = cacheHintFor(url.pathname, env);
    return proxy(request, env, upstreamPath, hint);
  },
};
