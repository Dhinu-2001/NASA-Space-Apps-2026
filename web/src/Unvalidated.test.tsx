import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { atResponse, baseRoutes, stubFetch, visResponse } from "./testFixtures";

const CAVEAT = "Terrain window ch3_60m_r200km (LDEM_60S_60MPP_ADJ, 60 m pixels) is implemented_unvalidated: the owner approved its integration, but it has NOT had the independent verification pass the IM-2 terrain had (published-height check numbers, raster header, alignment confirmation), so results that use it are provisional.";

function renderApp(limitations: string[]) {
  const v = visResponse();
  v.limitations = [...v.limitations, ...limitations];
  const s = stubFetch({ ...baseRoutes(), "/visibility/series": v, "/visibility/at": atResponse(1) });
  vi.stubGlobal("fetch", vi.fn(s.fn));
  window.history.replaceState(null, "", "/#view");
  render(<App />);
}

async function compute() {
  await screen.findByTestId("health-status");
  fireEvent.click(screen.getByRole("button", { name: "Compute" }));
  await screen.findByTestId("now-sun");
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("implemented_unvalidated terrain in the Site & time view", () => {
  it("shows the same pill as an implemented_unvalidated capability on the terrain and visibility panels, plus the backend's caveat in plain sight", async () => {
    renderApp([CAVEAT]);
    await compute();
    const pills = screen.getAllByTestId("terrain-unvalidated");
    expect(pills).toHaveLength(2);                                                       // panel 4 and panel 5
    for (const p of pills) {
      expect(p).toHaveClass("tag", "tag-implemented_unvalidated");                      // the project's existing visual convention
      expect(p).toHaveTextContent("terrain: implemented unvalidated");
      expect(p).toHaveAttribute("title", CAVEAT);
    }
    expect(screen.getByTestId("terrain-unvalidated-note")).toHaveTextContent("Provisional terrain.");
    expect(screen.getByTestId("terrain-unvalidated-note")).toHaveTextContent(CAVEAT);   // visible text, not only a tooltip
  });

  it("shows nothing of the kind for terrain without that status (IM-2)", async () => {
    renderApp([]);
    await compute();
    expect(screen.queryByTestId("terrain-unvalidated")).toBeNull();
    expect(screen.queryByTestId("terrain-unvalidated-note")).toBeNull();
  });
});
