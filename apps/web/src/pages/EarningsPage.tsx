/** Savings & Earnings page: income sources, business records, savings
 * contributions and a forecast. Expected income is clearly a planning figure,
 * never counted as received; the forecast states its assumptions. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type {
  BusinessProfit,
  BusinessRecord,
  BusinessRecordType,
  Contribution,
  EarningsSummary,
  Goal,
  IncomeFrequency,
  IncomeReliability,
  IncomeSource,
} from "../types/api";

const FREQUENCIES: IncomeFrequency[] = ["daily", "weekly", "monthly", "yearly", "once"];
const RELIABILITY: IncomeReliability[] = ["uncertain", "likely", "confirmed"];

const toMinor = (v: string) =>
  v.trim() === "" ? null : Math.round(Number(v) * 100);

interface IncomeValues {
  name: string;
  expected_amount: string;
  frequency: IncomeFrequency;
  next_expected_date: string;
  reliability: IncomeReliability;
}

interface BusinessValues {
  business_name: string;
  type: BusinessRecordType;
  amount: string;
  category: string;
  occurred_on: string;
}

export function EarningsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"overview" | "income" | "business">("overview");
  const [error, setError] = useState<string | null>(null);
  const [contribGoal, setContribGoal] = useState<number | null>(null);

  const summary = useQuery({
    queryKey: ["earnings-summary"],
    queryFn: () => api<EarningsSummary>("/api/earnings/summary"),
  });
  const income = useQuery({
    queryKey: ["income-sources"],
    queryFn: () => api<IncomeSource[]>("/api/earnings/income-sources"),
  });
  const business = useQuery({
    queryKey: ["business-records"],
    queryFn: () => api<BusinessRecord[]>("/api/earnings/business"),
  });
  const profit = useQuery({
    queryKey: ["business-profit"],
    queryFn: () => api<BusinessProfit[]>("/api/earnings/business/profit"),
  });
  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => api<Goal[]>("/api/goals"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["earnings-summary"] });
    queryClient.invalidateQueries({ queryKey: ["income-sources"] });
    queryClient.invalidateQueries({ queryKey: ["business-records"] });
    queryClient.invalidateQueries({ queryKey: ["business-profit"] });
    queryClient.invalidateQueries({ queryKey: ["goals"] });
  };

  const incomeForm = useForm<IncomeValues>({
    defaultValues: { frequency: "monthly", reliability: "likely" },
  });
  const addIncome = useMutation({
    mutationFn: (v: IncomeValues) => {
      const amount = toMinor(v.expected_amount);
      if (amount === null || amount <= 0) throw new Error("Enter an expected amount");
      return api<IncomeSource>("/api/earnings/income-sources", {
        body: {
          name: v.name,
          expected_amount_minor: amount,
          frequency: v.frequency,
          reliability: v.reliability,
          next_expected_date: v.next_expected_date || null,
        },
      });
    },
    onSuccess: () => {
      refresh();
      incomeForm.reset();
      setTab("overview");
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const toggleIncome = useMutation({
    mutationFn: (v: { id: number; active: boolean }) =>
      api<IncomeSource>(`/api/earnings/income-sources/${v.id}`, {
        method: "PUT",
        body: { active: v.active },
      }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  const businessForm = useForm<BusinessValues>({
    defaultValues: { type: "revenue" },
  });
  const addBusiness = useMutation({
    mutationFn: (v: BusinessValues) => {
      const amount = toMinor(v.amount);
      if (amount === null || amount <= 0) throw new Error("Enter an amount");
      return api<BusinessRecord>("/api/earnings/business", {
        body: {
          business_name: v.business_name,
          type: v.type,
          amount_minor: amount,
          category: v.category || null,
          occurred_on: v.occurred_on || null,
        },
      });
    },
    onSuccess: () => {
      refresh();
      businessForm.reset();
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const contribForm = useForm<{ amount: string }>();
  const contribute = useMutation({
    mutationFn: (v: { amount: string; goalId: number }) => {
      const amount = toMinor(v.amount);
      if (amount === null || amount <= 0) throw new Error("Enter a contribution amount");
      return api<Contribution>(`/api/goals/${v.goalId}/contributions`, {
        body: { amount_minor: amount },
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

  const s = summary.data;

  return (
    <div>
      <div className="page-header">
        <h1>Savings &amp; Earnings</h1>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}

      <div className="tabs" role="tablist">
        {(["overview", "income", "business"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "tab-btn active" : "tab-btn"}
            onClick={() => setTab(t)}
          >
            {t === "income" ? "Income sources" : t === "business" ? "Business" : "Overview"}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="stat-grid">
            <div className="card stat-card">
              <span className="stat-label">Recorded balance</span>
              <strong>{s ? formatMinor(s.recorded_available_balance_minor) : "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Expected income / month</span>
              <strong>{formatMinor(s?.monthly_expected_income_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Business net (this month)</span>
              <strong>{formatMinor(s?.business_net_profit_this_month_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Saved toward goals</span>
              <strong>{formatMinor(s?.total_saved_in_goals_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Outstanding obligations</span>
              <strong>{formatMinor(s?.outstanding_obligations_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Available for planning</span>
              <strong>
                {s?.available_for_planning_minor === null ||
                s?.available_for_planning_minor === undefined
                  ? "Not enough data"
                  : formatMinor(s.available_for_planning_minor)}
              </strong>
            </div>
          </div>
          <p className="muted">
            “Available for planning” is an estimate — recorded balance plus
            expected recurring income minus outstanding goal obligations. It is
            not a bank balance, and expected income is never counted as received.
          </p>
          {s && s.assumptions.length > 0 && (
            <div className="card">
              <h2>Forecast assumptions</h2>
              <ul className="muted">
                {s.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="card">
            <h2>Fund a savings goal</h2>
            {(goals.data ?? [])
              .filter((g) => g.status === "active" && g.type === "money")
              .map((g) => (
                <div key={g.id} className="list-row">
                  <span>
                    <strong>{g.name}</strong>{" "}
                    <span className="muted">
                      {formatMinor(g.amount_saved_minor)} of{" "}
                      {formatMinor(g.target_amount_minor)}
                    </span>
                  </span>
                  {contribGoal === g.id ? (
                    <form
                      className="btn-row"
                      onSubmit={contribForm.handleSubmit((v) =>
                        contribute.mutate({ amount: v.amount, goalId: g.id }),
                      )}
                    >
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        placeholder="KES"
                        autoFocus
                        {...contribForm.register("amount", { required: true })}
                      />
                      <button className="btn primary" type="submit" disabled={contribute.isPending}>
                        Record
                      </button>
                      <button className="btn ghost" type="button" onClick={() => setContribGoal(null)}>
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <button className="btn small" onClick={() => setContribGoal(g.id)}>
                      Add contribution
                    </button>
                  )}
                </div>
              ))}
            {(goals.data ?? []).filter((g) => g.status === "active" && g.type === "money")
              .length === 0 && (
              <p className="muted">No active money goals. Create one under Goals.</p>
            )}
          </div>
        </>
      )}

      {tab === "income" && (
        <>
          <form
            className="card auth-form"
            onSubmit={incomeForm.handleSubmit((v) => addIncome.mutate(v))}
          >
            <h2>Add income source</h2>
            <p className="muted">
              Expected amounts are used only for planning - they are never
              recorded as money you already have.
            </p>
            <label>
              Name
              <input {...incomeForm.register("name", { required: true })} />
            </label>
            <div className="btn-row">
              <label>
                Expected amount (KES)
                <input type="number" min="0.01" step="0.01" {...incomeForm.register("expected_amount", { required: true })} />
              </label>
              <label>
                Frequency
                <select {...incomeForm.register("frequency")}>
                  {FREQUENCIES.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label>
                Reliability
                <select {...incomeForm.register("reliability")}>
                  {RELIABILITY.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label>
                Next expected (optional)
                <input type="date" {...incomeForm.register("next_expected_date")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addIncome.isPending}>
              <Plus size={16} aria-hidden /> Add Source
            </button>
          </form>

          <div className="card">
            <h2>Income sources</h2>
            {(income.data ?? []).map((src) => (
              <div key={src.id} className="list-row">
                <span>
                  <strong>{src.name}</strong>{" "}
                  <span className="badge">{src.frequency}</span>{" "}
                  <span className="badge">{src.reliability}</span>{" "}
                  {!src.active && <span className="badge warn">inactive</span>}
                  <span className="muted"> · {formatMinor(src.monthly_expected_minor)}/mo expected</span>
                </span>
                <button
                  className="btn ghost small"
                  onClick={() => toggleIncome.mutate({ id: src.id, active: !src.active })}
                >
                  {src.active ? "Deactivate" : "Activate"}
                </button>
              </div>
            ))}
            {income.data?.length === 0 && <p className="muted">No income sources yet.</p>}
          </div>
        </>
      )}

      {tab === "business" && (
        <>
          <form
            className="card auth-form"
            onSubmit={businessForm.handleSubmit((v) => addBusiness.mutate(v))}
          >
            <h2>Record business entry</h2>
            <div className="btn-row">
              <label>
                Business
                <input {...businessForm.register("business_name", { required: true })} />
              </label>
              <label>
                Type
                <select {...businessForm.register("type")}>
                  <option value="revenue">Revenue</option>
                  <option value="expense">Expense</option>
                </select>
              </label>
              <label>
                Amount (KES)
                <input type="number" min="0.01" step="0.01" {...businessForm.register("amount", { required: true })} />
              </label>
              <label>
                Category (optional)
                <input placeholder="e.g. direct cost, stock" {...businessForm.register("category")} />
              </label>
              <label>
                Date
                <input type="date" {...businessForm.register("occurred_on")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addBusiness.isPending}>
              <Plus size={16} aria-hidden /> Record Entry
            </button>
          </form>

          <div className="card">
            <h2>Net profit by business</h2>
            {(profit.data ?? []).map((p) => (
              <div key={p.business_name} className="list-row">
                <span><strong>{p.business_name}</strong></span>
                <span>
                  {formatMinor(p.revenue_minor)} revenue − {formatMinor(p.expenses_minor)} costs ={" "}
                  <strong>{formatMinor(p.net_profit_minor)}</strong>
                </span>
              </div>
            ))}
            {profit.data?.length === 0 && <p className="muted">No business records yet.</p>}
          </div>

          <div className="card">
            <h2>Recent entries</h2>
            {(business.data ?? []).map((r) => (
              <div key={r.id} className="list-row">
                <span>
                  <span className={`badge ${r.type === "revenue" ? "income" : "expense"}`}>{r.type}</span>{" "}
                  <strong>{r.business_name}</strong>
                  {r.category ? ` · ${r.category}` : ""}
                  <span className="muted"> · {r.occurred_on}</span>
                </span>
                <span>{formatMinor(r.amount_minor)}</span>
              </div>
            ))}
            {business.data?.length === 0 && <p className="muted">Nothing recorded yet.</p>}
          </div>
        </>
      )}
    </div>
  );
}
