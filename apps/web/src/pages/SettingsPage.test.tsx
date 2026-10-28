/** Settings page test. The milestone's acceptance criterion is what this
 * guards: the screen must distinguish an integration that works from one that
 * is manual or does not exist, must not let you corrupt your sign-in identity,
 * and must not delete anything without the typed confirmation. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { setToken } from "../services/api";
import type { ResetResult, SettingsView } from "../types/api";

const view: SettingsView = {
  profile: {
    id: 1,
    email: "local@lifesmart.desktop",
    full_name: "David M",
    currency: "KES",
    country: "Kenya",
    timezone: "Africa/Nairobi",
    is_student: true,
    onboarded: true,
    created_at: "2026-01-05T08:00:00Z",
  },
  preferences: {
    id: 1,
    deadline_alerts: true,
    task_reminders: true,
    low_stock_warnings: false,
    savings_nudges: true,
    fee_due_alerts: true,
    quiet_start: null,
    quiet_end: null,
    updated_at: "2026-10-01T00:00:00Z",
  },
  integrations: [
    {
      key: "local_model",
      label: "On-device AI model",
      status: "on_demand",
      detail: "qwen2.5.gguf is on this machine but not in memory.",
      action: "AI Assistant > Load model",
    },
    {
      key: "google_signin",
      label: "Google sign-in",
      status: "not_configured",
      detail: "No Google client is configured.",
      action: ".env: GOOGLE_CLIENT_ID",
    },
    {
      key: "image_classification",
      label: "Picture classification",
      status: "manual",
      detail: "The category is the folder you put an image in.",
      action: "Images",
    },
    {
      key: "price_sourcing",
      label: "Price sources",
      status: "manual",
      detail: "Prices come from you.",
      action: "Inventory > Add or edit an item",
    },
    {
      key: "mpesa",
      label: "M-PESA",
      status: "unavailable",
      detail: "There is no M-PESA connection.",
      action: "Money > Add transaction",
    },
    {
      key: "bank",
      label: "Bank feeds",
      status: "unavailable",
      detail: "No bank or card API is connected.",
      action: "Money",
    },
    {
      key: "delivery_channels",
      label: "Email, SMS and push alerts",
      status: "not_configured",
      detail: "Reminders appear inside the app only.",
      action: "Notifications",
    },
    {
      key: "backup",
      label: "Backups",
      status: "manual",
      detail: "Copy the database file, or download the export.",
      action: "Settings > Your data",
    },
  ],
  privacy: {
    local_only: true,
    data_dir: "/home/david/.local/share/lifesmart",
    stored: [
      { key: "inventory_items", label: "Inventory items", rows: 3 },
      { key: "transactions", label: "Transactions", rows: 4 },
      { key: "inventory_categories", label: "Inventory categories", rows: 7 },
      { key: "goals", label: "Goals", rows: 0 },
    ],
    row_total: 14,
    excluded: [
      {
        key: "assets",
        label: "Picture index",
        reason: "shared by every account, so it is neither exported nor deleted",
      },
    ],
    statement: ["Everything you enter is stored in one database file on this machine."],
  },
  export_note: "Nothing is uploaded to produce it.",
};

const emptied: ResetResult = {
  deleted: { inventory_items: 3, transactions: 4, goals: 0 },
  deleted_total: 7,
  kept: ["account sign-in", "profile details", "picture index"],
  reseeded: ["Clothing", "Household"],
  note: "Every record owned by this account was deleted.",
};

function jsonResponse(body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** Records every request the page makes so the assertions can read the body
 * that was actually sent (the point of the email and confirmation tests). */
let requests: { url: string; method: string; body: string | null }[];

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    requests.push({
      url,
      method,
      body: typeof init?.body === "string" ? init.body : null,
    });
    if (url.includes("/api/account/export")) {
      return new Response(new Blob(["zip"]), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="lifesmart-export-2026-10-28.zip"',
        },
      });
    }
    if (url.includes("/api/account/reset")) return jsonResponse(emptied);
    if (url.includes("/api/auth/me")) {
      const sent = JSON.parse(String(requests.at(-1)?.body ?? "{}"));
      return jsonResponse({ ...view.profile, ...sent });
    }
    return jsonResponse(view);
  }) as unknown as typeof fetch;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** A row's own status chip, ignoring the legend that explains the vocabulary. */
function statusOf(label: string): string {
  const row = screen.getByText(label).closest(".integration-row") as HTMLElement;
  return row.querySelector(".badge")?.textContent ?? "";
}

/** The last request the page made to a route, with its decoded body. */
function sentTo(path: string, method: string): Record<string, unknown> | undefined {
  const call = [...requests]
    .reverse()
    .find((r) => r.url.includes(path) && r.method === method);
  return call ? JSON.parse(call.body ?? "{}") : undefined;
}

describe("SettingsPage", () => {
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  beforeEach(() => {
    requests = [];
    setToken("test-token");
    URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
    vi.stubGlobal("fetch", mockFetch());
  });
  afterEach(() => {
    setToken(null);
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    vi.unstubAllGlobals();
  });

  it("shows the profile with the sign-in identity readable but not editable", async () => {
    renderPage();

    const name = await screen.findByLabelText(/Name shown to you/);
    expect(name).toHaveValue("David M");
    const email = screen.getByLabelText(/Sign-in identity/) as HTMLInputElement;
    expect(email).toHaveValue("local@lifesmart.desktop");
    expect(email.readOnly).toBe(true);
    // A reason is given rather than a disabled control with no explanation.
    expect(screen.getByText(/how - or whether - you sign back in/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Currency/)).toHaveValue("KES");
    expect(screen.getByLabelText(/Student/)).toHaveValue("yes");
  });

  it("distinguishes what works from what is manual or absent", async () => {
    renderPage();
    await screen.findByText("On-device AI model");

    expect(statusOf("M-PESA")).toBe("Not available");
    expect(statusOf("Bank feeds")).toBe("Not available");
    expect(statusOf("Price sources")).toBe("You do this");
    expect(statusOf("Backups")).toBe("You do this");
    expect(statusOf("Email, SMS and push alerts")).toBe("Switched off");
    expect(statusOf("On-device AI model")).toBe("Only when you start it");
    // The vocabulary is explained once, so a chip is never a bare claim.
    expect(screen.getByText("no such connection exists")).toBeInTheDocument();
    // And the page never claims a payment connection of its own accord.
    expect(screen.queryByText(/connected to M-PESA/i)).not.toBeInTheDocument();
  });

  it("saves the profile to the profile route, without the email", async () => {
    renderPage();
    const name = await screen.findByLabelText(/Name shown to you/);
    fireEvent.change(name, { target: { value: "Dave" } });
    fireEvent.click(screen.getByRole("button", { name: /Save profile/i }));

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    const sent = sentTo("/api/auth/me", "PATCH");
    expect(sent?.full_name).toBe("Dave");
    // Email is the sign-in identity, so it is never even offered to the server.
    expect("email" in (sent ?? {})).toBe(false);
  });

  it("counts what is stored and names what is deliberately left out", async () => {
    renderPage();
    await screen.findByText(/Rows in your account/);

    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText(/Inventory items/)).toBeInTheDocument();
    // Empty kinds are reported as a count, not as a row of zeros pretending to be data.
    expect(screen.getByText(/1 further kind of record/)).toBeInTheDocument();
    expect(screen.getByText(/shared by every account/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is uploaded to produce it/)).toBeInTheDocument();
    expect(screen.getByText(/\.local\/share\/lifesmart/)).toBeInTheDocument();
  });

  it("downloads the export from the account route", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Download everything/i }));

    expect(await screen.findByText(/Saved to your downloads/)).toBeInTheDocument();
    expect(requests.some((r) => r.url.includes("/api/account/export"))).toBe(true);
  });

  it("sits between the export it restores from and the reset it can undo", async () => {
    renderPage();
    const heading = await screen.findByText("Bring a backup back");
    const card = heading.closest(".card") as HTMLElement;
    const download = screen.getByRole("button", { name: /Download everything/i });
    const danger = screen.getByText("Start again").closest(".card") as HTMLElement;

    // Ordered where a person reads it: take a copy, put one back, only then
    // delete what is here.
    expect(card.compareDocumentPosition(download) & Node.DOCUMENT_POSITION_PRECEDING)
      .toBeTruthy();
    expect(card.compareDocumentPosition(danger) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    // It asks for a file and waits, with nothing claimed about the archive yet.
    expect(card.querySelector('input[type="file"]')).toBeInTheDocument();
    expect(screen.getByText("No file selected.")).toBeInTheDocument();
    // The reset warning no longer promises there is no way back.
    expect(screen.getByText(/can be put back above/)).toBeInTheDocument();
  });

  it("will not delete anything before the word RESET is typed", async () => {
    renderPage();
    const button = await screen.findByRole("button", { name: /Delete my records/i });
    const field = screen.getByLabelText(/Type RESET to confirm/) as HTMLInputElement;

    expect(button).toBeDisabled();
    fireEvent.change(field, { target: { value: "yes" } });
    expect(button).toBeDisabled();
    fireEvent.change(field, { target: { value: "reset" } });
    expect(button).toBeEnabled(); // the server compares case-insensitively

    fireEvent.click(button);
    expect(await screen.findByText(/Deleted 7 records/)).toBeInTheDocument();
    expect(sentTo("/api/account/reset", "POST")).toEqual({ confirm: "RESET" });
    // A table emptied to zero is not listed as though something was removed.
    expect(screen.queryByText(/goals/)).not.toBeInTheDocument();
    expect(screen.getByText(/account sign-in/)).toBeInTheDocument();
  });
});
