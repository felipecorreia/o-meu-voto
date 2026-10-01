// Same-origin proxy from the Pages domain to the Cloud Run service (ADR 0005, issue #22).
// Only /api/* and /mcp reach this function (_routes.json); every other path is a free
// static asset. Environment: ORIGIN_URL (the run.app URL), EDGE_SECRET (optional secret,
// sent as x-edge-secret so the service can refuse traffic that bypassed the edge).
export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  // The service is stateless and never sends server-initiated messages: answer the MCP
  // GET stream with 405 (allowed by the Streamable HTTP spec) instead of holding an idle
  // SSE request open on Cloud Run, which keeps an instance billed while it lasts.
  if (url.pathname === "/mcp" && request.method === "GET") {
    return new Response(null, { status: 405, headers: { allow: "POST" } });
  }
  const target = new URL(url.pathname + url.search, env.ORIGIN_URL);
  const headers = new Headers(request.headers);
  headers.delete("host");
  if (env.EDGE_SECRET) headers.set("x-edge-secret", env.EDGE_SECRET);
  const init = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
  // Short edge cache for REST GETs, except requests carrying the voter's coordinates,
  // which must not be kept anywhere (ADR 0004). The origin reads a literal "&amp;" as a
  // separator (issue #115), so the coordinates are looked up the same way here.
  const query = new URLSearchParams(url.search.replace(/&amp;/gi, "&"));
  const cacheable =
    request.method === "GET" &&
    url.pathname.startsWith("/api/v1/") &&
    !query.has("lat") &&
    !query.has("lon");
  if (cacheable) init.cf = { cacheTtl: 60, cacheEverything: true };
  return fetch(target, init);
}
