import { afterEach, describe, expect, it, vi } from "vitest";
import { api, auditProject, ApiError, recoverCsrfIfForbidden, refreshSessionTokens, safeSourceUrl } from "./api";

const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function token(name: string, value: string) {
  const meta = document.createElement("meta");
  meta.name = name;
  meta.content = value;
  document.head.append(meta);
}

describe("workspace API boundary", () => {
  it("retains an explicit failed audit report returned as HTTP 400, but never accepts gateway failure", async () => {
    const report = { ok: false, report: { findings: ["Unresolved evidence"] }, operation: "state", exit_code: 1, adapter_sha256: "fixture", semantic_acceptance: "not_performed" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(report, 400)).mockResolvedValueOnce(response(report, 503)));
    await expect(auditProject("p", {})).resolves.toEqual(report);
    await expect(auditProject("p", {})).rejects.toMatchObject({ status: 503 });
  });
  it("preserves server error and code for a rejected mutation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            ok: false,
            error: "File is outside workspace",
            code: "outside_root",
          },
          400,
        ),
      ),
    );
    await expect(
      api("/projects/p/artifacts", { path: "../paper.md" }),
    ).rejects.toMatchObject({
      name: "ApiError",
      message: "File is outside workspace",
      code: "outside_root",
      status: 400,
    });
  });
  it("rejects an application error even when HTTP status is 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({ ok: false, error: "Not authorized", code: "forbidden" }),
        ),
    );
    await expect(api("/workspace")).rejects.toBeInstanceOf(ApiError);
  });
  it("rejects malformed and non-JSON responses", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(null))
      .mockResolvedValueOnce(
        new Response("gateway unavailable", { status: 502 }),
      );
    vi.stubGlobal("fetch", fetch);
    await expect(api("/workspace")).rejects.toMatchObject({
      code: "invalid_response",
    });
    await expect(api("/workspace")).rejects.toMatchObject({
      code: "invalid_response",
      status: 502,
    });
  });
  it("preserves cancellation after headers arrive while the JSON body is pending", async () => {
    const controller = new AbortController();
    const body = new ReadableStream({
      start(stream) {
        controller.signal.addEventListener(
          "abort",
          () => stream.error(controller.signal.reason),
          { once: true },
        );
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const pending = api("/workspace", undefined, controller.signal);
    await Promise.resolve();
    controller.abort();
    await expect(pending).rejects.toBe(controller.signal.reason);
  });
  it("uses CSRF for every POST and sends human proof only to the decision endpoint", async () => {
    token("research-hub-csrf-token", "test-csrf");
    token("research-hub-human-token", "test-human");
    const fetch = vi
      .fn()
      .mockImplementation(async () => response({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    await api("/projects/p/records", { kind: "question" });
    await api("/tasks/t/decision", { outcome: "accept" });
    await api("/workspace");
    expect(fetch.mock.calls[0][1].headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": "test-csrf",
    });
    expect(fetch.mock.calls[1][1].headers["X-Human-Token"]).toBe("test-human");
    expect(fetch.mock.calls[2][1].headers["X-CSRF-Token"]).toBeUndefined();
    expect(
      fetch.mock.calls.every((call) => !call[0].includes("test-human")),
    ).toBe(true);
  });
  it("never adds human authorization when the local server did not provide it", async () => {
    const fetch = vi.fn().mockResolvedValue(response({ ok: true }));
    vi.stubGlobal("fetch", fetch);
    await api("/tasks/t/decision", { outcome: "accept" });
    expect(fetch.mock.calls[0][1].headers["X-Human-Token"]).toBeUndefined();
  });
  it("limits external source links to HTTP(S)", () => {
    expect(safeSourceUrl("https://doi.org/10.1/example")).toBe(
      "https://doi.org/10.1/example",
    );
    expect(safeSourceUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeSourceUrl("file:///private.txt")).toBeUndefined();
    expect(safeSourceUrl("paper-local")).toBeUndefined();
  });

  describe("session token refresh", () => {
    afterEach(() => {
      vi.useRealTimers();
      vi.unstubAllGlobals();
    });

    it("refreshes CSRF token on explicit 403 forbidden recovery without replaying the POST write", async () => {
      document.head.innerHTML = "";
      token("research-hub-csrf-token", "stale-token");
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(response({ ok: false, error: "Untrusted request", code: "forbidden" }, 403))
        .mockResolvedValueOnce(
          new Response('<meta name="research-hub-csrf-token" content="new-csrf-token">', {
            status: 200,
            headers: { "Content-Type": "text/html" },
          }),
        );
      vi.stubGlobal("fetch", fetchMock);

      let caught: unknown;
      try {
        await api("/integrations/credentials", { zotero_library_id: "123" });
      } catch (err) {
        caught = err;
        await recoverCsrfIfForbidden(err);
      }
      expect(caught).toMatchObject({ status: 403, code: "forbidden" });
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/integrations/credentials");
      expect(fetchMock.mock.calls[1][0]).toBe("/app/");
      expect(document.querySelector<HTMLMetaElement>('meta[name="research-hub-csrf-token"]')?.content).toBe(
        "new-csrf-token",
      );
    });

    it("bounds stalled refreshSessionTokens reads with a 5s timeout", async () => {
      vi.useFakeTimers();
      const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), {
            once: true,
          });
        });
      });
      vi.stubGlobal("fetch", fetchMock);

      const pending = refreshSessionTokens();
      await vi.advanceTimersByTimeAsync(5100);
      await expect(pending).resolves.toBe(false);
    });
  });
});
