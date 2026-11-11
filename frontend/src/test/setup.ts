import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrollIntoView natively
Element.prototype.scrollIntoView = () => {};

// Mock clipboard for copy button verification
Object.defineProperty(navigator, "clipboard", {
  value: {
    writeText: async () => undefined,
  },
  configurable: true,
});
