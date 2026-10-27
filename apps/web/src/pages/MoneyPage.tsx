/** Money page: accounts, balances, transactions - precise minor-unit math. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type {
  Account,
  AccountType,
  BalanceSummary,
  MonthSummary,
  Transaction,
  TransactionPage,
  TransactionType,
} from "../types/api";

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "mpesa", label: "M-PESA" },
  { value: "bank", label: "Bank account" },
  { value: "wallet", label: "Other wallet" },
  { value: "custom", label: "Custom" },
];

export function MoneyPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"accounts" | "transaction">("accounts");
  const [error, setError] = useState<string | null>(null);

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/accounts"),
  });
  const summary = useQuery({
    queryKey: ["accounts-summary"],
    queryFn: () => api<BalanceSummary>("/api/accounts/summary"),
  });
  const txns = useQuery({
    queryKey: ["transactions"],
    queryFn: () => api<TransactionPage>("/api/transactions", {
      params: { page_size: 15 },
    }),
  });
  const month = useQuery({
    queryKey: ["month-summary"],
    queryFn: () => api<MonthSummary>("/api/transactions/summary/month"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
    queryClient.invalidateQueries({ queryKey: ["accounts-summary"] });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
    queryClient.invalidateQueries({ queryKey: ["month-summary"] });
  };

  const accountForm = useForm<{ name: string; type: AccountType }>();
  const createAccount = useMutation({
    mutationFn: (v: { name: string; type: AccountType }) =>
      api<Account>("/api/accounts", { body: v }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  const initialize = useMutation({
    mutationFn: (v: { account_id: string; balance: string }) =>
      api(`/api/accounts/${v.account_id}/initialize`, {
        body: { balance_minor: Math.round(Number(v.balance) * 100) },
      }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  interface TxnValues {
    type: TransactionType;
    amount: string;
    account_id: string;
    category: string;
  }
  const txnForm = useForm<TxnValues>({ defaultValues: { type: "expense" } });
  const txnType = txnForm.watch("type");
  const isExpense = txnType !== "income";
  const createTxn = useMutation({
    mutationFn: (v: TxnValues) => {
      const amount_minor = Math.round(Number(v.amount) * 100);
      if (!Number.isFinite(amount_minor) || amount_minor <= 0) {
        throw new Error("Enter a positive amount");
      }
      return api<Transaction>("/api/transactions", {
        body: {
          type: v.type,
          amount_minor,
          occurred_on: new Date().toISOString().slice(0, 10),
          category: v.category || null,
          account_id: v.account_id ? Number(v.account_id) : null,
          idempotency_key: crypto.randomUUID(),
        },
      });
    },
    onSuccess: () => {
      refresh();
      txnForm.reset();
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const reverse = useMutation({
    mutationFn: (id: number) => api(`/api/transactions/${id}/reverse`, { body: {} }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  return (
    <div>
      <h1>Money</h1>
      {error && <p className="error-banner" role="alert">{error}</p>}

      <div className="stat-grid">
        <div className="card stat-card">
          <span className="stat-label">Available (recorded)</span>
          <strong>
            {summary.data?.total_available_minor === null ||
            summary.data?.total_available_minor === undefined
              ? "Not initialized"
              : formatMinor(summary.data.total_available_minor)}
          </strong>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Income this month</span>
          <strong>{formatMinor(month.data?.income_minor)}</strong>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Expenses this month</span>
          <strong>{formatMinor(month.data?.expense_minor)}</strong>
        </div>
      </div>
      <p className="muted">
        Balances are manually recorded, not bank-verified. Transfers are never
        counted as income or expenses.
      </p>

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "accounts"}
          className={tab === "accounts" ? "tab-btn active" : "tab-btn"}
          onClick={() => setTab("accounts")}
        >
          Accounts
        </button>
        <button
          role="tab"
          aria-selected={tab === "transaction"}
          className={tab === "transaction" ? "tab-btn active" : "tab-btn"}
          onClick={() => setTab("transaction")}
        >
          Add Transaction
        </button>
      </div>

      {tab === "accounts" && (
        <>
          <div className="card">
            <h2>Add account</h2>
            <form
              className="btn-row"
              onSubmit={accountForm.handleSubmit((v) => createAccount.mutate(v))}
            >
              <input placeholder="e.g. M-PESA" {...accountForm.register("name", { required: true })} />
              <select {...accountForm.register("type")}>
                {ACCOUNT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <button className="btn primary" type="submit" disabled={createAccount.isPending}>
                <Plus size={16} aria-hidden /> Add Account
              </button>
            </form>
          </div>
          <div className="card">
            <h2>Accounts</h2>
            {(accounts.data ?? []).map((a) => (
              <div key={a.id} className="list-row">
                <span>
                  <strong>{a.name}</strong>{" "}
                  <span className="badge">{a.type}</span>{" "}
                  {!a.initialized && <span className="badge warn">balance unknown</span>}
                </span>
                <span>
                  {formatMinor(a.balance_minor)}{" "}
                  {!a.initialized && (
                    <button
                      className="btn ghost small"
                      onClick={() => {
                        const input = window.prompt(
                          `Set starting balance for ${a.name} (KES):`,
                        );
                        if (input !== null) {
                          initialize.mutate({ account_id: String(a.id), balance: input });
                        }
                      }}
                    >
                      Initialize
                    </button>
                  )}
                </span>
              </div>
            ))}
            {accounts.data?.length === 0 && <p className="muted">No accounts yet.</p>}
          </div>
          <div className="card">
            <h2>Recent transactions</h2>
            {(txns.data?.transactions ?? []).map((t) => (
              <div key={t.id} className="list-row">
                <span>
                  <span className={`badge ${t.type}`}>{t.type}</span>{" "}
                  {t.description ?? t.category ?? "-"}
                  {t.reversed && <span className="badge warn"> reversed</span>}
                  {t.reversal_of_id && <span className="muted"> (correction)</span>}
                </span>
                <span>
                  {t.type === "expense" ? "-" : t.type === "income" ? "+" : "↔ "}
                  {formatMinor(t.amount_minor, t.currency)}{" "}
                  {!t.reversed && !t.reversal_of_id && (
                    <button
                      className="btn ghost small"
                      onClick={() => reverse.mutate(t.id)}
                      title="Record a correction"
                    >
                      Reverse
                    </button>
                  )}
                </span>
              </div>
            ))}
            {txns.data?.transactions.length === 0 && (
              <p className="muted">No transactions recorded.</p>
            )}
          </div>
        </>
      )}

      {tab === "transaction" && (
        <form
          className="card auth-form"
          onSubmit={txnForm.handleSubmit((v) => createTxn.mutate(v))}
        >
          <h2>Add transaction</h2>
          <label>
            Money
            <select {...txnForm.register("type")}>
              <option value="expense">Removed (I spent it)</option>
              <option value="income">Added (I received it)</option>
            </select>
          </label>
          <label>
            Amount (KES)
            <input type="number" min="0.01" step="0.01" {...txnForm.register("amount", { required: true })} />
          </label>
          <label>
            {isExpense ? "Paid from account" : "Added to account"}
            <select {...txnForm.register("account_id", { required: true })}>
              <option value="">Select…</option>
              {(accounts.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </label>
          <label>
            {isExpense ? "What was it used for?" : "Source"}
            <input
              placeholder={isExpense ? "e.g. food, fees, transport" : "e.g. salary, gift"}
              {...txnForm.register("category")}
            />
          </label>
          <button className="btn primary" type="submit" disabled={createTxn.isPending}>
            Save Transaction
          </button>
        </form>
      )}
    </div>
  );
}
