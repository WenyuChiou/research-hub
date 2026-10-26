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
