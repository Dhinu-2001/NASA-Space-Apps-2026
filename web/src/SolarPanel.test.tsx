import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SolarEnergyResponse } from "./api/types";
import { SolarPanel } from "./components/SolarPanel";
import { fmtEnergy, fmtHours, fmtPower } from "./format";
import { CapabilitiesContext } from "./ui";

const caps = [
  { key: "engineering", title: "Solar energy availability (idealised direct-beam upper bound)", stage: 8, status: "validated" },
  { key: "visibility", title: "Terrain-corrected Sun/Earth visibility", stage: 5, status: "validated" },
] as never;

const scenario = { sel: { site_id: "im2-athena" }, startUtc: "2027-01-15T00:00:00Z", days: 30, height: null, bandM: 100 };

const supported: SolarEnergyResponse = {
  status: "supported", scenario_id: "abc", data_class: "calculated",
  kind: "idealised direct-beam solar energy: an UPPER BOUND, not a power budget and not battery state",
  panel: { area_m2: 1, efficiency: 0.3, irradiance_w_m2: 1361, irradiance_is_default_assumption: true, peak_electrical_power_w: 408.3, formula: "E[Wh] = …" },
  window_hours: 720,
  terrain_corrected: {
    headline_state: "any_part_visible",
    energy_wh: { nominal: 143010.4, band: [133590.2, 143873.0] },
    mean_power_w: { nominal: 198.6, band: [185.5, 199.8] },
    sunlit_hours: { nominal: 350.3, band: [327.2, 352.4] },
    longest_without_direct_sunlight: { hours: 369.7, band_hours: [367.6, 392.8], includes_open_interval: true, note: "cut off by the window edge" },
  },
  geometric: { energy_wh: 156766.9, mean_power_w: 217.7, sunlit_hours: 383.95, note: "x" },
  terrain_effect: { energy_wh_terrain_minus_geometric: -13756.5, note: "x" },
  partial_disc_bracket: { whole_disc_energy_wh: 137104.0, any_part_energy_wh: 143010.4, note: "Nominal positions only; no position band for the whole-disc figure." },
  position_sensitivity: { status: "computed", assumption: "observer position uncertain by +/-100 m", assumed_position_uncertainty_m: 100 },
  assumptions: ["Panel faces the Sun whenever any part of the Sun's disc is above the terrain horizon (sun-tracking)."],
  limitations: ["Idealised direct-beam energy: an upper bound, not a power budget and not battery state."],
};

function stub(response: unknown, ok = true) {
  const fn = vi.fn(async () => (ok ? { ok: true, json: async () => response } : { ok: false, status: 422, json: async () => response }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const ui = () => render(<CapabilitiesContext.Provider value={caps}><SolarPanel scenario={scenario} /></CapabilitiesContext.Provider>);

afterEach(() => vi.restoreAllMocks());

describe("Solar energy panel (read-only display of the backend result)", () => {
  it("requires the panel inputs before asking the backend and says what is missing", () => {
    const f = stub(supported);
    ui();
    fireEvent.click(screen.getByRole("button", { name: "Estimate energy" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/panel area/);
    fireEvent.change(screen.getByLabelText(/Panel area/), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/Efficiency/), { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate energy" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/between 0 and 1/);
    expect(f).not.toHaveBeenCalled();
  });

  it("is tagged with the real capability status and calls it an upper bound, not a power budget", () => {
    stub(supported);
    ui();
    expect(screen.getByTestId("status-engineering")).toHaveTextContent("engineering: validated");
    expect(screen.getByText(/upper bound, not a power budget and not battery state/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Irradiance/)).toHaveAttribute("placeholder", expect.stringMatching(/default assumption/));
  });

  it("sends the panel and scenario to the backend and shows every number with its band, flags and assumptions", async () => {
    const f = stub(supported);
    ui();
    fireEvent.click(screen.getByRole("button", { name: /Use example/ }));
    expect(screen.getByLabelText(/Panel area/)).toHaveValue("1");
    fireEvent.click(screen.getByRole("button", { name: "Estimate energy" }));
    const result = await screen.findByTestId("solar-result");
    const [url, init] = f.mock.calls[0] as unknown as [string, { method: string; body: string }];
    expect(url).toBe("/api/engineering/solar") ;
    const sent = JSON.parse(init.body);
    expect(init.method).toBe("POST");
    expect(sent).toMatchObject({ site: { site_id: "im2-athena" }, start_utc: "2027-01-15T00:00:00Z", duration_days: 30,
      position_uncertainty_m: 100, area_m2: 1, efficiency: 0.3, irradiance_w_m2: null });
    expect(result).toHaveTextContent("143.0 kWh");
    expect(result).toHaveTextContent(/band 133\.6 kWh to 143\.9 kWh/);            // band, not just the nominal
    expect(result).toHaveTextContent("156.8 kWh");                                // geometric beside it
    expect(result).toHaveTextContent(/band 185\.5 W to 199\.8 W/);
    expect(result).toHaveTextContent("cut off");                                  // open interval flagged
    expect(result).toHaveTextContent(/irradiance is the default assumption/);
    expect(result).toHaveTextContent(/±100 m \(a sensitivity, not an error bar/);
    expect(screen.getByTestId("solar-bracket")).toHaveTextContent(/137\.1 kWh .* to 143\.0 kWh/);
    expect(screen.getByText(/UPPER BOUND/)).toBeInTheDocument();
    expect(screen.getByText(/Assumptions and limitations of this estimate/)).toBeInTheDocument();
  });

  it("shows a data-insufficient site as a label with no energy figure", async () => {
    stub({ status: "terrain_data_insufficient", scenario_id: "x", reason: "terrain coverage is insufficient to certify the horizon (360 truncated)", reason_code: "TERRAIN_NOT_CERTIFIED" });
    ui();
    fireEvent.click(screen.getByRole("button", { name: /Use example/ }));
    fireEvent.click(screen.getByRole("button", { name: "Estimate energy" }));
    expect(await screen.findByTestId("terrain-insufficient")).toHaveTextContent(/360 truncated/);
    expect(screen.queryByTestId("solar-result")).toBeNull();
    expect(document.body.textContent).not.toMatch(/\d\s?(kWh|Wh)\b/);
  });

  it("shows backend validation errors with the field instead of a result", async () => {
    stub({ code: "INVALID_INPUT", message: "irradiance_w_m2 must be in [1000, 1500] W/m^2", field: "irradiance_w_m2", details: {}, request_id: null }, false);
    ui();
    fireEvent.change(screen.getByLabelText(/Panel area/), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Efficiency/), { target: { value: "0.3" } });
    fireEvent.change(screen.getByLabelText(/Irradiance/), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate energy" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/irradiance_w_m2/));
    expect(screen.queryByTestId("solar-result")).toBeNull();
  });

  it("formats units for display only", () => {
    expect(fmtEnergy(143010.4)).toBe("143.0 kWh");
    expect(fmtEnergy(820)).toBe("820 Wh");
    expect(fmtPower(408.3)).toBe("408.3 W");
    expect(fmtHours(369.7)).toBe("15.4 d");
    expect(fmtHours(12.25)).toBe("12.3 h");
  });
});
