import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import App from "./App";
import { translator } from "./i18n";

const t = translator("en");

function workspacePayload() {
  return {
    ok: true as const,
    projects: [],
    protection_scope: "synthetic",
    capabilities: {
      codex: { status: "unavailable" as const, message: "synthetic" },
      writing: { status: "unavailable" as const, message: "synthetic" },
      approval: { status: "unavailable" as const, message: "synthetic" },
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  document.head.innerHTML = '<meta name="research-hub-csrf-token" content="old-token">';
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it("schedules zero reconnect timers when healthy and idle", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(workspacePayload()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(<App />);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(vi.getTimerCount()).toBe(0);
});

it("auto-reconnects with backoff and refreshes CSRF token after server restart", async () => {
  let workspaceCalls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.startsWith("/api/v1/workspace")) {
      workspaceCalls += 1;
      if (workspaceCalls === 1) {
        return new Response(JSON.stringify({ ok: false, error: "restarting", code: "unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(workspacePayload()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url === "/app/") {
      return new Response('<html><head><meta name="research-hub-csrf-token" content="fresh-token"></head></html>', {
        status: 200,
        headers: { "Content-Type": "text/html" },
      });
    }
    return new Response("{}", { status: 404 });
  });

  render(<App />);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(screen.getByText(t("pollReconnecting"))).toBeVisible();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(3100);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(workspaceCalls).toBe(2);
  expect(
    document.querySelector<HTMLMetaElement>('meta[name="research-hub-csrf-token"]')?.content,
  ).toBe("fresh-token");
  expect(screen.getByText(t("pollReconnected"))).toBeVisible();
  expect(vi.getTimerCount()).toBe(0);
});
