/** Which way the saved net worth has been moving - or why we cannot say.

 * The numbers are the backend's reading of the saved snapshots shown in the
 * table beside it: a least-squares slope and the first-to-last change, both in
 * integer minor units. Days whose total was unknown are announced as gaps and
 * were left out of the arithmetic; nothing here fills them in. A steady record
 * is reported as steady, because a slope inside the band genuinely is one.
 */
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { formatMinor } from "../../lib/money";
import type { NetWorthTrend } from "../../types/api";

const READING = {
  building: { icon: TrendingUp, words: "Your saved net worth has been building" },
  declining: { icon: TrendingDown, words: "Your saved net worth has been declining" },
  steady: { icon: Minus, words: "Your saved net worth has been holding steady" },
} as const;

export function TrendSummary({
  trend,
  currency = "KES",
}: {
  trend: NetWorthTrend;
  currency?: string;
}) {
  const { icon: Icon, words } = READING[trend.direction];
  return (
    <p className="muted trend-summary">
      <Icon size={14} aria-hidden /> {words}:{" "}
      {formatMinor(trend.change_minor, currency)} across{" "}
      {trend.known_days} recorded days ({trend.from_date} to {trend.to_date}),
      about {formatMinor(Math.abs(trend.slope_minor_per_day), currency)} a day{" "}
      {trend.slope_minor_per_day >= 0 ? "up" : "down"}. Recent days average{" "}
      {formatMinor(trend.recent_average_minor, currency)}.
      {trend.gap_days > 0 &&
        ` ${trend.gap_days} day${trend.gap_days === 1 ? "" : "s"} left out for want of a known total.`}
    </p>
  );
}
