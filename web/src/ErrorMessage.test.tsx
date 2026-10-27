import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ErrorMessage } from "./components";
import { translator } from "./i18n";

afterEach(cleanup);
for (const language of ["en", "zh-TW"] as const) {
  it(`${language}: uncertain guidance does not advise retry, ordinary errors retain advice`, () => {
    const t = translator(language);
    const view = render(
      <ErrorMessage
        error={new Error("Synthetic error")}
        t={t}
        guidance="uncertain"
      />,
    );
    expect(screen.getByText(t("errorUncertainHelp"))).toBeVisible();
    expect(screen.queryByText(t("errorHelp"))).not.toBeInTheDocument();
    view.rerender(
      <ErrorMessage error={new Error("Synthetic validation error")} t={t} />,
    );
    expect(screen.getByText(t("errorHelp"))).toBeVisible();
    expect(screen.queryByText(t("errorUncertainHelp"))).not.toBeInTheDocument();
  });
}

import { PreparationRecoveryPanel } from "./PrepareRecovery";
import { TextIntakeRecoveryPanel } from "./TextIntakeRecovery";

for (const phase of ["error", "conflict", "not_observed", "unsent"] as const) {
  it(`recovery panels use ${phase} state without changing retry permissions`, () => {
    const t = translator("en");
    const shared = {
      supported: true,
      blocked: phase !== "unsent",
      storageUnavailable: false,
      entries: [
        {
          version: 1 as const,
          workspace_instance_id: "synthetic",
          project_id: "project",
          key: "opaque",
          state: "pending" as const,
          phase,
          error: new Error("Synthetic lookup error"),
        },
      ],
      park: () => false,
      check: async () => undefined,
      retry: async () => {},
      canRetry: () => false,
      canDismiss: () => false,
      dismiss: () => {},
    };
    const view = render(
      <PreparationRecoveryPanel
        recovery={{ ...shared, prepare: async () => ({ key: "opaque" }) }}
        t={t}
        onReview={() => {}}
      />,
    );
    const expected = phase === "unsent" ? "errorHelp" : "errorUncertainHelp";
    const absent = phase === "unsent" ? "errorUncertainHelp" : "errorHelp";
    expect(screen.getByText(t(expected))).toBeVisible();
    expect(screen.queryByText(t(absent))).not.toBeInTheDocument();
    view.rerender(
      <TextIntakeRecoveryPanel
        recovery={{ ...shared, submit: async () => ({ key: "opaque" }) }}
        t={t}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByText(t(expected))).toBeVisible();
    expect(screen.queryByText(t(absent))).not.toBeInTheDocument();
  });
}

it("a parked old unknown does not reclassify a newer known rejection", () => {
  const t = translator("en");
  const shared = {
    supported: true,
    blocked: false,
    storageUnavailable: false,
    entries: [
      {
        version: 1 as const,
        workspace_instance_id: "synthetic",
        project_id: "project",
        key: "old-opaque",
        state: "pending" as const,
        phase: "error" as const,
        parked: true,
        error: new Error("Old unknown"),
      },
    ],
    park: () => false,
    check: async () => undefined,
    retry: async () => {},
    canRetry: () => false,
    canDismiss: () => false,
    dismiss: () => {},
  };
  const rejected = new Error("Newer request was rejected before dispatch");
  const view = render(
    <PreparationRecoveryPanel
      recovery={{
        ...shared,
        retryError: rejected,
        prepare: async () => ({ key: "new-opaque" }),
      }}
      t={t}
      onReview={() => {}}
    />,
  );
  expect(screen.getByText(t("errorHelp"))).toBeVisible();
  expect(screen.getByText(t("errorUncertainHelp"))).toBeVisible();
  view.rerender(
    <TextIntakeRecoveryPanel
      recovery={{
        ...shared,
        error: rejected,
        submit: async () => ({ key: "new-opaque" }),
      }}
      t={t}
      onOpen={() => {}}
    />,
  );
  expect(screen.getByText(t("errorHelp"))).toBeVisible();
  expect(screen.getByText(t("errorUncertainHelp"))).toBeVisible();
});
