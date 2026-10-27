/** Goals page: list, create and fund goals. All figures come from the API -
 * nothing here simulates progress or invents savings. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type { Contribution, Goal, GoalPriority, GoalType } from "../types/api";

const GOAL_TYPES: { value: GoalType; label: string }[] = [
  { value: "money", label: "Money target" },
  { value: "quantity", label: "Quantity target" },
  { value: "obligation", label: "Obligation (fees, bills)" },
  { value: "custom", label: "Custom" },
];

const PRIORITIES: GoalPriority[] = ["low", "medium", "high", "critical"];

interface GoalValues {
  name: string;
  type: GoalType;
  target_amount: string;
  target_quantity: string;
  estimated_unit_cost: string;
  deadline: string;
  priority: GoalPriority;
  notes: string;
}

export function GoalsPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contribGoal, setContribGoal] = useState<number | null>(null);

  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => api<Goal[]>("/api/goals"),
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["goals"] });

  const goalForm = useForm<GoalValues>({
    defaultValues: { type: "money", priority: "medium" },
  });
  const goalType = goalForm.watch("type");

  const createGoal = useMutation({
    mutationFn: (v: GoalValues) => {
      const body: Record<string, unknown> = {
        name: v.name,
        type: v.type,
        priority: v.priority,
        deadline: v.deadline || null,
        notes: v.notes || null,
      };
      if (v.target_amount) {
        body.target_amount_minor = Math.round(Number(v.target_amount) * 100);
      }
      if (v.target_quantity) body.target_quantity = Number(v.target_quantity);
      if (v.estimated_unit_cost) {
        body.estimated_unit_cost_minor = Math.round(
          Number(v.estimated_unit_cost) * 100,
        );
      }
      return api<Goal>("/api/goals", { body });
    },
    onSuccess: () => {
      refresh();
      goalForm.reset();
      setShowForm(false);
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const contribForm = useForm<{ amount: string; note: string }>();
  const contribute = useMutation({
    mutationFn: (v: { amount: string; goalId: number }) => {
      const amount_minor = Math.round(Number(v.amount) * 100);
      if (!Number.isFinite(amount_minor) || amount_minor <= 0) {
        throw new Error("Enter a positive contribution amount");
      }
      return api<Contribution>(`/api/goals/${v.goalId}/contributions`, {
        body: { amount_minor },
      });
    },
    onSuccess: () => {
      refresh();
      setContribGoal(null);
      contribForm.reset();
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const pause = useMutation({
    mutationFn: (id: number) => api<Goal>(`/api/goals/${id}/pause`, { body: {} }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  const complete = useMutation({
    mutationFn: (id: number) => api<Goal>(`/api/goals/${id}/complete`, { body: {} }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Goals &amp; Priorities</h1>
        <button className="btn primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={16} aria-hidden /> New Goal
        </button>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}

      {showForm && (
        <form
          className="card auth-form"
          onSubmit={goalForm.handleSubmit((v) => createGoal.mutate(v))}
        >
          <h2>New goal</h2>
          <label>
            Name
            <input {...goalForm.register("name", { required: true })} />
          </label>
          <label>
            Type
            <select {...goalForm.register("type")}>
              {GOAL_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
          {goalType === "money" && (
            <label>
              Target amount (KES)
              <input
                type="number"
                min="0.01"
                step="0.01"
                {...goalForm.register("target_amount", {
                  required: goalType === "money",
                })}
              />
            </label>
          )}
          {goalType === "quantity" && (
            <>
              <label>
                Target quantity
                <input
                  type="number"
                  min="1"
                  {...goalForm.register("target_quantity", {
                    required: goalType === "quantity",
                  })}
                />
              </label>
              <label>
                Estimated unit cost (KES, optional)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  {...goalForm.register("estimated_unit_cost")}
                />
              </label>
            </>
          )}
          <div className="btn-row">
            <label>
              Deadline (optional)
              <input type="date" {...goalForm.register("deadline")} />
            </label>
            <label>
              Priority
              <select {...goalForm.register("priority")}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Notes
            <input {...goalForm.register("notes")} />
          </label>
          <button className="btn primary" type="submit" disabled={createGoal.isPending}>
            Save Goal
          </button>
        </form>
      )}

      {goals.isPending && <p className="muted">Loading…</p>}
      {goals.data?.length === 0 && !showForm && (
        <div className="card empty-state">
          <p>No goals yet. Set a money target, a quantity target or an
          obligation - required monthly saving is calculated from your deadline.</p>
        </div>
      )}

      {(goals.data ?? []).map((g) => (
        <div key={g.id} className="card goal-card">
          <div className="goal-header">
            <strong>{g.name}</strong>
            <span>
              <span className={`badge ${g.status}`}>{g.status}</span>{" "}
              <span className={`badge priority-${g.priority}`}>{g.priority}</span>
            </span>
          </div>

          {g.type === "money" && g.target_amount_minor !== null && (
            <>
              <div className="progress-track" role="progressbar"
                aria-valuenow={g.amount_saved_minor} aria-valuemin={0}
                aria-valuemax={g.target_amount_minor}>
                <div
                  className="progress-fill"
                  style={{
                    width: `${Math.min((g.amount_saved_minor / g.target_amount_minor) * 100, 100)}%`,
                  }}
                />
              </div>
              <p>
                {formatMinor(g.amount_saved_minor)} saved of{" "}
                {formatMinor(g.target_amount_minor)} ·{" "}
                {formatMinor(g.remaining_amount_minor)} still needed
              </p>
            </>
          )}
          {g.type === "quantity" && g.target_quantity !== null && (
            <p>
              {g.current_quantity ?? 0} of {g.target_quantity} acquired
              {g.estimated_remaining_cost_minor !== null &&
                ` · remaining cost ${formatMinor(g.estimated_remaining_cost_minor)} (estimate)`}
            </p>
          )}

          <p className="muted">
            {g.deadline
              ? g.deadline_state === "deadline_passed"
                ? `Deadline ${g.deadline} has passed - review and adjust the plan.`
                : g.required_monthly_saving_minor !== null
                  ? `${formatMinor(g.required_monthly_saving_minor)} per month needed by ${g.deadline} (rounded up)`
                  : `Deadline ${g.deadline}`
              : "No deadline set"}
          </p>

          {g.status === "active" && (
            <div className="btn-row">
              {contribGoal === g.id ? (
                <form
                  className="btn-row"
                  onSubmit={contribForm.handleSubmit((v) =>
                    contribute.mutate({ amount: v.amount, goalId: g.id }),
                  )}
                >
                  <label>
                    Contribution (KES)
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      autoFocus
                      {...contribForm.register("amount", { required: true })}
                    />
                  </label>
                  <button className="btn primary" type="submit"
                    disabled={contribute.isPending}>
                    Record
                  </button>
                  <button className="btn ghost" type="button"
                    onClick={() => setContribGoal(null)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <>
                  <button className="btn" onClick={() => setContribGoal(g.id)}>
                    Contribute
                  </button>
                  <button className="btn ghost small"
                    onClick={() => pause.mutate(g.id)}>
                    Pause
                  </button>
                  <button className="btn ghost small"
                    onClick={() => complete.mutate(g.id)}>
                    Mark complete
                  </button>
                </>
              )}
            </div>
          )}
          {g.status === "paused" && (
            <p className="muted">Paused - contributions are still accepted when resumed.</p>
          )}
          {g.status === "completed" && (
            <p className="muted">Completed {g.completed_at?.slice(0, 10) ?? ""}</p>
          )}
        </div>
      ))}
    </div>
  );
}
