/** Wiring smoke test: GoalsPage renders API-provided computed figures -
 * the UI never invents goal math of its own. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoalsPage } from "./GoalsPage";
import { setToken } from "../services/api";
import type { Goal } from "../types/api";

const goal: Goal = {
  id: 1,
  name: "New laptop",
  type: "money",
  status: "active",
  target_amount_minor: 8000000,
  target_quantity: null,
  current_quantity: null,
  estimated_unit_cost_minor: null,
  deadline: "2026-12-31",
  priority: "high",
  inventory_item_id: null,
  notes: null,
  created_at: "2026-10-01T00:00:00Z",
  completed_at: null,
  amount_saved_minor: 1200000,
  remaining_amount_minor: 6800000,
  remaining_quantity: null,
  estimated_remaining_cost_minor: null,
  required_monthly_saving_minor: 755556,
  deadline_state: "ok",
  projection: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GoalsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GoalsPage", () => {
  beforeEach(() => setToken("test-token"));
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders saved amounts from the API response", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([goal]));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("New laptop")).toBeInTheDocument();
    // KES 12,000.00 saved of KES 80,000.00 - formatted minor units.
    expect(screen.getByText(/KES 12,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/KES 68,000\.00/)).toBeInTheDocument();
    // Required monthly saving comes straight from the backend calculation.
    expect(screen.getByText(/KES 7,555\.56 per month/)).toBeInTheDocument();
    // No contribution history in the response means no projected date printed.
    expect(screen.queryByText(/reached around/)).toBeNull();
  });

  it("shows an empty state when no goals exist", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
    renderPage();
    expect(await screen.findByText(/No goals yet/)).toBeInTheDocument();
  });
});
