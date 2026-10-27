/** AssistantPage smoke test: it renders the server's structured result cards
 * verbatim, shows a confirmation control for a proposed change (nothing is
 * applied until the user confirms), and offers the optional local model
 * without ever loading it on its own. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AssistantPage } from "./AssistantPage";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const sendResponse = {
  conversation_id: 1,
  user_message: {
    id: 1, role: "user", content: "What am I missing?",
    cards: null, asset_id: null, created_at: "2026-10-01T00:00:00Z", proposal: null,
  },
  assistant_message: {
    id: 2, role: "assistant", content: "Here's what you're short on.",
    asset_id: null, created_at: "2026-10-01T00:00:00Z",
    cards: [
      {
        kind: "list", title: "Items to restock",
        rows: [
          { heading: "Chinos", sub: "Clothing", badge: "need 2",
            minor: null, lines: ["price needed"] },
        ],
      },
    ],
    proposal: {
      id: 9, kind: "add_inventory_item", title: "Add Chinos to inventory",
      payload: {}, status: "pending", result: null,
      created_at: "2026-10-01T00:00:00Z", resolved_at: null,
    },
  },
};

const modelStatus = {
  enabled: true,
  available: true,
  state: "unloaded",
  model_file: "qwen2.5-0.5b-instruct-q2_k.gguf",
  size_mb: 350.4,
  threads: 2,
  ctx: 2048,
  error: null,
};

describe("AssistantPage", () => {
  let calls: string[];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const path = url.pathname;
        calls.push(`${init?.method ?? "GET"} ${path}`);
        if (path.endsWith("/suggestions")) {
          return jsonResponse(["What am I missing?"]);
        }
        if (path.endsWith("/messages")) return jsonResponse(sendResponse);
        if (path === "/api/assistant/model/load") {
          return jsonResponse({ ...modelStatus, state: "ready" });
        }
        if (path === "/api/assistant/model/unload") {
          return jsonResponse({ ...modelStatus, state: "unloaded" });
        }
        if (path === "/api/assistant/model") return jsonResponse(modelStatus);
        return jsonResponse({});
      }) as unknown as typeof fetch,
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders a suggested prompt, then result cards and a confirm control", async () => {
    render(<AssistantPage />);

    // Suggested prompt loads from the API.
    const chip = await screen.findByText("What am I missing?");
    fireEvent.click(chip);

    // The server's list row and proposal render verbatim.
    expect(await screen.findByText("Chinos")).toBeInTheDocument();
    expect(screen.getByText("need 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirm & apply/i })).toBeInTheDocument();
  });

  it("offers the local model but never loads it until asked", async () => {
    render(<AssistantPage />);

    // Mounting only reads the status; no load request is made.
    expect(await screen.findByText("Not loaded")).toBeInTheDocument();
    expect(screen.getByText("qwen2.5-0.5b-instruct-q2_k.gguf")).toBeInTheDocument();
    expect(calls).not.toContain("POST /api/assistant/model/load");

    fireEvent.click(screen.getByRole("button", { name: /Load model/i }));

    // The server's "ready" state drives the badge and the unload control.
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Unload model/i })).toBeInTheDocument();
    expect(calls).toContain("POST /api/assistant/model/load");
  });
});
