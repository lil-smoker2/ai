/** Images gallery smoke test: it renders exactly what the asset API returns
 * (server-side categories, metadata and analysis) and never invents a picture
 * — an asset without a usable thumbnail stays a labelled placeholder. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ImagesPage } from "./ImagesPage";
import { setToken } from "../services/api";
import type { Asset, AssetPage } from "../types/api";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const jeans: Asset = {
  id: "a1",
  original_filename: "jeans-black.jpeg",
  category: "clothing/jeans",
  format: "JPEG",
  width: 447,
  height: 447,
  size_bytes: 19408,
  status: "active",
  duplicate_of: null,
  attribution: null,
  license: null,
  last_seen_at: "2026-10-01T00:00:00Z",
  analysis: {
    predicted_category: "clothing",
    predicted_item_type: "jeans",
    confidence: 0.82,
    attributes: null,
    source: "folder",
  },
};

const unanalysed: Asset = {
  ...jeans,
  id: "a2",
  original_filename: "mystery.jpg",
  category: "household/plates",
  analysis: null,
};

const page: AssetPage = {
  assets: [jeans, unanalysed],
  page: { total: 2, page: 1, page_size: 18 },
};

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/api/assets/categories")) {
      return jsonResponse(["clothing/jeans", "household/plates"]);
    }
    if (url.includes("/thumbnail")) return jsonResponse({});
    if (url.includes("/api/assets")) return jsonResponse(page);
    return jsonResponse({});
  }) as unknown as typeof fetch;
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ImagesPage />
    </QueryClientProvider>,
  );
}

describe("ImagesPage", () => {
  // jsdom has no object-URL support, so stub the two calls fetchObjectUrl makes.
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  beforeEach(() => {
    setToken("test-token");
    vi.stubGlobal("fetch", mockFetch());
    URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
  });
  afterEach(() => {
    setToken(null);
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    vi.unstubAllGlobals();
  });

  it("lists indexed pictures with their server-supplied metadata", async () => {
    renderPage();

    expect(await screen.findByText("jeans-black.jpeg")).toBeInTheDocument();
    // Dimensions, format and size are shown exactly as the scanner recorded them.
    expect(screen.getByText("447×447 · JPEG · 19 KB")).toBeInTheDocument();
    expect(screen.getByText(/jeans · 82%/)).toBeInTheDocument();

    // An asset the pipeline never analysed must not borrow a confident label.
    expect(screen.getByText("mystery.jpg")).toBeInTheDocument();
    expect(screen.getByText("not analysed")).toBeInTheDocument();
  });

  it("offers the server's categories as filters and a rescan control", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: "clothing/jeans" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "household/plates" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rescan library/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "household/plates" }));
    expect(screen.getByRole("button", { name: "household/plates" })).toHaveClass("active");
  });
});
