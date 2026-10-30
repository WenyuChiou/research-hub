import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { translator } from "./i18n";
const t = translator("en");
const namespace = "11111111-1111-4111-8111-111111111111",
  key = "22222222-2222-4222-8222-222222222222";
const project = {
  id: "river",
  title: "Public river study",
  archetype: "review",
  goal: "Read a source",
};
const workspace = {
  ok: true,
  projects: [project],
  capabilities: {
    codex: { status: "unavailable", message: "Unavailable" },
    writing: { status: "unavailable", message: "Unavailable" },
    approval: { status: "unavailable", message: "Unavailable" },
    prepare_reconciliation: { version: 1, workspace_instance_id: namespace },
    text_intake: {
      version: 1,
      status: "available",
      workspace_instance_id: namespace,
      max_source_bytes: 40000,
      formats: ["txt", "md"],
      message: "Bounded local copies",
    },
  },
  protection_scope: "Local only",
};
const detail = {
  ok: true,
  project,
  records: [],
  artifacts: [],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const text = "Public abstract 😀\r\nSecond line.";
const artifact = {
  id: "saved-artifact",
  project_id: project.id,
  path: "hub-sources/river/saved-source/copy.txt",
  role: "evidence",
  sha256: "a".repeat(64),
  current: true,
  source_record_id: "saved-source",
  origin: "hub-text-intake",
};
const record = {
  id: "saved-source",
  kind: "source",
  data: {
    title: "Public paper",
    locator: "hub-source:saved-source",
    locator_kind: "local-copy",
    identity_status: "unverified",
    publication_version: "unknown",
    human_acceptance: "pending",
    reading_scope: "unknown",
    intake: {
      version: 1,
      key,
      artifact_id: artifact.id,
      sha256: artifact.sha256,
      input_kind: "paste",
      format: "txt",
      payload_digest: "b".repeat(64),
    },
  },
};
const preview = {
  artifact_id: artifact.id,
  path: artifact.path,
  sha256: artifact.sha256,
  text,
  codepoint_length: Array.from(text).length,
  bytes_read: new TextEncoder().encode(text).length,
  truncated: false,
};
const pair = { record, artifact, preview, preview_status: "available" };
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function serve(lost = false) {
  let saved = false;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.endsWith(`/source-text/${key}`))
        return response({
          ok: true,
          intake: { version: 1, key, state: "found" },
          ...pair,
        });
      if (options?.method === "POST") {
        saved = true;
        if (lost) throw new TypeError("reply lost");
        return response({
          ok: true,
          intake: { version: 1, key, disposition: "created" },
          ...pair,
        });
      }
      return response(
        saved
          ? { ...detail, records: [record], artifacts: [artifact] }
          : detail,
      );
    },
  );
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(key);
  return fetch;
}
async function savePaste() {
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Add existing text" }),
  );
  await user.type(screen.getByLabelText("Text title"), "Public paper");
  fireEvent.change(screen.getByLabelText("Paste abstract or text"), {
    target: { value: text },
  });
  await user.click(screen.getByRole("button", { name: "Save Hub text copy" }));
}
it("saves pasted text from empty Literature and opens its linked preview without staging paths or preparing a task", async () => {
  const fetch = serve();
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  const area = await screen.findByLabelText(t("abstractText"));
  expect(area).toHaveValue(text.replace(/\r\n/g, "\n"));
  expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue(
    artifact.id,
  );
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeDisabled();
  const writes = fetch.mock.calls.filter((call) => call[1]?.method === "POST");
  expect(writes).toHaveLength(1);
  expect(String(writes[0][0])).toContain("/source-text");
  expect(JSON.parse(String(writes[0][1]?.body)).intake_request).toEqual({
    version: 1,
    workspace_instance_id: namespace,
    key,
  });
  expect(
    fetch.mock.calls.some(
      (call) =>
        String(call[0]).endsWith("/text") ||
        String(call[0]).endsWith("/run") ||
        String(call[0]).endsWith("/tasks"),
    ),
  ).toBe(false);
}, 10000);
it("recovers a lost intake reply by one exact intake GET, never the Prepare endpoint", async () => {
  const fetch = serve(true);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  await screen.findByLabelText(t("abstractText"));
  expect(
    fetch.mock.calls.filter((call) =>
      String(call[0]).endsWith(`/source-text/${key}`),
    ),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(1);
  expect(
    fetch.mock.calls.some((call) => String(call[0]).includes("/preparations/")),
  ).toBe(false);
}, 10000);

it("preserves file bytes and uses explicit abstract selection before any Prepare", async () => {
  const rawText = "\ufeffHeader\r\n😀 abstract\rEnd",
    raw = new TextEncoder().encode(rawText);
  let inputBody: Record<string, unknown> | undefined,
    taskBody: Record<string, unknown> | undefined;
  const delegate = serve();
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (
        options?.method === "POST" &&
        String(input).endsWith("/source-text")
      ) {
        inputBody = JSON.parse(String(options.body));
        return response({
          ok: true,
          intake: { version: 1, key, disposition: "created" },
          ...pair,
          preview: {
            ...preview,
            text: rawText,
            codepoint_length: Array.from(rawText).length,
            bytes_read: raw.length,
          },
        });
      }
      if (options?.method === "POST" && String(input).endsWith("/tasks")) {
        taskBody = JSON.parse(String(options.body));
        return response(
          {
            ok: false,
            code: "invalid_source",
            error: "Synthetic stopped before task creation",
          },
          400,
        );
      }
      return delegate(input, options);
    },
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: t("intakeAdd") }));
  await user.selectOptions(screen.getByLabelText(t("intakeInput")), "file");
  await user.type(screen.getByLabelText(t("intakeTitle")), "Public file");
  await user.upload(
    screen.getByLabelText(t("intakeFile")),
    new File([raw], "public.md"),
  );
  await screen.findByText(t("intakeLocalPreview"));
  await user.click(screen.getByRole("button", { name: t("intakeSave") }));
  const area = (await screen.findByLabelText(
    t("abstractText"),
  )) as HTMLTextAreaElement;
  expect(
    Array.from(atob(String(inputBody!.content_base64)), (c) => c.charCodeAt(0)),
  ).toEqual(Array.from(raw));
  expect(inputBody).toMatchObject({
    input_kind: "file",
    format: "md",
    reading_scope: "unknown",
  });
  expect(inputBody).not.toHaveProperty("filename");
  expect(taskBody).toBeUndefined();
  act(() => {
    area.focus();
    area.setSelectionRange(8, 10);
    fireEvent.select(area);
  });
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  expect(taskBody?.source_selection).toEqual({
    artifact_id: artifact.id,
    source_record_id: record.id,
    start: 9,
    end: 10,
  });
  expect(
    fetch.mock.calls.some((call) => String(call[0]).endsWith("/run")),
  ).toBe(false);
}, 10000);
it("rejects invalid UTF-8 before saving and leaves source markup inert", async () => {
  const fetch = serve();
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: t("intakeAdd") }));
  await user.selectOptions(screen.getByLabelText(t("intakeInput")), "file");
  await user.type(screen.getByLabelText(t("intakeTitle")), "Public");
  await user.upload(
    screen.getByLabelText(t("intakeFile")),
    new File([new Uint8Array([0xff])], "bad.txt"),
  );
  expect(await screen.findByText(/not strict UTF-8/)).toBeVisible();
  expect(screen.getByRole("button", { name: t("intakeSave") })).toBeDisabled();
  await user.upload(
    screen.getByLabelText(t("intakeFile")),
    new File(
      ["<script>throw 1</script> ![image](https://example.org/image.png)"],
      "inert.md",
    ),
  );
  await screen.findByText(t("intakeLocalPreview"));
  expect(document.querySelector("script, img")).toBeNull();
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(0);
  expect(
    fetch.mock.calls.every((call) => String(call[0]).startsWith("/api/v1/")),
  ).toBe(true);
});
it("shows unsupported capability without writes while metadata-only source entry remains available", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("/workspace")
      ? response({
          ...workspace,
          capabilities: {
            ...workspace.capabilities,
            text_intake: {
              ...workspace.capabilities.text_intake,
              status: "unavailable",
              message: "Windows publication unsupported",
            },
          },
        })
      : response(detail),
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  expect(
    await screen.findByRole("button", { name: t("intakeAdd") }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: t("intakeAdd") })).toHaveAccessibleDescription(t("intakeUnavailable"));
  expect(screen.getByText(t("intakeUnavailable"))).toBeVisible();
  await user.click(screen.getByText(t("intakeDetails")));
  expect(screen.getByText(/Windows publication unsupported/)).toBeVisible();
  expect(screen.getByRole("button", { name: t("addSource") })).toBeEnabled();
  expect(
    fetch.mock.calls.some((call) => String(call[0]).includes("/source-text")),
  ).toBe(false);
});
it("discloses denied storage before the explicit session-only save", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Denied", "SecurityError");
  });
  const fetch = serve();
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(0);
  expect(screen.getByText(t("intakeStorageUnavailable"))).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeSessionOnly") }),
  );
  await waitFor(() =>
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1),
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeOpenSaved") }),
  );
  expect(await screen.findByLabelText(t("abstractText"))).toBeVisible();
});
const intakeStorageKey =
  "research-hub:text-intake:v1:" +
  encodeURIComponent(location.origin) +
  ":" +
  namespace +
  ":river:" +
  key;
const pendingIdentity = {
  version: 1,
  workspace_instance_id: namespace,
  project_id: project.id,
  key,
  state: "pending",
};
it("reload recovers only opaque identity; exact source opens even when the bulk project refresh fails", async () => {
  localStorage.setItem(intakeStorageKey, JSON.stringify(pendingIdentity));
  let reads = 0;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (options?.method === "POST") throw new Error("No replay allowed");
      const url = String(input);
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.endsWith(`/source-text/${key}`))
        return response({
          ok: true,
          intake: { version: 1, key, state: "found" },
          ...pair,
        });
      reads++;
      return reads === 1
        ? response(detail)
        : response(
            { ok: false, error: "Public synthetic refresh unavailable" },
            503,
          );
    },
  );
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await screen.findByText(t("refreshError"));
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeOpenSaved") }),
  );
  expect(await screen.findByLabelText(t("abstractText"))).toHaveValue(
    text.replace(/\r\n/g, "\n"),
  );
  expect(screen.getByText(t("refreshRetained"))).toBeVisible();
  expect(
    fetch.mock.calls.filter((call) =>
      String(call[0]).endsWith(`/source-text/${key}`),
    ),
  ).toHaveLength(1);
  expect(fetch.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
    false,
  );
  expect(localStorage.getItem(intakeStorageKey)).toBeNull();
});
it("not_observed stays unknown; manual retry retains byte-identical payload and the same key", async () => {
  let posts = 0;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.endsWith(`/source-text/${key}`))
        return response({
          ok: true,
          intake: { version: 1, key, state: "not_observed" },
        });
      if (options?.method === "POST") {
        posts++;
        expect(JSON.parse(localStorage.getItem(intakeStorageKey)!)).toEqual(
          pendingIdentity,
        );
        if (posts === 1) throw new TypeError("Lost");
        return response({
          ok: true,
          intake: { version: 1, key, disposition: "existing" },
          ...pair,
        });
      }
      return response(detail);
    },
  );
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(key);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  expect(await screen.findByText(t("intakeNotObserved"))).toBeVisible();
  expect(posts).toBe(1);
  expect(screen.getByRole("button", { name: t("intakeSave") })).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeRetrySame") }),
  );
  await screen.findByRole("button", { name: t("intakeOpenSaved") });
  const writes = fetch.mock.calls.filter((call) => call[1]?.method === "POST");
  expect(writes).toHaveLength(2);
  expect(writes[1][1]?.body).toBe(writes[0][1]?.body);
  expect(
    fetch.mock.calls.some(
      (call) =>
        String(call[0]).includes("/preparations/") ||
        String(call[0]).endsWith("/run"),
    ),
  ).toBe(false);
});
it("late save after Cancel and newer navigation stays recoverable without hijacking the page", async () => {
  const delegate = serve();
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) =>
      options?.method === "POST"
        ? new Promise<Response>((resolve) => (finish = resolve))
        : delegate(input, options),
  );
  vi.stubGlobal("fetch", fetch);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  await userEvent.click(screen.getByRole("button", { name: t("cancel") }));
  act(() => {
    window.history.replaceState({}, "", "#manuscript");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await act(async () => {
    finish(
      response({
        ok: true,
        intake: { version: 1, key, disposition: "created" },
        ...pair,
      }),
    );
  });
  expect(
    await screen.findByRole("button", { name: t("intakeOpenSaved") }),
  ).toBeVisible();
  expect(location.hash).toBe("#manuscript");
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeOpenSaved") }),
  );
  expect(await screen.findByLabelText(t("abstractText"))).toBeVisible();
});
it("retains a saved stale pair without inventing preview text or automatically preparing", async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) =>
    String(input).endsWith("/workspace")
      ? response(workspace)
      : String(input).endsWith(`/source-text/${key}`)
        ? response({
            ok: true,
            intake: { version: 1, key, state: "found" },
            record,
            artifact: { ...artifact, current: false },
            preview: null,
            preview_status: "stale",
          })
        : response(detail),
  );
  localStorage.setItem(intakeStorageKey, JSON.stringify(pendingIdentity));
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await screen.findByText(t("intakeSavedUnavailable"));
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeOpenSaved") }),
  );
  expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.some(
      (call) =>
        String(call[0]).endsWith("/text") || String(call[0]).endsWith("/tasks"),
    ),
  ).toBe(false);
});

it("independent Open saved text restores its linked artifact after another evidence file was selected", async () => {
  const other = {
    ...artifact,
    id: "other-evidence",
    path: "evidence/other.txt",
    source_record_id: undefined,
    origin: undefined,
  };
  const otherText = "Other evidence, not the saved local copy.";
  let saved = false;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/workspace")) return response(workspace);
      if (url.endsWith("/source-text") && options?.method === "POST") {
        saved = true;
        return response({
          ok: true,
          intake: { version: 1, key, disposition: "created" },
          ...pair,
        });
      }
      if (url.endsWith("/artifacts/other-evidence/text"))
        return response({
          ok: true,
          preview: {
            ...preview,
            artifact_id: other.id,
            path: other.path,
            text: otherText,
            codepoint_length: Array.from(otherText).length,
            bytes_read: new TextEncoder().encode(otherText).length,
          },
        });
      if (url.endsWith("/projects/river"))
        return response({
          ...detail,
          records: saved ? [record] : [],
          artifacts: saved ? [artifact, other] : [other],
        });
      throw new Error(`Unexpected request ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(key);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  expect(await screen.findByLabelText(t("abstractText"))).toHaveValue(
    text.replace(/\r\n/g, "\n"),
  );
  await userEvent.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    other.id,
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("abstractReadText") }),
  );
  expect(await screen.findByLabelText(t("abstractText"))).toHaveValue(
    otherText,
  );
  await userEvent.click(
    screen.getByRole("button", { name: t("intakeOpenSaved") }),
  );
  expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue(
    artifact.id,
  );
  expect(screen.getByLabelText(t("abstractText"))).toHaveValue(
    text.replace(/\r\n/g, "\n"),
  );
  expect(
    fetch.mock.calls.filter((call) => call[1]?.method === "POST"),
  ).toHaveLength(1);
}, 10000);

it("newer source choice on the same page is not replaced by a late text save", async () => {
  const existing = {
    id: "other-source",
    kind: "source",
    data: {
      title: "Existing public source",
      locator: "https://example.org/other",
    },
  };
  let saved = false;
  let finish!: (r: Response) => void;
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).endsWith("/workspace")) return response(workspace);
      if (options?.method === "POST")
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      return response({
        ...detail,
        records: saved ? [existing, record] : [existing],
        artifacts: saved ? [artifact] : [],
      });
    },
  );
  vi.stubGlobal("fetch", fetch);
  vi.spyOn(crypto, "randomUUID").mockReturnValue(key);
  window.history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  await userEvent.click(
    screen.getByRole("button", { name: t("abstractOpen") }),
  );
  expect(screen.queryByLabelText(t("intakeTitle"))).not.toBeInTheDocument();
  await act(async () => {
    saved = true;
    finish(
      response({
        ok: true,
        intake: { version: 1, key, disposition: "created" },
        ...pair,
      }),
    );
  });
  await screen.findByRole("button", { name: t("intakeOpenSaved") });
  expect(screen.getByLabelText(t("abstractChooseFile"))).toHaveValue("");
  expect(screen.queryByLabelText(t("abstractText"))).not.toBeInTheDocument();
  expect(location.hash).toBe("#literature");
});
it("park keeps old input locked until explicit empty separate intake; late found preserves new title", async () => {
  const fetch = serve(),
    original = fetch.getMockImplementation()!;
  let oldFound = false;
  fetch.mockImplementation(async (input, options) => {
    if (options?.method === "POST") throw TypeError("Synthetic lost reply");
    if (String(input).includes("/source-text/"))
      return response({
        ok: true,
        intake: { version: 1, key, state: oldFound ? "found" : "not_observed" },
        ...(oldFound ? pair : {}),
      });
    return original(input, options);
  });
  history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  await screen.findByText(t("intakeNotObserved"));
  fireEvent.click(screen.getByText(t("recoveryPark")));
  fireEvent.click(screen.getByText(t("recoveryParkConfirm")));
  expect(screen.getByLabelText(t("intakeTitle"))).toHaveValue("Public paper");
  expect(screen.getByRole("button", { name: t("intakeSave") })).toBeDisabled();
  fireEvent.click(screen.getByText(t("recoverySeparate")));
  expect(screen.getByLabelText(t("intakeTitle"))).toHaveValue("");
  expect(screen.getByLabelText(t("intakePasteMode"))).toHaveValue("");
  fireEvent.change(screen.getByLabelText(t("intakeTitle")), {
    target: { value: "Different intent" },
  });
  await userEvent.click(screen.getByRole("link", { name: "Manuscript" }));
  oldFound = true;
  fireEvent.click(screen.getByText(t("intakeCheck")));
  await screen.findByText(t("intakeOpenSaved"));
  expect(location.hash).toBe("#manuscript");
  expect(screen.getByLabelText(t("intakeTitle"))).toHaveValue(
    "Different intent",
  );
  expect(fetch.mock.calls.filter((c) => c[1]?.method === "POST")).toHaveLength(
    1,
  );
  expect(fetch.mock.calls.some((c) => String(c[0]).includes("/run"))).toBe(
    false,
  );
});
it("exact saved source label retains artifact ID, title, declared scope and path without a new read", async () => {
  const fetch = serve();
  history.replaceState({}, "", "#literature");
  render(<App />);
  await savePaste();
  await screen.findByLabelText(t("abstractText"));
  const select = screen.getByLabelText(
    t("abstractChooseFile"),
  ) as HTMLSelectElement;
  const option = Array.from(select.options).find(
    (o) => o.value === artifact.id,
  )!;
  expect(select).toHaveValue(artifact.id);
  expect(option.textContent).toContain(record.data.title);
  expect(option.textContent).toContain(t("intakeScopeUnknown"));
  expect(option.textContent).toContain(artifact.path);
  expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/text"))).toBe(
    false,
  );
});
