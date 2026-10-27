/** Honest module placeholder - routes exist, functionality lands per milestone. */
import { Construction } from "lucide-react";

export function UnderConstruction({
  title,
  milestone,
  detail,
}: {
  title: string;
  milestone: number;
  detail: string;
}) {
  return (
    <div>
      <h1>{title}</h1>
      <div className="card placeholder-card">
        <Construction size={28} aria-hidden />
        <h2>Not built yet — Milestone {milestone}</h2>
        <p>{detail}</p>
        <p className="muted">
          This page intentionally shows no fake data or simulated actions.
        </p>
      </div>
    </div>
  );
}
