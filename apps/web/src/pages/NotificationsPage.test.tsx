/** The notifications page: the derived list, and the switches that decide what
 * may appear in it. The important cases are the ones where the app has nothing
 * to say - an empty list must never read as "all clear" when it actually means
 * "your switches are hiding things" or "this did not come back properly". */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NotificationsPage } from "./NotificationsPage";
import { setToken } from "../services/api";
import type {
  AlertKind,
  AlertsResponse,
  NotificationAlert,
  NotificationPreference,
} from "../types/api";

const pref: NotificationPreference = {
  id: 1,
  deadline_alerts: true,
  task_reminders: false,
  low_stock_warnings: true,
  savings_nudges: true,
  fee_due_alerts: true,
  quiet_start: null,
  quiet_end: null,
  updated_at: "2026-10-01T00:00:00Z",
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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Routes each call by URL, recording the order, because this page now makes
 * two queries and saving the switches must re-run the alert one. `_init` is
 * part of fetch's signature; the page's assertions never need the request body. */
function stubRoutes(reply: (url: string) => unknown) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      urls.push(url);
      return jsonResponse(reply(url));
    }),
  );
  return urls;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationsPage", () => {
  beforeEach(() => {
    setToken("test-token");
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders toggles matching the stored boolean values", async () => {
    stubRoutes((url) =>
      url.includes("/alerts") ? alertsBody([]) : pref,
    );
    renderPage();

    expect(await screen.findByText("Task reminders")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal deadline alerts")).toBeChecked();
    // task_reminders is false in the stored record.
    expect(screen.getByLabelText("Task reminders")).not.toBeChecked();
  });

  it("lists what needs attention, with its own money figures", async () => {
    stubRoutes((url) =>
      url.includes("/alerts") ? alertsBody([feeAlert, paceAlert]) : pref,
    );
    renderPage();

    expect(await screen.findByText("Semester tuition")).toBeInTheDocument();
    expect(screen.getByText("due in 3 days · tuition")).toBeInTheDocument();
    // Minor units formatted here, once: 60000 is KES 600.00, not "60000".
    expect(screen.getByText("KES 600.00 still to cover")).toBeInTheDocument();

    expect(screen.getByText("Laptop fund")).toBeInTheDocument();
    expect(
      screen.getByText("about KES 3,000.00 per 30-day closes the gap"),
    ).toBeInTheDocument();
    expect(screen.getByText("Behind pace")).toBeInTheDocument();
  });

  it("formats figures in the currency the profile uses", async () => {
    stubRoutes((url) =>
      url.includes("/alerts")
        ? { ...alertsBody([feeAlert]), currency: "UGX" }
        : pref,
    );
    renderPage();

    // The amount arrives as minor units; the currency name comes from the
    // response rather than a hard-coded default.
    expect(await screen.findByText("UGX 600.00 still to cover")).toBeInTheDocument();
  });

  it("links an alert to the page that can settle it", async () => {
    stubRoutes((url) => (url.includes("/alerts") ? alertsBody([feeAlert]) : pref));
    renderPage();

    await screen.findByText("Semester tuition");
    const link = screen.getByRole("link", { name: "Open" });
    expect(link).toHaveAttribute("href", "/app/student");
  });

  it("says the switches hid things rather than claiming all is quiet", async () => {
    stubRoutes((url) =>
      url.includes("/alerts") ? alertsBody([], ["task", "savings"]) : pref,
    );
    renderPage();

    const note = await screen.findByText(/switched off below/);
    expect(note).toHaveTextContent("task reminders");
    expect(note).toHaveTextContent("savings pace nudges");
    expect(screen.queryByText(/Nothing in your records needs attention/)).toBeNull();
  });

  it("only offers the honest empty answer when nothing is switched off", async () => {
    stubRoutes((url) => (url.includes("/alerts") ? alertsBody([]) : pref));
    renderPage();

    expect(
      await screen.findByText(/a deadline you never recorded cannot appear in it/),
    ).toBeInTheDocument();
  });

  it("treats a response that is not the alert shape as unknown, not clear", async () => {
    // The preferences object arriving on the alerts URL is exactly what a
    // single-stub fetch would produce; the page must not read that as "all
    // clear".
    stubRoutes(() => pref);
    renderPage();

    expect(await screen.findByText(/could not read what needs attention/)).toBeInTheDocument();
    expect(screen.queryByText(/Nothing in your records needs attention/)).toBeNull();
  });

  it("notes quiet hours without hiding the list", async () => {
    stubRoutes((url) =>
      url.includes("/alerts") ? alertsBody([feeAlert], [], true) : pref,
    );
    renderPage();

    expect(await screen.findByText("Semester tuition")).toBeInTheDocument();
    expect(
      screen.getByText(/quiet hours until 06:00:00, so the sidebar shows no count/),
    ).toBeInTheDocument();
  });

  it("re-reads the alerts after the switches are saved", async () => {
    const urls = stubRoutes((url) => (url.includes("/alerts") ? alertsBody([feeAlert]) : pref));
    renderPage();

    await screen.findByText("Semester tuition");
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    await vi.waitFor(() => {
      expect(urls.filter((u) => u.includes("/alerts")).length).toBeGreaterThan(1);
    });
  });
});
