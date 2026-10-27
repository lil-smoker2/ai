/**
 * AssetThumb - the thumbnail for one specific asset id.
 *
 * AssetImage (the sibling helper) picks *a* picture for a product category;
 * this one shows a *known* asset, which is what the Images gallery needs.
 * Pixels still come only from the authenticated asset endpoint - ids are the
 * only thing ever passed around, never a filename or a server path.
 */
import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { fetchObjectUrl } from "../../services/api";

interface Props {
  assetId: string;
  alt: string;
  /** Rendered square; the source is never upscaled by the API. */
  size?: number;
}

export function AssetThumb({ assetId, alt, size = 160 }: Props) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    setUrl(null);
    fetchObjectUrl(`/api/assets/${assetId}/thumbnail`)
      .then((u) => {
        objectUrl = u;
        if (active) setUrl(u);
      })
      .catch(() => active && setUrl(null));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [assetId]);

  if (url) {
    return (
      <img
        src={url}
        alt={alt}
        width={size}
        height={size}
        loading="lazy"
        className="asset-image gallery-thumb"
      />
    );
  }
  return (
    <span
      className="asset-placeholder gallery-thumb"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`No preview for ${alt}`}
    >
      <ImageOff size={Math.round(size / 4)} />
    </span>
  );
}
