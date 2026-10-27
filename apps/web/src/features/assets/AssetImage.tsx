/**
 * AssetImage - the ONLY way images reach the UI.
 * Requests candidates from the dynamic asset API and renders a stable
 * thumbnail; falls back to a neutral placeholder. No filenames or URLs are
 * ever hardcoded.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { api, fetchObjectUrl } from "../../services/api";
import type { Asset, AssetPage } from "../../types/api";

interface Props {
  /** e.g. "clothing/trousers". Category folders are dynamic. */
  category?: string;
  /**
   * A known asset id, already chosen for this row (an item's pinned picture or
   * the server's category match). It wins over the lookup below.
   */
  assetId?: string | null;
  /** Stable selection per inventory item id (hash pick, never random). */
  seed?: string | number;
  size?: number;
  alt?: string;
}

function pickStable(assets: Asset[], seed?: string | number): Asset | undefined {
  if (assets.length === 0) return undefined;
  if (seed === undefined) return assets[0];
  const idx = Math.abs(String(seed).split("").reduce((a, c) => a + c.charCodeAt(0), 0)) % assets.length;
  return assets[idx];
}

export function AssetImage({ category, assetId, seed, size = 48, alt }: Props) {
  const [url, setUrl] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["assets", category],
    queryFn: () =>
      api<AssetPage>("/api/assets", { params: { category, page_size: 12 } }),
    // No request when the caller already knows which picture this row shows.
    enabled: !assetId && !!category,
    staleTime: 60_000,
  });

  const assetIdResolved =
    assetId ?? (data ? pickStable(data.assets, seed)?.id : undefined);

  useEffect(() => {
    if (!assetIdResolved) return;
    let active = true;
    let objectUrl = "";
    fetchObjectUrl(`/api/assets/${assetIdResolved}/thumbnail`)
      .then((u) => {
        objectUrl = u;
        if (active) setUrl(u);
      })
      .catch(() => active && setUrl(null));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [assetIdResolved]);

  if (url) {
    return (
      <img
        src={url}
        alt={alt ?? category ?? "LifeSmart image"}
        width={size}
        height={size}
        loading="lazy"
        className="asset-image"
      />
    );
  }
  return (
    <span
      className="asset-placeholder"
      style={{ width: size, height: size }}
      role="img"
      aria-label={alt ?? "No image available"}
    >
      <ImageOff size={Math.round(size / 2)} />
    </span>
  );
}
