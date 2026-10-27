/** Student Life: school fee obligations, accommodation options and a food
 * budget. Fees only count as paid through recorded payments; hostels only
 * change availability when the user reports it - the app never claims either. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type {
  Account,
  FeeCategory,
  FeeObligation,
  FeePayment,
  FoodBudget,
  HostelOption,
  HostelStatus,
  StudentSummary,
} from "../types/api";

const FEE_CATEGORIES: FeeCategory[] = ["tuition", "registration", "other"];
const HOSTEL_STATUSES: HostelStatus[] = ["unchecked", "available", "taken", "booked"];

const toMinor = (v: string) => (v.trim() === "" ? null : Math.round(Number(v) * 100));

type Tab = "overview" | "fees" | "accommodation" | "food";

interface FeeForm {
  name: string;
  category: FeeCategory;
  amount_due: string;
  due_on: string;
  reference: string;
}
interface PaymentForm {
  amount: string;
  occurred_on: string;
  account_id: string;
  reference: string;
}
interface HostelForm {
  name: string;
  location: string;
  monthly_rent: string;
  deposit: string;
  facilities: string;
  booking_source: string;
}

export function StudentPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [payingFee, setPayingFee] = useState<FeeObligation | null>(null);

  const summary = useQuery({
    queryKey: ["student-summary"],
    queryFn: () => api<StudentSummary>("/api/student/summary"),
  });
  const fees = useQuery({
    queryKey: ["student-fees"],
    queryFn: () => api<FeeObligation[]>("/api/student/fees"),
  });
  const hostels = useQuery({
    queryKey: ["student-hostels"],
    queryFn: () => api<HostelOption[]>("/api/student/hostels"),
  });
  const food = useQuery({
    queryKey: ["student-food-budget"],
    queryFn: () => api<FoodBudget>("/api/student/food-budget"),
  });
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["student-summary"] });
    queryClient.invalidateQueries({ queryKey: ["student-fees"] });
    queryClient.invalidateQueries({ queryKey: ["student-hostels"] });
    queryClient.invalidateQueries({ queryKey: ["student-food-budget"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
  };

  // --- Fees ---
  const feeForm = useForm<FeeForm>({ defaultValues: { category: "tuition" } });
  const addFee = useMutation({
    mutationFn: (v: FeeForm) => {
      const amount = toMinor(v.amount_due);
      if (amount === null || amount <= 0) throw new Error("Enter an amount due");
      return api<FeeObligation>("/api/student/fees", {
        body: {
          name: v.name,
          category: v.category,
          amount_due_minor: amount,
          due_on: v.due_on || null,
          reference: v.reference || null,
        },
      });
    },
    onSuccess: () => {
      feeForm.reset();
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  const payForm = useForm<PaymentForm>();
  const recordPayment = useMutation({
    mutationFn: (v: PaymentForm) => {
      const amount = toMinor(v.amount);
      if (amount === null || amount <= 0) throw new Error("Enter a payment amount");
      return api<FeePayment>(`/api/student/fees/${payingFee!.id}/payments`, {
        body: {
          amount_minor: amount,
          occurred_on: v.occurred_on || undefined,
          account_id: v.account_id ? Number(v.account_id) : null,
          reference: v.reference || null,
          idempotency_key: crypto.randomUUID(),
        },
      });
    },
    onSuccess: () => {
      setPayingFee(null);
      payForm.reset();
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  const deleteFee = useMutation({
    mutationFn: (id: number) =>
      api<void>(`/api/student/fees/${id}`, { method: "DELETE", params: { confirm: true } }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  // --- Accommodation ---
  const hostelForm = useForm<HostelForm>();
  const addHostel = useMutation({
    mutationFn: (v: HostelForm) =>
      api<HostelOption>("/api/student/hostels", {
        body: {
          name: v.name,
          location: v.location || null,
          monthly_rent_minor: toMinor(v.monthly_rent),
          deposit_minor: toMinor(v.deposit),
          facilities: v.facilities || null,
          booking_source: v.booking_source || null,
        },
      }),
    onSuccess: () => {
      hostelForm.reset();
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });
  const setAvailability = useMutation({
    mutationFn: (v: { id: number; status: HostelStatus }) =>
      api<HostelOption>(`/api/student/hostels/${v.id}/availability`, {
        method: "POST",
        body: { status: v.status },
      }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  // --- Food budget ---
  const foodForm = useForm<{ weekly: string }>();
  const saveFood = useMutation({
    mutationFn: (v: { weekly: string }) =>
      api<FoodBudget>("/api/student/food-budget", {
        method: "PUT",
        body: { weekly_budget_minor: toMinor(v.weekly) },
      }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  const s = summary.data;

  return (
    <div>
      <div className="page-header">
        <h1>Student Life</h1>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}

      <div className="tabs" role="tablist">
        {(["overview", "fees", "accommodation", "food"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "tab-btn active" : "tab-btn"}
            onClick={() => setTab(t)}
          >
            {t === "accommodation" ? "Accommodation" : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="stat-grid">
            <div className="card stat-card">
              <span className="stat-label">Fees due</span>
              <strong>{s ? formatMinor(s.total_fees_due_minor) : "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Fees paid</span>
              <strong>{s ? formatMinor(s.total_fees_paid_minor) : "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Outstanding</span>
              <strong>{s ? formatMinor(s.total_fees_outstanding_minor) : "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Overdue fees</span>
              <strong>{s?.overdue_fees_count ?? "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Food budget / week</span>
              <strong>{formatMinor(food.data?.weekly_budget_minor)}</strong>
            </div>
          </div>
          <p className="muted">
            Fees are marked paid only from payments you record, and a hostel is
            only "available/booked" when you say so — LifeSmart never claims
            either on your behalf.
          </p>
        </>
      )}

      {tab === "fees" && (
        <>
          <form className="card auth-form" onSubmit={feeForm.handleSubmit((v) => addFee.mutate(v))}>
            <h2>Add fee obligation</h2>
            <div className="btn-row">
              <label>
                Name
                <input {...feeForm.register("name", { required: true })} />
              </label>
              <label>
                Category
                <select {...feeForm.register("category")}>
                  {FEE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label>
                Amount due (KES)
                <input type="number" min="0.01" step="0.01" {...feeForm.register("amount_due", { required: true })} />
              </label>
              <label>
                Due date
                <input type="date" {...feeForm.register("due_on")} />
              </label>
              <label>
                Reference (optional)
                <input {...feeForm.register("reference")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addFee.isPending}>
              <Plus size={16} aria-hidden /> Add Fee
            </button>
          </form>

          <div className="card">
            <h2>Fee obligations</h2>
            {(fees.data ?? []).map((f) => (
              <div key={f.id} className="list-row">
                <span>
                  <strong>{f.name}</strong> <span className="badge">{f.category}</span>
                  <span className="muted">
                    {" "}· {formatMinor(f.amount_paid_minor)} of {formatMinor(f.amount_due_minor)} paid
                    {f.due_on ? ` · due ${f.due_on}` : ""}
                  </span>
                </span>
                <span>
                  <span className={`badge ${f.status === "paid" ? "income" : f.status === "unpaid" ? "warn" : ""}`}>
                    {f.status}
                  </span>{" "}
                  <span className="muted">{formatMinor(f.outstanding_minor)} left</span>{" "}
                  {f.status !== "paid" && (
                    <button className="btn small" onClick={() => { setPayingFee(f); payForm.reset(); }}>
                      Record payment
                    </button>
                  )}{" "}
                  <button className="btn ghost small" onClick={() => deleteFee.mutate(f.id)}>
                    Delete
                  </button>
                </span>
              </div>
            ))}
            {fees.data?.length === 0 && <p className="muted">No fee obligations yet.</p>}
          </div>
        </>
      )}

      {tab === "accommodation" && (
        <>
          <form className="card auth-form" onSubmit={hostelForm.handleSubmit((v) => addHostel.mutate(v))}>
            <h2>Add hostel option</h2>
            <div className="btn-row">
              <label>
                Name
                <input {...hostelForm.register("name", { required: true })} />
              </label>
              <label>
                Location
                <input {...hostelForm.register("location")} />
              </label>
              <label>
                Monthly rent (KES)
                <input type="number" min="0" step="0.01" {...hostelForm.register("monthly_rent")} />
              </label>
              <label>
                Deposit (KES)
                <input type="number" min="0" step="0.01" {...hostelForm.register("deposit")} />
              </label>
              <label>
                Facilities
                <input {...hostelForm.register("facilities")} />
              </label>
              <label>
                Booking source
                <input {...hostelForm.register("booking_source")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addHostel.isPending}>
              <Plus size={16} aria-hidden /> Add Option
            </button>
          </form>

          <div className="card">
            <h2>Accommodation options</h2>
            {(hostels.data ?? []).map((h) => (
              <div key={h.id} className="list-row">
                <span>
                  <strong>{h.name}</strong>
                  {h.location ? <span className="muted"> · {h.location}</span> : null}
                  <span className="muted">
                    {" "}· rent {formatMinor(h.monthly_rent_minor)} · deposit {formatMinor(h.deposit_minor)}
                  </span>
                  {h.last_checked_at && (
                    <span className="muted"> · checked {h.last_checked_at.slice(0, 10)}</span>
                  )}
                </span>
                <select
                  className="btn small"
                  value={h.status}
                  onChange={(e) =>
                    setAvailability.mutate({ id: h.id, status: e.target.value as HostelStatus })
                  }
                >
                  {HOSTEL_STATUSES.map((st) => <option key={st} value={st}>{st}</option>)}
                </select>
              </div>
            ))}
            {hostels.data?.length === 0 && <p className="muted">No accommodation options yet.</p>}
          </div>
        </>
      )}

      {tab === "food" && (
        <form
          className="card auth-form"
          onSubmit={foodForm.handleSubmit((v) => saveFood.mutate(v))}
        >
          <h2>Food budget</h2>
          <p className="muted">
            Grocery lists reuse Shopping; food stock reuses Inventory. Here just
            set your weekly food budget and we derive a daily estimate.
          </p>
          <label>
            Weekly budget (KES)
            <input type="number" min="0" step="0.01"
              defaultValue={food.data?.weekly_budget_minor ? food.data.weekly_budget_minor / 100 : ""}
              {...foodForm.register("weekly")} />
          </label>
          <p className="muted">
            Current: {formatMinor(food.data?.weekly_budget_minor)} / week
            {food.data?.daily_estimate_minor != null
              ? ` · about ${formatMinor(food.data.daily_estimate_minor)} / day`
              : ""}
          </p>
          <button className="btn primary" type="submit" disabled={saveFood.isPending}>
            Save Budget
          </button>
        </form>
      )}

      {payingFee && (
        <div className="more-sheet-backdrop" onClick={() => setPayingFee(null)}>
          <div className="card auth-form" role="dialog"
            aria-label={`Record payment for ${payingFee.name}`} onClick={(e) => e.stopPropagation()}>
            <h2>Record payment: {payingFee.name}</h2>
            <p className="muted">
              {formatMinor(payingFee.outstanding_minor)} outstanding. LifeSmart only
              marks fees paid from payments you confirm.
            </p>
            <form onSubmit={payForm.handleSubmit((v) => recordPayment.mutate(v))}>
              <div className="btn-row">
                <label>
                  Amount (KES)
                  <input type="number" min="0.01" step="0.01" {...payForm.register("amount", { required: true })} />
                </label>
                <label>
                  Date
                  <input type="date" {...payForm.register("occurred_on")} />
                </label>
              </div>
              <label>
                Paid from account (optional)
                <select {...payForm.register("account_id")}>
                  <option value="">Not allocated</option>
                  {(accounts.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </label>
              <label>
                Payment reference (optional)
                <input {...payForm.register("reference")} />
              </label>
              <button className="btn primary" type="submit" disabled={recordPayment.isPending}>
                Confirm Payment
              </button>{" "}
              <button className="btn" type="button" onClick={() => setPayingFee(null)}>Cancel</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
