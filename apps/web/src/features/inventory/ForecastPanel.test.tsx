/** The forecast panel: it says a date only where there is a date, keeps money
 * in the currency it was handed, and never turns a missing price into a zero. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ForecastPanel } from "./ForecastPanel";
import type { InventoryForecast, InventoryForecasts } from "../../types/api";

function forecast(over: Partial<InventoryForecast> = {}): InventoryForecast {
  return {
    item_id: 1, name: "Socks", category_name: "Clothing", unit: "pair",
    quantity_owned: 2, target_quantity: 6, shortage: 4,
    consumption_per_day: 0.5, consumption_events: 2, window_days: 4,
    days_to_zero: 4, runout_on: "2026-11-01", restock_soon: false,
    estimated_refill_cost_minor: 60000, confidence: "limited", ...over,
  };
}

function panel(forecasts: InventoryForecast[]): InventoryForecasts {
  return { generated_on: "2026-10-28", currency: "KES", forecasts };
}

describe("ForecastPanel", () => {
  it("offers the honest empty answer when nothing has a rate yet", () => {
    render(<ForecastPanel data={panel([])} />);
    expect(screen.getByText(/enough usage history/)).toBeInTheDocument();
    expect(screen.queryByText(/refill/)).toBeNull();
  });

  it("states the projected date and the rate it was derived from", () => {
    render(<ForecastPanel data={panel([forecast()])} />);
    expect(screen.getByText(/out by 2026-11-01/)).toBeInTheDocument();
    expect(screen.getByText(/used ~0\.5 pair a day/)).toBeInTheDocument();
  });

  it("formats the refill cost in minor units with the currency given", () => {
    render(<ForecastPanel data={panel([forecast()])} />);
    // 60000 minor is KES 600.00, spelled the same way as everywhere else.
    expect(screen.getByText(/refill ≈ KES 600\.00/)).toBeInTheDocument();
  });

  it("says a price is needed rather than inventing a zero", () => {
    render(
      <ForecastPanel data={panel([forecast({ estimated_refill_cost_minor: null })])} />,
    );
    expect(screen.getByText(/price needed to refill/)).toBeInTheDocument();
    expect(screen.queryByText(/KES/)).toBeNull();
  });

  it("calls a single-day projection what it is: out now", () => {
    render(<ForecastPanel data={panel([forecast({ days_to_zero: 0 })])} />);
    expect(screen.getByText(/Out now/)).toBeInTheDocument();
  });

  it("flags a limited history and only marks steady habits otherwise", () => {
    const { unmount } = render(<ForecastPanel data={panel([forecast()])} />);
    expect(screen.getByText(/limited history/)).toBeInTheDocument();
    unmount();

    render(<ForecastPanel data={panel([forecast({ confidence: "steady" })])} />);
    expect(screen.queryByText(/limited history/)).toBeNull();
  });

  it("badges only the imminent ones as restock soon", () => {
    render(
      <ForecastPanel
        data={panel([forecast({ item_id: 1, restock_soon: true }),
                    forecast({ item_id: 2, days_to_zero: 60, restock_soon: false })])}
      />,
    );
    expect(screen.getAllByText("restock soon")).toHaveLength(1);
  });
});
