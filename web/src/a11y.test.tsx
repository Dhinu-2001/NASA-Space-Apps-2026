import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { baseRoutes, stubFetch } from "./testFixtures";

function renderApp(hash = "#view") {
  const s = stubFetch(baseRoutes());
  vi.stubGlobal("fetch", vi.fn(s.fn));
  window.history.replaceState(null, "", `/${hash}`);
  return render(<App />);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

async function audit(label: string) {
  // jsdom has no layout engine, so colour contrast is checked separately against the real stylesheet (below).
  const res = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  const summary = res.violations.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(summary, `axe violations on ${label}`).toEqual([]);
}

describe("Keyboard navigation and landmarks", () => {
  it("implements the tabs pattern: arrow keys, Home/End, roving tab index, linked panel", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Site & time", "Compare", "Landing sites", "Explore sweeps", "Delay simulator", "Learn", "Data & assumptions"]);
    expect(tabs.filter((t) => t.getAttribute("tabindex") === "0")).toHaveLength(1);       // only the selected tab is in the tab order
    const first = screen.getByRole("tab", { name: "Site & time" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Compare" })).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Compare" }));
    fireEvent.keyDown(screen.getByRole("tab", { name: "Compare" }), { key: "ArrowLeft" });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Site & time" }), { key: "ArrowLeft" });   // wraps to the last tab
    expect(screen.getByRole("tab", { name: "Data & assumptions" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Data & assumptions" }), { key: "Home" });
    expect(screen.getByRole("tab", { name: "Site & time" })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Site & time" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Data & assumptions" })).toHaveAttribute("aria-selected", "true");
    expect(window.location.hash).toBe("#about");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", "tab-about");
    expect(screen.getByRole("tab", { name: "Data & assumptions" })).toHaveAttribute("aria-controls", panel.id);
  });

  it("provides a skip link to the current panel and a single main landmark with a level-1 heading", async () => {
    renderApp("#compare");
    await screen.findByTestId("health-status");
    const skip = screen.getByRole("link", { name: "Skip to the main content" });
    expect(skip.getAttribute("href")).toBe("#panel-compare");
    expect(document.getElementById("panel-compare")).not.toBeNull();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("keeps the Learn toggle a real button with a pressed state", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    const t = screen.getByRole("button", { name: /Learn mode/ });
    expect(t).toHaveAttribute("aria-pressed");
  });
});

describe("Automated accessibility audit (axe-core, WCAG 2 A/AA rules that work without layout)", () => {
  it("Site & time, before computing", async () => {
    renderApp("#view");
    await screen.findByTestId("health-status");
    await audit("Site & time (idle)");
  });

  it("Site & time after computing: results, charts, time player, metrics", async () => {
    renderApp("#view");
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    await screen.findByLabelText(/Time within the window/);
    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: /Learn mode: off/ }));            // explanations on
    await audit("Site & time (computed, scrubbing, learn mode on)");
  });

  it.each(["compare", "delay", "learn", "about"])("%s tab", async (tab) => {
    renderApp(`#${tab}`);
    await screen.findByTestId("health-status");
    if (tab === "learn") await screen.findByText(/A live example from the backend/);
    if (tab === "about") await screen.findByText(/de440s\.bsp/);
    await audit(tab);
  });
});

// ---------------------------------------------------------------------------------------------- colour contrast
// Parses the real stylesheet, so a token change that breaks contrast fails here. WCAG 2: 4.5:1 for text, 3:1 for graphics.

const css = readFileSync("src/styles.css", "utf-8");
const lightBlock = css.slice(css.indexOf(":root {"), css.indexOf("@media (prefers-color-scheme: dark)"));
const darkBlock = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"), css.indexOf("* { box-sizing"));
const tokens = (block: string) => Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
const light = tokens(lightBlock);
const dark = { ...light, ...tokens(darkBlock) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const TEXT_PAIRS: [string, string][] = [
  ["text", "surface"], ["text", "bg"], ["muted", "surface"], ["muted", "bg"], ["accent", "surface"], ["accent", "bg"],
  ["warn", "surface"], ["ok", "surface"], ["bad", "surface"], ["sun-text", "surface"], ["earth", "surface"], ["on-accent", "accent"],
  ["text", "validated-bg"], ["text", "unvalidated-bg"], ["text", "notimpl-bg"], ["muted", "notimpl-bg"],
  ["warn", "unvalidated-bg"], ["ok", "validated-bg"], ["terrain", "surface"],
];
const GRAPHIC_PAIRS: [string, string][] = [["sun", "surface"], ["earth", "surface"], ["accent", "surface"], ["focus", "surface"], ["warn", "surface"]];

describe("Colour contrast of the design tokens (read from styles.css)", () => {
  for (const [theme, t] of [["light", light], ["dark", dark]] as const) {
    it.each(TEXT_PAIRS)(`${theme}: text %s on %s is at least 4.5:1`, (fg, bg) => {
      expect(t[fg], `token ${fg}`).toBeDefined();
      expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
    });
    it.each(GRAPHIC_PAIRS)(`${theme}: graphic %s on %s is at least 3:1`, (fg, bg) => {
      expect(ratio(t[fg], t[bg])).toBeGreaterThanOrEqual(3);
    });
  }

  it("honours reduced-motion and forced-colours preferences and shows focus", () => {
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("@media (forced-colors: active)");
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px/);
    expect(css).toMatch(/\.tabs button\s*\{[^}]*min-height:\s*44px/);
  });
});
