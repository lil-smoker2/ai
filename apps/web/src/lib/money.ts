/** Money helpers - integer minor units only, formatted for display. */

export function formatMinor(
  minor: number | null | undefined,
  currency = "KES",
): string {
  if (minor === null || minor === undefined) return "—";
  const major = minor / 100;
  return `${currency} ${major.toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Display rule from the spec: unknown prices show "Price needed", never $0. */
export function shortageLabel(
  estimatedCostMinor: number | null,
  priceNeeded: boolean,
): string {
  if (priceNeeded) return "Price needed";
  if (estimatedCostMinor === null) return "—";
  return formatMinor(estimatedCostMinor);
}

/** Spec 4.4: estimated_total = item_cost + delivery + transport + fees.
 * Minor units are integers, so the sum stays exact - no float rounding.
 * A missing unit price has no total (null), never a fake zero. */
export function lineTotalMinor(
  quantityNeeded: number,
  unitCostMinor: number | null,
  deliveryMinor = 0,
  transportMinor = 0,
  feesMinor = 0,
): number | null {
  if (unitCostMinor === null) return null;
  return (
    quantityNeeded * unitCostMinor + deliveryMinor + transportMinor + feesMinor
  );
}
