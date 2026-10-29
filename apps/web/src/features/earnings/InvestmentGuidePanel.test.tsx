/** The curated reading list is static reference, so it is held to a simple
 * line: every site is presented with a link that leaves the app's window, no
 * rate or promise of return is dressed up as fact, and the one money example is
 * labelled a hypothetical the moment it appears. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { InvestmentGuidePanel } from "./InvestmentGuidePanel";
import { GUIDE_ENTRIES } from "./investmentGuide";

describe("InvestmentGuidePanel", () => {
  it("renders one entry per curated site, each with a safe external link", () => {
    render(<InvestmentGuidePanel />);

    expect(
      screen.getByRole("heading", {
        name: /Investment and betting websites/i,
      }),
    ).toBeInTheDocument();

    const items = screen.getAllByTestId("guide-item");
    expect(items).toHaveLength(GUIDE_ENTRIES.length);

    // A sample across the three groups the list spans.
    expect(screen.getByText("Interactive Brokers — Buying American shares")).toBeInTheDocument();
    expect(screen.getByText("Betika Kenya — Sports betting")).toBeInTheDocument();
    expect(screen.getByText("Capital Markets Authority Kenya")).toBeInTheDocument();

    // Every link opens the site in the real browser, never inside the app, and
    // carries the noopener guard a cross-origin link needs.
    for (const link of screen.getAllByRole("link", { name: "Open site" })) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link.getAttribute("href")).toMatch(/^https?:\/\//);
    }
  });

  it("frames the list as not-a-connection and the example as not-a-prediction", () => {
    render(<InvestmentGuidePanel />);

    // The honesty lead-in: the app cannot check these sites or vouch for them.
    expect(screen.getByText(/not connected to any of these sites/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing below is a recommendation/i)).toBeInTheDocument();

    // The one money figure is a worked hypothetical and says so plainly.
    expect(screen.getByText(/what can happen to KSh 5,000/i)).toBeInTheDocument();
    expect(
      screen.getByText(/hypothetical calculations .* not predictions/i),
    ).toBeInTheDocument();
  });
});
