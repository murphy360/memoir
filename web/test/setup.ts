import "@testing-library/jest-dom/vitest";
// Every file gets an IndexedDB: the shell resumes uploads from it on mount.
import "fake-indexeddb/auto";

/** jsdom has no matchMedia: answer width queries from a width the test can set. */
let width = 390;
const listeners = new Set<() => void>();

export function setWidth(next: number) {
  width = next;
  listeners.forEach((notify) => notify());
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => {
    const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? 0);
    return {
      get matches() {
        return width >= min;
      },
      media: query,
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
    };
  },
});

beforeEach(() => setWidth(390));
