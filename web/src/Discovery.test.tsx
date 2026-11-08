import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { DiscoveryPanel } from "./Discovery";
import { translator } from "./i18n";
import generated from "./test-fixtures/discovery-view.json";

const artifact = generated.view.artifact.id;
const link = (id = artifact, project = "p") =>
  "#literature?" + new URLSearchParams({ project, discovery: id });
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function serve(overrides?: (url: string) => Promise<Response> | undefined) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const custom = overrides?.(url);
    if (custom) return custom;
    if (url.endsWith("/workspace"))
      return response({
        ok: true,
        projects: [generated.detail.project],
        capabilities: {
          codex: { status: "unavailable" },
          writing: { status: "unavailable" },
          approval: { status: "unavailable" },
        },
        protection_scope: "Synthetic only",
      });
    if (url.endsWith("/discovery")) return response(generated.view);
    if (url.endsWith("/projects/p")) return response(generated.detail);
    return response(
      { ok: false, code: "not_found", error: "Selected project unavailable" },
      404,
    );
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function route(hash: string) {
  act(() => {
    window.history.pushState({}, "", hash);
    fireEvent(window, new HashChangeEvent("hashchange"));
  });
}
afterEach(() => vi.unstubAllGlobals());

it("labels supplied completion and exposes failed observations by exact need without writes", async () => {
  window.history.replaceState({}, "", link());
  const view = structuredClone(generated.view);
  view.discovery.needs[0].status = "covered";
  view.discovery.completion = { status: "bounded-complete", reason: "Caller assessment", residual_need_ids: [] };
  view.discovery.attempts = [
    { ...view.discovery.attempts[0], id: "closest", status: "observed", outcome: "success" },
    { ...view.discovery.attempts[0], id: "contrary", status: "observed", outcome: "timeout", input: "Retained failed query" },
    { ...view.discovery.attempts[0], id: "foreign", need_ids: ["other"], input: "Other need only" },
  ];
  const fetch = serve((url) => url.endsWith("/discovery") ? Promise.resolve(response(view)) : undefined);
  render(<App />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  expect(within(result).getByText(/Declared need status: covered/)).toBeVisible();
  expect(within(result).getByText(/Declared completion: bounded-complete/)).toBeVisible();
  expect(within(result).getByText(/Search-family linkage: unknown/)).toBeVisible();
  const summary = within(result).getByText(/^Linked attempts \/ sources: 2 \/ 2 · Attempts to inspect: 1/);
  const before = fetch.mock.calls.length;
  await userEvent.click(summary);
  const details = summary.closest("details")!;
  expect(within(details).getByText(/contrary · search · Retained failed query/)).toBeVisible();
  expect(within(details).getByText(/observed \/ timeout/)).toBeVisible();
  expect(within(details).queryByText(/Other need only/)).not.toBeInTheDocument();
  expect(fetch.mock.calls).toHaveLength(before);
  expect(view.discovery.completion.status).toBe("bounded-complete");
});

it("keeps a successful empty search distinct from missing source evidence", async () => {
  window.history.replaceState({}, "", link());
  const view = structuredClone(generated.view);
  const changed = { ...view, discovery: { ...view.discovery,
    sources: [], attempts: [{ ...view.discovery.attempts[0], status: "observed", outcome: "empty", result_count: 0 }] } };
  serve((url) => url.endsWith("/discovery") ? Promise.resolve(response(changed)) : undefined);
  render(<App />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  const summary = within(result).getByText("Linked attempts / sources: 1 / 0 · Attempts to inspect: 0");
  await userEvent.click(summary);
  const details = summary.closest("details")!;
  expect(within(details).getByText(/observed \/ empty · Caller-declared result count: 0/)).toBeVisible();
  expect(within(details).getByText(/does not prove no relevant literature exists/)).toBeVisible();
  expect(within(result).getByText(/not verified coverage, source reliability or relevance/)).toBeVisible();
});

it("provides matching Traditional Chinese declaration and unknown-linkage labels", () => {
  const t = translator("zh-TW");
  expect(t("discoveryDeclaredStatus")).toBe("宣告的需求狀態");
  expect(t("discoveryDeclaredCompletion")).toBe("宣告的完成狀態");
  expect(t("discoveryFamilyUnknown")).toContain("未知");
  expect(t("discoveryNoLinkedAttempts")).toContain("不代表未曾搜尋");
});

it("keeps the need disclosure keyboard-focusable and click activation reversible without a new request", async () => {
  const fetch = serve();
  const user = userEvent.setup();
  render(<DiscoveryPanel projectId="p" artifacts={[]} selected={artifact} invalid={false} active={true} t={translator("en")} />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  const summary = within(result).getByText("Linked attempts / sources: 1 / 2 · Attempts to inspect: 1");
  const details = summary.closest("details")!;
  const before = fetch.mock.calls.length;
  await user.tab();
  expect(screen.getByText("About saved research")).toHaveFocus();
  await user.tab();
  expect(summary).toHaveFocus();
  // user-event 14 does not emulate native summary Enter/Space activation.
  // Test tab order and click toggling here; native keys need a real browser.
  await user.click(summary);
  expect(details).toHaveAttribute("open");
  expect(within(details).getByText(/a1 · search · synthetic query/)).toBeVisible();
  expect(summary).toHaveFocus();
  await user.click(summary);
  expect(details).not.toHaveAttribute("open");
  expect(summary).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByText("About saved research")).toHaveFocus();
  expect(fetch.mock.calls).toHaveLength(before);
});

it("shows and expands all 52 related attempts and sources with explicit displayed totals", async () => {
  const view = structuredClone(generated.view);
  view.discovery.attempts = Array.from({ length: 52 }, (_, i) => ({
    ...generated.view.discovery.attempts[0], id: `linked-attempt-${i}`, input: `Query ${i}`,
  }));
  view.discovery.sources = Array.from({ length: 52 }, (_, i) => ({
    ...generated.view.discovery.sources[0], id: `linked-source-${i}`, title: `Related source ${i}`,
  }));
  const fetch = serve((url) => url.endsWith("/discovery") ? Promise.resolve(response(view)) : undefined);
  render(<DiscoveryPanel projectId="p" artifacts={[]} selected={artifact} invalid={false} active={true} t={translator("en")} />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  const summary = within(result).getByText("Linked attempts / sources: 52 / 52 · Attempts to inspect: 52");
  await userEvent.click(summary);
  const details = summary.closest("details")!;
  expect(within(details).getByText("Linked attempts shown / recorded (50 / 52)")).toBeVisible();
  expect(within(details).getByText("Linked sources shown / recorded (50 / 52)")).toBeVisible();
  expect(within(details).queryByText(/linked-attempt-51 ·/)).not.toBeInTheDocument();
  expect(within(details).queryByText(/linked-source-51 ·/)).not.toBeInTheDocument();
  const before = fetch.mock.calls.length;
  await userEvent.click(within(result).getByRole("button", { name: "Show the next 50 entries in each list" }));
  expect(details).toHaveAttribute("open");
  expect(within(details).getByText("Linked attempts shown / recorded (52 / 52)")).toBeVisible();
  expect(within(details).getByText("Linked sources shown / recorded (52 / 52)")).toBeVisible();
  expect(within(details).getByText(/linked-attempt-51 · search · Query 51/)).toBeVisible();
  expect(within(details).getByText(/linked-source-51 · Related source 51/)).toBeVisible();
  expect(within(result).queryByRole("button", { name: "Show the next 50 entries in each list" })).not.toBeInTheDocument();
  expect(fetch.mock.calls).toHaveLength(before);
});

it("does not guess a need relationship when an incomplete response omits need_ids", async () => {
  const view = { ...generated.view, discovery: { ...generated.view.discovery,
    attempts: [{ ...generated.view.discovery.attempts[0], need_ids: undefined }],
    sources: [{ ...generated.view.discovery.sources[0], need_ids: undefined }],
  } };
  serve((url) => url.endsWith("/discovery") ? Promise.resolve(response(view)) : undefined);
  render(<DiscoveryPanel projectId="p" artifacts={[]} selected={artifact} invalid={false} active={true} t={translator("en")} />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  const summary = within(result).getByText(/Linked attempts \/ sources: 0 \/ 0.*Snapshot attempts \/ sources with need-link issues: 1 \/ 1/);
  await userEvent.click(summary);
  const details = summary.closest("details")!;
  expect(within(details).getByText(/missing or invalid need links/)).toBeVisible();
  expect(within(details).queryByText(/a1 · search ·/)).not.toBeInTheDocument();
  expect(within(details).getByText(/Missing records do not prove no search occurred/)).toBeVisible();
});

it("keeps valid mixed links visible and identifies both mixed and foreign-only record issues", async () => {
  const view = structuredClone(generated.view);
  const needId = view.discovery.needs[0].id;
  view.discovery.attempts = [
    { ...view.discovery.attempts[0], id: "foreign", need_ids: ["ghost"], input: "Foreign query" },
    { ...view.discovery.attempts[0], id: "mixed", need_ids: [needId, "ghost"], input: "Mixed query" },
  ];
  view.discovery.sources = [
    { ...view.discovery.sources[0], id: "foreign-source", need_ids: ["ghost"], title: "Foreign source" },
    { ...view.discovery.sources[0], id: "mixed-source", need_ids: [needId, "ghost"], title: "Mixed source" },
  ];
  const fetch = serve((url) => url.endsWith("/discovery") ? Promise.resolve(response(view)) : undefined);
  render(<DiscoveryPanel projectId="p" artifacts={[]} selected={artifact} invalid={false} active={true} t={translator("en")} />);
  const result = await screen.findByRole("region", { name: "Saved Stage 1 result" });
  const summary = within(result).getByText("Linked attempts / sources: 1 / 1 · Attempts to inspect: 1 · Snapshot attempts / sources with need-link issues: 2 / 2");
  const before = fetch.mock.calls.length;
  await userEvent.click(summary);
  const details = summary.closest("details")!;
  expect(within(details).getByText(/Counts include partly linked records/)).toBeVisible();
  expect(within(details).getByText("Snapshot attempt IDs with need-link issues shown / recorded (2 / 2): foreign, mixed")).toBeVisible();
  expect(within(details).getByText("Snapshot source IDs with need-link issues shown / recorded (2 / 2): foreign-source, mixed-source")).toBeVisible();
  expect(within(details).getByText(/mixed · search · Mixed query/)).toBeVisible();
  expect(within(details).getByText(/mixed-source · Mixed source/)).toBeVisible();
  expect(within(details).queryByText(/foreign · search · Foreign query/)).not.toBeInTheDocument();
  expect(within(details).queryByText(/foreign-source · Foreign source/)).not.toBeInTheDocument();
  expect(fetch.mock.calls).toHaveLength(before);
});

it("explains the Crossref request and project record next to the search field", async () => {
  window.history.replaceState({}, "", "#literature");
  serve();
  render(<App />);
  const field = await screen.findByRole("textbox", { name: "Search question or keywords" });
  expect(field).toHaveAccessibleDescription(translator("en")("searchPrivacy"));
  expect(translator("zh-TW")("searchPrivacy")).toContain("Crossref");
});

it("keeps the Windows limitation visible and opens optional guidance", async () => {
  const user = userEvent.setup();
  render(<DiscoveryPanel projectId="p" artifacts={[]} selected={null} invalid={false} active={true} t={translator("en")} />);
  expect(screen.getByText(/not yet available on Windows/)).toBeVisible();
  expect(screen.getByText(/No saved research in this project/)).toBeVisible();
  expect(screen.getByText(/Do not repeat research solely/)).not.toBeVisible();
  await user.tab();
  expect(screen.getByText("About saved research")).toHaveFocus();
  await user.click(screen.getByText("About saved research"));
  expect(screen.getByText(/Do not repeat research solely/)).toBeVisible();
});

it("one agent link opens exact saved native result with no integrations or writes, and setup interruption preserves it", async () => {
  window.history.replaceState({}, "", generated.view_path);
  const fetch = serve();
  const user = userEvent.setup();
  render(<App />);
  const result = await screen.findByRole("region", {
    name: "Saved Stage 1 result",
  });
  expect(
    within(result).getAllByRole("heading", { name: "Same synthetic title" }),
  ).toHaveLength(2);
  expect(within(result).getByText("s1", { exact: true })).toBeVisible();
  expect(within(result).getByText("s2", { exact: true })).toBeVisible();
  expect(within(result).getByText(/Unknown · restricted/)).toBeVisible();
  expect(within(result).getByText(/not authenticate execution/)).toBeVisible();
  expect(result.querySelector('a[href^="javascript:"]')).toBeNull();
  const calls = fetch.mock.calls.length;
  await user.click(
    screen.getByRole("button", { name: "Integrations & setup" }),
  );
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(result).toBeVisible();
  expect(fetch.mock.calls).toHaveLength(calls);
  expect(
    fetch.mock.calls.every(
      (c) =>
        (c as unknown as [unknown, RequestInit])[1]?.method === undefined ||
        (c as unknown as [unknown, RequestInit])[1]?.method === "GET",
    ),
  ).toBe(true);
});

it("hash Back/Forward transitions retain exact selected result without changing existing page routes", async () => {
  window.history.replaceState({}, "", link());
  serve();
  render(<App />);
  await screen.findByRole("region", { name: "Saved Stage 1 result" });
  route("#overview");
  expect(
    screen.queryByRole("region", { name: "Saved Stage 1 result" }),
  ).not.toBeInTheDocument();
  route(link());
  expect(
    await screen.findByRole("region", { name: "Saved Stage 1 result" }),
  ).toBeVisible();
  route("#literature");
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Saved Stage 1 result" }),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole("heading", { name: "Literature", level: 1 }),
  ).toBeVisible();
});

it("a late A projection cannot replace selected B, and unknown bytes remain visibly not-current", async () => {
  window.history.replaceState({}, "", link("held"));
  let release!: (value: Response) => void;
  const fetch = serve((url) => {
    if (url.endsWith("/artifacts/held/discovery"))
      return new Promise((resolve) => {
        release = resolve;
      });
    if (url.endsWith("/artifacts/b/discovery"))
      return Promise.resolve(
        response({
          ...generated.view,
          artifact: { ...generated.view.artifact, id: "b" },
          discovery: { ...generated.view.discovery, brief: "New B" },
          report: { ...generated.view.report, binding: "not-current" },
        }),
      );
  });
  render(<App />);
  await waitFor(() => expect(release).toBeDefined());
  route(link("b"));
  await screen.findByRole("heading", { name: "New B" });
  await act(async () =>
    release(
      response({
        ...generated.view,
        artifact: { ...generated.view.artifact, id: "held" },
      }),
    ),
  );
  expect(screen.getByRole("heading", { name: "New B" })).toBeVisible();
  expect(
    screen.getByText(/Referenced bytes at last check: not-current/),
  ).toBeVisible();
  expect(
    fetch.mock.calls.some((c) =>
      String(c[0]).includes("/artifacts/b/discovery"),
    ),
  ).toBe(true);
});

it.each([
  "#literature?project=p",
  "#literature?project=p&project=other&discovery=x",
])(
  "malformed link is explicit and never selects a guessed snapshot: %s",
  async (hash) => {
    window.history.replaceState({}, "", hash);
    const fetch = serve();
    render(<App />);
    expect(
      await screen.findByText(/link is incomplete or ambiguous/),
    ).toBeVisible();
    expect(
      fetch.mock.calls.some((c) => String(c[0]).endsWith("/discovery")),
    ).toBe(false);
  },
);

it("foreign project link does not silently fall back to first project's artifact", async () => {
  window.history.replaceState({}, "", link(artifact, "foreign"));
  const fetch = serve();
  render(<App />);
  await screen.findByText("Selected project unavailable");
  expect(
    fetch.mock.calls.some((c) => String(c[0]).endsWith("/projects/p")),
  ).toBe(false);
  expect(
    screen.queryByRole("region", { name: "Saved Stage 1 result" }),
  ).not.toBeInTheDocument();
});

it("actual history Back and Forward restore the exact discovery selection", async () => {
  window.history.replaceState({}, "", link());
  serve();
  render(<App />);
  await screen.findByRole("region", { name: "Saved Stage 1 result" });
  route("#overview");
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Saved Stage 1 result" }),
    ).not.toBeInTheDocument(),
  );
  act(() => window.history.back());
  expect(
    await screen.findByRole("region", { name: "Saved Stage 1 result" }),
  ).toBeVisible();
  act(() => window.history.forward());
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Saved Stage 1 result" }),
    ).not.toBeInTheDocument(),
  );
});

it("a mismatched server identity never renders or silently switches selected project", async () => {
  window.history.replaceState({}, "", link());
  serve((url) =>
    url.endsWith("/discovery")
      ? Promise.resolve(
          response({
            ...generated.view,
            discovery: { ...generated.view.discovery, project_id: "other" },
          }),
        )
      : undefined,
  );
  render(<App />);
  await screen.findByText(/response belongs to a different/);
  expect(
    screen.queryByRole("region", { name: "Saved Stage 1 result" }),
  ).not.toBeInTheDocument();
});

it("failed read retains identity and only explicit read retry is offered, not new research", async () => {
  window.history.replaceState({}, "", link());
  let fail = true;
  const fetch = serve((url) =>
    url.endsWith("/discovery")
      ? Promise.resolve(
          fail
            ? response(
                {
                  ok: false,
                  code: "source_unavailable",
                  error: "Saved evidence unavailable",
                },
                503,
              )
            : response(generated.view),
        )
      : undefined,
  );
  render(<App />);
  await screen.findByText("Saved evidence unavailable");
  expect(window.location.hash).toBe(link());
  fail = false;
  await userEvent.click(
    screen.getByRole("button", { name: "Recheck saved evidence (read only)" }),
  );
  expect(
    await screen.findByRole("region", { name: "Saved Stage 1 result" }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("/discovery")),
  ).toHaveLength(2);
});

it.each(["unknown", "stale"])(
  "shows exact query capture binding %s separately from caller-observed outcome",
  async (status) => {
    window.history.replaceState({}, "", link());
    serve((url) =>
      url.endsWith("/discovery")
        ? Promise.resolve(
            response({
              ...generated.view,
              report: {
                ...generated.view.report,
                binding: "not-current",
                material_bindings: [{ kind: "attempt", id: "a1", status }],
              },
              discovery: {
                ...generated.view.discovery,
                attempts: [
                  {
                    ...generated.view.discovery.attempts[0],
                    status: "observed",
                    outcome: "success",
                  },
                ],
              },
            }),
          )
        : undefined,
    );
    render(<App />);
    const result = await screen.findByRole("region", {
      name: "Saved Stage 1 result",
    });
    await userEvent.click(
      within(result).getByText(
        "Recorded searches and reads (not live agent activity)",
      ),
    );
    expect(
      within(result).getByText("Captured observation-byte binding: " + status),
    ).toBeVisible();
    expect(within(result).getByText(/observed · success/)).toBeVisible();
  },
);

it("does not render unknown profile formats as a supported saved result", async () => {
  window.history.replaceState({}, "", link());
  serve((url) =>
    url.endsWith("/discovery")
      ? Promise.resolve(
          response({
            ...generated.view,
            discovery: { ...generated.view.discovery, format: "future/99" },
          }),
        )
      : undefined,
  );
  render(<App />);
  await screen.findByText("Unsupported saved discovery format.");
  expect(
    screen.queryByRole("region", { name: "Saved Stage 1 result" }),
  ).not.toBeInTheDocument();
});

it("large source sets render a bounded first page with an explicit more control, not silent truncation", async () => {
  window.history.replaceState({}, "", link());
  serve((url) =>
    url.endsWith("/discovery")
      ? Promise.resolve(
          response({
            ...generated.view,
            discovery: {
              ...generated.view.discovery,
              sources: Array.from({ length: 52 }, (_, i) => ({
                ...generated.view.discovery.sources[0],
                id: "source-" + i,
                title: "Bounded source " + i,
              })),
            },
          }),
        )
      : undefined,
  );
  render(<App />);
  const result = await screen.findByRole("region", {
    name: "Saved Stage 1 result",
  });
  expect(
    within(result).getAllByRole("heading", { name: /Bounded source/ }),
  ).toHaveLength(50);
  expect(
    within(result).queryByRole("heading", { name: "Bounded source 51" }),
  ).not.toBeInTheDocument();
  await userEvent.click(
    within(result).getByRole("button", {
      name: "Show the next 50 entries in each list",
    }),
  );
  expect(
    within(result).getAllByRole("heading", { name: /Bounded source/ }),
  ).toHaveLength(52);
  expect(
    within(result).queryByRole("button", {
      name: "Show the next 50 entries in each list",
    }),
  ).not.toBeInTheDocument();
});

it("uses a padded discovery body and separates exact source ID from its external locator", async () => {
  window.history.replaceState({}, "", link());
  serve();
  render(<App />);
  const result = await screen.findByRole("region", {
    name: "Saved Stage 1 result",
  });
  expect(result.closest(".discovery-body")).not.toBeNull();
  const source = within(result)
    .getAllByRole("heading", { name: "Same synthetic title" })[0]
    .closest("article")!;
  const meta = source.querySelector<HTMLElement>(".discovery-source-meta")!;
  expect(meta).not.toBeNull();
  expect(within(meta).getByText("s1", { exact: true }).tagName).toBe("CODE");
  expect(within(meta).getByRole("link")).toHaveAttribute(
    "href",
    "https://example.org/synthetic",
  );
});
