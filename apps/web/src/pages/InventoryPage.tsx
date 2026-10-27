/** Inventory page: real records, shortage math and dynamic images. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus, Minus } from "lucide-react";
import { api } from "../services/api";
import { shortageLabel } from "../lib/money";
import { AssetImage } from "../features/assets/AssetImage";
import type {
  InventoryCategory,
  InventoryItem,
  ItemPage,
  ScanStatus,
} from "../types/api";

interface NewItemForm {
  name: string;
  category_id: number;
  quantity_owned: number;
  target_quantity: string;
  estimated_unit_cost: string; // major units; converted to minor
  price_source: string;
  price_verified: boolean;
}

/** How a recorded price is described, so an estimate never reads as a fact. */
function priceLabel(item: InventoryItem): string {
  if (item.estimated_unit_cost_minor === null) return "";
  const parts = [item.price_verified ? "verified" : "estimate"];
  if (item.price_source) parts.push(item.price_source);
  return ` (${parts.join(" · ")})`;
}

export function InventoryPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  const categories = useQuery({
    queryKey: ["inventory-categories"],
    queryFn: () => api<InventoryCategory[]>("/api/inventory/categories"),
  });
  const items = useQuery({
    queryKey: ["inventory-items"],
    queryFn: () => api<ItemPage>("/api/inventory/items"),
  });

  const { register, handleSubmit, reset, watch } = useForm<NewItemForm>({
    defaultValues: {
      quantity_owned: 0,
      estimated_unit_cost: "",
      price_source: "",
      price_verified: false,
    },
  });
  // A source or a verification tick only mean something about a price that
  // exists, so the two extra fields stay inert until one is typed.
  const hasCost = (watch("estimated_unit_cost") ?? "").trim() !== "";

  const createItem = useMutation({
    mutationFn: (v: NewItemForm) => {
      const target = v.target_quantity ? Number(v.target_quantity) : null;
      const costMajor = v.estimated_unit_cost ? Number(v.estimated_unit_cost) : null;
      if (costMajor !== null && !Number.isFinite(costMajor)) {
        throw new Error("Unit cost must be a number");
      }
      const source = v.price_source.trim();
      return api<InventoryItem>("/api/inventory/items", {
        body: {
          name: v.name,
          category_id: Number(v.category_id),
          quantity_owned: Number(v.quantity_owned) || 0,
          target_quantity: target,
          estimated_unit_cost_minor:
            costMajor !== null ? Math.round(costMajor * 100) : null,
          price_verified: costMajor !== null ? v.price_verified : false,
          price_source: costMajor !== null && source ? source : null,
        },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
      reset();
      setShowForm(false);
      setFormError(null);
    },
    onError: (e) => setFormError(e.message),
  });

  const adjust = useMutation({
    mutationFn: ({ id, change }: { id: number; change: number }) =>
      api<InventoryItem>(`/api/inventory/items/${id}/adjust-quantity`, {
        body: { change },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["inventory-items"] }),
    onError: (e) => setFormError(e.message),
  });

  const scan = useMutation({
    mutationFn: async () => {
      await api("/api/assets/scan", { body: {} });
      let status = await api<ScanStatus>("/api/assets/scan/status");
      for (let i = 0; i < 50 && status.state === "running"; i++) {
        await new Promise((r) => setTimeout(r, 300));
        status = await api<ScanStatus>("/api/assets/scan/status");
      }
      return status;
    },
    onSuccess: (s) =>
      setScanMsg(
        s.state === "completed"
          ? `Scan complete: ${s.new} new, ${s.updated} updated, ${s.corrupted} rejected`
          : `Scan failed: ${s.error ?? "unknown error"}`,
      ),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Inventory</h1>
        <button className="btn primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={16} aria-hidden /> Add Item
        </button>
      </div>

      <div className="card scan-card">
        <span>
          Image library: pictures placed in <code>assets/</code> folders are
          discovered automatically - filenames are never changed.
        </span>
        <button className="btn" onClick={() => scan.mutate()} disabled={scan.isPending}>
          {scan.isPending ? "Scanning…" : "Rescan library"}
        </button>
        {scanMsg && <p className="muted">{scanMsg}</p>}
      </div>

      {showForm && (
        <form
          className="card auth-form"
          onSubmit={handleSubmit((v) => createItem.mutate(v))}
        >
          <h2>New item</h2>
          {formError && <p className="error-banner">{formError}</p>}
          <label>
            Name
            <input {...register("name", { required: true })} />
          </label>
          <label>
            Category
            <select {...register("category_id", { required: true })}>
              {(categories.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>
          <div className="btn-row">
            <label>
              Quantity owned
              <input type="number" min={0} {...register("quantity_owned")} />
            </label>
            <label>
              Target (optional)
              <input type="number" min={0} {...register("target_quantity")} />
            </label>
            <label>
              Unit cost, KES (optional)
              <input type="number" min={0} step="0.01" {...register("estimated_unit_cost")} />
            </label>
          </div>
          {/* LifeSmart fetches no price from anywhere: where a figure came from
              is part of the record, and an unchecked figure stays an estimate. */}
          <label>
            Where the price came from (optional)
            <input
              placeholder="Town shop, seller, quote…"
              maxLength={120}
              disabled={!hasCost}
              {...register("price_source")}
            />
          </label>
          <label className="field-inline">
            <input type="checkbox" disabled={!hasCost} {...register("price_verified")} />
            I checked this price myself
          </label>
          {!hasCost && (
            <p className="muted">
              Leave the cost empty for something you still need to price - it is
              kept unknown, never zero.
            </p>
          )}
          <button className="btn primary" type="submit" disabled={createItem.isPending}>
            Save Item
          </button>
        </form>
      )}

      {items.isPending && <p className="muted">Loading…</p>}
      {items.error && (
        <p className="error-banner">Could not load inventory: {items.error.message}</p>
      )}
      {items.data && items.data.items.length === 0 && !showForm && (
        <div className="card empty-state">
          <p>No items recorded yet. Add what you own and what you want -
          shortages will be calculated automatically.</p>
        </div>
      )}
      <div className="item-grid">
        {(items.data?.items ?? []).map((item) => (
          <div key={item.id} className="card item-card">
            {/* Category derived from item, image chosen by the asset API. */}
            <AssetImage
              category={item.category_name?.toLowerCase().replace(/\s+/g, "-")}
              seed={item.id}
              size={56}
              alt={item.name}
            />
            <div className="item-info">
              <strong>{item.name}</strong>
              <span className="muted">{item.category_name}</span>
              <span>
                {item.quantity_owned}
                {item.target_quantity !== null ? ` / ${item.target_quantity}` : ""} owned
              </span>
              {item.shortage > 0 && (
                <span className="badge warn">short by {item.shortage}</span>
              )}
              <span className="muted">
                To target: {item.target_quantity === null ? "no target set" :
                  shortageLabel(item.estimated_cost_to_target_minor, item.price_needed)}
                {priceLabel(item)}
              </span>
            </div>
            <div className="qty-controls">
              <button
                className="icon-btn"
                aria-label={`Decrease ${item.name} quantity`}
                onClick={() => adjust.mutate({ id: item.id, change: -1 })}
              >
                <Minus size={16} />
              </button>
              <button
                className="icon-btn"
                aria-label={`Increase ${item.name} quantity`}
                onClick={() => adjust.mutate({ id: item.id, change: 1 })}
              >
                <Plus size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
