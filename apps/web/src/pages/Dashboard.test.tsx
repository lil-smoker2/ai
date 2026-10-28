/** Home's share of the notifications feature.
 *
 * The rule the whole card exists to keep: a short list on Home must never read
 * as "everything is fine". The cases that matter are the ones where Home has
 * nothing to show - because the user's own switches hid it, because the server
 * answered with something that is not an alert list at all, or because the call
 * did not succeed. Each has to say so instead of offering an all-clear.
 *
 * Every figure here arrives as minor units, so a second set of assertions
 * watches that Home does not re-derive a sum the way the page finds convenient. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Dashboard } from "./Dashboard";
import { AuthProvider } from "../features/auth/AuthProvider";
import { setToken } from "../services/api";
import type { AlertKind, AlertsResponse, DashboardSummary, NotificationAlert, User } from "../types/api";

const user: User = {
  id: 1,
  email: "david@example.com",
  full_name: "David",
  currency: "KES",
  country: "KE",
  timezone: "Africa/Nairobi",
  is_student: true,
  onboarded: true,
  created_at: "2026-01-01T00:00:00Z",
};

const summary: DashboardSummary = {
  total_available_minor: 2125050,
  income_this_month_minor: 4000000,
  expenses_this_month_minor: 1250000,
  savings_this_month_minor: 300000,
  active_goals: 2,
  outstanding_goal_amount_minor: 600000,
  distinct_inventory_items: 14,
  items_below_target: 0,
  estimated_shortage_cost_minor: null,
  price_needed_items: 0,
  net_worth_minor: 8750000,
};

const feeAlert: NotificationAlert = {
  key: "fee:7",
  kind: "fee",
  severity: "due",
  title: "Semester tuition",
  detail: "due in 3 days · tuition",
  amount_minor: 60000,
  period_amount_minor: null,
  period_label: null,
  due_on: "2026-11-02",
  days_out: 3,
  link: "/app/student",
};

const paceAlert: NotificationAlert = {
  key: "goal:3",
  kind: "savings",
  severity: "soon",
  title: "Laptop fund",
  detail: "nothing has gone into it in the last 30 days · deadline 20 Dec",
  amount_minor: 600000,
  period_amount_minor: 300000,
  period_label: "30-day",
  due_on: "2026-12-20",
  days_out: 60,
  link: "/app/goals",
};

function taskAlert(i: number): NotificationAlert {
  return {
    key: `task:${i}`,
    kind: "task",
    severity: "overdue",
    title: `Task ${i}`,
    detail: "1 day past due",
    amount_minor: null,
    period_amount_minor: null,
    period_label: null,
    due_on: "2026-10-27",
    days_out: -1,
    link: "/app/tasks",
  };
}

function alertsBody(
  alerts: NotificationAlert[] = [],
  hidden: AlertKind[] = [],
  quiet = false,
): AlertsResponse {
  return {
    generated_on: "2026-10-28",
    generated_at: "10:15:00",
    currency: "KES",
    alerts,
    count: alerts.length,
    hidden_by_preferences: hidden,
    in_quiet_hours: quiet,
    quiet_ends_at: quiet ? "06:00:00" : null,
    quiet_start: quiet ? "22:00:00" : null,
    quiet_end: quiet ? "06:00:00" : null,
  };
}

/** Which record the card answers from. `_init` is part of fetch's signature;
 * these assertions only ever look at the URL. Routes answering 500 are named
 * rather than blanket-failed, because the point of those cases is that one half
 * of Home is unknown while the other half is perfectly readable. */
function stubRoutes(
  reply: (url: string) => unknown,
  failing: string[] = [],
) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      urls.push(url);
      const failed = failing.some((frag) => url.includes(frag));
      return new Response(JSON.stringify(reply(url)), {
        status: failed ? 500 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return urls;
}

/** The account is seeded rather than fetched: which name the greeting uses is
 * not what these cases are about, and the fetch stub routes by URL. */
function renderDashboard(client = new QueryClient()) {
  client.setQueryData(["me"], user);
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/app"]}>
          <Dashboard />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("Dashboard attention card", () => {
  beforeEach(() => {
    setToken("test-token");
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("lists what needs attention in the same words the Notifications page uses", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts") ? alertsBody([feeAlert, paceAlert]) : summary,
    );
    renderDashboard();

    expect(await screen.findByText("Semester tuition")).toBeInTheDocument();
    // The greeting waits for the account rather than printing a name it made up.
    expect(await screen.findByText(/Karibu, David/)).toBeInTheDocument();
    expect(screen.getByText("due in 3 days · tuition")).toBeInTheDocument();
    // Minor units formatted once, by the shared row: 60000 is KES 600.00.
    expect(screen.getByText("KES 600.00 still to cover")).toBeInTheDocument();
    expect(
      screen.getByText("about KES 3,000.00 per 30-day closes the gap"),
    ).toBeInTheDocument();
    expect(screen.getByText("Behind pace")).toBeInTheDocument();
  });

  it("shows the top three and hands the rest to Notifications", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts")
        ? alertsBody([taskAlert(1), taskAlert(2), taskAlert(3), taskAlert(4), taskAlert(5)])
        : summary,
    );
    renderDashboard();

    await screen.findByText("Task 1");
    expect(screen.getByText("Task 3")).toBeInTheDocument();
    expect(screen.queryByText("Task 4")).toBeNull();
    expect(screen.getByText("2 more in Notifications, which has them all.")).toBeInTheDocument();

    const seeAll = screen.getByRole("link", { name: "See all 5" });
    expect(seeAll).toHaveAttribute("href", "/app/notifications");
  });

  it("says the switches hid things rather than claiming all is quiet", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts") ? alertsBody([], ["task", "savings"]) : summary,
    );
    renderDashboard();

    const note = await screen.findByText(/Nothing is showing, because/);
    expect(note).toHaveTextContent("task reminders");
    expect(note).toHaveTextContent("savings pace nudges");
    expect(screen.queryByText(/Nothing in your records needs attention/)).toBeNull();
  });

  it("only offers the honest empty answer when nothing is switched off", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts") ? alertsBody([]) : summary,
    );
    renderDashboard();

    expect(
      await screen.findByText(/something you never recorded cannot appear here/),
    ).toBeInTheDocument();
  });

  it("names what the switches hid even when other alerts are showing", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts") ? alertsBody([feeAlert], ["task"]) : summary,
    );
    renderDashboard();

    await screen.findByText("Semester tuition");
    const note = screen.getByText(/^Not included:/);
    expect(note).toHaveTextContent("task reminders");
    expect(note).toHaveTextContent("switched off in Notifications");
  });

  it("treats a response that is not the alert shape as unknown, not clear", async () => {
    // An older server answering the alerts URL with the summary is exactly what
    // a careless stub produces. The summary has no `alerts` array, so the card
    // has no basis for any claim about what needs attention.
    stubRoutes(() => summary);
    renderDashboard();

    expect(
      await screen.findByText("The app could not read what needs attention."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Nothing in your records needs attention/)).toBeNull();
    expect(screen.queryByText(/Nothing is showing, because/)).toBeNull();
  });

  it("reports a failed alerts call without taking the dashboard down", async () => {
    // Only the alerts route fails, so the summary still arrives: the point is
    // that one half of Home is unknown while the other half stays readable.
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts")
        ? { detail: "alert computation failed" }
        : summary,
      ["/api/notifications/alerts"],
    );
    renderDashboard(new QueryClient({ defaultOptions: { queries: { retry: false } } }));

    expect(await screen.findByText(/Could not read what needs attention/)).toBeInTheDocument();
    // The figures that did arrive stay on screen, and no all-clear is offered
    // for the half that never answered.
    expect(screen.getByText("Net worth")).toBeInTheDocument();
    expect(screen.getByText("87,500.00")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing in your records needs attention/)).toBeNull();
  });

  it("keeps the list while quiet hours take the number off the sidebar", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts") ? alertsBody([feeAlert], [], true) : summary,
    );
    renderDashboard();

    expect(await screen.findByText("Semester tuition")).toBeInTheDocument();
    expect(screen.getByText(/hide the sidebar count/)).toHaveTextContent("until 06:00:00");
  });

  it("reads from the sidebar's fetch rather than making its own", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { staleTime: 60_000, retry: false } },
    });
    // The shell has already answered this query on the way in.
    client.setQueryData(["notification-alerts"], alertsBody([feeAlert]));
    const urls = stubRoutes(() => summary);

    renderDashboard(client);
    expect(await screen.findByText("Semester tuition")).toBeInTheDocument();

    expect(urls.some((u) => u.includes("/api/notifications/alerts"))).toBe(false);
  });

  it("states the figures it was given, in the currency it was told", async () => {
    stubRoutes((url) =>
      url.includes("/api/notifications/alerts")
        ? { ...alertsBody([feeAlert]), currency: "UGX" }
        : summary,
    );
    renderDashboard();

    // Home must not quietly re-format the alert's amount in the profile's
    // currency: the response names the one the minor units were written in.
    expect(await screen.findByText("UGX 600.00 still to cover")).toBeInTheDocument();
  });
});
