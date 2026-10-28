/** The restore control. Its whole job is to refuse: a file must be read before
 * anything is offered, the server's numbers must be the ones on screen, a second
 * file must not inherit the first file's preview, and the button must stay shut
 * until the word is typed. So these tests push on the doors rather than checking
 * that a successful restore looks nice. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RestoreCard } from "./RestoreCard";
import { setToken } from "../../services/api";
import type { RestorePreview, RestoreResult } from "../../types/api";

const TABLE_LABELS = new Map([
  ["goals", "Goals"],
  ["transactions", "Transactions"],
  ["inventory_items", "Inventory items"],
]);

const FIRST = "lifesmart-export-2026-10-28.zip";
const BYTES = "PK\u0003\u0004 some archive bytes";

function previewBody(over: Partial<RestorePreview> = {}): RestorePreview {
  return {
    generated_at: "2026-10-28T17:55:40+00:00",
    currency_of_origin: "KES",
    current_currency: "KES",
    photo_links_kept: 0,
    photo_links_cleared: 0,
    archive_total: 3,
    current_total: 5,
    warnings: [],
    tables: [
      { key: "goals", label: "Goals", archive_rows: 2, current_rows: 1 },
      { key: "transactions", label: "Transactions", archive_rows: 1, current_rows: 4 },
    ],
    ...over,
  };
}

function resultBody(over: Partial<RestoreResult> = {}): RestoreResult {
  return {
    written: { goals: 2, transactions: 1 },
    written_total: 3,
    replaced: { goals: 1, transactions: 4 },
    replaced_total: 5,
    generated_at: "2026-10-28T17:55:40+00:00",
    currency: "KES",
    currency_changed_from: null,
    photo_links_kept: 0,
    photo_links_cleared: 0,
    warnings: [],
    reseeded_categories: false,
    kept: ["account sign-in", "profile details", "picture index"],
    note: "Every record in this account was replaced by the archive.",
    ...over,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const REFUSAL = "2 inventory items have no inventory category to belong to. Nothing was changed.";

/** Requests as they left the component, so an assertion can read the body the
 * server was actually handed rather than trusting the state on screen. */
let sent: { url: string; method: string; body: Record<string, unknown> }[];

function stubRoutes(
  handlers: {
    preview?: (body: Record<string, unknown>) => Response;
    restore?: (body: Record<string, unknown>) => Response;
  } = {},
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : {};
    sent.push({ url, method, body });
    // The preview route is a prefix of the restore route, so it is matched first.
    if (url.includes("/restore/preview")) {
      return handlers.preview?.(body) ?? jsonResponse(previewBody());
    }
    if (url.includes("/api/account/restore")) {
      return handlers.restore?.(body) ?? jsonResponse(resultBody());
    }
    throw new Error(`RestoreCard asked for an unexpected route: ${url}`);
  }) as unknown as typeof fetch;
}

function renderCard(client = new QueryClient()) {
  return render(
    <QueryClientProvider client={client}>
      <RestoreCard tableLabels={TABLE_LABELS} />
    </QueryClientProvider>,
  );
}

function fileInput(): HTMLInputElement {
  return screen.getByLabelText("Export file") as HTMLInputElement;
}

/** Picks a file and waits for the reader to finish: jsdom reads the real bytes,
 * so the archive the component holds is the one its own reader produced. */
async function chooseFile(name = FIRST, content = BYTES): Promise<void> {
  fireEvent.change(fileInput(), {
    target: { files: [new File([content], name, { type: "application/zip" })] },
  });
  // The name only appears once the file is in the component's hand. Until then
  // the read button is disabled, and clicking it earlier would click nothing.
  await screen.findByText(name);
}

async function readArchive(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: /Read the archive/i }));
  await screen.findByText(/records in that file/);
}

/** File chosen and read: the state the destructive button appears in. */
async function previewed(name = FIRST): Promise<void> {
  await chooseFile(name);
  await readArchive();
}

function typed(word: string): void {
  fireEvent.change(screen.getByLabelText(/Type RESTORE to confirm/), {
    target: { value: word },
  });
}

function pressRestore(): void {
  fireEvent.click(screen.getByRole("button", { name: /Put my records back/i }));
}

/** The archive the preview was asked about, as base64. */
function previewedArchive(): string {
  return String(sent.find((r) => r.url.includes("/restore/preview"))?.body.archive_base64);
}

function restoreCall(): Record<string, unknown> | undefined {
  return sent.find((r) => r.url.endsWith("/api/account/restore"))?.body;
}

describe("RestoreCard", () => {
  beforeEach(() => {
    sent = [];
    setToken("test-token");
  });
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it("offers nothing to restore until a file has been read", async () => {
    vi.stubGlobal("fetch", stubRoutes());
    renderCard();

    expect(await screen.findByText("No file selected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Read the archive/i })).toBeDisabled();
    // The confirm field and the destructive button do not exist yet at all: a
    // disabled control beside a file nobody has checked is still a trap.
    expect(screen.queryByLabelText(/Type RESTORE to confirm/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Put my records back/i })).toBeNull();
    expect(sent).toHaveLength(0);
  });

  it("hands the server the file's own bytes, not its name", async () => {
    vi.stubGlobal("fetch", stubRoutes());
    renderCard();
    await previewed();

    const ask = sent.find((r) => r.url.includes("/restore/preview"));
    expect(ask?.method).toBe("POST");
    expect(atob(previewedArchive())).toBe(BYTES);
    // The filename says nothing about what is inside, so it is not even sent.
    expect(JSON.stringify(ask?.body)).not.toContain("lifesmart-export");
  });

  it("states the archive and the account side by side, in the server's words", async () => {
    vi.stubGlobal(
      "fetch",
      stubRoutes({
        preview: () =>
          jsonResponse(
            previewBody({
              warnings: [
                "This export was written on 2026-10-28. Records you made after that are not in it and would be replaced.",
              ],
            }),
          ),
      }),
    );
    renderCard();
    await previewed();

    expect(screen.getByText("3 records in that file")).toBeInTheDocument();
    expect(screen.getByText(/written on 2026-10-28/)).toBeInTheDocument();
    // The minute a backup was written at is not information; the day is.
    expect(screen.queryByText(/17:55/)).toBeNull();
    expect(screen.getByText(/would replace the 5 records you have now/)).toBeInTheDocument();

    expect(screen.getByText("Goals", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText("2 in the file · 1 now")).toBeInTheDocument();
    // The server's label, never the column key the row came in under.
    expect(screen.queryByText("goals", { selector: "li" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("not in it and would be replaced");
  });

  it("says so when the account holds nothing to overwrite", async () => {
    vi.stubGlobal(
      "fetch",
      stubRoutes({
        preview: () =>
          jsonResponse(
            previewBody({
              archive_total: 1,
              current_total: 0,
              tables: [{ key: "goals", label: "Goals", archive_rows: 1, current_rows: 0 }],
            }),
          ),
      }),
    );
    renderCard();
    await previewed();

    expect(screen.getByText("1 record in that file")).toBeInTheDocument();
    expect(screen.getByText(/nothing is overwritten/)).toBeInTheDocument();
  });

  it("keeps no way forward when the archive is refused", async () => {
    vi.stubGlobal("fetch", stubRoutes({ preview: () => jsonResponse({ detail: REFUSAL }, 400) }));
    renderCard();
    await chooseFile();

    fireEvent.click(screen.getByRole("button", { name: /Read the archive/i }));

    // The server's reason, verbatim, rather than a generic failure.
    expect(await screen.findByRole("alert")).toHaveTextContent(REFUSAL);
    expect(screen.getByText(/Nothing was changed\. Pick a different file/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Type RESTORE to confirm/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Put my records back/i })).toBeNull();
    expect(restoreCall()).toBeUndefined();
  });

  it("does not let a second file inherit the first one's preview", async () => {
    let archive = previewBody();
    vi.stubGlobal("fetch", stubRoutes({ preview: () => jsonResponse(archive) }));
    renderCard();
    await previewed("first-export.zip");
    expect(screen.getByText("3 records in that file")).toBeInTheDocument();

    // A different file, so a different answer has to be earned before the button.
    archive = previewBody({
      archive_total: 40,
      current_total: 3,
      tables: [
        { key: "inventory_items", label: "Inventory items", archive_rows: 40, current_rows: 3 },
      ],
    });
    await chooseFile("second-export.zip");

    expect(screen.getByText("second-export.zip")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Read the archive/i })).toBeEnabled();
    expect(screen.queryByText("3 records in that file")).toBeNull();
    expect(screen.queryByText(/would replace the 5 records/)).toBeNull();
    expect(screen.queryByLabelText(/Type RESTORE to confirm/)).toBeNull();

    await readArchive();
    expect(screen.getByText("40 records in that file")).toBeInTheDocument();
  });

  it("will not restore until the word RESTORE is typed", async () => {
    vi.stubGlobal("fetch", stubRoutes());
    renderCard();
    await previewed();

    const button = screen.getByRole("button", { name: /Put my records back/i });
    expect(button).toBeDisabled();

    typed("yes");
    expect(button).toBeDisabled();
    typed("RESTOR");
    expect(button).toBeDisabled();
    // The server compares case-insensitively and ignores spacing, so the page
    // must not be stricter about it than the route is.
    typed(" restore ");
    expect(button).toBeEnabled();

    pressRestore();
    expect(restoreCall()?.confirm).toBe("RESTORE");
    // The archive goes over again rather than being referenced: a preview is not
    // a permission, so the server re-checks whatever it is actually handed.
    expect(restoreCall()?.archive_base64).toBe(previewedArchive());
  });

  it("reports what came back, then lets go of the file", async () => {
    const client = new QueryClient();
    const drop = vi.spyOn(client, "invalidateQueries");
    vi.stubGlobal(
      "fetch",
      stubRoutes({
        restore: () =>
          jsonResponse(resultBody({ currency: "KES", currency_changed_from: "UGX",
                                   photo_links_cleared: 2 })),
      }),
    );
    renderCard(client);
    await previewed();
    typed("RESTORE");

    pressRestore();

    expect(await screen.findByText("Restored 3 records.")).toBeInTheDocument();
    expect(
      screen.getByText(/5 records previously in the account were replaced/),
    ).toBeInTheDocument();
    // The result names tables in the page's own words, never as a column key.
    expect(screen.getByText("Goals", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/switched from UGX to KES/)).toBeInTheDocument();
    expect(screen.getByText(/2 picture links could not be kept/)).toBeInTheDocument();
    expect(screen.getByText(/Kept: account sign-in/)).toBeInTheDocument();

    // The file is let go, so the same archive cannot be restored twice without
    // reading it and agreeing to it again.
    expect(drop).toHaveBeenCalled();
    expect(screen.queryByText(FIRST)).toBeNull();
    expect(screen.getByRole("button", { name: /Read the archive/i })).toBeDisabled();
    expect(screen.queryByLabelText(/Type RESTORE to confirm/)).toBeNull();
  });

  it("says nothing was changed when the restore itself is refused", async () => {
    vi.stubGlobal(
      "fetch",
      stubRoutes({
        restore: () =>
          jsonResponse({ detail: "The archive holds a table this app does not know. Nothing was changed." }, 400),
      }),
    );
    renderCard();
    await previewed();
    typed("RESTORE");

    pressRestore();

    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
    expect(screen.queryByText(/Restored/)).toBeNull();
    // The file stays in hand, so a person can download a fresh export without
    // losing the one they were told is not usable.
    expect(screen.getByText(FIRST)).toBeInTheDocument();
  });

  it("restores into an account that holds nothing without claiming a replacement", async () => {
    vi.stubGlobal(
      "fetch",
      stubRoutes({
        preview: () => jsonResponse(previewBody({ current_total: 0 })),
        restore: () => jsonResponse(resultBody({ replaced_total: 0 })),
      }),
    );
    renderCard();
    await previewed();
    typed("RESTORE");

    pressRestore();

    expect(await screen.findByText("Restored 3 records.")).toBeInTheDocument();
    expect(screen.queryByText(/previously in the account were replaced/)).toBeNull();
  });

  it("un-picking the file takes the preview with it", async () => {
    vi.stubGlobal("fetch", stubRoutes());
    renderCard();
    await previewed();
    typed("RESTORE");

    // Clearing a file input is possible, and must not leave a live button.
    fireEvent.change(fileInput(), { target: { files: [] } });

    expect(await screen.findByText("No file selected.")).toBeInTheDocument();
    expect(screen.queryByText(/records in that file/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Put my records back/i })).toBeNull();
  });
});
