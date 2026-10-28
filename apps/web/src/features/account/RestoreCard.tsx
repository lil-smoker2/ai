/** Bring a downloaded export back.
 *
 * This is the only control in the app that can destroy records you are looking
 * at, so it is built in two steps and the second one is not possible by
 * accident. Reading the archive asks the server what it holds and what it would
 * overwrite; the restore itself needs the file, a typed word, and a fresh check
 * of both, because a preview you trusted a minute ago describes a different
 * moment. Nothing is uploaded anywhere: the file is read on this machine and
 * sent to the app's own server, the one that wrote it.
 *
 * The page states no figures of its own. Counts, warnings and the currency the
 * amounts were written in all come from the server, which is the only thing
 * that has actually opened the file.
 */
import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, Upload } from "lucide-react";
import { api, readArchive } from "../../services/api";
import type { RestorePreview, RestoreResult } from "../../types/api";

/** The same word the server expects, and the same one the reset asks for. */
const RESTORE_PHRASE = "RESTORE";

interface ArchiveFile {
  name: string;
  base64: string;
}

/** "2026-10-28T17:55:40+00:00" -> "2026-10-28". A backup's age matters more
 * than its minute, and the day needs no locale to read. */
function dayOf(stamp: string): string {
  return stamp.slice(0, 10);
}

export function RestoreCard({ tableLabels }: { tableLabels: Map<string, string> }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [archive, setArchive] = useState<ArchiveFile | null>(null);
  const [preview, setPreview] = useState<RestorePreview | null>(null);
  const [result, setResult] = useState<RestoreResult | null>(null);
  const [word, setWord] = useState("");

  // Choosing a file clears everything derived from the previous one. A stale
  // preview beside a new filename would be a lie about the file being restored.
  const read = useMutation({
    mutationFn: async (file: File): Promise<ArchiveFile> => ({
      name: file.name,
      base64: await readArchive(file),
    }),
    onSuccess: (loaded) => {
      setArchive(loaded);
      setPreview(null);
      setResult(null);
      setWord("");
    },
  });

  const inspect = useMutation({
    mutationFn: (file: ArchiveFile) =>
      api<RestorePreview>("/api/account/restore/preview", {
        body: { archive_base64: file.base64 },
      }),
    onSuccess: setPreview,
    // A refused archive has no preview, and the button must not keep one.
    onError: () => setPreview(null),
  });

  const apply = useMutation({
    mutationFn: (input: { file: ArchiveFile; confirm: string }) =>
      api<RestoreResult>("/api/account/restore", {
        body: { archive_base64: input.file.base64, confirm: input.confirm },
      }),
    onSuccess: (finished) => {
      setResult(finished);
      setPreview(null);
      setArchive(null);
      setWord("");
      if (inputRef.current) inputRef.current.value = "";
      // Every page reads from the rows that have just been replaced.
      queryClient.invalidateQueries();
    },
  });

  const canApply =
    archive !== null && preview !== null && word.trim().toUpperCase() === RESTORE_PHRASE;

  const failure = read.isError || inspect.isError || apply.isError;

  return (
    <div className="card">
      <h2>
        <Archive size={16} aria-hidden /> Bring a backup back
      </h2>
      <p className="muted">
        A restore puts the records from an exported zip back into this account.
        It replaces everything the account holds now, so read the archive first
        and check what it says.
      </p>

      <div className="restore-pick">
        <label className="confirm-field">
          Export file (.zip)
          <input
            ref={inputRef}
            type="file"
            accept=".zip,application/zip"
            aria-label="Export file"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) {
                setArchive(null);
                setPreview(null);
                return;
              }
              read.mutate(file);
            }}
          />
        </label>
        <button
          className="btn"
          type="button"
          disabled={!archive || inspect.isPending}
          onClick={() => archive && inspect.mutate(archive)}
        >
          <Upload size={16} aria-hidden />
          {inspect.isPending ? "Reading…" : "Read the archive"}
        </button>
      </div>

      {read.isPending && <p className="muted">Reading the file…</p>}
      {archive && !read.isPending && (
        <p className="muted">
          Selected <strong>{archive.name}</strong>.
        </p>
      )}
      {!archive && !read.isPending && !result && (
        <p className="muted">No file selected.</p>
      )}

      {preview && (
        <div className="restore-preview">
          <p>
            <strong>
              {preview.archive_total} record{preview.archive_total === 1 ? "" : "s"} in that
              file
            </strong>
            {preview.generated_at
              ? `, written on ${dayOf(preview.generated_at)}.`
              : ". The file does not say when it was written."}{" "}
            {preview.current_total === 0
              ? "Your account holds nothing now, so nothing is overwritten."
              : `It would replace the ${preview.current_total} record${
                  preview.current_total === 1 ? "" : "s"
                } you have now.`}
          </p>
          <ul className="stored-list">
            {preview.tables.map((table) => (
              <li key={table.key}>
                {table.label}{" "}
                <span>
                  {table.archive_rows} in the file · {table.current_rows} now
                </span>
              </li>
            ))}
          </ul>
          {preview.warnings.length > 0 && (
            <ul className="restore-warnings" role="status">
              {preview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}

          <div className="btn-row">
            <label className="confirm-field">
              Type {RESTORE_PHRASE} to confirm
              <input
                value={word}
                onChange={(event) => setWord(event.target.value)}
                placeholder={RESTORE_PHRASE}
                autoComplete="off"
              />
            </label>
            <button
              className="btn danger"
              type="button"
              disabled={!canApply || apply.isPending}
              title={canApply ? undefined : "Read the archive and type RESTORE first"}
              onClick={() => archive && apply.mutate({ file: archive, confirm: word.trim().toUpperCase() })}
            >
              {apply.isPending ? "Restoring…" : "Put my records back"}
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="reset-result" role="status">
          <strong>
            Restored {result.written_total} record{result.written_total === 1 ? "" : "s"}.
          </strong>
          {result.replaced_total > 0 && (
            <p className="muted">
              {result.replaced_total} record{result.replaced_total === 1 ? "" : "s"} previously in
              the account were replaced.
            </p>
          )}
          <ul className="stored-list">
            {Object.entries(result.written)
              .filter(([, rows]) => rows > 0)
              .map(([key, rows]) => (
                <li key={key}>
                  {tableLabels.get(key) ?? key} <span>{rows}</span>
                </li>
              ))}
          </ul>
          {result.currency_changed_from && (
            <p className="muted">
              The amounts were written in {result.currency}, so the account was
              switched from {result.currency_changed_from} to {result.currency}.
            </p>
          )}
          {result.photo_links_cleared > 0 && (
            <p className="muted">
              {result.photo_links_cleared} picture link
              {result.photo_links_cleared === 1 ? "" : "s"} could not be kept
              because the picture is not in this machine's index. The records
              themselves came back.
            </p>
          )}
          {result.warnings.map((warning) => (
            <p className="muted" key={warning}>
              {warning}
            </p>
          ))}
          <p className="muted">{result.note}</p>
          <p className="muted">Kept: {result.kept.join(", ")}.</p>
        </div>
      )}

      {failure && (
        <p className="error-banner" role="alert">
          {(read.error ?? inspect.error ?? apply.error)?.message}
        </p>
      )}
      {inspect.isError && (
        <p className="muted">
          Nothing was changed. Pick a different file, or download a fresh export.
        </p>
      )}
      {apply.isError && <p className="muted">Nothing was changed.</p>}
    </div>
  );
}
