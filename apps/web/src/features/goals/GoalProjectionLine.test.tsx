/** The pace line speaks only from the projection it is handed: exact date,
 * exact minor-unit pace, and a deadline verdict that was computed upstream. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GoalProjectionLine } from "./GoalProjectionLine";
import type { GoalProjection } from "../../types/api";

function projection(over: Partial<GoalProjection> = {}): GoalProjection {
  return {
    amount_per_day_minor: 500000, contribution_count: 2, window_days: 8,
    days_to_target: 8, projected_on: "2026-11-05", status: "no_deadline",
    ...over,
  };
}

describe("GoalProjectionLine", () => {
  it("states the projected date and the pace it came from", () => {
    render(<GoalProjectionLine projection={projection()} />);
    expect(screen.getByText(/reached around 2026-11-05/)).toBeInTheDocument();
    // 500000 minor is KES 5,000.00 a day, formatted like every other figure.
    expect(screen.getByText(/KES 5,000\.00 a day/)).toBeInTheDocument();
    expect(screen.getByText(/2 contributions over 8 days/)).toBeInTheDocument();
  });

  it("badges an on-pace projection without mentioning a deadline it lacks", () => {
    render(<GoalProjectionLine projection={projection({ status: "on_track" })} />);
    expect(screen.getByText("on pace")).toBeInTheDocument();
    expect(screen.queryByText(/deadline/)).toBeNull();
  });

  it("says plainly when the pace misses the user's deadline", () => {
    render(
      <GoalProjectionLine projection={projection({ status: "after_deadline" })} />,
    );
    expect(screen.getByText(/misses the deadline/)).toBeInTheDocument();
    expect(screen.getByText("behind pace")).toBeInTheDocument();
  });

  it("marks a projection with no deadline as such", () => {
    render(<GoalProjectionLine projection={projection()} />);
    expect(screen.getByText(/no deadline set/)).toBeInTheDocument();
    expect(screen.queryByText(/on pace|behind pace/)).toBeNull();
  });

  it("formats the pace in the currency it was given", () => {
    render(<GoalProjectionLine projection={projection()} currency="UGX" />);
    expect(screen.getByText(/UGX 5,000\.00 a day/)).toBeInTheDocument();
  });
});
