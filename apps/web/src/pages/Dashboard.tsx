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
  BellRing,
} from "lucide-react";
import { api } from "../services/api";
import { formatMinor, shortageLabel } from "../lib/money";
import { useAuth } from "../features/auth/AuthProvider";
import { AlertRow, KIND_LABELS } from "../features/notifications/AlertRow";
import type { AlertsResponse, DashboardSummary } from "../types/api";

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

/** How many alerts Home lists before sending the rest to the Notifications page.
 * Three is enough to see whether today holds anything urgent; beyond that the
 * full list is one click away and this card stops being a summary. */
const HOME_ALERT_LIMIT = 3;

/** The first half of "what needs attention", in the same rows the Notifications
 * page uses. Nothing is fetched twice: this shares the sidebar's query, so one
 * load of Home answers both the badge and this list.
 *
 * A short list here is never allowed to read as an all-clear. Whatever the
 * records did not surface - because a switch hid it, because only the top three
 * are shown, or because the answer did not arrive at all - is stated rather
 * than left for the person to assume. */
function AttentionCard() {
  const alerts = useQuery({
    queryKey: ["notification-alerts"],
    queryFn: () => api<AlertsResponse>("/api/notifications/alerts"),
    staleTime: 60_000,
  });

  if (alerts.isPending) return <p className="muted">Checking your records…</p>;
  if (alerts.isError) {
    return (
      <p className="error-banner" role="alert">
        Could not read what needs attention: {(alerts.error as Error).message}
      </p>
    );
  }

  const data = alerts.data;
  // An answer that is not the shape expected (an older server, a stubbed fetch)
  // is reported as unknown. Showing "nothing needs you" for it would be a
  // claim about records this response never described.
  if (!data || !Array.isArray(data.alerts)) {
    return <p className="muted">The app could not read what needs attention.</p>;
  }

  const shown = data.alerts.slice(0, HOME_ALERT_LIMIT);
  const hiddenNames = data.hidden_by_preferences.map((k) => KIND_LABELS[k]).join(", ");

  return (
    <section className="card">
      <div className="btn-row spaced">
        <h2>
          <BellRing size={16} aria-hidden /> Needs your attention
        </h2>
        <Link className="btn small ghost" to="/app/notifications">
          {data.count > shown.length ? `See all ${data.count}` : "Open"}
        </Link>
      </div>

      {data.count === 0 ? (
        <p className="muted">
          {data.hidden_by_preferences.length > 0
            ? `Nothing is showing, because ${hiddenNames} are switched off in Notifications.`
            : "Nothing in your records needs attention today. This is built from what you have saved, so something you never recorded cannot appear here."}
        </p>
      ) : (
        <>
          {shown.map((alert) => (
            <AlertRow key={alert.key} alert={alert} currency={data.currency} />
          ))}
          {data.count > shown.length && (
            <p className="muted">
              {data.count - shown.length} more in Notifications, which has them all.
            </p>
          )}
          {data.hidden_by_preferences.length > 0 && (
            <p className="muted">
              Not included: {hiddenNames}, switched off in Notifications.
            </p>
          )}
        </>
      )}

      {data.in_quiet_hours && data.count > 0 && (
        <p className="muted">
          Quiet hours{data.quiet_ends_at ? ` until ${data.quiet_ends_at}` : ""} hide the
          sidebar count - this list stays as it is.
        </p>
      )}
    </section>
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

          <AttentionCard />

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
            <h2>Where the figures come from</h2>
            <p className="muted">
              Every screen below writes to the same records the numbers above are
              read from, so a sum is stated in one place only. Nothing here is a
              placeholder: if a figure is missing, the page says which record it
              is waiting on rather than guessing.
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
