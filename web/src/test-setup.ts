import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  document
    .querySelectorAll('meta[name^="research-hub-"]')
    .forEach((meta) => meta.remove());
  window.history.replaceState({}, "", "/");
  try {
    window.localStorage.removeItem("research-hub:locale");
  } catch {
    // Ignore when a test replaces localStorage with a throwing mock.
  }
});
