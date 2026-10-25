import { act, render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { translator } from "./i18n";
const t = translator("en");
const namespace = "11111111-1111-4111-8111-111111111111";
const project = {
  id: "selected",
  title: "Synthetic project",
  archetype: "review",
  goal: "Synthetic",
};
const sources = ["a", "b"].map((id) => ({
  id: "source-" + id,
  kind: "source",
  data: {
    title: "Same synthetic title",
    locator: "https://example.invalid/" + id,
  },
}));
const artifacts = ["a", "b"].map((id) => ({
  id: "file-" + id,
  path: "synthetic-" + id + ".txt",
  role: "evidence",
  sha256: id.repeat(64),
  current: true,
}));
const detail = {
  ok: true,
  project,
  records: [
    ...sources,
    ...["a", "b"].map((id) => ({
      id: "decision-" + id,
      kind: "screening",
      data: {
        source_id: "source-" + id,
        decision: "include",
        rationale: "Synthetic",
      },
    })),
  ],
  artifacts,
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
};
const response = (value: unknown) =>
  new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});
async function setup(mode: string) {
  window.history.replaceState({}, "", "/#literature");
  const fetch = vi.fn(
    async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (options?.method === "POST")
        throw new TypeError("Synthetic lost Prepare response");
      if (url.includes("/preparations/"))
        return response({
          ok: true,
          preparation: { state: "not_observed", key: url.split("/").pop() },
        });
      if (url.endsWith("/text")) {
        const a = artifacts.find((a) => url.includes(a.id))!;
        return response({
          ok: true,
          preview: {
            artifact_id: a.id,
            path: a.path,
            sha256: a.sha256,
            text: "Selected synthetic passage " + a.id,
            codepoint_length: 33,
            bytes_read: 33,
            truncated: false,
          },
        });
      }
      return response(
        url.endsWith("/workspace")
          ? {
              ok: true,
              projects: [
                project,
                { ...project, id: "other", title: "Other synthetic project" },
              ],
              capabilities: {
                codex: { status: "unavailable" },
                writing: { status: "unavailable" },
                approval: { status: "unavailable" },
                ...(mode.startsWith("durable")
                  ? {
                      prepare_reconciliation: {
                        version: 1,
                        workspace_instance_id: namespace,
                      },
                    }
                  : {}),
              },
              protection_scope: "Synthetic",
            }
          : url.includes("/projects/other")
            ? {
                ...detail,
                project: {
                  ...project,
                  id: "other",
                  title: "Other synthetic project",
                },
              }
            : detail,
      );
    },
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("heading", { name: "Screening decisions" });
  await user.click(
    within(document.getElementById("record-source-a")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  await user.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    "file-a",
  );
  await user.click(screen.getByRole("button", { name: t("abstractReadText") }));
  await screen.findByLabelText(t("abstractText"));
  await user.click(
    screen.getByRole("button", { name: t("abstractSelectEntire") }),
  );
  await user.type(
    screen.getByLabelText(t("abstractPurpose")),
    "Retain synthetic purpose A",
  );
  if (mode !== "unsent" && mode !== "durable-ready") {
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    await screen.findByText(
      t(
        mode.startsWith("durable")
          ? "prepareNotObserved"
          : "abstractPrepareUncertain",
      ),
    );
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeDisabled();
  }
  return { user, fetch };
}
it.each(["unsent", "legacy-unknown", "durable-unknown"])(
  "screening returns B then A preserve existing %s composer, range and lock",
  async (mode) => {
    const { user, fetch } = await setup(mode);
    const input = screen.getByLabelText(t("abstractPurpose"));
    const text = screen.getByLabelText(t("abstractText"));
    const posts = fetch.mock.calls.filter(
      (c) => c[1]?.method === "POST",
    ).length;
    for (const id of ["b", "a"]) {
      await user.click(
        within(document.getElementById("record-decision-" + id)!).getByRole(
          "button",
          { name: t("abstractReturnSource") },
        ),
      );
      await waitFor(() =>
        expect(document.getElementById("record-source-" + id)).toHaveFocus(),
      );
      expect(screen.getByLabelText(t("abstractPurpose"))).toBe(input);
      expect(input).toHaveValue("Retain synthetic purpose A");
      expect(screen.getByLabelText(t("abstractText"))).toBe(text);
      expect(text).toHaveValue("Selected synthetic passage file-a");
      if (mode === "unsent")
        expect(
          screen.getByRole("button", { name: t("abstractPrepare") }),
        ).toBeEnabled();
      else
        expect(
          screen.getByRole("button", { name: t("abstractPrepare") }),
        ).toBeDisabled();
    }
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(posts);
    expect(posts).toBe(mode === "unsent" ? 0 : 1);
    expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/run"))).toBe(
      false,
    );
  },
  10000,
);
it.each(["unsent", "legacy-unknown", "durable-unknown"])(
  "explicit open B then A preserves original %s draft and lock",
  async (mode) => {
    const { user, fetch } = await setup(mode);
    for (const id of ["b", "a"])
      await user.click(
        within(document.getElementById("record-source-" + id)!).getByRole(
          "button",
          { name: t("abstractOpen") },
        ),
      );
    expect(
      screen.queryByLabelText(t("abstractPurpose")),
      "original purpose must remain after explicit source roundtrip",
    ).toHaveValue("Retain synthetic purpose A");
    if (mode !== "unsent")
      expect(
        screen.getByRole("button", { name: t("abstractPrepare") }),
      ).toBeDisabled();
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(mode === "unsent" ? 0 : 1);
  },
  10000,
);
it.each(["legacy-unknown", "durable-unknown"])(
  "diagnostic explicit source roundtrip preserves uncertainty guard (%s)",
  async (mode) => {
    const { user, fetch } = await setup(mode);
    for (const id of ["b", "a"])
      await user.click(
        within(document.getElementById("record-source-" + id)!).getByRole(
          "button",
          { name: t("abstractOpen") },
        ),
      );
    const chooser = screen.getByLabelText(
      t("abstractChooseFile"),
    ) as HTMLSelectElement;
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
    if (!chooser.disabled) {
      await user.selectOptions(chooser, "file-a");
      await user.click(
        screen.getByRole("button", { name: t("abstractReadText") }),
      );
      await screen.findByLabelText(t("abstractText"));
      await user.click(
        screen.getByRole("button", { name: t("abstractSelectEntire") }),
      );
      const prepare = screen.getByRole("button", {
        name: t("abstractPrepare"),
      });
      expect(
        prepare,
        "lost-response same source must not become eligible again",
      ).toBeDisabled();
    } else expect(chooser).toBeDisabled();
  },
  10000,
);

it.each(["unsent", "legacy-unknown", "durable-unknown"])(
  "project roundtrip preserves only the original exact-source %s state",
  async (mode) => {
    const { user, fetch } = await setup(mode);
    await user.selectOptions(
      screen.getByRole("combobox", { name: t("chooseProject") }),
      "other",
    );
    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: t("chooseProject") }),
      ).toHaveValue("other"),
    );
    await user.click(
      await within(document.getElementById("record-source-a")!).findByRole(
        "button",
        { name: t("abstractOpen") },
      ),
    );
    expect(
      screen.queryByDisplayValue("Retain synthetic purpose A"),
    ).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: t("chooseProject") }),
      "selected",
    );
    await screen.findByRole("heading", { name: "Screening decisions" });
    await user.click(
      within(document.getElementById("record-source-a")!).getByRole("button", {
        name: t("abstractOpen"),
      }),
    );
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Retain synthetic purpose A",
    );
    expect(screen.getByRole("button", { name: t("abstractPrepare") }))[
      mode === "unsent" ? "toBeEnabled" : "toBeDisabled"
    ]();
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(mode === "unsent" ? 0 : 1);
    expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/run"))).toBe(
      false,
    );
  },
  10000,
);
it("late keyless completion updates original A without navigating or replacing newer B input", async () => {
  const { user, fetch } = await setup("unsent");
  const original = fetch.getMockImplementation()!;
  let resolve!: (value: Response) => void;
  fetch.mockImplementation(async (input, options) =>
    options?.method === "POST"
      ? new Promise<Response>((yes) => {
          resolve = yes;
        })
      : original(input, options),
  );
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  await user.click(
    within(document.getElementById("record-source-b")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  await user.selectOptions(
    screen.getByLabelText(t("abstractChooseFile")),
    "file-b",
  );
  await user.click(screen.getByRole("button", { name: t("abstractReadText") }));
  await screen.findByLabelText(t("abstractText"));
  await user.type(
    screen.getByLabelText(t("abstractPurpose")),
    "Newer B purpose",
  );
  const hash = window.location.hash;
  await act(async () =>
    resolve(
      response({
        ok: true,
        task: {
          id: "late-exact-A",
          operation: "paper-abstract-draft",
          mode: "connected",
          status: "ready",
        },
      }),
    ),
  );
  expect(window.location.hash).toBe(hash);
  expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
    "Newer B purpose",
  );
  await user.click(
    within(document.getElementById("record-source-a")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
    "Retain synthetic purpose A",
  );
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeDisabled();
  expect(screen.getByText(t("abstractPreparedKnown"))).toBeVisible();
  expect(fetch.mock.calls.filter((c) => c[1]?.method === "POST")).toHaveLength(
    1,
  );
  expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/run"))).toBe(
    false,
  );
}, 10000);

it("explicitly dismissing a storage-denied unsent preparation releases only its draft lock", async () => {
  const { user, fetch } = await setup("durable-ready");
  const storage = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(() => {
      throw new DOMException("Synthetic denied", "SecurityError");
    });
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  await screen.findByText(t("prepareStorageConfirm"));
  expect(
    screen.queryByText(t("abstractPrepareUncertain")),
  ).not.toBeInTheDocument();
  await user.click(
    within(document.getElementById("record-source-b")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  const region = screen.getByRole("region", {
    name: t("prepareRecoveryTitle"),
  });
  await user.click(within(region).getByRole("button", { name: t("cancel") }));
  await user.click(
    within(document.getElementById("record-source-a")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
    "Retain synthetic purpose A",
  );
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeEnabled();
  expect(fetch.mock.calls.filter((c) => c[1]?.method === "POST")).toHaveLength(
    0,
  );
  storage.mockRestore();
}, 10000);
it("confirmed rejection of an explicit same-key retry retires that lock without discarding input", async () => {
  const { user, fetch } = await setup("durable-unknown");
  const original = fetch.getMockImplementation()!;
  fetch.mockImplementation(async (input, options) =>
    options?.method === "POST"
      ? new Response(
          JSON.stringify({
            ok: false,
            code: "invalid_source",
            error: "Synthetic validation rejection",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        )
      : original(input, options),
  );
  await user.click(
    within(document.getElementById("record-source-b")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  await user.click(screen.getByRole("button", { name: t("prepareRetrySame") }));
  await user.click(
    within(document.getElementById("record-source-a")!).getByRole("button", {
      name: t("abstractOpen"),
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeEnabled(),
  );
  expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
    "Retain synthetic purpose A",
  );
  const posts = fetch.mock.calls.filter((c) => c[1]?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(posts[1][1]?.body).toBe(posts[0][1]?.body);
}, 10000);

it.each(["screening-return", "same-source-open"])(
  "newer same-page %s prevents late Prepare from navigating to Review",
  async (intent) => {
    const { user, fetch } = await setup("unsent");
    const original = fetch.getMockImplementation()!;
    let resolve!: (value: Response) => void;
    fetch.mockImplementation(async (input, options) =>
      options?.method === "POST"
        ? new Promise<Response>((yes) => {
            resolve = yes;
          })
        : original(input, options),
    );
    await user.click(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    );
    if (intent === "screening-return")
      await user.click(
        within(document.getElementById("record-decision-b")!).getByRole(
          "button",
          { name: t("abstractReturnSource") },
        ),
      );
    else
      await user.click(
        within(document.getElementById("record-source-a")!).getByRole(
          "button",
          { name: t("abstractOpen") },
        ),
      );
    const hash = window.location.hash;
    await act(async () =>
      resolve(
        response({
          ok: true,
          task: {
            id: "late-same-page-A",
            project_id: project.id,
            operation: "paper-abstract-draft",
            mode: "connected",
            status: "ready",
          },
        }),
      ),
    );
    expect(window.location.hash).toBe(hash);
    if (intent === "screening-return")
      await waitFor(() =>
        expect(document.getElementById("record-source-b")).toHaveFocus(),
      );
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Retain synthetic purpose A",
    );
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
  },
  10000,
);
it.each(["successful", "failed"])(
  "a found keyed result while A is unmounted survives %s refresh and replacement of project controllers",
  async (refresh) => {
    const { user, fetch } = await setup("durable-unknown");
    const original = fetch.getMockImplementation()!;
    await user.click(
      within(document.getElementById("record-source-b")!).getByRole("button", {
        name: t("abstractOpen"),
      }),
    );
    let failRefresh = refresh === "failed";
    const task = {
      id: "found-hidden-A",
      project_id: project.id,
      operation: "paper-abstract-draft",
      mode: "connected",
      status: "ready",
      action_hash: "c".repeat(64),
    };
    fetch.mockImplementation(async (input, options) => {
      const url = String(input);
      if (url.includes("/preparations/"))
        return response({
          ok: true,
          preparation: { state: "found", key: url.split("/").pop() },
          task,
        });
      if (url.endsWith("/projects/selected")) {
        if (failRefresh) {
          failRefresh = false;
          return new Response(
            JSON.stringify({
              ok: false,
              error: "Synthetic refresh unavailable",
            }),
            { status: 503 },
          );
        }
        return response({ ...detail, tasks: [task] });
      }
      return original(input, options);
    });
    await user.click(screen.getByRole("button", { name: t("prepareCheck") }));
    await waitFor(() =>
      expect(
        Object.keys(localStorage).filter((key) =>
          key.startsWith("research-hub:prepare:"),
        ),
      ).toHaveLength(0),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: t("chooseProject") }),
      "other",
    );
    await screen.findByRole("heading", { name: "Screening decisions" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: t("chooseProject") }),
      "selected",
    );
    await screen.findByRole("heading", { name: "Screening decisions" });
    await user.click(
      within(document.getElementById("record-source-a")!).getByRole("button", {
        name: t("abstractOpen"),
      }),
    );
    expect(screen.getByText(t("abstractPreparedKnown"))).toBeVisible();
    expect(
      screen.getByRole("button", { name: t("abstractOpenPrepared") }),
    ).toBeEnabled();
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Retain synthetic purpose A",
    );
    expect(
      screen.getByRole("button", { name: t("abstractPrepare") }),
    ).toBeDisabled();
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
    expect(fetch.mock.calls.some((c) => String(c[0]).endsWith("/run"))).toBe(
      false,
    );
  },
  10000,
);
it("positive keyed acknowledgement settles the original session before a pending bulk refresh", async () => {
  const { user, fetch } = await setup("durable-ready");
  const original = fetch.getMockImplementation()!;
  let posted = false,
    resolveDetail!: (value: Response) => void;
  const task = {
    id: "ack-before-refresh",
    project_id: project.id,
    operation: "paper-abstract-draft",
    mode: "connected",
    status: "ready",
    action_hash: "d".repeat(64),
  };
  fetch.mockImplementation(async (input, options) => {
    if (options?.method === "POST") {
      posted = true;
      return response({
        ok: true,
        preparation: {
          version: 1,
          key: JSON.parse(String(options.body)).prepare_request.key,
          disposition: "created",
        },
        task,
      });
    }
    if (posted && String(input).endsWith("/projects/selected"))
      return new Promise<Response>((yes) => {
        resolveDetail = yes;
      });
    return original(input, options);
  });
  await user.click(screen.getByRole("button", { name: t("abstractPrepare") }));
  await waitFor(() => expect(resolveDetail).toBeTypeOf("function"));
  for (const id of ["b", "a"])
    await user.click(
      within(document.getElementById("record-source-" + id)!).getByRole(
        "button",
        { name: t("abstractOpen") },
      ),
    );
  try {
    expect(screen.getByText(t("abstractPreparedKnown"))).toBeVisible();
    expect(
      screen.queryByText(t("abstractPreparingLeave")),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: t("abstractOpenPrepared") }),
    ).toBeEnabled();
    expect(
      fetch.mock.calls.filter((c) => c[1]?.method === "POST"),
    ).toHaveLength(1);
  } finally {
    await act(async () =>
      resolveDetail(response({ ...detail, tasks: [task] })),
    );
  }
}, 10000);

it("refreshing into another exact workspace namespace never displays an older namespace's draft", async () => {
  const { user, fetch } = await setup("durable-ready");
  const original = fetch.getMockImplementation()!;
  let currentNamespace = "33333333-3333-4333-8333-333333333333";
  fetch.mockImplementation(async (input, options) => {
    const result = await original(input, options);
    if (!String(input).endsWith("/workspace")) return result;
    const value = await result.json();
    value.capabilities.prepare_reconciliation.workspace_instance_id =
      currentNamespace;
    return response(value);
  });
  await user.click(screen.getByRole("button", { name: t("refresh") }));
  await waitFor(() =>
    expect(
      screen.queryByDisplayValue("Retain synthetic purpose A"),
    ).not.toBeInTheDocument(),
  );
  currentNamespace = namespace;
  await user.click(screen.getByRole("button", { name: t("refresh") }));
  await waitFor(() =>
    expect(screen.getByLabelText(t("abstractPurpose"))).toHaveValue(
      "Retain synthetic purpose A",
    ),
  );
  expect(
    screen.getByRole("button", { name: t("abstractPrepare") }),
  ).toBeEnabled();
  expect(fetch.mock.calls.filter((c) => c[1]?.method === "POST")).toHaveLength(
    0,
  );
}, 10000);
