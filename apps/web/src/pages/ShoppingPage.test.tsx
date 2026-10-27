/** Wiring smoke test: ShoppingPage renders server-computed totals and the
 * honest empty state - the UI never fabricates prices or purchases. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ShoppingPage } from "./ShoppingPage";
import { setToken } from "../services/api";
import type { ShoppingItem, ShoppingListPage } from "../types/api";

const listPage: ShoppingListPage = {
  lists: [
    {
      id: 1,
      name: "Market run",
      notes: null,
      goal_id: null,
      created_at: "2026-10-01T00:00:00Z",
    },
  ],
  page: { total: 1, page: 1, page_size: 50 },
};

const pricedLine: ShoppingItem = {
  id: 10,
  list_id: 1,
  name: "Sufuria",
  quantity_needed: 2,
  estimated_unit_cost_minor: 250000,
  price_source: "verified",
  seller: "Kariokor",
  delivery_cost_minor: 10000,
  transport_cost_minor: 5000,
  fees_minor: 1500,
  status: "needed",
  inventory_item_id: null,
  goal_id: null,
  notes: null,
  created_at: "2026-10-01T00:00:00Z",
  estimated_item_cost_minor: 500000,
  estimated_total_minor: 516500,
  price_needed: false,
};

const unknownPriceLine: ShoppingItem = {
  ...pricedLine,
  id: 11,
  name: "Mystery gadget",
  estimated_unit_cost_minor: null,
  price_source: "estimate",
  estimated_item_cost_minor: null,
  estimated_total_minor: null,
  price_needed: true,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(items: ShoppingItem[]) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/shopping/lists?") || url.endsWith("/api/shopping/lists")) {
      return jsonResponse(listPage);
    }
    if (url.includes("/items")) return jsonResponse(items);
    if (url.includes("/api/accounts")) return jsonResponse([]);
    return jsonResponse({});
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ShoppingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ShoppingPage", () => {
  beforeEach(() => setToken("test-token"));
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders server-computed totals and the verified-price badge", async () => {
    vi.stubGlobal("fetch", mockFetch([pricedLine]));
    renderPage();

    expect(await screen.findByText("Sufuria")).toBeInTheDocument();
    // 5,165.00 total comes straight from the API, never recomputed in the UI.
    expect(screen.getByText(/KES 5,165\.00/)).toBeInTheDocument();
    expect(screen.getByText(/verified price/)).toBeInTheDocument();
  });

  it("shows 'Price needed' when the backend flags a missing price", async () => {
    vi.stubGlobal("fetch", mockFetch([unknownPriceLine]));
    renderPage();

    expect(await screen.findByText("Mystery gadget")).toBeInTheDocument();
    expect(screen.getByText(/Price needed/)).toBeInTheDocument();
    // Must not accidentally render a fabricated zero-cost total.
    expect(screen.queryByText(/KES 0\.00/)).not.toBeInTheDocument();
  });

  it("shows an empty state when no lists exist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/api/shopping/lists")) {
          return jsonResponse({
            lists: [],
            page: { total: 0, page: 1, page_size: 50 },
          });
        }
        return jsonResponse([]);
      }),
    );
    renderPage();
    expect(await screen.findByText(/No shopping lists yet/)).toBeInTheDocument();
  });
});
