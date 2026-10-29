/** Projected run-out dates, read from the item's own quantity history.
 *
 * The backend only lists an item once a consumption rate has actually been
 * observed, so an entry here is a projection from recorded use - never a rule of
 * thumb. A figure that was never priced is said to need a price rather than
 * showing a zero. Everything is passed in as props so this stays testable and
 * the Inventory page owns the fetch.
 */
import { TrendingDown } from "lucide-react";
import { formatMinor } from "../../lib/money";
import type { InventoryForecast, InventoryForecasts } from "../../types/api";

function ForecastRow({ f, currency }: { f: InventoryForecast; currency: string }) {
  const when = f.days_to_zero <= 0 ? "Out now" : `~${f.days_to_zero} days left · out by ${f.runout_on}`;
  const rate = `used ~${f.consumption_per_day}${f.unit ? ` ${f.unit}` : ""} a day`;
  const costText =
    f.estimated_refill_cost_minor !== null
      ? `refill ≈ ${formatMinor(f.estimated_refill_cost_minor, currency)}`
      : f.shortage > 0
        ? "price needed to refill"
        : null;

  return (
    <div className="list-row forecast-row">
      <div>
        <strong>{f.name}</strong>
        <p className="muted">
          {when} · {rate}
          {f.confidence === "limited" && " · limited history"}
          {costText && ` · ${costText}`}
        </p>
      </div>
      {f.restock_soon && <span className="badge warn">restock soon</span>}
    </div>
  );
}

export function ForecastPanel({ data }: { data: InventoryForecasts }) {
  return (
    <section className="card">
      <h2>
        <TrendingDown size={16} aria-hidden /> When things run out
      </h2>
      {data.forecasts.length === 0 ? (
        <p className="muted">
          Nothing has enough usage history to predict a run-out yet. This appears
          once you record quantity going down on an item.
        </p>
      ) : (
        <>
          <p className="muted">
            Projected from your own quantity history as at {data.generated_on}.
          </p>
          {data.forecasts.map((f) => (
            <ForecastRow key={f.item_id} f={f} currency={data.currency} />
          ))}
        </>
      )}
    </section>
  );
}
