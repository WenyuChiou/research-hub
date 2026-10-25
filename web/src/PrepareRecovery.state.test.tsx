import { StrictMode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  preparationPrefix,
  usePreparationRecovery,
  type DraftPreparePayload,
} from "./PrepareRecovery";
import type { Task } from "./types";

const namespace = "11111111-1111-4111-8111-111111111111";
const key = "22222222-2222-4222-8222-222222222222";
const capability = { version: 1, workspace_instance_id: namespace };
const payload: DraftPreparePayload = {
  operation: "paper-abstract-draft",
  mode: "connected",
  instructions: "Public instruction",
  source_selection: {
    artifact_id: "public-text",
    source_record_id: "public-source",
    start: 0,
    end: 8,
  },
};
const task = {
  id: "exact-task",
  project_id: "river",
  operation: "paper-abstract-draft",
  status: "ready",
  mode: "connected",
} as Task;
const prefix = preparationPrefix(window.location.origin, namespace, "river");
const identity = (k = key) => ({
  version: 1,
  workspace_instance_id: namespace,
  project_id: "river",
  key: k,
  state: "pending",
});
const response = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status });
const absent = (k = key) =>
  response({ ok: true, preparation: { state: "not_observed", key: k } });
const found = (k = key) =>
  response({ ok: true, preparation: { state: "found", key: k }, task });
const receipt = () =>
  response({
    ok: true,
    preparation: { version: 1, key, disposition: "existing" },
    task,
  });
function setup(
  fetch: ReturnType<typeof vi.fn>,
  onFound = vi.fn(async () => {}),
) {
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(window.crypto, "randomUUID").mockReturnValue(key);
  return renderHook(
    ({ project = "river", cap = capability, tasks = [] as Task[] }) =>
      usePreparationRecovery(project, cap, tasks, onFound),
    {
      initialProps: { project: "river", cap: capability, tasks: [] as Task[] },
    },
  );
}
afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("keeps not_observed unknown and retries only the same retained payload/key explicitly", async () => {
  let posts = 0;
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) => {
    if (options?.method === "POST") {
      posts++;
      if (posts === 1) throw new TypeError("lost");
      return receipt();
    }
    return absent();
  });
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(result.current.entries[0].phase).toBe("not_observed");
  expect(result.current.blocked).toBe(true);
  expect(result.current.canRetry(key)).toBe(true);
  await expect(
    result.current.prepare({ ...payload, instructions: "different" }),
  ).rejects.toThrow("pending");
  expect(posts).toBe(1);
  expect(JSON.parse(localStorage.getItem(prefix + key)!)).toEqual(identity());
  await act(async () => {
    await result.current.retry(key);
  });
  expect(posts).toBe(2);
  const writes = fetch.mock.calls.filter((call) => call[1]?.method === "POST");
  expect(writes[1][1]?.body).toBe(writes[0][1]?.body);
  expect(result.current.entries[0].phase).toBe("found");
  expect(localStorage.getItem(prefix + key)).not.toBeNull(); // not incorporated yet
  expect(fetch.mock.calls).toHaveLength(3);
});
it("reload never reconstructs a payload or offers same-key POST; ordinary refresh does not loop", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () => absent());
  const { result, rerender } = setup(fetch);
  await waitFor(() =>
    expect(result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(result.current.canRetry(key)).toBe(false);
  await act(async () => {
    await result.current.retry(key);
  });
  rerender({ project: "river", cap: { ...capability }, tasks: [] });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(result.current.blocked).toBe(true);
});
it("bounds automatic recovery to three exact scoped keys; other origins, workspaces and projects are ignored", async () => {
  for (let i = 0; i < 5; i++) {
    const k = `22222222-2222-4222-8222-22222222222${i}`;
    localStorage.setItem(prefix + k, JSON.stringify(identity(k)));
  }
  for (const p of [
    preparationPrefix("http://other:9999", namespace, "river"),
    preparationPrefix(
      window.location.origin,
      "33333333-3333-4333-8333-333333333333",
      "river",
    ),
    preparationPrefix(window.location.origin, namespace, "other"),
  ])
    localStorage.setItem(p + key, JSON.stringify(identity()));
  const fetch = vi.fn(async (url: unknown) =>
    absent(String(url).split("/").at(-1)),
  );
  const { result } = setup(fetch);
  await waitFor(() =>
    expect(
      result.current.entries.filter((e) => e.phase === "not_observed"),
    ).toHaveLength(3),
  );
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(result.current.entries).toHaveLength(5);
  expect(
    fetch.mock.calls.every((call) =>
      String(call[0]).includes("/projects/river/preparations/"),
    ),
  ).toBe(true);
});
it("storage denied sends nothing until explicit in-session confirmation", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Denied", "SecurityError");
  });
  const fetch = vi.fn(async () => receipt());
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(fetch).not.toHaveBeenCalled();
  expect(result.current.storageUnavailable).toBe(true);
  expect(result.current.entries[0].phase).toBe("unsent");
  await act(async () => {
    await result.current.retry(key);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(result.current.entries[0].phase).toBe("found");
});
it.each(["request_key_conflict", "workspace_mismatch"])(
  "does not fall back or replay on %s",
  async (code) => {
    const fetch = vi.fn(async () =>
      response({ ok: false, code, error: "Conflict" }, 400),
    );
    const { result } = setup(fetch);
    await act(async () => {
      await result.current.prepare(payload);
    });
    expect(result.current.entries[0].phase).toBe("conflict");
    expect(result.current.canRetry(key)).toBe(false);
    expect(result.current.blocked).toBe(true);
    await act(async () => {
      await result.current.retry(key);
      await result.current.check(key);
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  },
);
it("unknown read failures retain pending identity and original payload, without automatic retry", async () => {
  const fetch = vi.fn(async () => {
    throw new TypeError("offline");
  });
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(result.current.entries[0].phase).toBe("error");
  expect(result.current.blocked).toBe(true);
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
});
it("a generic ledger error is uncertain, not a confirmed refusal", async () => {
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) =>
    options?.method === "POST"
      ? response(
          { ok: false, code: "ledger_unavailable", error: "Unavailable" },
          400,
        )
      : absent(),
  );
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(result.current.entries[0].phase).toBe("not_observed");
});
it("clears persisted identity only after the exact task is in authoritative project state", async () => {
  const fetch = vi.fn(async () => receipt());
  const { result, rerender } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
  rerender({
    project: "river",
    cap: capability,
    tasks: [{ ...task, id: "other-task" }],
  });
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
  rerender({ project: "river", cap: capability, tasks: [task] });
  await waitFor(() => expect(localStorage.getItem(prefix + key)).toBeNull());
});
it("a refresh failure does not demote a confirmed preparation or offer another POST", async () => {
  const fetch = vi.fn(async () => receipt());
  const { result } = setup(
    fetch,
    vi.fn(async () => {
      throw new Error("refresh failed");
    }),
  );
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(result.current.entries[0].phase).toBe("found");
  expect(result.current.canRetry(key)).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
});
it("ignores late lookup from a previous project, even if its transport ignores abort", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => (finish = resolve)),
  );
  const notify = vi.fn(async () => {});
  const { result, rerender } = setup(fetch, notify);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  rerender({ project: "other", cap: capability, tasks: [] });
  await act(async () => {
    finish(found());
  });
  expect(result.current.entries).toHaveLength(0);
  expect(notify).not.toHaveBeenCalled();
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
});
it("rejects a found response from a different project instead of focusing a guessed task", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () =>
    response({
      ok: true,
      preparation: { state: "found", key },
      task: { ...task, project_id: "other" },
    }),
  );
  const notify = vi.fn(async () => {});
  const { result } = setup(fetch, notify);
  await waitFor(() => expect(result.current.entries[0]?.phase).toBe("error"));
  expect(notify).not.toHaveBeenCalled();
  expect(result.current.blocked).toBe(true);
});
it("fails closed if secure UUID generation is unavailable", async () => {
  const fetch = vi.fn();
  const { result } = setup(fetch);
  vi.spyOn(window.crypto, "randomUUID").mockImplementation(() => {
    throw new Error("Unavailable");
  });
  await expect(result.current.prepare(payload)).rejects.toThrow(
    "no task was sent",
  );
  expect(fetch).not.toHaveBeenCalled();
  expect(localStorage.length).toBe(0);
});
it("future capability versions do not issue reconciliation requests", () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() =>
    usePreparationRecovery(
      "river",
      { ...capability, version: 2 },
      [],
      async () => {},
    ),
  );
  expect(result.current.supported).toBe(false);
  expect(fetch).not.toHaveBeenCalled();
});

it("StrictMode probe mount does not duplicate the bounded automatic exact lookup", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () => absent());
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(
    () => usePreparationRecovery("river", capability, [], async () => {}),
    { wrapper: StrictMode },
  );
  await waitFor(() =>
    expect(result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("parallel clicks cannot allocate a second key or send the same request concurrently", async () => {
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => (finish = resolve)),
  );
  const { result } = setup(fetch);
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.prepare(payload);
  });
  await expect(result.current.prepare(payload)).rejects.toThrow("pending");
  await act(async () => {
    await result.current.retry(key);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish(receipt());
    await pending;
  });
});

it("parks only by explicit action, preserves opaque identity and read-only recovery across reload", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () => absent());
  const first = setup(fetch);
  await waitFor(() =>
    expect(first.result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(first.result.current.blocked).toBe(true);
  act(() => {
    expect(first.result.current.park(key)).toBe(true);
    expect(first.result.current.park(key)).toBe(false);
  });
  expect(first.result.current.entries[0].parked).toBe(true);
  expect(first.result.current.blocked).toBe(false);
  expect(first.result.current.canRetry(key)).toBe(false);
  expect(localStorage.getItem(prefix + key)).toBe(JSON.stringify(identity()));
  const markerKey = `research-hub:disposition:v1:${encodeURIComponent(location.origin)}:${namespace}:river:prepare:${key}`;
  expect(JSON.parse(localStorage.getItem(markerKey)!)).toEqual({
    version: 1,
    origin: location.origin,
    workspace_instance_id: namespace,
    project_id: "river",
    type: "prepare",
    key,
    disposition: "parked",
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(crypto.randomUUID).not.toHaveBeenCalled();
  first.unmount();
  const next = setup(fetch);
  await waitFor(() =>
    expect(next.result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(next.result.current.entries[0].parked).toBe(true);
  expect(next.result.current.blocked).toBe(false);
  await act(async () => {
    await next.result.current.retry(key);
  });
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("session-only parking needs second confirmation and reload conservatively relocks", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () => absent());
  const first = setup(fetch);
  await waitFor(() =>
    expect(first.result.current.entries[0]?.phase).toBe("not_observed"),
  );
  const denied = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw Error("synthetic denied");
    });
  act(() => {
    expect(first.result.current.park(key, true)).toBe(false);
    expect(first.result.current.park(key)).toBe(false);
  });
  expect(first.result.current.blocked).toBe(true);
  act(() => {
    expect(first.result.current.park(key, true)).toBe(true);
  });
  expect(first.result.current.entries[0].parkSessionOnly).toBe(true);
  expect(localStorage.getItem(prefix + key)).toBe(JSON.stringify(identity()));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(crypto.randomUUID).not.toHaveBeenCalled();
  denied.mockRestore();
  first.unmount();
  const next = setup(fetch);
  await waitFor(() =>
    expect(next.result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(next.result.current.blocked).toBe(true);
  expect(next.result.current.canRetry(key)).toBe(false);
});
it.each(["extra", "scope", "type", "oversized", "malformed", "orphan"])(
  "ignores %s parking marker without granting authority",
  async (variant) => {
    if (variant !== "orphan")
      localStorage.setItem(prefix + key, JSON.stringify(identity()));
    const markerKey = `research-hub:disposition:v1:${encodeURIComponent(location.origin)}:${namespace}:river:prepare:${key}`;
    const value = {
      version: 1,
      origin: location.origin,
      workspace_instance_id: namespace,
      project_id: "river",
      type: "prepare",
      key,
      disposition: "parked",
    };
    localStorage.setItem(
      markerKey,
      variant === "malformed"
        ? "{"
        : variant === "oversized"
          ? " ".repeat(2000) + JSON.stringify(value)
          : JSON.stringify({
              ...value,
              ...(variant === "extra" ? { title: "not opaque" } : {}),
              ...(variant === "scope" ? { project_id: "other" } : {}),
              ...(variant === "type" ? { type: "text-intake" } : {}),
            }),
    );
    const fetch = vi.fn(async () => absent());
    const { result } = setup(fetch);
    if (variant === "orphan") {
      await act(async () => {
        await Promise.resolve();
      });
      expect(result.current.entries).toHaveLength(0);
      expect(fetch).not.toHaveBeenCalled();
    } else {
      await waitFor(() =>
        expect(result.current.entries[0]?.phase).toBe("not_observed"),
      );
      expect(result.current.blocked).toBe(true);
      expect(result.current.entries[0].parked).toBe(false);
    }
  },
);
it("parked live conflict remains exact-checkable, never replayable; only explicit new submit allocates another key", async () => {
  const nextKey = "33333333-3333-4333-8333-333333333333";
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) =>
    options?.method === "POST"
      ? response(
          {
            ok: false,
            code: "request_key_conflict",
            error: "Synthetic conflict",
          },
          409,
        )
      : absent(),
  );
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.prepare(payload);
  });
  expect(result.current.entries[0].phase).toBe("conflict");
  act(() => {
    expect(result.current.park(key)).toBe(true);
  });
  await act(async () => {
    await result.current.retry(key);
    await result.current.check(key);
  });
  expect(result.current.entries[0].phase).toBe("not_observed");
  expect(fetch.mock.calls.filter((c) => c[1]?.method === "POST")).toHaveLength(
    1,
  );
  vi.mocked(crypto.randomUUID).mockReturnValue(nextKey);
  await act(async () => {
    await result.current.prepare(payload);
  });
  const posts = fetch.mock.calls.filter((c) => c[1]?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(JSON.parse(String(posts[1][1]?.body)).prepare_request.key).toBe(
    nextKey,
  );
  expect(localStorage.getItem(prefix + key)).toBe(JSON.stringify(identity()));
});

it("cannot park while an exact read or POST is in flight", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  let finish!: (response: Response) => void;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
  );
  const first = setup(fetch);
  await waitFor(() =>
    expect(first.result.current.entries[0]?.phase).toBe("checking"),
  );
  act(() => {
    expect(first.result.current.park(key)).toBe(false);
  });
  await act(async () => {
    finish(absent());
  });
  first.unmount();
  localStorage.clear();
  const second = setup(fetch);
  let pending!: Promise<unknown>;
  act(() => {
    pending = second.result.current.prepare(payload);
  });
  await waitFor(() =>
    expect(second.result.current.entries[0]?.phase).toBe("sending"),
  );
  act(() => {
    expect(second.result.current.park(key)).toBe(false);
  });
  await act(async () => {
    finish(receipt());
    await pending;
  });
  expect(second.result.current.entries[0].phase).toBe("found");
  expect(second.result.current.entries[0].parked).not.toBe(true);
});
