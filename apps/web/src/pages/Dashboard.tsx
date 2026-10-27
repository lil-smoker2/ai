/** Home dashboard - every figure derives from saved records via the API. */
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Coins,
  Gem,
  Wallet,
  Target,
  PiggyBank,
  PackageSearch,
  TrendingUp,
} from "lucide-react";
import { api } from "../services/api";
import { formatMinor, shortageLabel } from "../lib/money";
import { useAuth } from "../features/auth/AuthProvider";
import type { DashboardSummary } from "../types/api";

function StatCard({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: typeof Wallet;
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="card stat-card">
      <Icon size={18} aria-hidden />
      <span className="stat-label">{label}</span>
      <strong>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardSummary>("/api/dashboard/summary"),
  });

  return (
    <div>
      <h1>Home</h1>
      <p className="muted">
        {user ? `Karibu, ${user.full_name}. Here is your current situation.` : "Loading…"}
      </p>
      {error && (
        <p className="error-banner" role="alert">
          Could not load your dashboard: {error.message}
        </p>
      )}
      {isPending && !error && <p className="muted">Loading…</p>}
      {data && (
        <>
          <div className="stat-grid">
            <StatCard
              icon={Wallet}
              label="Available balance"
              value={
                data.total_available_minor === null
                  ? "Not initialized"
                  : formatMinor(data.total_available_minor, user?.currency)
              }
              note={
                data.total_available_minor === null
                  ? "Set a starting balance on the Money page"
                  : "manually recorded"
              }
            />
            <StatCard
              icon={Gem}
              label="Net worth"
              value={
                data.net_worth_minor === null
                  ? "Price needed"
                  : formatMinor(data.net_worth_minor, user?.currency)
              }
              note="Value of your things, saved automatically"
            />
            <StatCard
              icon={TrendingUp}
              label="Income this month"
              value={formatMinor(data.income_this_month_minor, user?.currency)}
            />
            <StatCard
              icon={Coins}
              label="Expenses this month"
              value={formatMinor(data.expenses_this_month_minor, user?.currency)}
            />
            <StatCard
              icon={PiggyBank}
              label="Saved this month"
              value={formatMinor(data.savings_this_month_minor, user?.currency)}
            />
            <StatCard
              icon={Target}
              label="Active goals"
              value={String(data.active_goals)}
              note={
                data.outstanding_goal_amount_minor > 0
                  ? `${formatMinor(data.outstanding_goal_amount_minor, user?.currency)} outstanding`
                  : undefined
              }
            />
            <StatCard
              icon={PackageSearch}
              label="Items below target"
              value={String(data.items_below_target)}
              note={
                data.items_below_target > 0
                  ? `Est. ${shortageLabel(data.estimated_shortage_cost_minor, data.price_needed_items > 0)} to complete`
                  : undefined
              }
            />
          </div>

          <section className="quick-actions card">
            <h2>Quick actions</h2>
            <div className="btn-row">
              <Link className="btn primary" to="/app/money">Add Transaction</Link>
              <Link className="btn" to="/app/inventory">Add Item</Link>
              <Link className="btn" to="/app/goals">Create Goal</Link>
              <Link className="btn" to="/app/assistant">AI Assistant</Link>
            </div>
          </section>

          <section className="card">
            <h2>Modules</h2>
            <p className="muted">
              The Inventory, Money and Goals services are live and tested.
              Their data-entry screens are the next implementation milestone;
              every module will read from the same shared records shown above.
            </p>
            <div className="btn-row wrap">
              <Link className="btn ghost" to="/app/inventory">View All Inventory</Link>
              <Link className="btn ghost" to="/app/networth">View Net Worth</Link>
              <Link className="btn ghost" to="/app/goals">View All Goals</Link>
              <Link className="btn ghost" to="/app/reports">View Reports</Link>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
