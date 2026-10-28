/** Which picture sits behind which section. The mapping is the whole point of
 * lib/backgrounds, so it is tested directly: a renamed route should fall back to
 * the default picture, but a swapped pair (school art behind Reports, water
 * behind Student Life) is a mistake nobody notices until they read it. */
import { describe, expect, it } from "vitest";
import blueWater from "../assets/backgrounds/blue-water.jpg";
import peacockPaper from "../assets/backgrounds/peacock-paper.jpg";
import redSpace from "../assets/backgrounds/red-space.jpg";
import sageAbstract from "../assets/backgrounds/sage-abstract.jpg";
import schoolFrame from "../assets/backgrounds/school-frame.jpg";
import { DEFAULT_BACKGROUND, backgroundForPath, sectionForPath } from "./backgrounds";

describe("sectionForPath", () => {
  it("reads the segment after /app", () => {
    expect(sectionForPath("/app/goals")).toBe("goals");
    expect(sectionForPath("/app/earnings-savings")).toBe("earnings-savings");
    expect(sectionForPath("/app/money/4")).toBe("money");
  });

  it("finds no section for the shell index or for anything outside it", () => {
    expect(sectionForPath("/app")).toBe("");
    expect(sectionForPath("/login")).toBe("");
    expect(sectionForPath("/")).toBe("");
  });
});

describe("backgroundForPath", () => {
  it("gives each of the five sections its own picture", () => {
    expect(backgroundForPath("/app/reports")).toBe(blueWater);
    expect(backgroundForPath("/app/goals")).toBe(peacockPaper);
    expect(backgroundForPath("/app/student")).toBe(schoolFrame);
    expect(backgroundForPath("/app/assistant")).toBe(redSpace);
    expect(backgroundForPath("/app/money")).toBe(sageAbstract);
  });

  it("keeps the money pages on one picture", () => {
    for (const path of ["/app/money", "/app/earnings-savings", "/app/networth"]) {
      expect(backgroundForPath(path)).toBe(sageAbstract);
    }
  });

  it("falls back to a picture rather than nothing for sections without one", () => {
    for (const path of ["/app", "/app/inventory", "/app/shopping", "/app/whatever"]) {
      expect(backgroundForPath(path)).toBe(DEFAULT_BACKGROUND);
    }
  });

  it("uses every picture the folder holds", () => {
    const used = new Set(
      [
        "/app/money",
        "/app/reports",
        "/app/goals",
        "/app/student",
        "/app/assistant",
      ].map(backgroundForPath),
    );
    expect(used).toEqual(
      new Set([sageAbstract, blueWater, peacockPaper, schoolFrame, redSpace]),
    );
  });
});
