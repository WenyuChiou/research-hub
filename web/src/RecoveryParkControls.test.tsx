import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { RecoveryParkControls } from "./RecoveryParkControls";
import { translator } from "./i18n";
const t = translator("en");
it("warning then confirmation parks, separate intent is a later explicit action", () => {
  const park = vi.fn(() => true),
    separate = vi.fn();
  const props = {
    entry: { key: "opaque", phase: "not_observed" },
    recovery: { blocked: true, park },
    t,
    onSeparate: separate,
  };
  const { rerender } = render(<RecoveryParkControls {...props} />);
  fireEvent.click(screen.getByText(t("recoveryPark")));
  expect(park).not.toHaveBeenCalled();
  expect(screen.getByText(t("recoveryParkWarning"))).toBeVisible();
  fireEvent.click(screen.getByText(t("recoveryParkConfirm")));
  expect(park).toHaveBeenCalledWith("opaque");
  expect(separate).not.toHaveBeenCalled();
  rerender(
    <RecoveryParkControls
      {...props}
      entry={{ ...props.entry, parked: true }}
      recovery={{ blocked: false, park }}
    />,
  );
  fireEvent.click(screen.getByText(t("recoverySeparate")));
  expect(separate).toHaveBeenCalledOnce();
});
it.each(["sending", "checking", "unsent", "found"])(
  "does not offer Park for %s",
  (phase) => {
    render(
      <RecoveryParkControls
        entry={{ key: "opaque", phase }}
        recovery={{ blocked: true, park: vi.fn() }}
        t={t}
      />,
    );
    expect(screen.queryByText(t("recoveryPark"))).not.toBeInTheDocument();
  },
);
it("denied marker storage requires explicit session-only choice", () => {
  const park = vi.fn(() => false);
  render(
    <RecoveryParkControls
      entry={{ key: "opaque", phase: "error", parkStorageFailed: true }}
      recovery={{ blocked: true, park }}
      t={t}
    />,
  );
  fireEvent.click(screen.getByText(t("recoveryPark")));
  expect(screen.getByRole("alert")).toHaveTextContent(
    t("recoveryParkSessionWarning"),
  );
  expect(park).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText(t("recoveryParkSession")));
  expect(park).toHaveBeenCalledWith("opaque", true);
});
