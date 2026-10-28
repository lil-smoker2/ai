/** Money page: accounts, balances, transactions - precise minor-unit math.
 *
 * An account is what the person tells us they hold. The M-PESA number and the
 * bank details are their own notes about which account a balance belongs to:
 * this app has no M-PESA or bank connection, so nothing here is read from an
 * institution, and recording a number never makes a balance verified.
 *
 * A mistake is corrected in place. Changing what an account is called, or which
 * kind it is, leaves its balance and every transaction recorded against it
 * exactly where they were.
 */
import { useEffect, useState } from "react";
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

const ACCOUNT_TYPES: { value: AccountType; label: string; hint: string }[] = [
  { value: "cash", label: "Cash", hint: "Money you carry. No number goes with it." },
  {
    value: "mpesa",
    label: "M-PESA",
    hint: "Give the phone number the wallet is held on. M-Shwari is a separate pocket on the same line, so it is recorded as an account of its own with its own balance.",
  },
  {
    value: "mshwari",
    label: "M-Shwari",
    hint: "M-Shwari savings sit on an M-PESA line but hold their own money, so they get their own account.",
  },
  {
    value: "bank",
    label: "Bank account",
    hint: "Which bank, and the account number you were given.",
  },
  { value: "wallet", label: "Other wallet", hint: "Any other place money sits that you track by hand." },
  { value: "custom", label: "Custom", hint: "Anything else you want to keep a balance for." },
];

const TYPE_LABEL = new Map(ACCOUNT_TYPES.map((t) => [t.value, t.label]));
const TYPE_HINT = new Map(ACCOUNT_TYPES.map((t) => [t.value, t.hint]));

/** The kinds of account that are a Safaricom line rather than a bank or a wallet. */
const PHONE_KINDS: AccountType[] = ["mpesa", "mshwari"];

/** A Safaricom number as it was typed, in the one form we keep, or null. */
export function mpesaNumber(raw: string): string | null {
  const compact = raw.replace(/[\s()-]/g, "");
  return /^(?:\+?254|0)[17]\d{8}$/.test(compact) ? `+254${compact.slice(-9)}` : null;
}

// Digits and at most two decimal places, nothing else: no hex, no exponent,
// no half a pesa.
const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;

/** "1,200.50" as a person writes it -> 120050 minor units, or null.
 * Built from the digits, so no floating point rounding can shift the amount. */
export function toMinor(raw: string): number | null {
  const cleaned = raw.trim().replace(/[,\s]/g, "");
  if (!AMOUNT.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

/** Left empty is allowed; anything typed must be a plain amount. */
const amountOrEmpty = (v: string) =>
  v.trim() === "" || toMinor(v) !== null || "Enter an amount like 1200 or 1200.50";

/** A transaction has to move something: not empty, not zero. */
const positiveAmount = (v: string) =>
  (toMinor(v) ?? 0) > 0 || "Enter an amount bigger than zero, like 150 or 150.50";

// Shared by the Add account card, the quick account inside the transaction
// form and the editor on an account row, so the same question cannot be worded
// or judged two different ways.
const accountNameRule = { required: "Give the account a name" };
const mpesaNumberRule = {
  required: "Which phone number holds this account?",
  validate: (v: string) =>
    mpesaNumber(v) !== null || "Use a Safaricom number, like 0712 345 678 or +254712345678",
};
const bankNameRule = {
  required: "Which bank is it?",
  validate: (v: string) => v.trim().length >= 2 || "Give the bank's name",
};
const accountNumberRule = {
  required: "What is the account number?",
  validate: (v: string) =>
    /^[0-9A-Za-z-]{4,30}$/.test(v.replace(/\s+/g, "")) || "4-30 digits, letters or dashes",
};

/** Picker entries that are not accounts yet, but ask for one. */
const NEW_BANK = "__new_bank";
const NEW_WALLET = "__new_wallet";

/** The account a transaction needs but the person has not added: named here,
 * then used by this same transaction. M-PESA is deliberately absent - that
 * account is a phone line, and the number has to be recorded with it, so it is
 * added on the Accounts tab where that field lives. */
interface QuickAccountValues {
  name: string;
  bank_name: string;
  account_number: string;
  balance: string;
}

const EMPTY_QUICK: QuickAccountValues = {
  name: "",
  bank_name: "",
  account_number: "",
  balance: "",
};

/** The identifier line under an account name, or empty when it has none. */
function accountDetail(a: Account): string {
  if (a.type === "bank") {
    return [a.bank_name, a.account_number && `A/C ${a.account_number}`]
      .filter(Boolean)
      .join(" · ");
  }
  return a.mpesa_number ?? "";
}

interface AccountValues {
  name: string;
  type: AccountType;
  mpesa_number: string;
  bank_name: string;
  account_number: string;
  balance: string;
  mshwari_balance: string;
}

const EMPTY_ACCOUNT: AccountValues = {
  name: "",
  type: "cash",
  mpesa_number: "",
  bank_name: "",
  account_number: "",
  balance: "",
  mshwari_balance: "",
};

/** What an account is called and how the money is held. No amount belongs here:
 * a balance is set when the account is created or initialized, never by a fix
 * to its name or kind. */
interface EditAccountValues {
  name: string;
  type: AccountType;
  mpesa_number: string;
  bank_name: string;
  account_number: string;
}

const BLANK_EDIT: EditAccountValues = {
  name: "",
  type: "cash",
  mpesa_number: "",
  bank_name: "",
  account_number: "",
};

/** The details as the API wants them: only what this kind of account really
 * has, the rest sent as null. The server drops them too, so a phone number
 * never survives on an account that has become a bank. */
function accountDetails(v: EditAccountValues) {
  return {
    name: v.name.trim(),
    type: v.type,
    mpesa_number: PHONE_KINDS.includes(v.type) ? mpesaNumber(v.mpesa_number) : null,
    bank_name: v.type === "bank" ? v.bank_name.trim() : null,
    account_number: v.type === "bank" ? v.account_number.replace(/\s+/g, "") : null,
  };
}

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

  const accountForm = useForm<AccountValues>({ defaultValues: EMPTY_ACCOUNT });
  const {
    formState: { errors: acctErrors },
  } = accountForm;
  const kind = accountForm.watch("type");
  const needsPhone = PHONE_KINDS.includes(kind);
  const isBank = kind === "bank";

  const createAccount = useMutation({
    mutationFn: async (v: AccountValues) => {
      const primary = await api<Account>("/api/accounts", {
        body: {
          ...accountDetails(v),
          // Left empty means not recorded yet, which is kept as unknown rather
          // than written down as a zero balance.
          balance_minor: v.balance.trim() === "" ? null : toMinor(v.balance),
        },
      });
      // M-Shwari is a second pocket on the same line, so it becomes its own
      // account: spending from M-PESA must not move M-Shwari money.
      if (v.type === "mpesa" && v.mshwari_balance.trim() !== "") {
        const savings = toMinor(v.mshwari_balance);
        if (savings === null) {
          throw new Error(
            `${primary.name} was saved. For M-Shwari, enter an amount like 5000 or 5000.50.`,
          );
        }
        try {
          await api<Account>("/api/accounts", {
            body: {
              name: "M-Shwari",
              type: "mshwari",
              mpesa_number: mpesaNumber(v.mpesa_number),
              balance_minor: savings,
            },
          });
        } catch (e) {
          // Say which half got saved. Someone who sees this knows M-PESA is
          // there and M-Shwari still needs adding.
          const reason = e instanceof Error ? e.message : String(e);
          throw new Error(`${primary.name} was saved, but M-Shwari was not: ${reason}`);
        }
      }
      return primary;
    },
    onSuccess: () => {
      accountForm.reset(EMPTY_ACCOUNT);
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  // One account can be initialized at a time, and the amount is typed right in
  // the list instead of a browser popup that can be blocked or misread.
  const [initFor, setInitFor] = useState<number | null>(null);
  const [initAmount, setInitAmount] = useState("");
  const initialize = useMutation({
    mutationFn: (v: { accountId: number; balance: string }) => {
      const minor = toMinor(v.balance);
      if (minor === null) {
        throw new Error("Enter the balance as an amount, like 1200 or 1200.50");
      }
      return api(`/api/accounts/${v.accountId}/initialize`, {
        body: { balance_minor: minor },
      });
    },
    onSuccess: () => {
      setInitFor(null);
      setInitAmount("");
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  // An account can be wrong in a way that has nothing to do with its money: two
  // rows called the same thing, or M-PESA typed where a bank was meant. Fixing
  // that used to mean deleting the account, which the app does not allow once
  // transactions name it, so the mistake lived forever. Only one row is open at
  // a time, and the balance is not one of the fields offered.
  const editForm = useForm<EditAccountValues>({ defaultValues: BLANK_EDIT });
  const {
    formState: { errors: editErrors },
  } = editForm;
  const [editingId, setEditingId] = useState<number | null>(null);
  const editKind = editForm.watch("type");
  const editNeedsPhone = PHONE_KINDS.includes(editKind);
  const editIsBank = editKind === "bank";

  const startEdit = (a: Account) => {
    setInitFor(null);
    setInitAmount("");
    setError(null);
    editForm.reset({
      name: a.name,
      type: a.type,
      mpesa_number: a.mpesa_number ?? "",
      bank_name: a.bank_name ?? "",
      account_number: a.account_number ?? "",
    });
    setEditingId(a.id);
  };

  const updateAccount = useMutation({
    mutationFn: (v: { accountId: number; values: EditAccountValues }) =>
      api<Account>(`/api/accounts/${v.accountId}`, {
        method: "PATCH",
        body: accountDetails(v.values),
      }),
    onSuccess: () => {
      setEditingId(null);
      editForm.reset(BLANK_EDIT);
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  interface TxnValues {
    type: TransactionType;
    amount: string;
    account_id: string;
    category: string;
  }
  const txnForm = useForm<TxnValues>({ defaultValues: { type: "expense" } });
  const {
    formState: { errors: txnErrors },
  } = txnForm;
  const txnType = txnForm.watch("type");
  const isExpense = txnType !== "income";
  const createTxn = useMutation({
    mutationFn: (v: TxnValues) => {
      const amount_minor = toMinor(v.amount);
      if (amount_minor === null || amount_minor <= 0) {
        throw new Error("Enter a positive amount, like 150 or 150.50");
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

  // A transaction can need an account that does not exist yet: money spent at a
  // bank, or kept in another wallet. Rather than sending the person off to the
  // Accounts tab and back, the picker offers to add one, and this same
  // transaction then uses it.
  const quickForm = useForm<QuickAccountValues>({ defaultValues: EMPTY_QUICK });
  const {
    formState: { errors: quickErrors },
  } = quickForm;
  // The panel is derived from what the picker holds, so it can never disagree
  // with it: the entry stays open until a real account is chosen.
  const picked = txnForm.watch("account_id") ?? "";
  const quickKind: AccountType | null =
    picked === NEW_BANK ? "bank" : picked === NEW_WALLET ? "wallet" : null;
  const [pendingQuickId, setPendingQuickId] = useState<number | null>(null);

  const createQuickAccount = useMutation({
    mutationFn: (v: QuickAccountValues) => {
      const type = quickKind ?? "wallet";
      return api<Account>("/api/accounts", {
        body: {
          name: v.name.trim(),
          type,
          // Neither of these kinds carries a phone number, so none is claimed.
          mpesa_number: null,
          bank_name: type === "bank" ? v.bank_name.trim() : null,
          account_number: type === "bank" ? v.account_number.replace(/\s+/g, "") : null,
          balance_minor: v.balance.trim() === "" ? null : toMinor(v.balance),
        },
      });
    },
    onSuccess: (created) => {
      quickForm.reset(EMPTY_QUICK);
      setPendingQuickId(created.id);
      setError(null);
      refresh();
    },
    onError: (e) => setError(e.message),
  });

  // A select cannot be pointed at an option it does not hold yet, so the new
  // account is chosen once the list has come back with it.
  useEffect(() => {
    if (pendingQuickId === null) return;
    if ((accounts.data ?? []).some((a) => a.id === pendingQuickId)) {
      txnForm.setValue("account_id", String(pendingQuickId));
      setPendingQuickId(null);
    }
  }, [accounts.data, pendingQuickId, txnForm]);

  const cancelQuick = () => {
    quickForm.reset(EMPTY_QUICK);
    txnForm.setValue("account_id", "");
  };

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
        counted as income or expenses. An M-PESA number or bank detail is your
        own note about an account - LifeSmart connects to neither.
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
              className="auth-form"
              onSubmit={accountForm.handleSubmit((v) => createAccount.mutate(v))}
            >
              <div className="btn-row">
                <label>
                  Name
                  <input
                    placeholder={kind === "mpesa" ? "e.g. My M-PESA" : "e.g. Pocket cash"}
                    {...accountForm.register("name", accountNameRule)}
                  />
                  {acctErrors.name && (
                    <span className="field-error">{acctErrors.name.message}</span>
                  )}
                </label>
                <label>
                  Kind of account
                  <select {...accountForm.register("type")}>
                    {ACCOUNT_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="field-hint">{TYPE_HINT.get(kind)}</p>

              {/* The number a bank or an M-PESA line goes with, shown only for
                  the kinds of account that have one. */}
              {needsPhone && (
                <label>
                  M-PESA phone number
                  <input
                    inputMode="tel"
                    placeholder="0712 345 678"
                    {...accountForm.register("mpesa_number", mpesaNumberRule)}
                  />
                  {acctErrors.mpesa_number && (
                    <span className="field-error">{acctErrors.mpesa_number.message}</span>
                  )}
                </label>
              )}
              {isBank && (
                <div className="btn-row">
                  <label>
                    Which bank
                    <input
                      placeholder="e.g. Equity Bank"
                      {...accountForm.register("bank_name", bankNameRule)}
                    />
                    {acctErrors.bank_name && (
                      <span className="field-error">{acctErrors.bank_name.message}</span>
                    )}
                  </label>
                  <label>
                    Account number
                    <input
                      inputMode="numeric"
                      placeholder="as printed on your statement"
                      {...accountForm.register("account_number", accountNumberRule)}
                    />
                    {acctErrors.account_number && (
                      <span className="field-error">{acctErrors.account_number.message}</span>
                    )}
                  </label>
                </div>
              )}

              <div className="btn-row">
                <label>
                  {kind === "mpesa" ? "M-PESA balance (KES)" : "Starting balance (KES)"}
                  <input
                    type="text"
                    inputMode="decimal"
                    placeholder="1200 or 1200.50"
                    {...accountForm.register("balance", { validate: amountOrEmpty })}
                  />
                  {acctErrors.balance && (
                    <span className="field-error">{acctErrors.balance.message}</span>
                  )}
                </label>
                {kind === "mpesa" && (
                  <label>
                    M-Shwari balance (KES)
                    <input
                      type="text"
                      inputMode="decimal"
                      placeholder="saved on the same line"
                      {...accountForm.register("mshwari_balance", { validate: amountOrEmpty })}
                    />
                    {acctErrors.mshwari_balance && (
                      <span className="field-error">{acctErrors.mshwari_balance.message}</span>
                    )}
                  </label>
                )}
              </div>
              {kind === "mpesa" && (
                <p className="field-hint">
                  An M-Shwari balance typed here is saved as its own account, so
                  spending from M-PESA never moves M-Shwari money.
                </p>
              )}
              <p className="field-hint">
                Leave a balance empty for money you have not counted. It stays
                unknown instead of being written down as zero.
              </p>
              <button className="btn primary" type="submit" disabled={createAccount.isPending}>
                <Plus size={16} aria-hidden /> Add Account
              </button>
            </form>
          </div>
          <div className="card">
            <h2>Accounts</h2>
            {(accounts.data ?? []).map((a) => (
              <div key={a.id} className="account-item">
                <div className="list-row">
                  <span>
                    <strong>{a.name}</strong>{" "}
                    <span className="badge">{TYPE_LABEL.get(a.type) ?? a.type}</span>{" "}
                    {!a.initialized && <span className="badge warn">balance unknown</span>}
                    {accountDetail(a) && <span className="account-id">{accountDetail(a)}</span>}
                  </span>
                  <span>
                    {formatMinor(a.balance_minor)}{" "}
                    {!a.initialized &&
                      (initFor === a.id ? (
                        <span className="init-row">
                          <input
                            type="text"
                            inputMode="decimal"
                            value={initAmount}
                            onChange={(e) => setInitAmount(e.target.value)}
                            placeholder="Balance (KES)"
                            aria-label={`Starting balance for ${a.name}`}
                          />
                          <button
                            className="btn small"
                            type="button"
                            disabled={initialize.isPending}
                            onClick={() =>
                              initialize.mutate({ accountId: a.id, balance: initAmount })
                            }
                          >
                            Save
                          </button>
                          <button
                            className="btn ghost small"
                            type="button"
                            onClick={() => {
                              setInitFor(null);
                              setInitAmount("");
                            }}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => {
                            setInitFor(a.id);
                            setInitAmount("");
                          }}
                        >
                          Initialize
                        </button>
                      ))}{" "}
                    {editingId !== a.id && (
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => startEdit(a)}
                      >
                        Edit
                      </button>
                    )}
                  </span>
                </div>

                {/* The account corrected in place: name and kind only, because
                    the balance belongs to the records under it. */}
                {editingId === a.id && (
                  <form
                    className="edit-account auth-form"
                    onSubmit={editForm.handleSubmit((v) =>
                      updateAccount.mutate({ accountId: a.id, values: v })
                    )}
                  >
                    <p className="field-hint">
                      Fix what this account is. Its balance and the transactions
                      already recorded against it stay exactly as they are.
                    </p>
                    <div className="btn-row">
                      <label>
                        Name
                        <input {...editForm.register("name", accountNameRule)} />
                        {editErrors.name && (
                          <span className="field-error">{editErrors.name.message}</span>
                        )}
                      </label>
                      <label>
                        Kind of account
                        <select {...editForm.register("type")}>
                          {ACCOUNT_TYPES.map((t) => (
                            <option key={t.value} value={t.value}>{t.label}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <p className="field-hint">{TYPE_HINT.get(editKind)}</p>
                    {editNeedsPhone && (
                      <label>
                        M-PESA phone number
                        <input
                          inputMode="tel"
                          placeholder="0712 345 678"
                          {...editForm.register("mpesa_number", mpesaNumberRule)}
                        />
                        {editErrors.mpesa_number && (
                          <span className="field-error">{editErrors.mpesa_number.message}</span>
                        )}
                      </label>
                    )}
                    {editIsBank && (
                      <div className="btn-row">
                        <label>
                          Which bank
                          <input
                            placeholder="e.g. Equity Bank"
                            {...editForm.register("bank_name", bankNameRule)}
                          />
                          {editErrors.bank_name && (
                            <span className="field-error">{editErrors.bank_name.message}</span>
                          )}
                        </label>
                        <label>
                          Account number
                          <input
                            inputMode="numeric"
                            placeholder="as printed on your statement"
                            {...editForm.register("account_number", accountNumberRule)}
                          />
                          {editErrors.account_number && (
                            <span className="field-error">{editErrors.account_number.message}</span>
                          )}
                        </label>
                      </div>
                    )}
                    <div className="btn-row">
                      <button
                        className="btn primary"
                        type="submit"
                        disabled={updateAccount.isPending}
                      >
                        Save changes
                      </button>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => {
                          setEditingId(null);
                          editForm.reset(BLANK_EDIT);
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
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
            {/* A plain text field, like the balances: a number input quietly
                empties itself on "1,200", which is how people write money. */}
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g. 150 or 150.50"
              {...txnForm.register("amount", { required: "How much?", validate: positiveAmount })}
            />
            {txnErrors.amount && <span className="field-error">{txnErrors.amount.message}</span>}
          </label>
          <label>
            {isExpense ? "Paid from account" : "Added to account"}
            <select
              {...txnForm.register("account_id", {
                required: isExpense
                  ? "Which account did the money leave?"
                  : "Which account did the money arrive in?",
                validate: (v) =>
                  v === NEW_BANK || v === NEW_WALLET
                    ? "Add that account first, or pick one you already have"
                    : true,
              })}
            >
              <option value="">Select…</option>
              {(accounts.data ?? []).map((a) => (
                // The kind is named with the account, so two M-PESA rows or an
                // M-PESA and a bank account are not confused in the list.
                <option key={a.id} value={a.id}>
                  {a.name} · {TYPE_LABEL.get(a.type) ?? a.type}
                  {accountDetail(a) ? ` (${accountDetail(a)})` : ""}
                </option>
              ))}
              {/* Not accounts yet - entries that ask for one right here. */}
              <option value={NEW_BANK}>+ Add a bank account…</option>
              <option value={NEW_WALLET}>+ Add another wallet…</option>
            </select>
            {txnErrors.account_id && (
              <span className="field-error">{txnErrors.account_id.message}</span>
            )}
          </label>

          {quickKind && (
            <div className="quick-account">
              <p className="field-hint">
                {quickKind === "bank"
                  ? "Which bank, and the number it gave you. LifeSmart does not connect to the bank - this is your own record of where the money sits."
                  : "Anything else you keep money in and track by hand."}
              </p>
              <div className="btn-row">
                <label>
                  Name
                  <input
                    placeholder={quickKind === "bank" ? "e.g. Equity account" : "e.g. Chama pot"}
                    {...quickForm.register("name", accountNameRule)}
                  />
                  {quickErrors.name && (
                    <span className="field-error">{quickErrors.name.message}</span>
                  )}
                </label>
                {quickKind === "bank" && (
                  <label>
                    Which bank
                    <input
                      placeholder="e.g. Equity Bank"
                      {...quickForm.register("bank_name", bankNameRule)}
                    />
                    {quickErrors.bank_name && (
                      <span className="field-error">{quickErrors.bank_name.message}</span>
                    )}
                  </label>
                )}
              </div>
              {quickKind === "bank" && (
                <label>
                  Account number
                  <input
                    inputMode="numeric"
                    placeholder="as printed on your statement"
                    {...quickForm.register("account_number", accountNumberRule)}
                  />
                  {quickErrors.account_number && (
                    <span className="field-error">{quickErrors.account_number.message}</span>
                  )}
                </label>
              )}
              <label>
                Balance now (KES)
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="leave empty if you have not checked"
                  {...quickForm.register("balance", { validate: amountOrEmpty })}
                />
                {quickErrors.balance && (
                  <span className="field-error">{quickErrors.balance.message}</span>
                )}
              </label>
              <div className="btn-row">
                <button
                  className="btn primary"
                  type="button"
                  disabled={createQuickAccount.isPending}
                  onClick={quickForm.handleSubmit((v) => createQuickAccount.mutate(v))}
                >
                  Save account
                </button>
                <button className="btn ghost" type="button" onClick={cancelQuick}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          <label>
            {isExpense ? "What was it used for?" : "Source"}
            <input
              placeholder={isExpense ? "e.g. food, fees, transport" : "e.g. salary, gift"}
              {...txnForm.register("category")}
            />
          </label>
          <button
            className="btn primary"
            type="submit"
            disabled={createTxn.isPending || createQuickAccount.isPending || pendingQuickId !== null}
          >
            Save Transaction
          </button>
        </form>
      )}
    </div>
  );
}
