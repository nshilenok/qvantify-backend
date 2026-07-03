const { Readable } = require("node:stream");

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "accept-encoding",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const DEFAULT_RAILWAY_URL = "https://qvantify.up.railway.app";
const PROXY_PREFIX = "/api/proxy";

function normalizeBaseUrl(rawUrl) {
  if (!rawUrl) {
    return DEFAULT_RAILWAY_URL;
  }
  return rawUrl.endsWith("/") ? rawUrl.slice(0, -1) : rawUrl;
}

function filterRequestHeaders(headers) {
  const result = {};
  for (const [key, value] of Object.entries(headers)) {
    const lowerKey = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lowerKey)) {
      continue;
    }
    if (typeof value !== "undefined") {
      result[key] = value;
    }
  }
  return result;
}

function applyResponseHeaders(res, response) {
  const setCookies = response.headers.getSetCookie?.() || [];
  if (setCookies.length > 0) {
    res.setHeader("set-cookie", setCookies);
  }

  response.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey === "set-cookie" ||
      lowerKey === "content-encoding" ||
      lowerKey === "content-length" ||
      lowerKey === "transfer-encoding"
    ) {
      return;
    }
    res.setHeader(key, value);
  });
}

async function readRequestBody(req) {
  if (req.method === "GET" || req.method === "HEAD") {
    return undefined;
  }

  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.from(chunk));
  }
  return chunks.length > 0 ? Buffer.concat(chunks) : undefined;
}

module.exports = async function proxyHandler(req, res) {
  try {
    const baseUrl = normalizeBaseUrl(process.env.QVANTIFY_RAILWAY_URL);
    // Non-secret debug header to validate routing (prod vs staging).
    res.setHeader("x-qvantify-proxy-base", baseUrl);
    const proxyPath = req.url.startsWith(PROXY_PREFIX)
      ? req.url.slice(PROXY_PREFIX.length)
      : req.url;
    const targetUrl = `${baseUrl}/api${proxyPath}`;

    const body = await readRequestBody(req);
    const response = await fetch(targetUrl, {
      method: req.method,
      headers: filterRequestHeaders(req.headers),
      body,
      redirect: "manual",
    });

    res.statusCode = response.status;
    applyResponseHeaders(res, response);

    if (!response.body) {
      res.end();
      return;
    }

    Readable.fromWeb(response.body).pipe(res);
  } catch (error) {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.end(
      JSON.stringify({
        error: "Proxy request failed",
        detail: error?.message || "Unknown error",
      })
    );
  }
};
