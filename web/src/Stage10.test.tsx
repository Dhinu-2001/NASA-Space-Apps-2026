import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { Explain, LearnProvider, LearnToggle } from "./learn";
import { BUILTIN_PROFILES, ProfilePicker, loadSaved } from "./profiles";
import { baseRoutes, scenarioSupported, stubFetch } from "./testFixtures";

function renderApp(routes: Record<string, unknown> = {}, hash = "#view") {
  const s = stubFetch({ ...baseRoutes(), ...routes });
  vi.stubGlobal("fetch", vi.fn(s.fn));
  window.history.replaceState(null, "", `/${hash}`);
  render(<App />);
  return s;
}

async function computeView() {
  await screen.findByTestId("health-status");
  fireEvent.click(screen.getByRole("button", { name: "Compute" }));
  await screen.findByTestId("now-sun");
  await screen.findByLabelText(/Time within the window/);
}

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

// ------------------------------------------------------------------ 1. scrubbing in the real View tab

describe("Time scrubbing in the Site & time tab", () => {
  it("moves the Sun/Earth cards from the series with NO extra API call, and returns to the chosen time", async () => {
    const s = renderApp();
    await computeView();
    const sun = screen.getByTestId("now-sun");
    expect(sun).toHaveTextContent("az 110.0°");                      // /visibility/at sample (index 1)
    expect(sun).toHaveTextContent("el +1.50°");
    const before = s.calls.length;

    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "3" } });
    expect(screen.getByTestId("now-sun")).toHaveTextContent("az 130.0°");        // series sample 3
    expect(screen.getByTestId("now-sun")).toHaveTextContent("el +2.50°");
    expect(screen.getByTestId("now-earth")).toHaveTextContent("az 330.0°");
    expect(screen.getByText(/3 · Sun and Earth at 2027-01-15 00:45:00 UTC/)).toBeInTheDocument();
    expect(screen.getByText(/showing the sample chosen with the time player/)).toBeInTheDocument();
    expect(s.calls.length).toBe(before);                                          // not one request while scrubbing

    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "2" } });
    expect(screen.getByTestId("now-sun")).toHaveTextContent("BLOCKED");
    expect(screen.getByTestId("now-sun")).toHaveTextContent("changes with position");
    expect(screen.getByTestId("now-sun")).toHaveTextContent("horizon incomplete: upper bound");

    fireEvent.click(screen.getByRole("button", { name: "Back to the chosen time" }));
    expect(screen.getByTestId("now-sun")).toHaveTextContent("az 110.0°");
    expect(screen.queryByText(/showing the sample chosen with the time player/)).toBeNull();
    expect(s.calls.length).toBe(before);
  });

  it("moves the horizon-plot markers and the timeline cursor to the scrubbed sample", async () => {
    renderApp();
    await computeView();
    const ellipsesBefore = Array.from(document.querySelectorAll("svg ellipse")).map((e) => e.getAttribute("cx"));
    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "4" } });
    const ellipsesAfter = Array.from(document.querySelectorAll("svg ellipse")).map((e) => e.getAttribute("cx"));
    expect(ellipsesAfter).not.toEqual(ellipsesBefore);                             // Sun and Earth markers moved
    const cursor = document.querySelector('svg[aria-label="Visibility timeline"] line[stroke-dasharray="2 2"]');
    expect(cursor).not.toBeNull();
  });

  it("offers the player only when the visibility series exists (an insufficient site gets none)", async () => {
    renderApp({
      "/visibility/series": { ...baseRoutes()["/visibility/series"], position_sensitivity: { status: "not_computed", reason: "terrain coverage is insufficient (360 truncated)", data_class: "calculated", kind: "k", assumed_position_uncertainty_m: 100, assumption: null, n_directions: null, method: "m", limitations: "l" } },
    });
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Compute" }));
    expect(await screen.findByTestId("terrain-insufficient")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Time within the window/)).toBeNull();
  });
});

// ------------------------------------------------------------------ 2. educational mode

describe("Learn mode", () => {
  it("is off by default, switches explanations on and off, and remembers the choice", () => {
    render(<LearnProvider><LearnToggle /><Explain id="horizon" /></LearnProvider>);
    expect(screen.queryByTestId("explain-horizon")).toBeNull();
    const toggle = screen.getByRole("button", { name: /Learn mode: off/ });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(screen.getByTestId("explain-horizon")).toHaveTextContent(/terrain skyline/);
    expect(screen.getByRole("button", { name: /Learn mode: on/ })).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem("lunarnav.learn")).toBe("1");
    // a fresh mount reads the stored choice
    document.body.innerHTML = "";
    render(<LearnProvider><LearnToggle /><Explain id="bands" /></LearnProvider>);
    expect(screen.getByTestId("explain-bands")).toHaveTextContent(/sensitivity to the input position, not an error bar/);
  });

  it("ignores unknown ids and works when browser storage is unavailable", () => {
    const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
    vi.spyOn(window, "localStorage", "get").mockReturnValue(broken as unknown as Storage);
    render(<LearnProvider><LearnToggle /><Explain id="does-not-exist" /><Explain id="player" /></LearnProvider>);
    fireEvent.click(screen.getByRole("button", { name: /Learn mode: off/ }));
    expect(screen.getByTestId("explain-player")).toBeInTheDocument();
    expect(screen.queryByTestId("explain-does-not-exist")).toBeNull();
  });

  it("shows the per-panel explanations in the Site & time tab only when Learn mode is on", async () => {
    renderApp();
    await computeView();
    for (const id of ["sunEarthNow", "horizon", "timelines", "bands", "profiles"]) expect(screen.queryByTestId(`explain-${id}`)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Learn mode: off/ }));
    for (const id of ["sunEarthNow", "horizon", "timelines", "bands", "profiles"]) expect(screen.getByTestId(`explain-${id}`)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Learn mode: on/ }));
    expect(screen.queryByTestId("explain-horizon")).toBeNull();
  });

  it("has a Learn tab with the seven-step workflow, the glossary, and honest limits", async () => {
    renderApp({}, "#learn");
    await screen.findByTestId("health-status");
    expect(screen.getByRole("tab", { name: "Learn" })).toHaveAttribute("aria-selected", "true");
    const steps = screen.getByRole("heading", { name: "How to use the app in seven steps" }).closest("section") as HTMLElement;
    expect(within(steps).getAllByRole("listitem")).toHaveLength(7);
    for (const term of ["Azimuth", "Elevation", "Terrain horizon", "Geometric visibility", "Position band", "Cut off", "Upper bound", "Terrain data insufficient", "Validated"]) {
      expect(screen.getByText(term, { selector: "dt" })).toBeInTheDocument();
    }
    expect(screen.getByText(/It does not mean proven against measurement/)).toBeInTheDocument();
    expect(screen.getByText(/not communication-link availability and not a power budget/)).toBeInTheDocument();
  });

  it("fills the live example from the backend (not from hard-coded numbers) and shows its band", async () => {
    renderApp({ "/scenarios/evaluate": scenarioSupported(0.412, 0.77) }, "#learn");
    const ex = await screen.findByText("A live example from the backend");
    const panel = ex.closest("section") as HTMLElement;
    await waitFor(() => expect(panel).toHaveTextContent("41.2 %"));          // follows the stub, so it is not hard-coded
    expect(panel).toHaveTextContent("77.0 %");
    expect(panel).toHaveTextContent(/band 38\.2 % to 41\.5 %/);
    expect(panel).toHaveTextContent("53.3 %");                               // geometric beside it
  });

  it("shows an insufficient example as a label with no figures, and backend errors as errors", async () => {
    renderApp({ "/scenarios/evaluate": { id: "x", status: "terrain_data_insufficient", reason: "terrain coverage is insufficient (360 truncated)", spec: {}, served_from: "computed" } }, "#learn");
    expect(await screen.findByTestId("terrain-insufficient")).toHaveTextContent(/360 truncated/);
    document.body.innerHTML = "";
    const s = stubFetch({ ...baseRoutes() });
    delete (s as unknown as { x?: unknown }).x;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { method?: string }) => {
      if (url.includes("/scenarios/evaluate")) return { ok: false, status: 422, json: async () => ({ code: "INVALID_INPUT", message: "boom", field: "site", details: {}, request_id: null }) };
      return s.fn(url, init);
    }));
    render(<App />);
    expect(await screen.findByText(/Example failed/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ 3. configurable mission profiles

describe("Mission profiles", () => {
  const current = { days: "30", height: "3", band: "50" };

  it("applies a built-in profile by filling in the form values only", () => {
    const onApply = vi.fn();
    render(<ProfilePicker current={current} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect(onApply).toHaveBeenLastCalledWith({ days: "14", height: "", band: "100" });
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "tight-position" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect(onApply).toHaveBeenLastCalledWith({ days: "30", height: "", band: "20" });
  });

  it("keeps the current observer height when the form has none (Compare/Delay)", () => {
    const onApply = vi.fn();
    render(<ProfilePicker current={current} onApply={onApply} showHeight={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect(onApply).toHaveBeenLastCalledWith({ days: "14", height: "3", band: "100" });
  });

  it("labels the built-in profiles as illustrative assumptions, never as real mission requirements", () => {
    render(<ProfilePicker current={current} onApply={() => undefined} />);
    expect(screen.getByText(/illustrative assumptions/)).toBeInTheDocument();
    expect(screen.getByText(/not real mission requirements/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Built-in (illustrative)" })).toBeInTheDocument();
    for (const p of BUILTIN_PROFILES) expect(p.days).toBeLessThanOrEqual(60);
    expect(BUILTIN_PROFILES.every((p) => p.band > 0 && p.builtin)).toBe(true);
  });

  it("saves the current settings as a named profile, persists it, applies it, and deletes it", () => {
    const onApply = vi.fn();
    render(<ProfilePicker current={current} onApply={onApply} />);
    fireEvent.change(screen.getByLabelText("Save the current settings as"), { target: { value: "My site survey" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const saved = JSON.parse(window.localStorage.getItem("lunarnav.profiles") ?? "[]");
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({ name: "My site survey", days: 30, height: "3", band: 50 });
    const select = screen.getByLabelText("Profile") as HTMLSelectElement;
    const option = within(screen.getByRole("group", { name: "Saved in this browser" })).getByRole("option", { name: "My site survey" });
    fireEvent.change(select, { target: { value: (option as HTMLOptionElement).value } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect(onApply).toHaveBeenLastCalledWith({ days: "30", height: "3", band: "50" });
    fireEvent.click(screen.getByRole("button", { name: "Delete this saved profile" }));
    expect(JSON.parse(window.localStorage.getItem("lunarnav.profiles") ?? "[]")).toHaveLength(0);
    expect(screen.queryByRole("option", { name: "My site survey" })).toBeNull();
  });

  it("refuses to save an unnamed or invalid profile and says why", () => {
    const { rerender } = render(<ProfilePicker current={current} onApply={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/name/);
    rerender(<ProfilePicker current={{ days: "0", height: "", band: "100" }} onApply={() => undefined} />);
    fireEvent.change(screen.getByLabelText("Save the current settings as"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/between 0 and 60 days/);
    rerender(<ProfilePicker current={{ days: "30", height: "abc", band: "100" }} onApply={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/observer height/);
    rerender(<ProfilePicker current={{ days: "30", height: "", band: "-1" }} onApply={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/above 0 m/);
    expect(window.localStorage.getItem("lunarnav.profiles")).toBeNull();
  });

  it("survives corrupt or unavailable storage and drops stored profiles that fail validation", () => {
    window.localStorage.setItem("lunarnav.profiles", "{not json");
    expect(loadSaved()).toEqual([]);
    window.localStorage.setItem("lunarnav.profiles", JSON.stringify([
      { id: "a", name: "ok", days: 10, height: "", band: 100 },
      { id: "b", name: "too long", days: 999, height: "", band: 100 },
      { id: "c", name: "bad band", days: 10, height: "", band: 0 },
      { id: 5, name: "bad id", days: 10, height: "", band: 100 },
      "junk",
    ]));
    expect(loadSaved().map((p) => p.name)).toEqual(["ok"]);
    vi.spyOn(window, "localStorage", "get").mockReturnValue({ getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } } as unknown as Storage);
    expect(loadSaved()).toEqual([]);
    render(<ProfilePicker current={current} onApply={() => undefined} />);
    fireEvent.change(screen.getByLabelText("Save the current settings as"), { target: { value: "still works" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("option", { name: "still works" })).toBeInTheDocument();      // in-memory for this session
  });

  it("fills the real form in the Site & time tab (window length, observer height, position uncertainty)", async () => {
    renderApp();
    await screen.findByTestId("health-status");
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "long" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect((screen.getByLabelText(/Window length/) as HTMLInputElement).value).toBe("60");
    expect((screen.getByLabelText(/Assumed landing-position uncertainty/) as HTMLInputElement).value).toBe("100");
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "loose-position" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect((screen.getByLabelText(/Assumed landing-position uncertainty/) as HTMLInputElement).value).toBe("200");
    expect((screen.getByLabelText(/Window length/) as HTMLInputElement).value).toBe("30");
  });

  it("is available in Compare and Delay and fills their window length and position uncertainty", async () => {
    renderApp({}, "#compare");
    await screen.findByTestId("health-status");
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect((screen.getByLabelText(/Window length/) as HTMLInputElement).value).toBe("14");
    fireEvent.click(screen.getByRole("tab", { name: "Delay simulator" }));
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "tight-position" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply profile" }));
    expect((screen.getByLabelText(/Position uncertainty/) as HTMLInputElement).value).toBe("20");
  });
});
