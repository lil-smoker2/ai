/** Pictures that look alike but are not the same file.

 * The list is the backend's reading of the image library through a deterministic
 * perceptual hash: each group is two or more genuinely different files - a
 * re-save, a resize, a light edit - that share a shape. Byte-for-byte copies are
 * folded away earlier by the content hash, so they never show up here. Nothing is
 * invented: while the check runs we say so, and when the library holds no look-
 * alikes the panel says so plainly instead of padding the page. */
import { useQuery } from "@tanstack/react-query";
import { api } from "../../services/api";
import type { SimilarAssets, SimilarGroup } from "../../types/api";
import { AssetThumb } from "../assets/AssetThumb";

export function SimilarAssetsPanel({ data }: { data: SimilarAssets }) {
  if (data.groups.length === 0) {
    return (
      <p className="muted">
        No two pictures look alike beyond an exact copy. Nothing was merged or
        hidden to reach that — the library simply holds no near-duplicates.
      </p>
    );
  }

  return (
    <div className="similar-groups">
      {data.groups.map((group, index) => (
        <SimilarGroupBlock
          key={index}
          group={group}
          threshold={data.threshold}
          hashBits={data.hash_bits}
        />
      ))}
    </div>
  );
}

function SimilarGroupBlock({
  group,
  threshold,
  hashBits,
}: {
  group: SimilarGroup;
  threshold: number;
  hashBits: number;
}) {
  return (
    <div className="similar-group">
      <div className="similar-group-header">
        <strong>{group.members.length} pictures look alike</strong>
        <span className="badge">near-duplicate</span>
      </div>
      <div className="similar-members">
        {group.members.map((member) => (
          <div className="similar-member" key={member.id}>
            <AssetThumb
              assetId={member.id}
              alt={member.original_filename}
              size={120}
            />
            <strong title={member.original_filename}>{member.original_filename}</strong>
            <span className="muted">{member.category}</span>
          </div>
        ))}
      </div>
      <span className="muted similar-note">
        {`Different files within ${threshold} of ${hashBits} shape bits \u2014 never an exact copy.`}
      </span>
    </div>
  );
}

/** Wrapper that owns the query so the gallery stays a thin composition. The
 * check reads every file on demand, so it is fetched only when the panel is
 * mounted, and shares the app-wide query key like every other read. */
export function SimilarAssetsSection() {
  const similar = useQuery({
    queryKey: ["assets", "similar"],
    queryFn: () => api<SimilarAssets>("/api/assets/similar"),
  });

  return (
    <section className="similar-assets">
      <h2>Pictures that look alike</h2>
      <p className="muted">
        Exact duplicates are already folded to one picture by the content hash.
        These are the harder case: the same shot re-saved, resized or lightly
        edited under different names.
      </p>
      {similar.isPending && <p className="muted">Checking…</p>}
      {similar.error && (
        <p className="error-banner">
          Could not check for similar pictures: {similar.error.message}
        </p>
      )}
      {similar.data && <SimilarAssetsPanel data={similar.data} />}
    </section>
  );
}
