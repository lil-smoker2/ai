/** The pace line under a goal: a date only when the contributions say so.

 * The backend leaves `projection` null unless money has actually been
 * arriving recently, so this component never has to decide whether a date is
 * justified - it states the one it was given, alongside the counts and the
 * per-day pace it was derived from. Amounts stay integer minor units and are
 * formatted like every other figure in the app.
 */
import { formatMinor } from "../../lib/money";
import type { GoalProjection } from "../../types/api";

export function GoalProjectionLine({
  projection,
  currency = "KES",
}: {
  projection: GoalProjection;
  currency?: string;
}) {
  const lead =
    projection.status === "on_track"
      ? "At your recorded saving pace"
      : projection.status === "after_deadline"
        ? "At your recorded pace this misses the deadline -"
        : "At your recorded saving pace (no deadline set) -";
  const badge =
    projection.status === "no_deadline"
      ? null
      : projection.status === "on_track"
        ? <span className="badge ok">on pace</span>
        : <span className="badge warn">behind pace</span>;

  return (
    <p className="muted goal-projection">
      {lead} {formatMinor(projection.amount_per_day_minor, currency)} a day,{" "}
      {projection.contribution_count} contributions over {projection.window_days}{" "}
      days: reached around {projection.projected_on}.
      {badge && <> {badge}</>}
    </p>
  );
}
