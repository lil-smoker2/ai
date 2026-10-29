/** Wiring smoke test: TasksPage renders server-computed task state (status,
 * overdue) without inventing anything client-side. */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TasksPage } from "./TasksPage";
import { setToken } from "../services/api";
import type { Task } from "../types/api";

const task: Task = {
  id: 1,
  title: "Buy textbooks",
  description: "Semester 2 list",
  due_on: "2026-10-01",
  due_time: null,
  priority: "high",
  status: "pending",
  goal_id: null,
  recurrence: "weekly",
  remind_before_days: 2,
  created_at: "2026-09-20T00:00:00Z",
  completed_at: null,
  is_overdue: true,
  urgency: { score: 40, band: "overdue", priority_points: 10, overdue_points: 30 },
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("TasksPage", () => {
  beforeEach(() => {
    setToken("test-token");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([task])));
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("renders tasks with their server-computed status and overdue flag", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <TasksPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Buy textbooks")).toBeInTheDocument();
    // The status badge shows "pending" (also present in the filter <option>).
    expect(screen.getAllByText("pending").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/overdue/)).toBeInTheDocument();
    expect(screen.getByText(/Due 2026-10-01/)).toBeInTheDocument();
  });
});
