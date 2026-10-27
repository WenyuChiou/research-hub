import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeliveryPanel, deliveryEligible } from "./Delivery";
import { TaskCard } from "./Tasks";
import { translator } from "./i18n";
import type { Task } from "./types";

const hash = "a".repeat(64);
const current = {
  status: "current",
  reasons: [],
  input_references: [
    {
      kind: "project-evidence",
      ref: "project:study:evidence-records",
      status: "current",
    },
  ],
  output_references: [
    {
      kind: "candidate-artifact",
      ref: "workspace:candidate.md",
      path: "candidate.md",
      status: "current",
      expected_sha256: hash,
      observed_sha256: hash,
    },
  ],
};
const accepted = {
  id: "accepted-1",
  operation: "draft",
  mode: "handoff",
  status: "completed",
  action_hash: hash,
  freshness: current,
  result: {
    prose: "Synthetic proposal, not verified research.",
    semantic_acceptance: "accept",
    artifacts: [{ path: "candidate.md", sha256: hash }],
  },
} as Task;
function withFreshness(freshness: unknown): Task {
  return { ...accepted, freshness } as Task;
}

describe("reviewed candidate revision handoff", () => {
  it.each(["stale", "unknown"])(
    "does not offer %s accepted candidates for delivery",
    (status) => {
      expect(deliveryEligible(withFreshness({ ...current, status }))).toBe(
        false,
      );
    },
  );
  it("does not promote a missing assessment or legacy acceptance flag into current evidence", () => {
    expect(
      deliveryEligible({
        ...withFreshness(undefined),
        acceptance_current: true,
      }),
    ).toBe(false);
  });
  it("retains the current accepted path without requiring a legacy acceptance flag", () => {
    expect(deliveryEligible(accepted)).toBe(true);
    expect(deliveryEligible({ ...accepted, acceptance_current: false })).toBe(
      false,
    );
    expect(deliveryEligible({ ...accepted, status: "awaiting_human" })).toBe(
      false,
    );
  });
  it.each([
    null,
    [],
    { status: "current" },
    { ...current, status: ["current"] },
    { ...current, reasons: [{ code: "source-unavailable" }] },
    { ...current, input_references: [], output_references: [] },
    { ...current, output_references: [] },
    {
      ...current,
      output_references: [{ kind: "", ref: "", status: "current" }],
    },
    {
      ...current,
      output_references: [
        {
          kind: "candidate-artifact",
          ref: "workspace:candidate.md",
          status: "unknown",
        },
      ],
    },
    {
      ...current,
      output_references: [
        {
          kind: "candidate-artifact",
          ref: "workspace:candidate.md",
          status: "stale",
        },
      ],
    },
  ])(
    "does not trust malformed or contradictory current metadata %#",
    (freshness) => {
      expect(deliveryEligible(withFreshness(freshness))).toBe(false);
    },
  );
  it.each(["en", "zh-TW"] as const)(
    "shows a changed revision without erasing historical human acceptance in %s",
    (locale) => {
      render(
        <TaskCard
          task={withFreshness({ ...current, status: "stale" })}
          t={translator(locale)}
          approvalMessage="Fixture only"
          onSaved={async () => {}}
        />,
      );
      expect(
        screen.getByText(locale === "en" ? "Accepted by human" : "人工已接受"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(locale === "en" ? "Revision changed" : "版本已變更"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          locale === "en"
            ? /Previous human acceptance applies to the reviewed revision/
            : /先前的人工接受只適用於當時審閱的版本/,
        ),
      ).toBeInTheDocument();
    },
  );
  it("labels unavailable checks as unknown, not a changed revision or scientific approval", () => {
    render(
      <TaskCard
        task={withFreshness(undefined)}
        t={translator("en")}
        approvalMessage="Fixture only"
        onSaved={async () => {}}
      />,
    );
    expect(screen.getByText("Revision not verified")).toBeInTheDocument();
    expect(screen.queryByText("Revision changed")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Matches prepared revisions"),
    ).not.toBeInTheDocument();
  });
  it("does not display a current badge when a legacy negative acceptance flag contradicts it", () => {
    render(
      <TaskCard
        task={{ ...accepted, acceptance_current: false }}
        t={translator("en")}
        approvalMessage="Fixture only"
        onSaved={async () => {}}
      />,
    );
    expect(screen.getByText("Revision not verified")).toBeInTheDocument();
    expect(
      screen.queryByText("Matches prepared revisions"),
    ).not.toBeInTheDocument();
  });
  it("keeps a version match distinct from scientific acceptance and makes no request", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(
      <TaskCard
        task={accepted}
        t={translator("en")}
        approvalMessage="Fixture only"
        onSaved={async () => {}}
      />,
    );
    expect(screen.getByText("Matches prepared revisions")).toBeInTheDocument();
    expect(
      screen.getByText(
        /This is not scientific validation or new human approval/,
      ),
    ).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("does not echo raw assessment errors or paths into the revision explanation", () => {
    render(
      <TaskCard
        task={withFreshness({
          ...current,
          status: "unknown",
          reasons: [
            {
              code: "source-unavailable",
              message: "synthetic-private-detail",
              ref: "synthetic-private-reference",
            },
          ],
        })}
        t={translator("en")}
        approvalMessage="Fixture only"
        onSaved={async () => {}}
      />,
    );
    expect(screen.getByText("Revision not verified")).toBeInTheDocument();
    expect(screen.queryByText(/synthetic-private/)).not.toBeInTheDocument();
  });
  it.each(["stale", "unknown", "missing"])(
    "removes a selected candidate when a later response is %s, without making a request",
    async (status) => {
      const user = userEvent.setup();
      const fetch = vi.fn();
      vi.stubGlobal("fetch", fetch);
      const props = {
        projectId: "study",
        actions: [],
        t: translator("en"),
        onSaved: async () => {},
      };
      const { rerender } = render(
        <DeliveryPanel {...props} tasks={[accepted]} />,
      );
      await user.click(screen.getByRole("checkbox"));
      rerender(
        <DeliveryPanel
          {...props}
          tasks={[
            withFreshness(
              status === "missing" ? undefined : { ...current, status },
            ),
          ]}
        />,
      );
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Prepare local bundle/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText(/Changed or unverified candidates are not selectable/),
      ).toBeInTheDocument();
      expect(fetch).not.toHaveBeenCalled();
    },
  );
  it.each(["stale", "unknown", "missing"])(
    "does not transfer a revoked %s selection to another eligible candidate",
    async (status) => {
      const user = userEvent.setup();
      const fetch = vi.fn();
      vi.stubGlobal("fetch", fetch);
      const other = { ...accepted, id: "accepted-2" };
      const props = {
        projectId: "study",
        actions: [],
        t: translator("en"),
        onSaved: async () => {},
      };
      const { rerender } = render(
        <DeliveryPanel {...props} tasks={[accepted, other]} />,
      );
      await user.click(screen.getAllByRole("checkbox")[0]);
      rerender(
        <DeliveryPanel
          {...props}
          tasks={[
            withFreshness(
              status === "missing" ? undefined : { ...current, status },
            ),
            other,
          ]}
        />,
      );
      expect(screen.getAllByRole("checkbox")).toHaveLength(1);
      expect(screen.getByRole("checkbox")).not.toBeChecked();
      await user.click(
        screen.getByRole("button", { name: /Prepare local bundle/ }),
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Select at least one currently accepted task with candidate files.",
      );
      expect(fetch).not.toHaveBeenCalled();
    },
  );
});

describe("abstract drafting composition retains delivery freshness", () => {
  it.each(["stale", "unknown", undefined])(
    "keeps historical abstract acceptance but rejects %s candidate delivery",
    (status) => {
      const task = {
        ...accepted,
        operation: "paper-abstract-draft",
        freshness: status ? { ...current, status } : undefined,
      } as Task;
      expect(task.result).toMatchObject({ semantic_acceptance: "accept" });
      expect(deliveryEligible(task)).toBe(false);
      render(
        <DeliveryPanel
          projectId="study"
          tasks={[task]}
          actions={[]}
          onSaved={vi.fn()}
          t={translator("en")}
        />,
      );
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    },
  );
  it("allows only current human-accepted abstract candidate delivery", () => {
    expect(
      deliveryEligible({
        ...accepted,
        operation: "paper-abstract-draft",
      }),
    ).toBe(true);
  });
});
