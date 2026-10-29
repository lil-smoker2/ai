/** The unusual-spending panel: every row is a stated comparison - this amount
 * against that median - and a thin history is admitted, not hidden. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnomalyPanel } from "./AnomalyPanel";
import type { ExpenseAnomalies, ExpenseAnomaly } from "../../types/api";

function anomaly(over: Partial<ExpenseAnomaly> = {}): ExpenseAnomaly {
  return {
    transaction_id: 1, description: "Lunch", category: "Food",
    amount_minor: 200000, currency: "KES", occurred_on: "2026-10-28",
    category_median_minor: 10000, deviation_score: 128.16, ...over,
  };
}

function body(anomalies: ExpenseAnomaly[]): ExpenseAnomalies {
  return { generated_on: "2026-10-28", window_days: 90,
           min_category_expenses: 5, anomalies };
}

describe("AnomalyPanel", () => {
  it("says what has to be true before any verdict is possible", () => {
    render(<AnomalyPanel data={body([])} />);
    expect(screen.getByText(/Nothing stands out/)).toBeInTheDocument();
    // The thresholds it was judged under are shown, not kept internal.
    expect(screen.getByText(/5 expenses/)).toBeInTheDocument();
    expect(screen.getByText(/90 days/)).toBeInTheDocument();
  });

  it("states the amount and the median it was compared against", () => {
    render(<AnomalyPanel data={body([anomaly()])} />);
    // 200000 minor against a 10000 minor median: KES 2,000.00 vs KES 100.00.
    expect(screen.getByText(/KES 2,000\.00 on 2026-10-28/)).toBeInTheDocument();
    expect(screen.getByText(/median KES 100\.00/)).toBeInTheDocument();
    expect(screen.getByText(/20\.0× typical/)).toBeInTheDocument();
    expect(screen.getByText("unusual")).toBeInTheDocument();
  });

  it("formats each row in the currency that transaction was recorded in", () => {
    render(<AnomalyPanel data={body([anomaly({ currency: "UGX" })])} />);
    expect(screen.getByText(/UGX 2,000\.00/)).toBeInTheDocument();
  });

  it("falls back to the category when a spend has no description", () => {
    render(<AnomalyPanel data={body([anomaly({ description: null })])} />);
    expect(screen.getByText("Food")).toBeInTheDocument();
  });

  it("shows every flagged expense it is handed", () => {
    render(
      <AnomalyPanel
        data={body([anomaly(), anomaly({ transaction_id: 2, description: "Data" })])}
      />,
    );
    expect(screen.getAllByText("unusual")).toHaveLength(2);
  });
});
