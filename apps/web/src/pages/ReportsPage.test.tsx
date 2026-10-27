/** ReportsPage smoke test: it renders the API's report sections and figures
 * verbatim (server-computed), including a formatted balance-history value. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReportsPage } from "./ReportsPage";
import { setToken } from "../services/api";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const report = {
  period: { date_from: null, date_to: null, account_id: null, account_name: null, category: null },
  currency: "KES",
  cash_flow: { income_minor: 50000, expense_minor: 20000, net_minor: 30000, transfers_minor: 0, txn_count: 3 },
  spending_by_category: [{ category: "Food", total_minor: 20000, count: 2 }],
  balance_history: {
    available: true, starting_balance_minor: 100000,
    points: [{ month: "2026-10", net_change_minor: 15000, running_balance_minor: 115000 }],
    note: null,
  },
  savings: { total_saved_in_goals_minor: 30000, saved_in_period_minor: 30000, active_goals: 1, completed_goals: 0 },
  goals: [{ id: 1, name: "Laptop", type: "money", status: "active", percent: 30, remaining_amount_minor: 70000, remaining_quantity: null }],
  shortage: { items_below_target: 1, price_needed_items: 1, estimated_cost_minor: null },
  business: { revenue_minor: 50000, expenses_minor: 20000, net_profit_minor: 30000 },
  obligations: {
    outstanding_fees_minor: 60000, overdue_count: 1,
    items: [{ name: "Tuition", kind: "fee", due_on: "2026-10-26", outstanding_minor: 60000, status: "overdue" }],
  },
  note: "Transfers are excluded.",
};

describe("ReportsPage", () => {
  beforeEach(() => {
    setToken("test-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = new URL(String(input)).pathname;
        if (path.endsWith("/accounts")) return jsonResponse([]);
        if (path.endsWith("/reports/summary")) return jsonResponse(report);
        return jsonResponse({});
      }) as unknown as typeof fetch,
    );
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders report sections with server-computed figures", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ReportsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    // Running balance from the API, formatted from integer minor units.
    expect(screen.getByText("KES 1,150.00")).toBeInTheDocument();
    expect(screen.getByText("Tuition")).toBeInTheDocument();
    expect(screen.getByText("Spending by category")).toBeInTheDocument();
  });
});
