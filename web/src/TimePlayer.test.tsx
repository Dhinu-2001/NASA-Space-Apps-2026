import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TimePlayer } from "./components/TimePlayer";
import { N, visResponse } from "./testFixtures";

const vis = visResponse();

function Harness({ spy, start = null }: { spy?: (i: number | null) => void; start?: number | null }) {
  const [i, setI] = useState<number | null>(start);
  return <TimePlayer vis={vis} index={i} onIndex={(v) => { spy?.(v); setI(v); }} />;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  // @ts-expect-error test cleanup of a stubbed browser API
  delete window.matchMedia;
});

describe("Time player (displays backend samples; computes nothing)", () => {
  it("exposes the whole window as an accessible slider with the sample time as its value text", () => {
    render(<Harness />);
    const slider = screen.getByLabelText(/Time within the window/) as HTMLInputElement;
    expect(slider).toHaveAttribute("type", "range");
    expect(slider.min).toBe("0");
    expect(slider.max).toBe(String(N - 1));
    expect(slider).toHaveAttribute("aria-valuetext", "2027-01-15 00:00:00 UTC");
    expect(screen.getByText(/sample 1 of 5, every 15 min/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Playback controls" })).toBeInTheDocument();
  });

  it("shows the sample the slider is on, straight from the series, with its flags and position band", () => {
    render(<Harness />);
    expect(screen.queryByTestId("player-sun")).toBeNull();                       // nothing until the user scrubs
    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "2" } });
    expect(screen.getByTestId("player-time")).toHaveTextContent("2027-01-15 00:30:00 UTC");
    const sun = screen.getByTestId("player-sun");
    expect(sun).toHaveTextContent("az 120.0°");
    expect(sun).toHaveTextContent("el +2.00°");
    expect(sun).toHaveTextContent("terrain horizon +2.20°");
    expect(sun).toHaveTextContent("BLOCKED");
    expect(sun).toHaveTextContent("changes with position");
    expect(sun).toHaveTextContent("horizon incomplete");
    expect(sun).toHaveTextContent(/up to 0\.90° for the assumed position error/);
    const earth = screen.getByTestId("player-earth");
    expect(earth).toHaveTextContent("az 320.0°");
    expect(earth).toHaveTextContent("el +7.00°");
    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "3" } });
    expect(screen.getByTestId("player-sun")).toHaveTextContent("VISIBLE");
    expect(screen.getByTestId("player-sun")).not.toHaveTextContent("changes with position");
  });

  it("steps one sample at a time and jumps to the ends, never leaving the window", () => {
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous sample" }));
    expect(spy).toHaveBeenLastCalledWith(0);                                       // clamped at the start
    fireEvent.click(screen.getByRole("button", { name: "Next sample" }));
    expect(spy).toHaveBeenLastCalledWith(1);
    fireEvent.click(screen.getByRole("button", { name: "Go to the end of the window" }));
    expect(spy).toHaveBeenLastCalledWith(N - 1);
    fireEvent.click(screen.getByRole("button", { name: "Next sample" }));
    expect(spy).toHaveBeenLastCalledWith(N - 1);                                   // clamped at the end
    fireEvent.click(screen.getByRole("button", { name: "Go to the start of the window" }));
    expect(spy).toHaveBeenLastCalledWith(0);
  });

  it("plays through the samples at the chosen speed and stops at the end", () => {
    vi.useFakeTimers();
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Speed"), { target: { value: "0" } });   // slow: 1 sample per 100 ms tick
    fireEvent.click(screen.getByRole("button", { name: /Play/ }));
    expect(screen.getByRole("button", { name: /Pause/ })).toHaveAttribute("aria-pressed", "true");
    act(() => { vi.advanceTimersByTime(300); });
    expect(screen.getByTestId("player-time")).toHaveTextContent("2027-01-15 00:45:00 UTC");   // sample 3
    act(() => { vi.advanceTimersByTime(200); });
    expect(screen.getByTestId("player-time")).toHaveTextContent("2027-01-15 01:00:00 UTC");   // last sample
    expect(screen.getByRole("button", { name: /Play/ })).toHaveAttribute("aria-pressed", "false");   // stopped itself
  });

  it("pauses when the user takes over, and 'back to the chosen time' hands control back", () => {
    vi.useFakeTimers();
    const spy = vi.fn();
    render(<Harness spy={spy} />);
    expect(screen.getByRole("button", { name: "Back to the chosen time" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Speed"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: /Play/ }));
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.click(screen.getByRole("button", { name: /Pause/ }));
    const before = screen.getByTestId("player-time").textContent;
    act(() => { vi.advanceTimersByTime(1000); });
    expect(screen.getByTestId("player-time").textContent).toBe(before);             // paused: time stays put
    fireEvent.click(screen.getByRole("button", { name: "Back to the chosen time" }));
    expect(spy).toHaveBeenLastCalledWith(null);
    expect(screen.queryByTestId("player-sun")).toBeNull();
  });

  it("never calls the network: every frame is a sample already computed", () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    render(<Harness />);
    fireEvent.change(screen.getByLabelText(/Time within the window/), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Previous sample" }));
    expect(f).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("states plainly that nothing is interpolated between samples", () => {
    render(<Harness />);
    expect(screen.getByText(/nothing is interpolated between samples/)).toBeInTheDocument();
  });

  it("respects a reduced-motion preference: autoplay is disabled, the slider and step buttons still work", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as unknown as typeof window.matchMedia;
    render(<Harness />);
    expect(screen.getByRole("button", { name: /Play/ })).toBeDisabled();
    expect(screen.getByText(/Autoplay is disabled because your system requests reduced motion/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next sample" }));
    expect(screen.getByTestId("player-time")).toHaveTextContent("2027-01-15 00:15:00 UTC");
  });

  it("announces the time politely only when not playing (no spam while animating)", () => {
    vi.useFakeTimers();
    render(<Harness />);
    expect(screen.getByTestId("player-time")).toHaveAttribute("aria-live", "polite");
    fireEvent.click(screen.getByRole("button", { name: /Play/ }));
    expect(screen.getByTestId("player-time")).toHaveAttribute("aria-live", "off");
  });

  it("renders nothing for a series with fewer than two samples", () => {
    const one = visResponse();
    for (const b of ["sun", "earth"] as const) {
      const s = one.bodies[b].series!;
      one.bodies[b].series = { ...s, times_s: [0] };
    }
    const { container } = render(<TimePlayer vis={one} index={null} onIndex={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
