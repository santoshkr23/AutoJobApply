import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

afterEach(() => { vi.restoreAllMocks(); document.cookie = "csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT"; });

describe("api client", () => {
  it("sends JSON bodies with the CSRF header read from the cookie", async () => {
    document.cookie = "csrf=abc123";
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { ok: true }));
    await api("/thing", { body: { a: 1 } });
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/thing");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("abc123");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
  });

  it("does not send a CSRF header on GET", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, {}));
    await api("/thing");
    expect((spy.mock.calls[0][1] as RequestInit).headers).not.toHaveProperty("X-CSRF-Token");
  });

  it("maps backend error envelopes to ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(402, { error: { code: "quota_exceeded", message: "Plan limit reached", details: { limit: 10 } } }));
    await expect(api("/x", { method: "POST" })).rejects.toMatchObject({ status: 402, code: "quota_exceeded", message: "Plan limit reached" });
  });

  it("joins FastAPI validation errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(422, { detail: [{ msg: "bad email" }, { msg: "too short" }] }));
    await expect(api("/x", { method: "POST" })).rejects.toThrow("bad email; too short");
  });

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
    const err = await api("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("network_error");
  });

  it("returns undefined for 204", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    expect(await api("/x", { method: "DELETE" })).toBeUndefined();
  });
});
