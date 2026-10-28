/** The shell now fetches, which it never used to.
 *
 * That is worth its own test: the alert count sits in the component that draws
 * every page's navigation, so a slow, empty or failed alerts call must not be
 * able to take the sidebar down with it. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";
import { AuthProvider } from "../features/auth/AuthProvider";
import { setToken } from "../services/api";
import type { AlertsResponse, User } from "../types/api";

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

function alerts(count: number, quiet = false): AlertsResponse {
  return {
    generated_on: "2026-10-28",
    generated_at: "10:15:00",
    currency: "KES",
    alerts: Array.from({ length: count }, (_unused, i) => ({
      key: `task:${i + 1}`,
      kind: "task" as const,
      severity: "overdue" as const,
      title: `Task ${i + 1}`,
      detail: "1 day past due",
      amount_minor: null,
      period_amount_minor: null,
      period_label: null,
      due_on: "2026-10-27",
      days_out: -1,
      link: "/app/tasks",
    })),
    count,
    hidden_by_preferences: [],
    in_quiet_hours: quiet,
    quiet_ends_at: quiet ? "06:00:00" : null,
    quiet_start: quiet ? "22:00:00" : null,
    quiet_end: quiet ? "06:00:00" : null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderShell(alertsResponse: () => Response) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/notifications/alerts")) return alertsResponse();
    if (url.includes("/api/auth/me")) return jsonResponse(user);
    return jsonResponse({});
  }));

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/app/money"]}>
          <AppShell />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("AppShell alert badge", () => {
  beforeEach(() => {
    setToken("test-token");
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("counts what needs attention beside the Notifications link", async () => {
    renderShell(() => jsonResponse(alerts(3)));
    const badge = await screen.findByText("3");
    expect(badge).toHaveClass("nav-badge");
    expect(badge.closest("a")).toHaveTextContent("Notifications");
  });

  it("shows no number when there is nothing to report", async () => {
    renderShell(() => jsonResponse(alerts(0)));
    // The nav has arrived, and the badge has not.
    expect(await screen.findByText("Savings & Earnings")).toBeInTheDocument();
    expect(document.querySelector(".nav-badge")).toBeNull();
  });

  it("quiet hours take the number off the sidebar without taking the nav", async () => {
    renderShell(() => jsonResponse(alerts(4, true)));
    expect(await screen.findByText("Savings & Earnings")).toBeInTheDocument();
    expect(document.querySelector(".nav-badge")).toBeNull();
  });

  it("a failed alerts call cannot break the navigation", async () => {
    renderShell(() => jsonResponse({ detail: "alert computation failed" }, 500));

    // Every item is still there: the badge is decoration, not a dependency.
    expect(await screen.findByText("Savings & Earnings")).toBeInTheDocument();
    expect(screen.getByText("Student Life")).toBeInTheDocument();
    expect(screen.getByLabelText("Main navigation")).toBeInTheDocument();
    expect(document.querySelector(".nav-badge")).toBeNull();
  });
});
