import { test } from "node:test";
import assert from "node:assert/strict";

import { rewritePath, cacheHintFor, type Env } from "../src/index.ts";

const env: Env = {
  ORIGIN_URL: "https://api.conet.studio",
  CACHE_TTL_CATALOG_S: "300",
  CACHE_TTL_PRICING_S: "60",
};

test("rewritePath maps known routes to FastAPI paths", () => {
  assert.equal(rewritePath("/"), "/healthz");
  assert.equal(rewritePath("/healthz"), "/healthz");
  assert.equal(rewritePath("/catalog"), "/v1/store/catalog");
  assert.equal(rewritePath("/pricing/quote"), "/v1/pricing/quote");
  assert.equal(rewritePath("/kiosk/config/edge-1"), "/v1/kiosk/edge-1/config");
});

test("rewritePath returns null for unhandled paths", () => {
  assert.equal(rewritePath("/v1/store/checkout/software"), null);
  assert.equal(rewritePath("/store/order/abc"), null);
});

test("rewritePath refuses traversal in kiosk id", () => {
  assert.equal(rewritePath("/kiosk/config/"), null);
  assert.equal(rewritePath("/kiosk/config/a/b"), null);
});

test("rewritePath url-encodes the kiosk id", () => {
  // ``edge with space`` is silly but the encoder should still spit
  // out a valid path so the upstream never sees a raw space.
  assert.equal(
    rewritePath("/kiosk/config/edge with space"),
    "/v1/kiosk/edge%20with%20space/config",
  );
});

test("cacheHintFor returns budgets for cached routes only", () => {
  const catalog = cacheHintFor("/catalog", env);
  assert.ok(catalog);
  assert.equal(catalog!.ttlSeconds, 300);
  assert.ok(catalog!.staleWhileRevalidateSeconds >= 60);

  const pricing = cacheHintFor("/pricing/quote", env);
  assert.ok(pricing);
  assert.equal(pricing!.ttlSeconds, 60);

  assert.equal(cacheHintFor("/kiosk/config/edge-1", env), null);
  assert.equal(cacheHintFor("/healthz", env), null);
});

test("cacheHintFor honours invalid env defaults", () => {
  const broken: Env = { ...env, CACHE_TTL_CATALOG_S: "not-a-number" };
  const catalog = cacheHintFor("/catalog", broken);
  assert.ok(catalog);
  assert.equal(catalog!.ttlSeconds, 300);
});
