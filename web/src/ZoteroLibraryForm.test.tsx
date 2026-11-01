import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ZoteroLibraryForm } from "./ZoteroLibraryForm";
import { translator } from "./i18n";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const t = translator("en");
const idInput = () =>
  screen.getByRole("textbox", { name: t("zoteroLibraryId") });
const typeInput = () =>
  screen.getByRole("combobox", { name: t("zoteroLibraryType") });
const check = () =>
  userEvent.click(screen.getByRole("button", { name: t("zoteroCheckFormat") }));

it("starts empty, without choosing a library type or claiming a saved connection", () => {
  render(<ZoteroLibraryForm t={t} />);
  expect(idInput()).toHaveValue("");
  expect(typeInput()).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent(t("zoteroNotChecked"));
  expect(screen.queryByRole("definition")).not.toBeInTheDocument();
});

it("identifies both missing fields and focuses the first error", async () => {
  render(<ZoteroLibraryForm t={t} />);
  await check();
  expect(screen.getByText(t("zoteroInvalidId"))).toHaveAttribute(
    "role",
    "alert",
  );
  expect(screen.getByText(t("zoteroMissingType"))).toHaveAttribute(
    "role",
    "alert",
  );
  expect(idInput()).toHaveFocus();
  expect(idInput()).toHaveAttribute("aria-invalid", "true");
  expect(typeInput()).toHaveAttribute("aria-invalid", "true");
  expect(idInput()).toHaveAccessibleDescription(
    expect.stringContaining(t("zoteroInvalidId")),
  );
});

it.each([
  "0",
  "0000",
  "-5",
  "12.5",
  "1e3",
  "12/34",
  "１２３",
  "<script>alert(1)</script>",
])(
  "rejects an invalid numeric draft %s without showing a preview",
  async (value) => {
    render(<ZoteroLibraryForm t={t} />);
    fireEvent.change(idInput(), { target: { value } });
    await userEvent.selectOptions(typeInput(), "user");
    await check();
    expect(screen.getByText(t("zoteroInvalidId"))).toBeVisible();
    expect(screen.queryByRole("definition")).not.toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  },
);

it.each(["user", "group"])(
  "checks %s and preserves large IDs as strings",
  async (type) => {
    render(<ZoteroLibraryForm t={t} />);
    fireEvent.change(idInput(), {
      target: { value: "  000900719925474099312345  " },
    });
    await userEvent.selectOptions(typeInput(), type);
    await check();
    expect(screen.getByRole("status")).toHaveTextContent(
      t("zoteroFormatValid"),
    );
    const preview = screen.getByLabelText(t("zoteroDraftPreview"));
    expect(within(preview).getByText("900719925474099312345")).toBeVisible();
    expect(
      within(preview).getByText(
        t(type === "user" ? "zoteroUserLibrary" : "zoteroGroupLibrary"),
      ),
    ).toBeVisible();
  },
);

it("focuses a missing type and clears the previous result after either field changes", async () => {
  render(<ZoteroLibraryForm t={t} />);
  fireEvent.change(idInput(), { target: { value: "123456" } });
  await check();
  expect(typeInput()).toHaveFocus();
  await userEvent.selectOptions(typeInput(), "user");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await check();
  await userEvent.selectOptions(typeInput(), "group");
  expect(
    screen.queryByLabelText(t("zoteroDraftPreview")),
  ).not.toBeInTheDocument();
  await check();
  fireEvent.change(idInput(), { target: { value: "123457" } });
  expect(
    screen.queryByLabelText(t("zoteroDraftPreview")),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(t("zoteroNotChecked"));
});

it.each(["en", "zh-TW"] as const)(
  "supports keyboard checking and cancellation in %s",
  async (locale) => {
    const tr = translator(locale);
    render(<ZoteroLibraryForm t={tr} />);
    const input = screen.getByRole("textbox", { name: tr("zoteroLibraryId") });
    await userEvent.type(input, "123456");
    await userEvent.selectOptions(screen.getByRole("combobox"), "group");
    screen.getByRole("button", { name: tr("zoteroCheckFormat") }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("status")).toHaveTextContent(
      tr("zoteroFormatValid"),
    );
    await userEvent.click(screen.getByRole("button", { name: tr("cancel") }));
    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(
      screen.queryByLabelText(tr("zoteroDraftPreview")),
    ).not.toBeInTheDocument();
  },
);

it("does not fetch or persist draft values to browser storage", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  const storage = vi.spyOn(Storage.prototype, "setItem");
  render(<ZoteroLibraryForm t={t} />);
  await userEvent.type(idInput(), "123456");
  await userEvent.selectOptions(typeInput(), "user");
  await check();
  await userEvent.click(screen.getByRole("button", { name: t("cancel") }));
  expect(fetch).not.toHaveBeenCalled();
  expect(storage).not.toHaveBeenCalled();
});
