/**
 * Net worth page: the list of things you own, priced.
 *
 * Every row answers the same four questions - what I have, what I still need,
 * what one costs, what mine adds up to - and the totals at the top are the
 * answer to "how much money should I have". Nothing here is typed in: the
 * figures come from inventory records and the saved total is re-recorded
 * whenever an item or a price changes. Pictures are resolved from the asset
 * library by category, so a new folder of photos shows up without a code edit.
 */
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Gem, Package, RefreshCw } from "lucide-react";
import { api } from "../services/api";
import { formatMinor, shortageLabel } from "../lib/money";
import { AssetImage } from "../features/assets/AssetImage";
import { TrendSummary } from "../features/networth/TrendSummary";
import type { Valuation, ValuationLine } from "../types/api";

function formatDay(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Total({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="card stat-card">
      <span className="stat-label">{label}</span>
      <strong>{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

function LineRow({ line, currency }: { line: ValuationLine; currency: string }) {
  const unitCost =
    line.unit_cost_minor === null ? (
      <span className="badge warn">Price needed</span>
    ) : (
      <>
        {formatMinor(line.unit_cost_minor, currency)}
        {!line.price_verified && <span className="muted"> est.</span>}
      </>
    );
  const toTarget =
    line.needed_quantity === 0
      ? line.target_quantity === null
        ? "No target"
        : "Target met"
      : shortageLabel(line.to_target_minor, line.to_target_minor === null);

  return (
    <tr>
      <td>
        {/* The server already picked the picture: the item's own photo if it
            has one, else a stable match from its category folder. */}
        <AssetImage
          assetId={line.image_asset_id}
          category={line.category_slug ?? undefined}
          seed={line.item_id}
          size={56}
          alt={line.name}
        />
      </td>
      <td>
        <span className="worth-item-name">{line.name}</span>
        <span className="muted">{line.category_name ?? "No category"}</span>
      </td>
      <td className="num">
        {line.quantity_owned}
        {line.unit ? ` ${line.unit}` : ""}
      </td>
      <td className="num">
        {line.target_quantity === null ? (
          <span className="muted">not set</span>
        ) : line.needed_quantity > 0 ? (
          <span className="badge warn">+{line.needed_quantity}</span>
        ) : (
          "0"
        )}
      </td>
      <td className="num">{unitCost}</td>
      <td className="num">
        {shortageLabel(line.value_minor, line.value_minor === null)}
      </td>
      <td className="num">{toTarget}</td>
    </tr>
  );
}

export function NetWorthPage() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: ["networth"],
    queryFn: () => api<Valuation>("/api/networth"),
  });
  const currency = data?.currency ?? "KES";

  const headline =
    data?.net_worth_minor === null || data?.net_worth_minor === undefined
      ? "Not known yet"
      : formatMinor(data?.net_worth_minor, currency);

  return (
    <div>
      <div className="page-header">
        <h1>Net worth</h1>
        <button className="btn" onClick={() => refetch()} disabled={isPending}>
          <RefreshCw size={16} aria-hidden /> Refresh
        </button>
      </div>

      {isPending && <p className="muted">Loading…</p>}
      {error && (
        <p className="error-banner">Could not price your things: {error.message}</p>
      )}

      {data && data.lines.length === 0 && (
        <div className="card empty-state">
          <p>
            Nothing recorded yet, so there is nothing to add up.{" "}
            <Link to="/app/inventory">Add items in Inventory</Link> - what they
            cost and what you own - and your net worth builds itself.
          </p>
        </div>
      )}

      {data && data.lines.length > 0 && (
        <>
          <div className="card worth-headline">
            <Gem size={22} aria-hidden />
            <div>
              <span className="stat-label">Your net worth (saved automatically)</span>
              <strong className="worth-amount">{headline}</strong>
              {data.net_worth_minor === null ? (
                <span className="worth-note">
                  At least {formatMinor(data.priced_value_minor, currency)} from{" "}
                  {data.valued_items} of {data.items} priced{" "}
                  {data.items === 1 ? "item" : "items"}; {data.unpriced_items}{" "}
                  {data.unpriced_items === 1 ? "is" : "are"} still without a price.
                </span>
              ) : (
                <span className="worth-note">
                  {data.valued_items} priced {data.items === 1 ? "item" : "items"}
                  , {data.units_owned} {data.units_owned === 1 ? "unit" : "units"} owned
                  {data.saved
                    ? ` · recorded ${formatDay(data.saved.on_date)}`
                    : ""}
                </span>
              )}
            </div>
          </div>

          <div className="stat-grid">
            <Total
              label="Value of what you own"
              value={
                data.net_worth_minor === null
                  ? `≥ ${formatMinor(data.priced_value_minor, currency)}`
                  : formatMinor(data.net_worth_minor, currency)
              }
              note={
                data.unpriced_items > 0
                  ? `${data.unpriced_items} item(s) without a price`
                  : "every item priced"
              }
            />
            <Total
              label="Still to reach your targets"
              value={shortageLabel(data.to_target_minor, data.to_target_minor === null)}
              note={`${data.units_needed} units to buy`}
            />
            <Total
              label="Total money you should have"
              value={shortageLabel(
                data.replacement_total_minor,
                data.replacement_total_minor === null,
              )}
              note="What you own plus what you still need"
            />
            <Total
              label="Items on record"
              value={String(data.items)}
              note="From your inventory"
            />
          </div>

          <div className="card">
            <h2>What you have, priced</h2>
            <div className="table-scroll">
              <table className="data-table worth-table">
                <thead>
                  <tr>
                    <th aria-label="Picture" />
                    <th>Item</th>
                    <th className="num">I have</th>
                    <th className="num">I need</th>
                    <th className="num">One costs</th>
                    <th className="num">Worth</th>
                    <th className="num">To target</th>
                  </tr>
                </thead>
                <tbody>
                  {data.lines.map((line) => (
                    <LineRow key={line.item_id} line={line} currency={currency} />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted worth-footnote">
              Estimates are your own recorded prices, never invented ones. An item
              with no price keeps the total unknown instead of quietly counting as
              free. Pictures come from your <Link to="/app/images">image library</Link>;
              quantities and prices are edited in{" "}
              <Link to="/app/inventory">Inventory</Link>.
            </p>
          </div>

          {data.history.length > 1 && (
            <div className="card">
              <h2>Saved over time</h2>
              {data.trend && <TrendSummary trend={data.trend} currency={currency} />}
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th className="num">Net worth</th>
                    <th className="num">Items priced</th>
                  </tr>
                </thead>
                <tbody>
                  {data.history.map((row) => (
                    <tr key={row.on_date}>
                      <td>{formatDay(row.on_date)}</td>
                      <td className="num">
                        {shortageLabel(row.net_worth_minor, !row.complete)}
                      </td>
                      <td className="num">
                        {row.valued_items}
                        {row.unpriced_items > 0 ? ` (+${row.unpriced_items} unpriced)` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="report-note">
            <Package size={14} aria-hidden /> {data.note}
          </p>
        </>
      )}
    </div>
  );
}
