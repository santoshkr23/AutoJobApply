// Runtime reverse proxy: the browser calls /api/* on this site and we forward it to the FastAPI backend.
// The target is read from the environment at request time (not baked in at build), so it works the same
// in docker compose, on Render's private network, or with a public backend URL.
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function backendBase(): string | null {
  const url = process.env.BACKEND_URL?.trim();
  if (url) return url.replace(/\/+$/, "");
  const hp = process.env.BACKEND_HOSTPORT?.trim();
  if (hp) return `http://${hp}`;
  return process.env.NODE_ENV === "production" ? null : "http://localhost:8000";
}

const HOP = new Set(["connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer", "proxy-authenticate", "proxy-authorization", "host", "content-length"]);

async function proxy(req: NextRequest, ctx: { params: { path: string[] } }): Promise<Response> {
  const base = backendBase();
  if (!base) {
    return Response.json({ error: { code: "backend_not_configured", message: "BACKEND_URL (or BACKEND_HOSTPORT) is not set on the web service." } }, { status: 502 });
  }
  const target = `${base}/api/${ctx.params.path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase())) headers.set(k, v); });
  const fwdFor = req.headers.get("x-forwarded-for");
  if (!fwdFor) headers.set("x-forwarded-for", "unknown");
  headers.set("x-forwarded-host", req.headers.get("host") ?? "");
  headers.set("x-forwarded-proto", req.headers.get("x-forwarded-proto") ?? "https");
  const hasBody = !["GET", "HEAD"].includes(req.method);
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // @ts-expect-error duplex is required by Node's fetch for streamed request bodies
      duplex: hasBody ? "half" : undefined,
      redirect: "manual",
      cache: "no-store",
    });
    const out = new Headers();
    upstream.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase()) && k.toLowerCase() !== "content-encoding" && k.toLowerCase() !== "set-cookie") out.set(k, v); });
    for (const c of upstream.headers.getSetCookie()) out.append("set-cookie", c);
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return Response.json({ error: { code: "backend_unreachable", message: "The web app could not reach the API service. Check BACKEND_URL on the web service and that the API is running." } }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as HEAD };
