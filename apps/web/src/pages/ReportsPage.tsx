/** Reports: monthly cash flow, spending by category, balance history, savings
 * & goal progress, inventory shortage cost, business profit and upcoming
 * obligations. Every figure comes from the API (which derives it from saved
 * records); unknowns render as "Unknown"/"—", never as a fabricated number. */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Printer } from "lucide-react";
import { api, downloadFile } from "../services/api";
import { formatMinor } from "../lib/money";
import type { Account, ReportSummary } from "../types/api";

interface Filters {
  date_from: string;
  date_to: string;
  account_id: string;
  category: string;
}

const EMPTY: Filters = { date_from: "", date_to: "", account_id: "", category: "" };

function money(minor: number | null, currency: string): string {
  return minor === null ? "Unknown" : formatMinor(minor, currency);
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="stat-card card">
      <span className="stat-label">{label}</span>
      <strong>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

function BarList({
  data,
  currency,
}: {
  data: { label: string; minor: number; meta?: string }[];
  currency: string;
}) {
  const max = Math.max(1, ...data.map((d) => Math.abs(d.minor)));
  return (
    <ul className="bar-list">
      {data.map((d) => (
        <li key={d.label}>
          <div className="bar-row">
            <span className="bar-label">{d.label}</span>
            <span className="bar-track">
              <span
                className="bar-fill"
                style={{ width: `${(Math.abs(d.minor) / max) * 100}%` }}
              />
            </span>
            <span className="bar-value">
              {formatMinor(d.minor, currency)}
              {d.meta && <span className="muted"> · {d.meta}</span>}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ReportsPage() {
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);

  const params = useMemo(
    () => ({
      date_from: applied.date_from || undefined,
      date_to: applied.date_to || undefined,
      account_id: applied.account_id || undefined,
      category: applied.category || undefined,
    }),
    [applied],
  );

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });

  const report = useQuery({
    queryKey: ["reports", params],
    queryFn: () => api<ReportSummary>("/api/reports/summary", { params }),
  });

  const r = report.data;
  const currency = r?.currency ?? "KES";

  return (
    <div className="reports-page">
      <div className="page-header">
        <h1>Reports</h1>
        <div className="btn-row">
          <button
            className="btn"
            onClick={() => downloadFile("/api/reports/export.csv", params)}
          >
            <Download size={16} aria-hidden /> Export CSV
          </button>
          <button className="btn" onClick={() => window.print()}>
            <Printer size={16} aria-hidden /> Print / PDF
          </button>
        </div>
      </div>

      <form
        className="card report-filters no-print"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(draft);
        }}
      >
        <label>
          From
          <input
            type="date"
            value={draft.date_from}
            onChange={(e) => setDraft({ ...draft, date_from: e.target.value })}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={draft.date_to}
            onChange={(e) => setDraft({ ...draft, date_to: e.target.value })}
          />
        </label>
        <label>
          Account
          <select
            value={draft.account_id}
            onChange={(e) => setDraft({ ...draft, account_id: e.target.value })}
          >
            <option value="">All accounts</option>
            {accounts.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <input
            value={draft.category}
            maxLength={80}
            placeholder="e.g. food"
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          />
        </label>
        <div className="btn-row">
          <button className="btn primary" type="submit">
            Apply
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => {
              setDraft(EMPTY);
              setApplied(EMPTY);
            }}
          >
            Reset
          </button>
        </div>
      </form>

      {report.isError && (
        <p className="error-banner" role="alert">
          Could not load reports: {(report.error as Error).message}
        </p>
      )}
      {report.isPending && !report.data && <p className="muted">Loading…</p>}

      {r && (
        <>
          <p className="muted report-note">{r.note}</p>

          <section className="card">
            <h2>Monthly income &amp; expenses</h2>
            <div className="stat-grid">
              <Stat label="Income" value={money(r.cash_flow.income_minor, currency)} />
              <Stat label="Expenses" value={money(r.cash_flow.expense_minor, currency)} />
              <Stat
                label="Net"
                value={money(r.cash_flow.net_minor, currency)}
                note={`${r.cash_flow.txn_count} transaction(s)`}
              />
              <Stat
                label="Transfers (excluded)"
                value={money(r.cash_flow.transfers_minor, currency)}
              />
            </div>
          </section>

          <section className="card">
            <h2>Spending by category</h2>
            {r.spending_by_category.length === 0 ? (
              <p className="muted">No expenses recorded for this selection.</p>
            ) : (
              <BarList
                currency={currency}
                data={r.spending_by_category.map((c) => ({
                  label: c.category,
                  minor: c.total_minor,
                  meta: `${c.count} item(s)`,
                }))}
              />
            )}
          </section>

          <section className="card">
            <h2>Account balance history</h2>
            {!r.balance_history.available ? (
              <p className="muted">{r.balance_history.note}</p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Change</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {r.balance_history.points.map((p) => (
                    <tr key={p.month}>
                      <td>{p.month}</td>
                      <td>{formatMinor(p.net_change_minor, currency)}</td>
                      <td>{formatMinor(p.running_balance_minor, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Savings &amp; goals</h2>
            <div className="stat-grid">
              <Stat
                label="Total saved in goals"
                value={money(r.savings.total_saved_in_goals_minor, currency)}
              />
              <Stat
                label="Saved in period"
                value={money(r.savings.saved_in_period_minor, currency)}
              />
              <Stat label="Active goals" value={String(r.savings.active_goals)} />
              <Stat label="Completed goals" value={String(r.savings.completed_goals)} />
            </div>
            {r.goals.length > 0 && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Goal</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {r.goals.map((g) => (
                    <tr key={g.id}>
                      <td>{g.name}</td>
                      <td>
                        <span className="badge">{g.status}</span>
                      </td>
                      <td>
                        {g.percent === null ? (
                          "—"
                        ) : (
                          <span className="progress-track" role="progressbar"
                            aria-valuenow={g.percent} aria-valuemin={0} aria-valuemax={100}>
                            <span className="progress-fill" style={{ width: `${g.percent}%` }} />
                          </span>
                        )}
                      </td>
                      <td>
                        {g.remaining_amount_minor !== null
                          ? formatMinor(g.remaining_amount_minor, currency)
                          : g.remaining_quantity !== null
                            ? `${g.remaining_quantity} left`
                            : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Inventory shortage cost</h2>
            <div className="stat-grid">
              <Stat label="Items below target" value={String(r.shortage.items_below_target)} />
              <Stat label="Need a price" value={String(r.shortage.price_needed_items)} />
              <Stat
                label="Estimated cost to target"
                value={
                  r.shortage.estimated_cost_minor === null
                    ? "Unknown (prices needed)"
                    : formatMinor(r.shortage.estimated_cost_minor, currency)
                }
              />
            </div>
          </section>

          <section className="card">
            <h2>Business revenue &amp; profit</h2>
            <div className="stat-grid">
              <Stat label="Revenue" value={money(r.business.revenue_minor, currency)} />
              <Stat label="Expenses" value={money(r.business.expenses_minor, currency)} />
              <Stat
                label="Net profit"
                value={money(r.business.net_profit_minor, currency)}
                note="revenue − expenses"
              />
            </div>
          </section>

          <section className="card">
            <h2>Upcoming obligations</h2>
            {r.obligations.items.length === 0 ? (
              <p className="muted">Nothing outstanding in your records.</p>
            ) : (
              <>
                <p className="muted">
                  Outstanding fees: {formatMinor(r.obligations.outstanding_fees_minor, currency)}
                  {" · "}
                  {r.obligations.overdue_count} overdue
                </p>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Type</th>
                      <th>Due</th>
                      <th>Status</th>
                      <th>Outstanding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.obligations.items.map((o, i) => (
                      <tr key={i}>
                        <td>{o.name}</td>
                        <td>{o.kind}</td>
                        <td>{o.due_on ?? "—"}</td>
                        <td>
                          <span className={`badge ${o.status}`}>{o.status}</span>
                        </td>
                        <td>
                          {o.outstanding_minor !== null
                            ? formatMinor(o.outstanding_minor, currency)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
