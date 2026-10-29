/** The trend sentence: direction, slope and gaps exactly as recorded.

 * TrendSummary renders only inside the "Saved over time" card when the
 * backend found enough complete days to read a direction, so these tests
 * cover the sentence it builds - including the signed change, the gap
 * admission and the currency it was told. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrendSummary } from "./TrendSummary";
import type { NetWorthTrend } from "../../types/api";

function trend(over: Partial<NetWorthTrend> = {}): NetWorthTrend {
  return {
    from_date: "2026-10-26", to_date: "2026-10-28", known_days: 3,
    gap_days: 0, slope_minor_per_day: 50000, change_minor: 100000,
    recent_average_minor: 150000, direction: "building", ...over,
  };
}

describe("TrendSummary", () => {
  it("states the direction, the change and the days it was read from", () => {
    render(<TrendSummary trend={trend()} />);
    expect(screen.getByText(/has been building/)).toBeInTheDocument();
    expect(screen.getByText(/KES 1,000\.00 across 3 recorded days/)).toBeInTheDocument();
    expect(screen.getByText(/2026-10-26 to 2026-10-28/)).toBeInTheDocument();
  });

  it("spells the slope the way it is: an absolute amount, up or down", () => {
    render(
      <TrendSummary trend={trend({ slope_minor_per_day: -50000, direction: "declining" })} />,
    );
    expect(screen.getByText(/has been declining/)).toBeInTheDocument();
    // The sign lives in the words, so the amount is not double-negative.
    expect(screen.getByText(/about KES 500\.00 a day down/)).toBeInTheDocument();
  });

  it("reports a steady record without dressing it up", () => {
    render(<TrendSummary trend={trend({ direction: "steady", slope_minor_per_day: 10 })} />);
    expect(screen.getByText(/holding steady/)).toBeInTheDocument();
    expect(screen.getByText(/KES 0\.10 a day up/)).toBeInTheDocument();
  });

  it("admits the days that were left out for want of a known total", () => {
    render(<TrendSummary trend={trend({ gap_days: 1 })} />);
    expect(screen.getByText(/1 day left out for want of a known total/)).toBeInTheDocument();
  });

  it("uses the currency it was given for every figure", () => {
    render(<TrendSummary trend={trend()} currency="UGX" />);
    expect(screen.getByText(/UGX 1,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/UGX 1,500\.00/)).toBeInTheDocument(); // recent average
  });
});
