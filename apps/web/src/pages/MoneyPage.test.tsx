/** Money page tests: the details that go with each kind of account.
 *
 * The page asks for the number a M-PESA wallet or a bank account is held on,
 * keeps M-Shwari as its own pocket, and never treats a balance nobody entered
 * as zero. Nothing here pretends to read M-PESA or a bank.
 *
 * The rest covers correcting an account afterwards: what it is called and which
 * kind it is can be changed, and doing so must not touch its money.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MoneyPage, mpesaNumber, toMinor } from "./MoneyPage";
import { setToken } from "../services/api";
import type { Account, AccountType, BalanceSummary, TransactionPage } from "../types/api";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

interface Call {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
}

let calls: Call[] = [];

const mpesaAccount: Account = {
  id: 1,
  name: "My M-PESA",
  type: "mpesa",
  mpesa_number: "+254712345678",
  bank_name: null,
  account_number: null,
  is_synced: false,
  initialized: true,
  initial_balance_minor: 120000,
  created_at: "2026-10-01T08:00:00Z",
  balance_minor: 120000,
};

const shwariAccount: Account = {
  ...mpesaAccount,
  id: 2,
  name: "M-Shwari",
  type: "mshwari",
  initial_balance_minor: 5000000,
  balance_minor: 5000000,
};

const uncheckedBank: Account = {
  id: 3,
  name: "Equity",
  type: "bank",
  mpesa_number: null,
  bank_name: "Equity Bank",
  account_number: "011004567890",
  is_synced: false,
  initialized: false,
  initial_balance_minor: 0,
  created_at: "2026-10-02T08:00:00Z",
  balance_minor: null,
};

const SUMMARY: BalanceSummary = {
  total_available_minor: 5120000,
  initialized_accounts: 2,
  uninitialized_accounts: 1,
};

const EMPTY_TXNS: TransactionPage = {
  transactions: [],
  page: { total: 0, page: 1, page_size: 15 },
};

function mockFetch(initial: Account[]) {
  // The created accounts are kept, the way the database would, so a later
  // fetch shows them and the transaction picker can actually select one.
  const list: Account[] = [...initial];
  let nextId = 90;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    calls.push({ url, method, body });

    if (url.includes("/api/accounts/summary")) return jsonResponse(SUMMARY);
    if (url.includes("/initialize")) return jsonResponse({ ...(list[0] ?? {}), ...body });
    // Correcting an account: what it is called and what it is change, and
    // nothing else does. The fake follows the server's own rule that details
    // belonging to another kind of account are dropped.
    if (method === "PATCH") {
      const id = Number(url.split("/").pop());
      const index = list.findIndex((a) => a.id === id);
      if (index === -1) return jsonResponse({ detail: "Not found" });
      const before = list[index];
      const type = (body?.type as AccountType) ?? before.type;
      const after: Account = { ...before, ...(body as object) as Partial<Account> };
      after.id = before.id;
      after.type = type;
      after.balance_minor = before.balance_minor;
      after.initialized = before.initialized;
      after.is_synced = false;
      after.mpesa_number =
        type === "mpesa" || type === "mshwari" ? after.mpesa_number : null;
      if (type !== "bank") {
        after.bank_name = null;
        after.account_number = null;
      }
      list[index] = after;
      return jsonResponse(after);
    }
    if (url.endsWith("/api/accounts")) {
      if (method === "POST") {
        const created: Account = {
          id: nextId++,
          name: String(body?.name ?? ""),
          type: body?.type as AccountType,
          mpesa_number: (body?.mpesa_number as string) ?? null,
          bank_name: (body?.bank_name as string) ?? null,
          account_number: (body?.account_number as string) ?? null,
          is_synced: false,
          initialized: body?.balance_minor != null,
          initial_balance_minor: Number(body?.balance_minor ?? 0),
          created_at: "2026-10-28T08:00:00Z",
          balance_minor: body?.balance_minor == null ? null : Number(body.balance_minor),
        };
        list.push(created);
        return jsonResponse(created);
      }
      return jsonResponse(list);
    }
    if (url.includes("/api/transactions/summary/month")) {
      return jsonResponse({ income_minor: 0, expense_minor: 0, transfers_minor: 0 });
    }
    if (url.includes("/api/transactions")) {
      return method === "POST"
        ? jsonResponse({ id: 500, ...body })
        : jsonResponse(EMPTY_TXNS);
    }
    return jsonResponse({});
  }) as unknown as typeof fetch;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MoneyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The accounts the page tried to create, in the order it sent them. */
async function createdAccounts(count: number) {
  await vi.waitFor(() => {
    expect(calls.filter(isCreate)).toHaveLength(count);
  });
  return calls.filter(isCreate).map((c) => c.body!);
}

function isCreate(c: Call): boolean {
  return c.method === "POST" && c.url.endsWith("/api/accounts");
}

function pickKind(value: string) {
  fireEvent.change(screen.getByLabelText(/Kind of account/), { target: { value: value } });
}

/** The editor opened under an account row. The Add account card asks the same
 * questions, so a lookup has to be kept inside the editor to be about it. */
function editor() {
  const form = screen.getByText(/Fix what this account is/).closest("form");
  if (!form) throw new Error("no account editor is open");
  return within(form as HTMLElement);
}

function patches() {
  return calls.filter((c) => c.method === "PATCH");
}

describe("MoneyPage accounts", () => {
  // The old starting-balance flow used a browser popup. It must not come back.
  const promptSpy = vi.fn();
  const originalPrompt = window.prompt;

  beforeEach(() => {
    setToken("test-token");
    calls = [];
    window.prompt = promptSpy as unknown as typeof window.prompt;
  });
  afterEach(() => {
    setToken(null);
    window.prompt = originalPrompt;
    vi.unstubAllGlobals();
  });

  it("keeps an M-PESA number in one shape and reads amounts exactly", () => {
    expect(mpesaNumber("0712 345 678")).toBe("+254712345678");
    expect(mpesaNumber("+254712-345-678")).toBe("+254712345678");
    expect(mpesaNumber("0412345678")).toBeNull();
    expect(toMinor("1,200.50")).toBe(120050);
    expect(toMinor("1200")).toBe(120000);
    expect(toMinor("10.005")).toBeNull(); // never rounded to a pesa that was not typed
    expect(toMinor("0x10")).toBeNull();
    expect(toMinor("")).toBeNull();
  });

  it("asks for the number that goes with the kind of account chosen", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();

    await screen.findByRole("heading", { name: "Accounts" });
    // Cash has no identifier at all.
    expect(screen.queryByLabelText(/M-PESA phone number/)).not.toBeInTheDocument();

    pickKind("mpesa");
    expect(screen.getByLabelText(/M-PESA phone number/)).toBeInTheDocument();
    expect(screen.getByLabelText(/M-PESA balance/)).toBeInTheDocument();
    expect(screen.getByLabelText(/M-Shwari balance/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Which bank/)).not.toBeInTheDocument();

    pickKind("bank");
    expect(screen.getByLabelText(/Which bank/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Account number/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/M-PESA phone number/)).not.toBeInTheDocument();
    // An M-Shwari balance belongs to M-PESA only.
    expect(screen.queryByLabelText(/M-Shwari balance/)).not.toBeInTheDocument();
  });

  it("saves M-PESA and M-Shwari as two pockets on one line", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "My M-PESA" } });
    pickKind("mpesa");
    fireEvent.change(screen.getByLabelText(/M-PESA phone number/), {
      target: { value: "0712 345 678" },
    });
    fireEvent.change(screen.getByLabelText(/M-PESA balance/), { target: { value: "1200" } });
    fireEvent.change(screen.getByLabelText(/M-Shwari balance/), { target: { value: "50000" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Account" }));

    const sent = await createdAccounts(2);
    expect(sent[0]).toMatchObject({
      name: "My M-PESA",
      type: "mpesa",
      mpesa_number: "+254712345678",
      balance_minor: 120000,
      bank_name: null,
      account_number: null,
    });
    expect(sent[1]).toMatchObject({
      name: "M-Shwari",
      type: "mshwari",
      mpesa_number: "+254712345678",
      balance_minor: 5000000,
    });
  });

  it("refuses an M-PESA number that is not a Safaricom line, and posts nothing", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "M-PESA" } });
    pickKind("mpesa");
    fireEvent.change(screen.getByLabelText(/M-PESA phone number/), {
      target: { value: "0412 345 678" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Account" }));

    expect(await screen.findByText(/Use a Safaricom number/)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(calls.filter(isCreate)).toHaveLength(0);
  });

  it("records a bank account with its bank and number, and no phone number", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    pickKind("bank");
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Equity" } });
    fireEvent.change(screen.getByLabelText(/Which bank/), { target: { value: "Equity Bank" } });
    fireEvent.change(screen.getByLabelText(/Account number/), {
      target: { value: "0110 0456 7890" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Account" }));

    const [sent] = await createdAccounts(1);
    expect(sent).toMatchObject({
      type: "bank",
      bank_name: "Equity Bank",
      account_number: "011004567890",
      mpesa_number: null,
      // No balance was typed, so none is claimed.
      balance_minor: null,
    });
  });

  it("lists the identifier with the account and initializes an unknown balance inline", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount, shwariAccount, uncheckedBank]));
    renderPage();

    expect(await screen.findByText("+254712345678")).toBeInTheDocument();
    expect(screen.getByText("Equity Bank · A/C 011004567890")).toBeInTheDocument();
    expect(screen.getByText("balance unknown")).toBeInTheDocument();
    // M-PESA and M-Shwari appear as separate rows, each with its own money.
    expect(screen.getByText("KES 1,200.00")).toBeInTheDocument();
    expect(screen.getByText("KES 50,000.00")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Initialize" }));
    const field = screen.getByLabelText("Starting balance for Equity");
    fireEvent.change(field, { target: { value: "2,500.75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await vi.waitFor(() => {
      const posted = calls.find((c) => c.method === "POST" && c.url.includes("/initialize"));
      expect(posted?.body).toEqual({ balance_minor: 250075 });
    });
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it("names the kind of account in the transaction picker", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount, shwariAccount, uncheckedBank]));
    renderPage();
    await screen.findByText("+254712345678");

    fireEvent.click(screen.getByRole("tab", { name: "Add Transaction" }));
    const picker = screen.getByLabelText(/Paid from account/) as HTMLSelectElement;
    const options = Array.from(picker.options).map((o) => o.textContent);
    expect(options).toContain("My M-PESA · M-PESA (+254712345678)");
    expect(options).toContain("M-Shwari · M-Shwari (+254712345678)");
    expect(options).toContain("Equity · Bank account (Equity Bank · A/C 011004567890)");
    // And the two kinds a person may need but not have added yet.
    expect(options).toContain("+ Add a bank account…");
    expect(options).toContain("+ Add another wallet…");
  });

  it("adds the bank account a transaction needs, then spends from it", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.click(screen.getByRole("tab", { name: "Add Transaction" }));
    const picker = screen.getByLabelText(/Paid from account/) as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: "__new_bank" } });

    // The bank questions appear under the picker, in the same form.
    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Equity account" } });
    fireEvent.change(screen.getByLabelText(/Which bank/), { target: { value: "Equity Bank" } });
    fireEvent.change(screen.getByLabelText(/Account number/), {
      target: { value: "0110 0456 7890" },
    });
    fireEvent.change(screen.getByLabelText(/Balance now/), { target: { value: "8,000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));

    const [sent] = await createdAccounts(1);
    expect(sent).toMatchObject({
      name: "Equity account",
      type: "bank",
      bank_name: "Equity Bank",
      account_number: "011004567890",
      mpesa_number: null,
      balance_minor: 800000,
    });

    // The new account is picked for this transaction, not left showing the
    // "add one" entry, and the panel closes.
    await vi.waitFor(() => {
      expect(picker.options[picker.selectedIndex]?.textContent).toContain("Equity account");
    });
    expect(screen.queryByRole("button", { name: "Save account" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText(/What was it used for/), { target: { value: "rent" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Transaction" }));

    await vi.waitFor(() => {
      const txn = calls.find((c) => c.method === "POST" && c.url.includes("/api/transactions"));
      expect(txn?.body).toMatchObject({
        type: "expense",
        amount_minor: 50000,
        category: "rent",
        account_id: Number(picker.value),
      });
    });
  });

  it("adds another wallet with just a name and a balance", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.click(screen.getByRole("tab", { name: "Add Transaction" }));
    const picker = screen.getByLabelText(/Paid from account/) as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: "__new_wallet" } });

    // A wallet has no bank and no phone number to give.
    expect(screen.queryByLabelText(/Which bank/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/M-PESA phone number/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Chama pot" } });
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));

    const [sent] = await createdAccounts(1);
    expect(sent).toMatchObject({
      name: "Chama pot",
      type: "wallet",
      bank_name: null,
      account_number: null,
      mpesa_number: null,
      balance_minor: null, // never counted, so never written as zero
    });
  });

  it("refuses an amount that is not money", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount]));
    renderPage();
    await screen.findByText("+254712345678");

    fireEvent.click(screen.getByRole("tab", { name: "Add Transaction" }));
    fireEvent.change(screen.getByLabelText(/Paid from account/), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Transaction" }));

    expect(await screen.findByText(/bigger than zero/)).toBeInTheDocument();
    expect(
      calls.filter((c) => c.method === "POST" && c.url.includes("/api/transactions")),
    ).toHaveLength(0);
  });

  it("will not record a transaction against an account nobody finished adding", async () => {
    vi.stubGlobal("fetch", mockFetch([]));
    renderPage();
    await screen.findByRole("heading", { name: "Accounts" });

    fireEvent.click(screen.getByRole("tab", { name: "Add Transaction" }));
    const picker = screen.getByLabelText(/Paid from account/) as HTMLSelectElement;
    fireEvent.change(picker, { target: { value: "__new_bank" } });

    fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Transaction" }));

    expect(await screen.findByText(/Add that account first/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST" && c.url.includes("/api/transactions"))).toHaveLength(0);

    // Cancelling clears the picker rather than leaving the false entry chosen.
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(picker.value).toBe("");
    expect(screen.queryByRole("button", { name: "Save account" })).not.toBeInTheDocument();
  });

  it("corrects a second M-PESA row into the bank account it really is", async () => {
    // The mistake the editor exists for: two rows named alike, holding the same
    // number, that every picker then shows twice.
    const dupe: Account = {
      ...mpesaAccount,
      id: 4,
      name: "mpesa",
      initial_balance_minor: 250000,
      balance_minor: 250000,
    };
    vi.stubGlobal("fetch", mockFetch([mpesaAccount, dupe]));
    renderPage();
    await screen.findByText("+254712345678");
    expect(screen.getAllByText("+254712345678")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    const ed = editor();
    fireEvent.change(ed.getByLabelText(/Name/), { target: { value: "Equity" } });
    fireEvent.change(ed.getByLabelText(/Kind of account/), { target: { value: "bank" } });
    fireEvent.change(ed.getByLabelText(/Which bank/), { target: { value: "Equity Bank" } });
    fireEvent.change(ed.getByLabelText(/Account number/), {
      target: { value: "0110 0456 7890" },
    });
    fireEvent.click(ed.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => {
      expect(patches()).toHaveLength(1);
    });
    expect(patches()[0]!.url).toContain("/api/accounts/4");
    expect(patches()[0]!.body).toMatchObject({
      name: "Equity",
      type: "bank",
      bank_name: "Equity Bank",
      account_number: "011004567890",
      // A bank account holds no M-PESA number, so the old one is not sent.
      mpesa_number: null,
    });
    // An edit never offers the balance: the money is not what is being fixed.
    expect(patches()[0]!.body).not.toHaveProperty("balance_minor");

    expect(await screen.findByText("Equity Bank · A/C 011004567890")).toBeInTheDocument();
    // What it held stays exactly where it was.
    expect(screen.getByText("KES 2,500.00")).toBeInTheDocument();
    expect(screen.getAllByText("+254712345678")).toHaveLength(1);
  });

  it("keeps the stored phone number when only the name is corrected", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount]));
    renderPage();
    await screen.findByText("+254712345678");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const ed = editor();
    fireEvent.change(ed.getByLabelText(/Name/), { target: { value: "Safaricom line" } });
    fireEvent.click(ed.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => {
      expect(patches()).toHaveLength(1);
    });
    expect(patches()[0]!.body).toMatchObject({
      name: "Safaricom line",
      type: "mpesa",
      mpesa_number: "+254712345678",
    });
    expect(await screen.findByText("Safaricom line")).toBeInTheDocument();
  });

  it("will not switch an account to a bank without saying which bank", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount]));
    renderPage();
    await screen.findByText("+254712345678");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const ed = editor();
    fireEvent.change(ed.getByLabelText(/Kind of account/), { target: { value: "bank" } });
    fireEvent.click(ed.getByRole("button", { name: "Save changes" }));

    expect(await ed.findByText(/Which bank is it\?/)).toBeInTheDocument();
    expect(patches()).toHaveLength(0);
    expect(screen.getByText("My M-PESA")).toBeInTheDocument();
  });

  it("cancelling an edit changes nothing", async () => {
    vi.stubGlobal("fetch", mockFetch([mpesaAccount]));
    renderPage();
    await screen.findByText("+254712345678");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const ed = editor();
    fireEvent.change(ed.getByLabelText(/Name/), { target: { value: "Something else" } });
    fireEvent.click(ed.getByRole("button", { name: "Cancel" }));

    expect(patches()).toHaveLength(0);
    expect(screen.queryByText(/Fix what this account is/)).not.toBeInTheDocument();
    expect(screen.getByText("My M-PESA")).toBeInTheDocument();

    // Reopening starts from the account, not from the typing nobody saved.
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect((editor().getByLabelText(/Name/) as HTMLInputElement).value).toBe("My M-PESA");
  });
});
