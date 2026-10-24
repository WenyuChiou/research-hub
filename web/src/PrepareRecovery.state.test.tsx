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
