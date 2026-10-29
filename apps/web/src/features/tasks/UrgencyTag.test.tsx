/** The urgency tag: it says the number it was handed and hides a settled task,
 * carrying the priority/overdue breakdown in the title for anyone to check. */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UrgencyTag } from "./UrgencyTag";
import type { TaskUrgency } from "../../types/api";

function urgency(over: Partial<TaskUrgency> = {}): TaskUrgency {
  return { score: 40, band: "overdue", priority_points: 10, overdue_points: 30, ...over };
}

describe("UrgencyTag", () => {
  it("shows the score the backend computed", () => {
    render(<UrgencyTag urgency={urgency()} />);
    expect(screen.getByText("urgency 40")).toBeInTheDocument();
  });

  it("carries the two weights in the title so the figure can be checked", () => {
    render(<UrgencyTag urgency={urgency()} />);
    expect(screen.getByText("urgency 40")).toHaveAttribute(
      "title",
      "10 priority + 30 overdue · overdue",
    );
  });

  it("says a no-date task is unscheduled rather than implying lateness", () => {
    render(
      <UrgencyTag
        urgency={urgency({ score: 10, band: "unscheduled", priority_points: 10, overdue_points: 0 })}
      />,
    );
    expect(screen.getByText(/urgency 10 · no date/)).toBeInTheDocument();
  });

  it("renders nothing for a settled task instead of a misleading zero", () => {
    const { container } = render(
      <UrgencyTag urgency={urgency({ score: 0, band: "settled", priority_points: 0, overdue_points: 0 })} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/urgency/)).toBeNull();
  });
});
