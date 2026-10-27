import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import type { ProjectDetail, ResearchRecord } from "./types";

const project = {
  id: "selected",
  title: "Selected project",
  archetype: "empirical" as const,
  goal: "Synthetic",
};
const source = (
  id: string,
  title: string,
  scope: unknown = "abstract",
): ResearchRecord => ({
  id,
  kind: "source",
  data: { title, reading_scope: scope },
});
const decision = (id: string, sourceId: string): ResearchRecord => ({
  id,
  kind: "screening",
  data: {
    source_id: sourceId,
    decision: "include",
    rationale: "Synthetic human rationale",
  },
});
const detail = (records: ResearchRecord[]): ProjectDetail => ({
  ok: true,
  project,
  records,
  artifacts: [],
  tasks: [],
  actions: [],
  manuscript: null,
  workflow: null,
  warnings: [],
});
function serve(records: ResearchRecord[]) {
  window.history.replaceState({}, "", "/#literature");
  const fetch = vi.fn(
    async (input: RequestInfo | URL) =>
      new Response(
        JSON.stringify(
          String(input).endsWith("/workspace")
            ? {
                ok: true,
                projects: [project],
                capabilities: {
                  codex: { status: "unavailable" },
                  writing: { status: "unavailable" },
                  approval: { status: "unavailable" },
                },
                protection_scope: "Synthetic only",
              }
            : detail(records),
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
async function card(id = "decision-a") {
  await screen.findByRole("heading", { name: "Screening decisions" });
  return document.getElementById(`record-${id}`)!;
}
afterEach(() => vi.unstubAllGlobals());

it("saved screening shows exact source title/scope and keyboard return focuses that record without writes", async () => {
  const fetch = serve([
    source("source-a", "Synthetic source A"),
    decision("decision-a", "source-a"),
  ]);
  const user = userEvent.setup();
  render(<App />);
  const saved = await card();
  expect(
    within(saved).getByRole("heading", { name: "Synthetic source A" }),
  ).toBeVisible();
  expect(
    within(saved).getByText(/Declared coverage.*This material is an abstract/),
  ).toBeVisible();
  const button = within(saved).getByRole("button", {
    name: "Return to this source",
  });
  const readsBeforeReturn = fetch.mock.calls.length;
  act(() => button.focus());
  await user.keyboard("{Enter}");
  await waitFor(() =>
    expect(document.getElementById("record-source-a")).toHaveFocus(),
  );
  expect(window.location.hash).toBe("#literature");
  expect(fetch.mock.calls).toHaveLength(readsBeforeReturn);
  expect(
    fetch.mock.calls.every((call) =>
      [undefined, "GET"].includes(
        (call as unknown as [unknown, RequestInit])[1]?.method,
      ),
    ),
  ).toBe(true);
});
it("duplicate titles retain their separate exact record targets", async () => {
  serve([
    source("source-a", "Same title"),
    source("source-b", "Same title"),
    decision("decision-a", "source-b"),
  ]);
  const user = userEvent.setup();
  render(<App />);
  await user.click(
    within(await card()).getByRole("button", { name: "Return to this source" }),
  );
  await waitFor(() =>
    expect(document.getElementById("record-source-b")).toHaveFocus(),
  );
  expect(document.getElementById("record-source-a")).not.toHaveFocus();
});
it.each([undefined, "full", "partial", "invented"])(
  "unrecognized or missing declared scope remains unknown (%s)",
  async (scope) => {
    const selected = source("source-a", "Synthetic source A");
    selected.data.reading_scope = scope;
    serve([selected, decision("decision-a", "source-a")]);
    render(<App />);
    expect(
      within(await card()).getByText(
        /Declared coverage.*Scope unknown or mixed text/,
      ),
    ).toBeVisible();
  },
);
it("missing/deleted source never joins by similar title and keeps decision/rationale with no return action", async () => {
  serve([source("other", "missing-id"), decision("decision-a", "missing-id")]);
  render(<App />);
  const saved = await card();
  expect(
    within(saved).getByText("Source record unavailable in this project."),
  ).toBeVisible();
  expect(within(saved).getByText("Synthetic human rationale")).toBeVisible();
  expect(
    within(saved).queryByRole("button", { name: "Return to this source" }),
  ).toBeNull();
  expect(
    within(saved).queryByRole("heading", { name: "missing-id" }),
  ).toBeNull();
});
it("refresh removing the exact source removes the return action without dropping the saved decision", async () => {
  const records = [
    source("source-a", "Synthetic source A"),
    decision("decision-a", "source-a"),
  ];
  const fetch = serve(records);
  const user = userEvent.setup();
  render(<App />);
  expect(
    within(await card()).getByRole("button", { name: "Return to this source" }),
  ).toBeVisible();
  records.splice(0, 1);
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(
      within(document.getElementById("record-decision-a")!).getByText(
        "Source record unavailable in this project.",
      ),
    ).toBeVisible(),
  );
  expect(
    within(document.getElementById("record-decision-a")!).queryByRole(
      "button",
      { name: "Return to this source" },
    ),
  ).toBeNull();
  expect(
    fetch.mock.calls.every((call) =>
      [undefined, "GET"].includes(
        (call as unknown as [unknown, RequestInit])[1]?.method,
      ),
    ),
  ).toBe(true);
});
