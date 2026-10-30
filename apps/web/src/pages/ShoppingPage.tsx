/** Shopping page: lists, planned lines with cost estimates and the
 * confirmed purchase workflow. Totals come from saved records; unknown
 * prices show "Price needed" and purchases only exist once confirmed. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus, ShoppingCart, Wand2 } from "lucide-react";
import { api } from "../services/api";
import { formatMinor, shortageLabel } from "../lib/money";
import type {
  Account,
  PurchaseRecord,
  ShoppingItem,
  ShoppingList,
  ShoppingListPage,
} from "../types/api";

interface NewListForm {
  name: string;
}

interface NewItemForm {
  name: string;
  category: string;
  subcategory: string;
  quantity_needed: number;
  unit_cost: string; // major units; converted to minor
  seller: string;
  delivery: string;
  transport: string;
}

interface PurchaseForm {
  quantity: number;
  amount_paid: string; // major units
  occurred_on: string;
  account_id: string;
  add_to_inventory: boolean;
}

const toMinor = (v: string) =>
  v.trim() === "" ? null : Math.round(Number(v) * 100);

export function ShoppingPage() {
  const queryClient = useQueryClient();
  const [listId, setListId] = useState<number | null>(null);
  const [showListForm, setShowListForm] = useState(false);
  const [showItemForm, setShowItemForm] = useState(false);
  const [buyingItem, setBuyingItem] = useState<ShoppingItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const lists = useQuery({
    queryKey: ["shopping-lists"],
    queryFn: () => api<ShoppingListPage>("/api/shopping/lists"),
  });
  const activeListId = listId ?? lists.data?.lists[0]?.id ?? null;

  const items = useQuery({
    queryKey: ["shopping-items", activeListId],
    queryFn: () =>
      api<ShoppingItem[]>(`/api/shopping/lists/${activeListId}/items`),
    enabled: activeListId !== null,
  });
  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });
  const purchases = useQuery({
    queryKey: ["shopping-purchases", buyingItem?.id],
    queryFn: () =>
      api<PurchaseRecord[]>(`/api/shopping/items/${buyingItem?.id}/purchases`),
    enabled: buyingItem !== null,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["shopping-lists"] });
    queryClient.invalidateQueries({ queryKey: ["shopping-items"] });
    queryClient.invalidateQueries({ queryKey: ["shopping-purchases"] });
    // Purchases move inventory, money and goal figures - refresh those too.
    queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
    queryClient.invalidateQueries({ queryKey: ["goals"] });
  };

  const listForm = useForm<NewListForm>();
  const createList = useMutation({
    mutationFn: (v: NewListForm) =>
      api<ShoppingList>("/api/shopping/lists", { body: { name: v.name } }),
    onSuccess: (lst) => {
      setListId(lst.id);
      setShowListForm(false);
      listForm.reset();
      invalidate();
    },
    onError: (e) => setError(e.message),
  });

  const itemForm = useForm<NewItemForm>({ defaultValues: { quantity_needed: 1 } });
  const createItem = useMutation({
    mutationFn: (v: NewItemForm) => {
      const unit = toMinor(v.unit_cost);
      if (unit !== null && !Number.isFinite(unit)) throw new Error("Unit cost must be a number");
      return api<ShoppingItem>(`/api/shopping/lists/${activeListId}/items`, {
        body: {
          name: v.name,
          category: v.category || null,
          subcategory: v.subcategory || null,
          quantity_needed: Number(v.quantity_needed) || 1,
          estimated_unit_cost_minor: unit,
          seller: v.seller || null,
          delivery_cost_minor: toMinor(v.delivery) ?? 0,
          transport_cost_minor: toMinor(v.transport) ?? 0,
        },
      });
    },
    onSuccess: () => {
      setShowItemForm(false);
      itemForm.reset();
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e.message),
  });

  const generate = useMutation({
    mutationFn: () =>
      api<ShoppingItem[]>(
        `/api/shopping/lists/${activeListId}/generate-from-shortages`,
        { body: {} },
      ),
    onSuccess: (created) => {
      setNotice(
        created.length > 0
          ? `Added ${created.length} line${created.length > 1 ? "s" : ""} from inventory shortages`
          : "No shortages to add - every item is at its target",
      );
      invalidate();
    },
    onError: (e) => setError(e.message),
  });

  const purchaseForm = useForm<PurchaseForm>();
  const recordPurchase = useMutation({
    mutationFn: (v: PurchaseForm) => {
      const amount = toMinor(v.amount_paid);
      if (amount === null || amount <= 0) throw new Error("Amount paid is required");
      return api<PurchaseRecord>(`/api/shopping/items/${buyingItem!.id}/purchase`, {
        body: {
          quantity: Number(v.quantity),
          amount_paid_minor: amount,
          occurred_on: v.occurred_on || undefined,
          account_id: v.account_id ? Number(v.account_id) : null,
          add_to_inventory: v.add_to_inventory,
          // One key per attempt: replays update nothing twice, retries are safe.
          idempotency_key: crypto.randomUUID(),
        },
      });
    },
    onSuccess: (record) => {
      setBuyingItem(null);
      purchaseForm.reset();
      setNotice(
        `Purchase recorded: ${formatMinor(record.amount_paid_minor)}` +
          (record.added_inventory_quantity > 0
            ? `, ${record.added_inventory_quantity} added to inventory`
            : ""),
      );
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e.message),
  });

  const openPurchase = (item: ShoppingItem) => {
    setError(null);
    setBuyingItem(item);
    purchaseForm.reset({
      quantity: item.quantity_needed,
      amount_paid: item.estimated_total_minor
        ? (item.estimated_total_minor / 100).toFixed(2)
        : "",
      add_to_inventory: item.inventory_item_id !== null,
    });
  };

  return (
    <div>
      <div className="page-header">
        <h1>Shopping</h1>
        <div className="btn-row">
          <button className="btn" onClick={() => setShowListForm((v) => !v)}>
            <Plus size={16} aria-hidden /> New List
          </button>
          {activeListId !== null && (
            <>
              <button className="btn" onClick={() => generate.mutate()} disabled={generate.isPending}>
                <Wand2 size={16} aria-hidden /> From Shortages
              </button>
              <button className="btn primary" onClick={() => setShowItemForm((v) => !v)}>
                <Plus size={16} aria-hidden /> Add Item
              </button>
            </>
          )}
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}
      {notice && <p className="muted">{notice}</p>}

      {showListForm && (
        <form className="card auth-form" onSubmit={listForm.handleSubmit((v) => createList.mutate(v))}>
          <h2>New shopping list</h2>
          <label>
            Name
            <input {...listForm.register("name", { required: true })} />
          </label>
          <button className="btn primary" type="submit" disabled={createList.isPending}>
            Create List
          </button>
        </form>
      )}

      {(lists.data?.lists.length ?? 0) > 0 && (
        <label className="field-inline">
          List
          <select
            value={activeListId ?? ""}
            onChange={(e) => setListId(Number(e.target.value))}
          >
            {lists.data?.lists.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </label>
      )}

      {showItemForm && activeListId !== null && (
        <form className="card auth-form" onSubmit={itemForm.handleSubmit((v) => createItem.mutate(v))}>
          <h2>Add to list</h2>
          <label>
            Item
            <input {...itemForm.register("name", { required: true })} />
          </label>
          <div className="btn-row">
            <label>
              Category
              <select {...itemForm.register("category")}>
                <option value="">Select...</option>
                <option value="food">Food</option>
                <option value="drinks">Drinks</option>
                <option value="clothing">Clothing</option>
                <option value="household">Household</option>
                <option value="electronics">Electronics</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              Subcategory
              <input {...itemForm.register("subcategory")} placeholder="e.g., vegetables, shirts" />
            </label>
            <label>
              Quantity needed
              <input type="number" min={1} {...itemForm.register("quantity_needed")} />
            </label>
            <label>
              Unit cost, KES (blank = unknown)
              <input type="number" min={0} step="0.01" {...itemForm.register("unit_cost")} />
            </label>
            <label>
              Seller (optional)
              <input {...itemForm.register("seller")} />
            </label>
            <label>
              Delivery, KES
              <input type="number" min={0} step="0.01" {...itemForm.register("delivery")} />
            </label>
            <label>
              Transport, KES
              <input type="number" min={0} step="0.01" {...itemForm.register("transport")} />
            </label>
          </div>
          <button className="btn primary" type="submit" disabled={createItem.isPending}>
            Save Item
          </button>
        </form>
      )}

      {items.isPending && <p className="muted">Loading…</p>}
      {activeListId === null && !lists.isPending && (
        <div className="card empty-state">
          <p>No shopping lists yet. Create one, or generate lines straight from
          your inventory shortages.</p>
        </div>
      )}
      {items.data?.length === 0 && (
        <div className="card empty-state">
          <p>This list is empty. Use “From Shortages” to pull in what you are
          missing, or add items manually.</p>
        </div>
      )}

      <div className="item-grid">
        {(items.data ?? []).map((item) => (
          <div key={item.id} className="card item-card">
            <div className="item-info">
              <strong>{item.name}</strong>
              <span className="muted">need {item.quantity_needed}</span>
              <span className="muted">
                Total: {shortageLabel(item.estimated_total_minor, item.price_needed)}
                {item.estimated_unit_cost_minor !== null && item.price_source === "estimate"
                  ? " (estimate)"
                  : ""}
              </span>
              {item.seller && <span className="muted">Seller: {item.seller}</span>}
              {item.price_source === "verified" && (
                <span className="badge">verified price</span>
              )}
              {item.status === "purchased" ? (
                <span className="badge">purchased</span>
              ) : (
                <button className="btn primary" onClick={() => openPurchase(item)}>
                  <ShoppingCart size={16} aria-hidden /> Record Purchase
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {buyingItem && (
        <div className="more-sheet-backdrop" onClick={() => setBuyingItem(null)}>
          <div
            className="card auth-form"
            role="dialog"
            aria-label={`Record purchase of ${buyingItem.name}`}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Record purchase: {buyingItem.name}</h2>
            <p className="muted">
              Confirm what you actually paid. LifeSmart only records purchases
              you confirm - nothing is marked bought automatically.
            </p>
            <form onSubmit={purchaseForm.handleSubmit((v) => recordPurchase.mutate(v))}>
              <div className="btn-row">
                <label>
                  Quantity
                  <input type="number" min={1} {...purchaseForm.register("quantity")} />
                </label>
                <label>
                  Amount paid, KES
                  <input type="number" min={0} step="0.01" {...purchaseForm.register("amount_paid", { required: true })} />
                </label>
                <label>
                  Date
                  <input type="date" {...purchaseForm.register("occurred_on")} />
                </label>
              </div>
              <label>
                Funding account (optional)
                <select {...purchaseForm.register("account_id")}>
                  <option value="">Not allocated</option>
                  {(accounts.data ?? []).map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </label>
              {buyingItem.inventory_item_id !== null && (
                <label className="field-inline">
                  <input type="checkbox" {...purchaseForm.register("add_to_inventory")} />
                  Add to inventory quantity
                </label>
              )}
              {(purchases.data?.length ?? 0) > 0 && (
                <p className="muted">
                  {purchases.data!.length} purchase(s) already recorded for this line.
                </p>
              )}
              <button className="btn primary" type="submit" disabled={recordPurchase.isPending}>
                {recordPurchase.isPending ? "Recording…" : "Confirm Purchase"}
              </button>{" "}
              <button className="btn" type="button" onClick={() => setBuyingItem(null)}>
                Cancel
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
