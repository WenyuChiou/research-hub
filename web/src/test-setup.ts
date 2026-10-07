import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  document
    .querySelectorAll('meta[name^="research-hub-"]')
    .forEach((meta) => meta.remove());
  window.history.replaceState({}, "", "/");
});
