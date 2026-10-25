import { StrictMode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { intakePrefix, useTextIntakeRecovery } from "./TextIntakeRecovery";
import type { ProjectDetail } from "./types";
import type { IntakePayload } from "./textIntake";
const namespace = "11111111-1111-4111-8111-111111111111",
  key = "22222222-2222-4222-8222-222222222222";
const capability = {
  version: 1,
  status: "available",
  workspace_instance_id: namespace,
  max_source_bytes: 40000,
  formats: ["txt", "md"],
  message: "Local copies",
};
const detail = {
  project: {
    id: "river",
    title: "Public project",
    archetype: "review",
    goal: "Read",
  },
  records: [],
  artifacts: [],
  tasks: [],
  actions: [],
  warnings: [],
  manuscript: null,
  workflow: null,
} as unknown as ProjectDetail;
const payload: IntakePayload = {
  title: "Public",
  locator: "",
  input_kind: "paste",
  reading_scope: "unknown",
  format: "txt",
  content_base64: btoa("Abstract"),
};
const record = {
  id: "saved-source",
  kind: "source",
  data: {
    title: "Public",
    intake: {
      version: 1,
      key,
      artifact_id: "saved-artifact",
      sha256: "a".repeat(64),
    },
  },
};
const artifact = {
  id: "saved-artifact",
  project_id: "river",
  source_record_id: record.id,
  origin: "hub-text-intake",
  role: "evidence",
  sha256: "a".repeat(64),
  path: "hub-sources/river/copy.txt",
  current: true,
};
const pair = {
  record,
  artifact,
  preview: {
    artifact_id: artifact.id,
    path: artifact.path,
    sha256: artifact.sha256,
    text: "Abstract",
    codepoint_length: 8,
    bytes_read: 8,
    truncated: false,
  },
  preview_status: "available",
};
const prefix = intakePrefix(location.origin, namespace, "river");
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
  response({ ok: true, intake: { version: 1, key: k, state: "not_observed" } });
const receipt = () =>
  response({
    ok: true,
    intake: { version: 1, key, disposition: "created" },
    ...pair,
  });
function setup(
  fetch: ReturnType<typeof vi.fn>,
  notify = vi.fn(async () => {}),
) {
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(key);
  return renderHook(
    ({ project = "river", cap = capability, snapshot = detail }) =>
      useTextIntakeRecovery(project, cap, snapshot, notify),
    { initialProps: { project: "river", cap: capability, snapshot: detail } },
  );
}
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("saves only opaque intake identity before POST, never title/locator/bytes/prepare identity", async () => {
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) => {
    expect(JSON.parse(localStorage.getItem(prefix + key)!)).toEqual(identity());
    expect(JSON.parse(String(options?.body)).intake_request).toEqual({
      version: 1,
      workspace_instance_id: namespace,
      key,
    });
    return receipt();
  });
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.submit(payload);
  });
  expect(localStorage.length).toBe(1);
  expect(localStorage.key(0)).toBe(prefix + key);
  expect(result.current.entries[0].phase).toBe("found");
});
it("reload does not reconstruct payload or loop on normal refresh", async () => {
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
  rerender({
    project: "river",
    cap: { ...capability },
    snapshot: { ...detail },
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(result.current.blocked).toBe(true);
});
it("bounds automatic reads and ignores Prepare/other origins/workspaces/projects and poisoned values", async () => {
  for (let i = 0; i < 5; i++) {
    const k = "22222222-2222-4222-8222-22222222222" + i;
    localStorage.setItem(prefix + k, JSON.stringify(identity(k)));
  }
  for (const p of [
    intakePrefix("http://other:9999", namespace, "river"),
    intakePrefix(
      location.origin,
      "33333333-3333-4333-8333-333333333333",
      "river",
    ),
    intakePrefix(location.origin, namespace, "other"),
    prefix.replace("text-intake", "prepare"),
  ])
    localStorage.setItem(p + key, JSON.stringify(identity()));
  localStorage.setItem(
    prefix + key,
    JSON.stringify({ ...identity(), content_base64: payload.content_base64 }),
  );
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
  expect(result.current.entries).toHaveLength(4); // poisoned key overlaps one of the five
});
it("StrictMode does not duplicate an automatic lookup", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () => absent());
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(
    () => useTextIntakeRecovery("river", capability, detail, async () => {}),
    { wrapper: StrictMode },
  );
  await waitFor(() =>
    expect(result.current.entries[0]?.phase).toBe("not_observed"),
  );
  expect(fetch).toHaveBeenCalledTimes(1);
});
it.each(["request_key_conflict", "workspace_mismatch", "file_conflict"])(
  "does not silently replay or allocate another key for %s",
  async (code) => {
    const fetch = vi.fn(async () =>
      response({ ok: false, code, error: "Public conflict" }, 400),
    );
    const { result } = setup(fetch);
    await act(async () => {
      await result.current.submit(payload);
    });
    expect(result.current.entries[0].phase).toBe("conflict");
    expect(result.current.canRetry(key)).toBe(false);
    await act(async () => {
      await result.current.retry(key);
      await result.current.check(key);
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(result.current.blocked).toBe(true);
  },
);
it("storage and ledger failures remain unknown, with one exact lookup rather than new-key save", async () => {
  const fetch = vi.fn(async (_url: unknown, options?: RequestInit) =>
    options?.method === "POST"
      ? response(
          {
            ok: false,
            code: "storage_unavailable",
            error: "An interrupted copy may remain",
          },
          400,
        )
      : absent(),
  );
  const { result } = setup(fetch);
  await act(async () => {
    await result.current.submit(payload);
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(result.current.entries[0].phase).toBe("not_observed");
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
});
it("wrong-project or broken returned linkage cannot be exposed as a saved source", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  const fetch = vi.fn(async () =>
    response({
      ok: true,
      intake: { version: 1, key, state: "found" },
      ...pair,
      artifact: { ...artifact, project_id: "other" },
    }),
  );
  const notify = vi.fn(async () => {});
  const { result } = setup(fetch, notify);
  await waitFor(() => expect(result.current.entries[0]?.phase).toBe("error"));
  expect(notify).not.toHaveBeenCalled();
  expect(result.current.blocked).toBe(true);
});
it("keeps known saved result if bulk refresh throws and only clears storage after incorporation", async () => {
  const fetch = vi.fn(async () => receipt());
  const { result, rerender } = setup(
    fetch,
    vi.fn(async () => {
      throw new Error("refresh unavailable");
    }),
  );
  await act(async () => {
    await result.current.submit(payload);
  });
  expect(result.current.entries[0].phase).toBe("found");
  expect(result.current.canRetry(key)).toBe(false);
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
  rerender({
    project: "river",
    cap: capability,
    snapshot: { ...detail, records: [record], artifacts: [artifact] },
  });
  await waitFor(() => expect(localStorage.getItem(prefix + key)).toBeNull());
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("ignores a late POST result after a project switch", async () => {
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => (finish = resolve)),
  );
  const notify = vi.fn(async () => {});
  const { result, rerender } = setup(fetch, notify);
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.submit(payload);
  });
  rerender({
    project: "other",
    cap: capability,
    snapshot: { ...detail, project: { ...detail.project, id: "other" } },
  });
  await act(async () => {
    finish(receipt());
    await pending;
  });
  expect(result.current.entries).toHaveLength(0);
  expect(notify).not.toHaveBeenCalled();
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
});
it("duplicate live clicks cannot send twice or allocate a replacement key", async () => {
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => (finish = resolve)),
  );
  const { result } = setup(fetch);
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.submit(payload);
  });
  await expect(result.current.submit(payload)).rejects.toThrow("pending");
  await act(async () => {
    await result.current.retry(key);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish(receipt());
    await pending;
  });
});
it("cryptographic identity failure sends and persists nothing", async () => {
  const fetch = vi.fn();
  const { result } = setup(fetch);
  vi.spyOn(crypto, "randomUUID").mockImplementation(() => {
    throw new Error("Unavailable");
  });
  await expect(result.current.submit(payload)).rejects.toThrow(
    "no text was sent",
  );
  expect(fetch).not.toHaveBeenCalled();
  expect(localStorage.length).toBe(0);
});

it("late exact lookup after a project switch cannot merge or consume the old identity", async () => {
  localStorage.setItem(prefix + key, JSON.stringify(identity()));
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    () => new Promise<Response>((resolve) => (finish = resolve)),
  );
  const notify = vi.fn(async () => {});
  const { result, rerender } = setup(fetch, notify);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  rerender({
    project: "other",
    cap: capability,
    snapshot: { ...detail, project: { ...detail.project, id: "other" } },
  });
  await act(async () => {
    finish(
      response({
        ok: true,
        intake: { version: 1, key, state: "found" },
        ...pair,
      }),
    );
  });
  expect(result.current.entries).toHaveLength(0);
  expect(notify).not.toHaveBeenCalled();
  expect(localStorage.getItem(prefix + key)).not.toBeNull();
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
  const markerKey = `research-hub:disposition:v1:${encodeURIComponent(location.origin)}:${namespace}:river:text-intake:${key}`;
  expect(JSON.parse(localStorage.getItem(markerKey)!)).toEqual({
    version: 1,
    origin: location.origin,
    workspace_instance_id: namespace,
    project_id: "river",
    type: "text-intake",
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
    const markerKey = `research-hub:disposition:v1:${encodeURIComponent(location.origin)}:${namespace}:river:text-intake:${key}`;
    const value = {
      version: 1,
      origin: location.origin,
      workspace_instance_id: namespace,
      project_id: "river",
      type: "text-intake",
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
              ...(variant === "type" ? { type: "prepare" } : {}),
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
    await result.current.submit(payload);
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
    await result.current.submit(payload);
  });
  const posts = fetch.mock.calls.filter((c) => c[1]?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(JSON.parse(String(posts[1][1]?.body)).intake_request.key).toBe(
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
    pending = second.result.current.submit(payload);
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
