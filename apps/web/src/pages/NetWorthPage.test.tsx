/** Net worth page test: it shows the inventory priced, row by row, and never
 * turns a missing price into a zero. Pictures are the asset library's own. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NetWorthPage } from "./NetWorthPage";
import { setToken } from "../services/api";
import type { Valuation } from "../types/api";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const trousers: Valuation = {
  currency: "KES",
  lines: [
    {
      item_id: 1,
      name: "Chino trousers",
      category_name: "Trousers",
      category_slug: "trousers",
      quantity_owned: 2,
      unit: null,
      target_quantity: 4,
      needed_quantity: 2,
      unit_cost_minor: 150000,
      price_verified: false,
      value_minor: 300000,
      to_target_minor: 300000,
      price_needed: false,
      image_asset_id: "asset-1",
    },
  ],
  items: 1,
  units_owned: 2,
  units_needed: 2,
  net_worth_minor: 300000,
  priced_value_minor: 300000,
  valued_items: 1,
  unpriced_items: 0,
  to_target_minor: 300000,
  replacement_total_minor: 600000,
  saved: {
    on_date: "2026-10-28",
    net_worth_minor: 300000,
    priced_value_minor: 300000,
    valued_items: 1,
    unpriced_items: 0,
    complete: true,
    updated_at: "2026-10-28T10:00:00Z",
  },
  history: [],
  note: "Net worth is the value of what you own.",
};

const partlyUnpriced: Valuation = {
  ...trousers,
  lines: [
    ...trousers.lines,
    {
      item_id: 2,
      name: "Socks",
      category_name: "Socks",
      category_slug: "socks",
      quantity_owned: 3,
      unit: null,
      target_quantity: null,
      needed_quantity: 0,
      unit_cost_minor: null,
      price_verified: false,
      value_minor: null,
      to_target_minor: 0,
      price_needed: true,
      image_asset_id: null,
    },
  ],
  items: 2,
  units_owned: 5,
  net_worth_minor: null,
  unpriced_items: 1,
  replacement_total_minor: null,
  saved: { ...trousers.saved!, net_worth_minor: null, complete: false },
};

function mockFetch(body: Valuation) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/thumbnail")) return jsonResponse({});
    if (url.includes("/api/networth")) return jsonResponse(body);
    return jsonResponse({});
  }) as unknown as typeof fetch;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NetWorthPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NetWorthPage", () => {
  // jsdom has no object-URL support, so stub the two calls the picture makes.
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  beforeEach(() => {
    setToken("test-token");
    URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
  });
  afterEach(() => {
    setToken(null);
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    vi.unstubAllGlobals();
  });

  it("prices each thing owned: have, need, unit cost and total", async () => {
    vi.stubGlobal("fetch", mockFetch(trousers));
    renderPage();

    expect(await screen.findByText("Chino trousers")).toBeInTheDocument();
    // how much I have / how much I may need / how much one costs
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.getByText(/1,500\.00/)).toBeInTheDocument();

    // the totals, including the money to have everything
    expect(screen.getByText("KES 6,000.00")).toBeInTheDocument();
    expect(screen.getByText(/saved automatically/i)).toBeInTheDocument();
  });

  it("leaves the total unknown when something owned has no price", async () => {
    vi.stubGlobal("fetch", mockFetch(partlyUnpriced));
    renderPage();

    expect(await screen.findByText("Socks")).toBeInTheDocument();
    expect(screen.getByText("Not known yet")).toBeInTheDocument();
    // The unpriced pair is flagged wherever its figure would have been, and no
    // total is quietly replaced by a zero.
    expect(screen.getAllByText("Price needed").length).toBeGreaterThan(1);
    expect(screen.getByText(/At least KES 3,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/still without a price/)).toBeInTheDocument();
    expect(screen.queryByText("KES 0.00")).not.toBeInTheDocument();
  });
});
