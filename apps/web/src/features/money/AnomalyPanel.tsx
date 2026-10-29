/** Unusual spending, stated as the comparison it was derived from.

 * The backend only lists an expense when its own category has enough recorded
 * spending to have a dependable median. So every row here is "this amount
 * against that median", never a verdict about whether the spend was wise -
 * and a thin history simply produces no rows, which this panel says plainly
 * instead of hiding the section.
 */
import { AlertTriangle } from "lucide-react";
import { formatMinor } from "../../lib/money";
import type { ExpenseAnomalies, ExpenseAnomaly } from "../../types/api";

function AnomalyRow({ a }: { a: ExpenseAnomaly }) {
  const times = (a.amount_minor / a.category_median_minor).toFixed(1);
  return (
    <div className="list-row anomaly-row">
      <div>
        <strong>{a.description ?? a.category}</strong>
        <p className="muted">
          {formatMinor(a.amount_minor, a.currency)} on {a.occurred_on} ·{" "}
          {a.category} median {formatMinor(a.category_median_minor, a.currency)} (
          {times}× typical)
        </p>
      </div>
      <span className="badge warn">unusual</span>
    </div>
  );
}

export function AnomalyPanel({ data }: { data: ExpenseAnomalies }) {
  return (
    <section className="card">
      <h2>
        <AlertTriangle size={16} aria-hidden /> Unusual spending
      </h2>
      {data.anomalies.length === 0 ? (
        <p className="muted">
          Nothing stands out against your own records. A category is only
          compared once it has {data.min_category_expenses} expenses in the last{" "}
          {data.window_days} days - before that there is no &ldquo;usual&rdquo;
          to measure against.
        </p>
      ) : (
        <>
          <p className="muted">
            Measured against each category&rsquo;s own median over the last{" "}
            {data.window_days} days, as at {data.generated_on}.
          </p>
          {data.anomalies.map((a) => (
            <AnomalyRow key={a.transaction_id} a={a} />
          ))}
        </>
      )}
    </section>
  );
}
