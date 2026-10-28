/** One derived alert, rendered the same way wherever it appears.
 *
 * The Notifications page and the Home dashboard both list what the app's own
 * records say needs attention. A figure must not be spelled one way on one page
 * and another way on the next, so the money line, the severity chip and the link
 * to the page that can settle it live here and nowhere else.
 *
 * Nothing here stores or sends anything: an alert is computed from saved records
 * on every load, so settling it makes the row disappear by itself.
 */
import { Link } from "react-router-dom";
import { formatMinor } from "../../lib/money";
import type { AlertKind, AlertSeverity, NotificationAlert } from "../../types/api";

export const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  overdue: "Overdue",
  due: "Due",
  soon: "Behind pace",
  attention: "Check",
};

/** How each kind of alert is described when a page has to name the ones the
 * user's own switches hid. Both Home and the Notifications page say this, and
 * the wording must match the switch labels it is pointing at. */
export const KIND_LABELS: Record<AlertKind, string> = {
  deadline: "goal deadlines",
  task: "task reminders",
  fee: "fee alerts",
  stock: "low-stock warnings",
  savings: "savings pace nudges",
};

/** The money line of an alert. Both figures are minor units straight from the
 * record, formatted here with the currency the API named, so a sum cannot be
 * stated one way by the backend and another way by the page. */
export function alertMoney(alert: NotificationAlert, currency: string): string | null {
  const parts: string[] = [];
  if (alert.amount_minor !== null) {
    parts.push(`${formatMinor(alert.amount_minor, currency)} still to cover`);
  }
  if (alert.period_amount_minor !== null) {
    parts.push(
      `about ${formatMinor(alert.period_amount_minor, currency)} per ${
        alert.period_label ?? "period"
      } closes the gap`,
    );
  }
  return parts.join(" · ") || null;
}

export function AlertRow({ alert, currency }: { alert: NotificationAlert; currency: string }) {
  const money = alertMoney(alert, currency);
  return (
    <div className={`list-row alert-row severity-${alert.severity}`}>
      <div>
        <strong>{alert.title}</strong>
        {alert.detail && <p className="muted">{alert.detail}</p>}
        {money && <p className="alert-money">{money}</p>}
      </div>
      <div className="alert-actions">
        <span className={`badge ${alert.severity}`}>{SEVERITY_LABELS[alert.severity]}</span>
        <Link className="btn small" to={alert.link}>
          Open
        </Link>
      </div>
    </div>
  );
}
