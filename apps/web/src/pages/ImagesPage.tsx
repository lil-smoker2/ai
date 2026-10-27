/** Images: everything the asset pipeline has discovered.
 *
 * A read-only browse over the dynamic asset API. Categories come from the
 * folder tree, so a new drop-folder shows up here after a rescan with no code
 * change and no renamed files. Rejected files (unreadable or unsupported) are
 * visible too, because hiding them makes a missing picture impossible to
 * diagnose. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "../services/api";
import { AssetThumb } from "../features/assets/AssetThumb";
import type { Asset, AssetPage, ScanStatus } from "../types/api";

const PAGE_SIZE = 18;
const STATUSES = ["active", "duplicate", "corrupted", "missing"] as const;
type StatusFilter = (typeof STATUSES)[number];

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.round(bytes / 1000)} KB`;
}

function ImageCard({ asset }: { asset: Asset }) {
  const analysis = asset.analysis;
  return (
    <div className="card image-card">
      <AssetThumb assetId={asset.id} alt={asset.original_filename} />
      <div className="image-card-info">
        <strong title={asset.original_filename}>{asset.original_filename}</strong>
        <span className="muted">{asset.category}</span>
        <span className="muted">
          {asset.width}×{asset.height} · {asset.format} · {formatBytes(asset.size_bytes)}
        </span>
        {analysis ? (
          <span className="badge">
            {analysis.predicted_item_type ?? analysis.predicted_category ?? "analysed"}{" "}
            · {Math.round(analysis.confidence * 100)}%
          </span>
        ) : (
          <span className="muted">not analysed</span>
        )}
        {asset.status !== "active" && <span className="badge warn">{asset.status}</span>}
      </div>
    </div>
  );
}

export function ImagesPage() {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("active");
  const [page, setPage] = useState(1);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  const categories = useQuery({
    queryKey: ["asset-categories"],
    queryFn: () => api<string[]>("/api/assets/categories"),
  });

  const assets = useQuery({
    queryKey: ["assets", category, status, page],
    queryFn: () =>
      api<AssetPage>("/api/assets", {
        params: { category: category ?? undefined, status, page, page_size: PAGE_SIZE },
      }),
  });

  const scan = useMutation({
    mutationFn: async () => {
      await api("/api/assets/scan", { body: {} });
      let s = await api<ScanStatus>("/api/assets/scan/status");
      for (let i = 0; i < 50 && s.state === "running"; i++) {
        await new Promise((r) => setTimeout(r, 300));
        s = await api<ScanStatus>("/api/assets/scan/status");
      }
      return s;
    },
    onSuccess: (s) => {
      setScanMsg(
        s.state === "completed"
          ? `Scan complete: ${s.new} new, ${s.updated} updated, ${s.duplicates} duplicate, ${s.corrupted} rejected, ${s.removed} gone`
          : `Scan failed: ${s.error ?? "unknown error"}`,
      );
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["asset-categories"] });
    },
    onError: (e) => setScanMsg(e.message),
  });

  const total = assets.data?.page.total ?? 0;
  const shown = assets.data?.assets.length ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function choose(next: string | null) {
    setCategory(next);
    setPage(1);
  }

  return (
    <div>
      <div className="page-header">
        <h1>Images</h1>
        <button
          className="btn"
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
        >
          <RefreshCw size={16} aria-hidden />
          {scan.isPending ? "Scanning…" : "Rescan library"}
        </button>
      </div>

      <p className="muted">
        These are the pictures LifeSmart found in your image folders, indexed by
        folder path. Drop files in and rescan — filenames are never changed and
        new folders are picked up automatically. Nothing here is generated or
        simulated.
      </p>

      {scanMsg && <p className="muted">{scanMsg}</p>}
      {assets.error && (
        <p className="error-banner">Could not load images: {assets.error.message}</p>
      )}

      <div className="chip-row filter-row">
        <button
          className={category === null ? "chip active" : "chip"}
          onClick={() => choose(null)}
        >
          All categories
        </button>
        {(categories.data ?? []).map((c) => (
          <button
            key={c}
            className={category === c ? "chip active" : "chip"}
            onClick={() => choose(c)}
          >
            {c}
          </button>
        ))}
        <label className="status-filter">
          <span className="muted">Show</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as StatusFilter);
              setPage(1);
            }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {assets.isPending && <p className="muted">Loading…</p>}

      {assets.data && shown === 0 && (
        <div className="card empty-state">
          <p>
            {status === "active"
              ? "No images indexed yet for this filter. Add pictures to your LifeSmart image folder and press Rescan library."
              : `No ${status} images — that is usually good news.`}
          </p>
        </div>
      )}

      {shown > 0 && (
        <>
          <div className="image-grid">
            {(assets.data?.assets ?? []).map((asset) => (
              <ImageCard key={asset.id} asset={asset} />
            ))}
          </div>
          <div className="btn-row spaced pager">
            <span className="muted">
              {total === 0 ? "0 images" : `Page ${page} of ${pages} · ${total} images`}
            </span>
            <div className="btn-row">
              <button
                className="btn"
                disabled={page <= 1 || scan.isPending}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <button
                className="btn"
                disabled={page >= pages || scan.isPending}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
