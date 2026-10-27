/** Wiring smoke test: EarningsPage renders server-computed planning figures
 * verbatim - it never fabricates money math or counts expected income as
 * received. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EarningsPage } from "./EarningsPage";
import { setToken } from "../services/api";
import type { EarningsSummary } from "../types/api";

const summary: EarningsSummary = {
  recorded_available_balance_minor: 300000,
  monthly_expected_income_minor: 4500000,
  business_revenue_this_month_minor: 1200000,
  business_expenses_this_month_minor: 200000,
  business_net_profit_this_month_minor: 1000000,
  savings_contributed_this_month_minor: 500000,
  total_saved_in_goals_minor: 1500000,
  outstanding_obligations_minor: 6800000,
  available_for_planning_minor: -1900000,
  assumptions: ["available_for_planning is a planning estimate, not a bank balance."],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Route the stubbed fetch by endpoint so each query gets its own payload. */
function stubFetch(overrides: Partial<Record<string, unknown>> = {}) {
  const routes: Record<string, unknown> = {
    "/api/earnings/summary": summary,
    "/api/earnings/income-sources": [],
    "/api/earnings/business": [],
    "/api/earnings/business/profit": [],
    "/api/goals": [],
    ...overrides,
  };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    // The api client passes an absolute URL; match on the path component.
    const path = new URL(String(input)).pathname;
    return jsonResponse(routes[path] ?? []);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <EarningsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EarningsPage", () => {
  beforeEach(() => setToken("test-token"));
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders server-computed planning figures and assumptions", async () => {
    stubFetch();
    renderPage();

    // Recorded balance KES 3,000.00 comes straight from the backend.
    expect(await screen.findByText(/KES 3,000\.00/)).toBeInTheDocument();
    // Expected income / month KES 45,000.00.
    expect(screen.getByText(/KES 45,000\.00/)).toBeInTheDocument();
    // Outstanding obligations KES 68,000.00.
    expect(screen.getByText(/KES 68,000\.00/)).toBeInTheDocument();
    // The forecast states its assumptions rather than hiding them.
    expect(
      screen.getByText(/planning estimate, not a bank balance/),
    ).toBeInTheDocument();
  });

  it("shows an honest placeholder when there is no recorded balance", async () => {
    stubFetch({
      "/api/earnings/summary": { ...summary, available_for_planning_minor: null },
    });
    renderPage();

    expect(await screen.findByText(/Not enough data/)).toBeInTheDocument();
  });
});
