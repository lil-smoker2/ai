/** Tasks & Reminders page: turn plans into actions. Completing a task only
 * records the action - it never marks fees or goals as done. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { ListChecks, Plus } from "lucide-react";
import { api } from "../services/api";
import { UrgencyTag } from "../features/tasks/UrgencyTag";
import type { Task, TaskPriority, TaskRecurrence, TaskStatus } from "../types/api";

const STATUSES: TaskStatus[] = [
  "proposed",
  "pending",
  "in_progress",
  "completed",
  "cancelled",
];
const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "critical"];
const RECURRENCE: TaskRecurrence[] = ["none", "daily", "weekly", "monthly", "yearly"];

const OPEN = new Set<TaskStatus>(["proposed", "pending", "in_progress"]);

interface NewTaskForm {
  title: string;
  description: string;
  due_on: string;
  priority: TaskPriority;
  recurrence: TaskRecurrence;
  remind_before_days: string;
}

export function TasksPage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<TaskStatus | "all">("all");
  const [sortBy, setSortBy] = useState<"due" | "urgency">("due");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tasks = useQuery({
    queryKey: ["tasks", filter, sortBy],
    queryFn: () =>
      api<Task[]>("/api/tasks", {
        params: {
          ...(filter === "all" ? {} : { status: filter }),
          ...(sortBy === "urgency" ? { sort: "urgency" } : {}),
        },
      }),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["tasks"] });

  const form = useForm<NewTaskForm>({
    defaultValues: { priority: "medium", recurrence: "none" },
  });
  const create = useMutation({
    mutationFn: (v: NewTaskForm) =>
      api<Task>("/api/tasks", {
        body: {
          title: v.title,
          description: v.description || null,
          due_on: v.due_on || null,
          priority: v.priority,
          recurrence: v.recurrence,
          remind_before_days:
            v.remind_before_days.trim() === "" ? null : Number(v.remind_before_days),
        },
      }),
    onSuccess: () => {
      setShowForm(false);
      form.reset();
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  const complete = useMutation({
    mutationFn: (id: number) =>
      api<Task>(`/api/tasks/${id}/complete`, { method: "POST", body: {} }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });
  const reopen = useMutation({
    mutationFn: (id: number) =>
      api<Task>(`/api/tasks/${id}/reopen`, { method: "POST", body: {} }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });
  const snooze = useMutation({
    mutationFn: (id: number) =>
      api<Task>(`/api/tasks/${id}/snooze`, { method: "POST", body: { days: 3 } }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });
  const setPriority = useMutation({
    mutationFn: (v: { id: number; priority: TaskPriority }) =>
      api<Task>(`/api/tasks/${v.id}`, { method: "PUT", body: { priority: v.priority } }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) =>
      api<void>(`/api/tasks/${id}`, { method: "DELETE", params: { confirm: true } }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Tasks &amp; Reminders</h1>
        <button className="btn primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={16} aria-hidden /> Add Task
        </button>
      </div>

      {error && <p className="error-banner" role="alert">{error}</p>}

      {showForm && (
        <form className="card auth-form" onSubmit={form.handleSubmit((v) => create.mutate(v))}>
          <h2>New task</h2>
          <label>
            Title
            <input {...form.register("title", { required: true })} />
          </label>
          <label>
            Description (optional)
            <input {...form.register("description")} />
          </label>
          <div className="btn-row">
            <label>
              Due date
              <input type="date" {...form.register("due_on")} />
            </label>
            <label>
              Priority
              <select {...form.register("priority")}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label>
              Recurrence
              <select {...form.register("recurrence")}>
                {RECURRENCE.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label>
              Remind (days before)
              <input type="number" min={0} max={90} {...form.register("remind_before_days")} />
            </label>
          </div>
          <button className="btn primary" type="submit" disabled={create.isPending}>
            Save Task
          </button>
        </form>
      )}

      <label className="field-inline">
        Show
        <select value={filter} onChange={(e) => setFilter(e.target.value as TaskStatus | "all")}>
          <option value="all">All</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>

      <label className="field-inline">
        Order
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "due" | "urgency")}
        >
          <option value="due">By due date</option>
          <option value="urgency">Most urgent first</option>
        </select>
      </label>

      {tasks.isPending && <p className="muted">Loading…</p>}
      {tasks.data?.length === 0 && (
        <div className="card empty-state">
          <p>No tasks here yet. Add one, or create a task from a goal.</p>
        </div>
      )}

      <div className="item-grid">
        {(tasks.data ?? []).map((t) => (
          <div key={t.id} className="card item-card">
            <div className="item-info">
              <strong>{t.title}</strong>
              {t.description && <span className="muted">{t.description}</span>}
              <span className="muted">
                {t.due_on ? `Due ${t.due_on}` : "No due date"}
                {t.recurrence !== "none" ? ` · ${t.recurrence}` : ""}
              </span>
              <span>
                <span className={`badge ${OPEN.has(t.status) ? "" : "income"}`}>{t.status}</span>{" "}
                {t.is_overdue && <span className="badge warn">overdue</span>}{" "}
                <UrgencyTag urgency={t.urgency} />
              </span>
              <select
                className="btn small"
                value={t.priority}
                onChange={(e) =>
                  setPriority.mutate({ id: t.id, priority: e.target.value as TaskPriority })
                }
              >
                {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <div className="btn-row">
                {OPEN.has(t.status) ? (
                  <>
                    <button className="btn primary" onClick={() => complete.mutate(t.id)}
                      disabled={complete.isPending}>
                      <ListChecks size={16} aria-hidden /> Complete
                    </button>
                    <button className="btn small" onClick={() => snooze.mutate(t.id)}>
                      Snooze 3d
                    </button>
                  </>
                ) : (
                  <button className="btn small" onClick={() => reopen.mutate(t.id)}>
                    Reopen
                  </button>
                )}
                <button className="btn ghost small" onClick={() => remove.mutate(t.id)}>
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
