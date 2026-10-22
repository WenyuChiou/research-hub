import { afterEach, describe, expect, it, vi } from "vitest";
import { api, READ_TIMEOUT_MS } from "./api";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
const response = () => new Response(JSON.stringify({ ok: true }));
describe("read deadline boundary", () => {
  it.each(["fetch", "body"])("bounds a hanging %s without replay", async (phase) => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockImplementation((_url, options) => phase === "fetch"
      ? new Promise(() => {})
      : Promise.resolve({ json: () => new Promise(() => {}) }));
    vi.stubGlobal("fetch", fetch);
    const rejected = expect(api("/workspace")).rejects.toMatchObject({ code: "read_timeout", status: 408 });
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
    await rejected;
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("preserves caller cancellation and removes timer/listener", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    const pending = api("/workspace", undefined, controller.signal);
    const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await rejected;
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
  });
  it("does not deadline or replay mutations", async () => {
    vi.useFakeTimers();
    let resolve!: (value: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>(yes => { resolve = yes; }));
    vi.stubGlobal("fetch", fetch);
    const pending = api("/projects/p/records", {});
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS * 2);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    resolve(response());
    await pending;
  });
});
