/** Wiring smoke test: EarningsPage renders server-computed planning figures
 * verbatim - it never fabricates money math or counts expected income as
 * received.
 *
 * The places tab is held to the same line: a rate is only ever shown with the
 * date it was checked, a plan prints the assumptions it rests on, a bet gets no
 * rate and no projected return, and a rate typed without a date never reaches
 * the API at all. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EarningsPage } from "./EarningsPage";
import { setToken } from "../services/api";
import type {
  EarningsSummary,
  Projection,
  SavingsVehicle,
} from "../types/api";

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
  // The second argument is never read here - it is declared so bodyOf() can
  // look at what a test made the page send.
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    // The api client passes an absolute URL; match on the path component.
    const path = new URL(String(input)).pathname;
    return jsonResponse(routes[path] ?? []);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The JSON body of the first request to a path ending this way, or null. */
function bodyOf(
  fetchMock: ReturnType<typeof stubFetch>,
  suffix: string,
): Record<string, unknown> | null {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith(suffix));
  return call?.[1]?.body ? (JSON.parse(String(call[1]!.body)) as Record<string, unknown>) : null;
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

  // --- Places money can sit ---

  it("shows a rate only with the day it was checked", async () => {
    stubFetch({ "/api/earnings/vehicles": [ziidi] });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));

    const card = await screen.findByText("Ziidi");
    expect(card).toBeInTheDocument();
    // Nothing here knows a platform's current rate: the figure is the person's
    // own note, and it is never shown as if it were fresh.
    expect(
      screen.getByText(/10\.75% a year, checked 2026-10-01/),
    ).toBeInTheDocument();
    expect(screen.getByText(/no records against it yet/)).toBeInTheDocument();
  });

  it("asks how much and how long, then prints what the rate would give", async () => {
    const fetchMock = stubFetch({
      "/api/earnings/vehicles": [ziidi],
      "/api/earnings/vehicles/7/project": projection,
    });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Save" }));

    fireEvent.change(screen.getByLabelText(/How much are you saving/i), {
      target: { value: "1000" },
    });
    fireEvent.change(screen.getByLabelText(/For how long/i), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Show what it would give/i }));

    await vi.waitFor(() => expect(screen.getByText("KES 10,750.00")).toBeInTheDocument());
    expect(screen.getByText("KES 110,750.00")).toBeInTheDocument();
    // The plan is arithmetic on the stated rate, and says so.
    expect(
      screen.getByText(/Uses the 10\.75% a year you recorded on 2026-10-01/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing is saved and no money moves by pressing this/),
    ).toBeInTheDocument();

    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "/api/earnings/vehicles/7/project")).toEqual({
        amount_minor: 100000,
        months: 12,
      }),
    );
  });

  it("refuses a rate with no date before asking the API at all", async () => {
    const fetchMock = stubFetch({ "/api/earnings/vehicles": [] });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));

    fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Ziidi" } });
    fireEvent.change(screen.getByLabelText(/Interest rate/i), {
      target: { value: "9" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Add Place/i }));

    expect(
      await screen.findByText(/Say when you checked that rate/),
    ).toBeInTheDocument();
    // A card the backend would reject is never even sent.
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/api/earnings/vehicles"),
      ),
    ).toBe(false);
  });

  it("gives a betting site a link and a record, but no rate and no promise", async () => {
    stubFetch({ "/api/earnings/vehicles": [aviator] });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));

    const item = (await screen.findByText("Aviator")).closest(".vehicle-item") as HTMLElement;
    expect(within(item).getByText(/a bet, not savings/)).toBeInTheDocument();
    // No plan to project and no button to press for one.
    expect(within(item).queryByRole("button", { name: "Save" })).toBeNull();
    expect(within(item).queryByText(/% a year/)).toBeNull();
    const link = within(item).getByRole("link", { name: /Open Aviator/i });
    expect(link).toHaveAttribute("href", "https://aviator.example/");
    // Out of the app's own window, so the shell can hand it to the browser.
    expect(link).toHaveAttribute("target", "_blank");

    // What it cost can still be written down, in the site's own words.
    fireEvent.click(within(item).getByRole("button", { name: /Records/i }));
    const panel = await screen.findByText(/What you staked and what was paid out/);
    expect(panel).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Staked" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Paid out to me" }),
    ).toBeInTheDocument();
  });

  it("records what really went in without touching a balance", async () => {
    const fetchMock = stubFetch({
      "/api/earnings/vehicles": [ziidi],
      "/api/earnings/vehicles/7/flows": [],
    });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Records/i }));

    await screen.findByText("Nothing recorded against Ziidi yet.");
    fireEvent.change(screen.getByLabelText(/Amount \(KES\)/i), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Add record/i }));

    await vi.waitFor(() =>
      expect(bodyOf(fetchMock, "/api/earnings/vehicles/7/flows")).toMatchObject({
        direction: "in",
        amount_minor: 50000,
      }),
    );
    // A note against a place, not a second copy of the same transfer.
    expect(
      screen.getByText(/No account balance moves here/),
    ).toBeInTheDocument();
  });

  it("says so when there is no rate to plan from", async () => {
    stubFetch({
      "/api/earnings/vehicles": [{ ...ziidi, rate_percent: null, rate_checked_on: null }],
    });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));

    expect(
      await screen.findByText(/no rate recorded yet - type the percentage/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    // The button is there, but pressing it sends nothing: no rate, no figure.
    expect(
      screen.getByText(/there is nothing to work from/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Show what it would give/i }),
    ).toBeDisabled();
  });

  it("shows the curated reading list under the places you can add", async () => {
    stubFetch({ "/api/earnings/vehicles": [] });
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: /Places to save/i }));

    // A directory of where to look - static reference beside your own cards.
    expect(
      await screen.findByRole("heading", { name: /Investment and betting websites/i }),
    ).toBeInTheDocument();
    // It keeps the app's own limit in view: not connected, not a recommendation.
    expect(screen.getByText(/not connected to any of these sites/i)).toBeInTheDocument();
  });
});

const ziidi: SavingsVehicle = {
  id: 7,
  name: "Ziidi",
  kind: "mpesa",
  url: "https://ziidi.example/",
  rate_percent: 10.75,
  rate_checked_on: "2026-10-01",
  units: null,
  value_minor: null,
  valued_on: null,
  notes: null,
  created_at: "2026-10-01T00:00:00Z",
  put_in_minor: 0,
  taken_out_minor: 0,
  net_in_minor: null,
  gain_minor: null,
};

const aviator: SavingsVehicle = {
  ...ziidi,
  id: 8,
  name: "Aviator",
  kind: "betting",
  url: "https://aviator.example/",
  rate_percent: null,
  rate_checked_on: null,
};

const projection: Projection = {
  amount_minor: 100000,
  months: 12,
  rate_percent: 10.75,
  rate_checked_on: "2026-10-01",
  interest_minor: 10750,
  total_minor: 110750,
  assumptions: [
    "Uses the 10.75% a year you recorded on 2026-10-01. LifeSmart is offline and did not verify it.",
  ],
};
