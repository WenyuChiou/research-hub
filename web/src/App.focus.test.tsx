import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

vi.mock("./api", () => ({
  api: () => new Promise(() => {}),
  segment: encodeURIComponent,
}));

describe("workspace navigation focus", () => {
  let frames: Map<number, FrameRequestCallback>;
  let nextFrame: number;

  beforeEach(() => {
    frames = new Map();
    nextFrame = 0;
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
    window.history.replaceState({}, "", "#literature");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function changeHash(hash: string) {
    window.history.replaceState({}, "", hash);
    fireEvent(window, new HashChangeEvent("hashchange"));
  }

  function flushFrames() {
    act(() => {
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach((callback) => callback(0));
    });
  }

  async function activateSkip() {
    const user = userEvent.setup();
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    // Deliver native anchor navigation separately so hashchange timing is controlled.
    skip.addEventListener("click", (event) => event.preventDefault(), {
      once: true,
    });
    await user.tab();
    expect(skip).toHaveFocus();
    await user.keyboard("{Enter}");
  }

  it("focuses main after keyboard skip and retains the current page", async () => {
    render(<App />);
    await activateSkip();
    expect(screen.getByRole("main")).toHaveFocus();
    changeHash("#main-content");
    flushFrames();
    expect(screen.getByRole("main")).toHaveFocus();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Literature",
    );
    expect(screen.getByRole("link", { name: /Literature/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("cancels pending heading focus as soon as skip is activated", async () => {
    render(<App />);
    changeHash("#evidence");
    expect(frames.size).toBe(1);
    await activateSkip();
    expect(frames.size).toBe(0);
    flushFrames();
    expect(screen.getByRole("main")).toHaveFocus();
    changeHash("#main-content");
    flushFrames();
    expect(screen.getByRole("main")).toHaveFocus();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Evidence",
    );
  });

  it("focuses the current page heading after navigation supersedes a pending frame", () => {
    render(<App />);
    changeHash("#evidence");
    changeHash("#review");
    expect(frames.size).toBe(1);
    flushFrames();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Review",
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
  });

  it("cancels pending focus and removes the hash listener on unmount", () => {
    const { unmount } = render(<App />);
    changeHash("#evidence");
    expect(frames.size).toBe(1);
    unmount();
    expect(frames.size).toBe(0);
    changeHash("#review");
    expect(frames.size).toBe(0);
  });
});
