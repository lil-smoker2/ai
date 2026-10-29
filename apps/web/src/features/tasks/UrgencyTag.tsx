/** A task's urgency, shown as the number and the two weights behind it.

 * The score arrives from the backend already computed; this only speaks it.
 * A settled (done/cancelled) task is showing no urgency, so it renders nothing
 * rather than a zero that could be mistaken for a real ranking. The breakdown
 * - priority points and overdue points, and the band they place it in - rides
 * in the title so the figure can be checked, not just trusted.
 */
import type { TaskUrgency } from "../../types/api";

export function UrgencyTag({ urgency }: { urgency: TaskUrgency }) {
  if (urgency.band === "settled") return null;

  const cls =
    urgency.band === "overdue"
      ? "badge warn"
      : urgency.band === "due-soon"
        ? "badge"
        : "muted urgency-quiet";
  const note = urgency.band === "unscheduled" ? " · no date" : "";
  const title =
    `${urgency.priority_points} priority + ${urgency.overdue_points} overdue · ${urgency.band}`;

  return (
    <span className={cls} title={title}>
      urgency {urgency.score}
      {note}
    </span>
  );
}
