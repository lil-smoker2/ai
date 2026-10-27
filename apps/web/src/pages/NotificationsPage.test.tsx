/** Wiring smoke test: NotificationsPage reflects the saved preferences from
 * the API (toggles checked according to the stored booleans). */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NotificationsPage } from "./NotificationsPage";
import { setToken } from "../services/api";
import type { NotificationPreference } from "../types/api";

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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("NotificationsPage", () => {
  beforeEach(() => {
    setToken("test-token");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(pref)));
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders toggles matching the stored boolean values", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <NotificationsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Task reminders")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal & task deadline alerts")).toBeChecked();
    // task_reminders is false in the stored record.
    expect(screen.getByLabelText("Task reminders")).not.toBeChecked();
  });
});
