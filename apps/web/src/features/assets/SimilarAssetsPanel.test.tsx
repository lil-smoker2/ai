/** Similar-picture panel: it renders exactly the groups the perceptual endpoint
 * reports and says so plainly when there are none — it never invents a match or
 * pads the empty case. Thumbnails come only through the asset-id endpoint, so a
 * member with no preview stays a labelled placeholder, never a guessed image. */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SimilarAssetsPanel } from "./SimilarAssetsPanel";
import { setToken } from "../../services/api";
import type { SimilarAssets } from "../../types/api";

const withGroups: SimilarAssets = {
  threshold: 10,
  hash_bits: 64,
  groups: [
    {
      members: [
        { id: "1", original_filename: "IMG_0001.png", category: "clothing/shirts" },
        { id: "2", original_filename: "re-saved.jpg", category: "clothing/shirts" },
        { id: "3", original_filename: "big.png", category: "transport/cars" },
      ],
    },
    {
      members: [
        { id: "4", original_filename: "patternA.png", category: "household/plates" },
        { id: "5", original_filename: "patternB.png", category: "household/plates" },
      ],
    },
  ],
};

const empty: SimilarAssets = { threshold: 10, hash_bits: 64, groups: [] };

describe("SimilarAssetsPanel", () => {
  beforeEach(() => {
    setToken("test-token");
    URL.createObjectURL = vi.fn(() => "blob:mock") as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
  });
  afterEach(() => {
    setToken(null);
    vi.restoreAllMocks();
  });

  it("lists every group with its members and the reported threshold", () => {
    render(<SimilarAssetsPanel data={withGroups} />);

    // One heading per group, counting its own members.
    expect(screen.getByText("3 pictures look alike")).toBeInTheDocument();
    expect(screen.getByText("2 pictures look alike")).toBeInTheDocument();

    // Member filenames are shown exactly as the server named them.
    expect(screen.getByText("IMG_0001.png")).toBeInTheDocument();
    expect(screen.getByText("re-saved.jpg")).toBeInTheDocument();
    expect(screen.getByText("patternB.png")).toBeInTheDocument();

    // The honesty note carries the real bit width and threshold, not a constant.
    expect(screen.getAllByText(/within 10 of 64 shape bits/)).toHaveLength(2);
  });

  it("reports an empty library as having no look-alikes", () => {
    render(<SimilarAssetsPanel data={empty} />);

    expect(screen.getByText(/no near-duplicates/i)).toBeInTheDocument();
    expect(screen.queryByText(/pictures look alike$/)).not.toBeInTheDocument();
  });
});
