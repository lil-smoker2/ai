import { describe, expect, it } from "vitest";
import { formatMinor, shortageLabel, lineTotalMinor } from "./money";

describe("formatMinor", () => {
  it("converts integer minor units to a KES display string", () => {
    expect(formatMinor(150000)).toBe("KES 1,500.00");
    expect(formatMinor(0)).toBe("KES 0.00");
    expect(formatMinor(2250000)).toBe("KES 22,500.00");
  });

  it("honours a custom currency", () => {
    expect(formatMinor(999, "UGX")).toBe("UGX 9.99");
  });

  it("shows an em dash for unknown values, never a fake zero", () => {
    expect(formatMinor(null)).toBe("—");
    expect(formatMinor(undefined)).toBe("—");
  });
});

describe("shortageLabel", () => {
  it("returns 'Price needed' when the price is unverified/unknown", () => {
    expect(shortageLabel(null, true)).toBe("Price needed");
    expect(shortageLabel(50000, true)).toBe("Price needed");
  });

  it("formats a known estimated cost", () => {
    expect(shortageLabel(2250000, false)).toBe("KES 22,500.00");
  });

  it("shows an em dash when there is neither a price nor a needed flag", () => {
    expect(shortageLabel(null, false)).toBe("—");
  });
});

describe("lineTotalMinor", () => {
  it("sums item cost plus delivery, transport and fees exactly", () => {
    // 2 x 2500.00 + 100.00 delivery + 50.00 transport + 15.00 fees
    expect(lineTotalMinor(2, 250000, 10000, 5000, 1500)).toBe(516500);
  });

  it("treats missing surcharges as zero", () => {
    expect(lineTotalMinor(3, 10000)).toBe(30000);
  });

  it("returns null (not a fake zero) when the unit price is unknown", () => {
    expect(lineTotalMinor(4, null)).toBeNull();
  });

  it("keeps integers exact with no float drift on large amounts", () => {
    expect(lineTotalMinor(1000000, 1000001)).toBe(1000001000000);
  });
});
