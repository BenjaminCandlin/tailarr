import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  document.documentElement.className = "";
});

// jsdom has no matchMedia; pretend the device prefers dark unless a test says otherwise.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("dark")
      ? !(window as { __prefersLight?: boolean }).__prefersLight
      : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }),
});

// jsdom has no ResizeObserver (Radix switches measure themselves with it).
class NoResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(window, "ResizeObserver", { writable: true, value: NoResizeObserver });
