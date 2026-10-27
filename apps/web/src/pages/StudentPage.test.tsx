/** Wiring smoke test: StudentPage overview renders server-computed fee
 * totals and food budget from the API, formatted from minor units. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StudentPage } from "./StudentPage";
import { setToken } from "../services/api";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const routes: Record<string, unknown> = {
  "/api/student/summary": {
    total_fees_due_minor: 6000000,
    total_fees_paid_minor: 1000000,
    total_fees_outstanding_minor: 5000000,
    overdue_fees_count: 1,
    hostel_options_count: 0,
  },
  "/api/student/fees": [],
  "/api/student/hostels": [],
  "/api/student/food-budget": {
    id: 1,
    weekly_budget_minor: 350000,
    notes: null,
    updated_at: "2026-10-01T00:00:00Z",
    daily_estimate_minor: 50000,
  },
  "/api/accounts": [],
};

describe("StudentPage", () => {
  beforeEach(() => {
    setToken("test-token");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        jsonResponse(routes[new URL(String(input)).pathname] ?? []),
      ),
    );
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders fee totals and the food budget from the API", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <StudentPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // KES 60,000.00 fees due, KES 50,000.00 outstanding.
    expect(await screen.findByText(/KES 60,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/KES 50,000\.00/)).toBeInTheDocument();
    // Weekly food budget KES 3,500.00.
    expect(screen.getByText(/KES 3,500\.00/)).toBeInTheDocument();
  });
});
