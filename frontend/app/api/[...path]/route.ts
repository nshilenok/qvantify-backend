import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

type RouteParams = {
  path?: string[];
};

type RouteContext = {
  params: Promise<RouteParams>;
};

const resolveBaseUrl = () => {
  const configured = (process.env.QVANTIFY_RAILWAY_URL || "").replace(/\/$/, "");
  if (configured) {
    return configured;
  }
  if (process.env.NODE_ENV !== "production") {
    return "http://127.0.0.1:5000";
  }
  throw new Error("Missing QVANTIFY_RAILWAY_URL");
};

const TRAILING_SLASH_PATHS = new Set([
  "respondent",
  "project",
  "reply",
  "interview",
  "quote",
  "heartbeat",
  "debug",
  "voice-transcribe",
]);

const buildTargetUrl = async (request: Request, context: RouteContext) => {
  const baseUrl = resolveBaseUrl();
  const params = await context.params;
  const path = Array.isArray(params.path) ? params.path.join("/") : "";
  const normalizedPath = path ? path.replace(/\/$/, "") : "";
  const needsSlash = normalizedPath ? TRAILING_SLASH_PATHS.has(normalizedPath) : false;
  const search = new URL(request.url).search || "";
  const slash = normalizedPath ? "/" : "";
  const trailing = needsSlash ? "/" : "";
  return `${baseUrl}/api${slash}${normalizedPath}${trailing}${search}`;
};

const proxyRequest = async (request: Request, context: RouteContext) => {
  let targetUrl: string;
  try {
    targetUrl = await buildTargetUrl(request, context);
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  }

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-qvantify-proxy", "nextjs");

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(targetUrl, init);
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.set("x-qvantify-proxy-base", resolveBaseUrl());
  responseHeaders.delete("content-length");

  const requestPath = new URL(request.url).pathname;
  const isProjectConfig =
    request.method === "GET" && (requestPath === "/api/project" || requestPath === "/api/project/");
  const isVoiceTranscribe =
    requestPath === "/api/voice-transcribe" || requestPath === "/api/voice-transcribe/";
  const isShareLogin = requestPath.includes("/api/share/") && requestPath.endsWith("/login");

  if (isProjectConfig) {
    const text = await upstream.text();
    if (upstream.ok && responseHeaders.get("content-type")?.includes("application/json")) {
      try {
        const data = JSON.parse(text);
        if (Array.isArray(data)) {
          let changed = false;
          const normalized = data.map((item) => {
            if (item && typeof item === "object" && !("voice_enabled" in item)) {
              changed = true;
              return { ...item, voice_enabled: false };
            }
            return item;
          });
          if (changed) {
            responseHeaders.delete("content-encoding");
            return new Response(JSON.stringify(normalized), {
              status: upstream.status,
              statusText: upstream.statusText,
              headers: responseHeaders,
            });
          }
        }
      } catch {
        // Fall through to return upstream body as-is.
      }
    }
    responseHeaders.delete("content-encoding");
    return new Response(text, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  }

  if (isVoiceTranscribe && upstream.status === 405) {
    responseHeaders.delete("content-encoding");
    responseHeaders.set("content-type", "application/json");
    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  }
  if (isShareLogin && upstream.status >= 500) {
    const text = await upstream.text();
    if (text.includes("Missing SECRET_KEY")) {
      return new Response(JSON.stringify({ error: "Share login unavailable" }), {
        status: 503,
        headers: { "content-type": "application/json", "x-qvantify-proxy-base": resolveBaseUrl() },
      });
    }
    return new Response(text, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
};

export const GET = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const POST = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const PUT = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const PATCH = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const DELETE = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const OPTIONS = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
export const HEAD = (request: NextRequest, context: RouteContext) => proxyRequest(request, context);
