/**
 * Settings page: who LifeSmart has on file, what is actually connected, and how
 * to take the data away, bring it back, or start again.
 *
 * Every claim on this screen is the server's, not the page's. The integration
 * list states per capability whether it works now, only runs when you start it,
 * is something you do by hand, is switched off, or does not exist in this
 * product - so nothing here can imply an M-PESA, bank or shop connection the
 * app does not have. The same rule reaches the data section: a stored row is
 * counted, an unknown stays unstated, and the account's own sign-in identity is
 * shown but never editable.
 *
 * A restore is the one control here that can destroy records you are looking
 * at, so it lives in features/account/RestoreCard, reads the archive before it
 * offers the button, and takes every figure from the server rather than
 * claiming any of its own.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  Bell,
  Database,
  Download,
  HardDrive,
  Plug,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  User,
} from "lucide-react";
import { api, downloadFile } from "../services/api";
import { RestoreCard } from "../features/account/RestoreCard";
import type {
  IntegrationStatus,
  ResetResult,
  SettingsView,
  User as Profile,
} from "../types/api";

const CURRENCIES = ["KES", "UGX", "TZS", "RWF", "NGN", "USD", "EUR", "GBP"];
const COUNTRIES = ["Kenya", "Uganda", "Tanzania", "Rwanda", "Nigeria", "Other"];

/** The vocabulary the server uses, in the user's words. The tone classes are the
 * existing badge colours: green = works, indigo = you start it, amber = manual
 * or off, red = does not exist. */
const STATUS_META: Record<IntegrationStatus, { label: string; tone: string }> = {
  available: { label: "Working", tone: "active" },
  on_demand: { label: "Only when you start it", tone: "transfer" },
  manual: { label: "You do this", tone: "partial" },
  not_configured: { label: "Switched off", tone: "warn" },
  unavailable: { label: "Not available", tone: "expense" },
};

/** Plain-language meaning of each status, shown once as a legend. */
const STATUS_TEXT: Record<IntegrationStatus, string> = {
  available: "works as it says",
  on_demand: "present, runs only when you start it",
  manual: "you do the work, the app records it",
  not_configured: "built, but switched off here",
  unavailable: "no such connection exists",
};

const LEGEND: IntegrationStatus[] = [
  "available",
  "on_demand",
  "manual",
  "not_configured",
  "unavailable",
];

interface ProfileForm {
  full_name: string;
  currency: string;
  country: string;
  timezone: string;
  /** Tri-state: a person may prefer not to say they are a student. */
  student: "unknown" | "yes" | "no";
}

function toProfileForm(profile: Profile): ProfileForm {
  return {
    full_name: profile.full_name,
    currency: profile.currency,
    country: profile.country,
    timezone: profile.timezone,
    student:
      profile.is_student === null ? "unknown" : profile.is_student ? "yes" : "no",
  };
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [confirmWord, setConfirmWord] = useState("");
  const [resetResult, setResetResult] = useState<ResetResult | null>(null);

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<SettingsView>("/api/settings"),
  });

  const initialProfile = settings.data?.profile;
  const form = useForm<ProfileForm>({
    values: initialProfile ? toProfileForm(initialProfile) : undefined,
  });

  const saveProfile = useMutation({
    mutationFn: (v: ProfileForm) =>
      api<Profile>("/api/auth/me", {
        method: "PATCH",
        body: {
          full_name: v.full_name.trim(),
          currency: v.currency,
          country: v.country,
          timezone: v.timezone.trim(),
          is_student: v.student === "unknown" ? null : v.student === "yes",
        },
      }),
    onSuccess: () => {
      // Currency labels every figure in the app, so the cached pages are
      // dropped rather than left showing the old symbol.
      queryClient.invalidateQueries();
    },
  });

  const exportData = useMutation({
    mutationFn: () =>
      downloadFile("/api/account/export", {}, "lifesmart-export.zip"),
    onSuccess: () => setExportMsg("Saved to your downloads. Built on this machine."),
    onError: (e) => setExportMsg(`Download failed: ${e.message}`),
  });

  const resetAccount = useMutation({
    mutationFn: (word: string) =>
      api<ResetResult>("/api/account/reset", { body: { confirm: word } }),
    onSuccess: (result) => {
      setResetResult(result);
      setConfirmWord("");
      setExportMsg(null);
      queryClient.invalidateQueries();
    },
  });

  if (settings.isPending) return <div className="page-loading">Loading…</div>;
  if (settings.error || !settings.data) {
    return (
      <div>
        <div className="page-header">
          <h1>Settings</h1>
        </div>
        <p className="error-banner" role="alert">
          Could not read your settings: {settings.error?.message ?? "no response"}
        </p>
      </div>
    );
  }

  const { profile, preferences, integrations, privacy, export_note: exportNote } =
    settings.data;
  const filled = privacy.stored.filter((t) => t.rows > 0);
  const emptyKinds = privacy.stored.length - filled.length;
  // The reset report names tables in the user's words, never as a column key.
  const tableLabels = new Map(privacy.stored.map((t) => [t.key, t.label]));
  // How many of the five switches are on. Settings states the number and hands
  // the naming to the Notifications page: the switches have their own labels
  // there, and a second list of names here would only drift from them.
  const remindersOn = [
    preferences.deadline_alerts,
    preferences.task_reminders,
    preferences.fee_due_alerts,
    preferences.low_stock_warnings,
    preferences.savings_nudges,
  ].filter(Boolean).length;
  const canReset = confirmWord.trim().toUpperCase() === "RESET";

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p className="muted">
          Your profile, what LifeSmart is connected to, and your data.
        </p>
      </div>

      {/* --- Profile --- */}
      <form
        className="card auth-form"
        onSubmit={form.handleSubmit((v) => saveProfile.mutate(v))}
      >
        <h2>
          <User size={16} aria-hidden /> Your profile
        </h2>
        <label>
          Name shown to you
          <input
            {...form.register("full_name", {
              required: "A name is needed - it appears in the top bar",
            })}
          />
        </label>
        {form.formState.errors.full_name && (
          <span className="field-error">
            {form.formState.errors.full_name.message}
          </span>
        )}

        <label>
          Sign-in identity
          <input value={profile.email} readOnly aria-readonly="true" />
          <span className="field-note">
            Not editable here. This is the address the account is filed under, so
            changing it would change how - or whether - you sign back in.
          </span>
        </label>

        <div className="btn-row">
          <label>
            Currency
            <select {...form.register("currency")}>{CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}</select>
          </label>
          <label>
            Country
            <select {...form.register("country")}>{COUNTRIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}</select>
          </label>
        </div>
        <label>
          Timezone
          <input placeholder="Africa/Nairobi" {...form.register("timezone", {
            required: "Reminders need a timezone",
          })} />
          <span className="field-note">
            Used for the dates and reminder times in this app only. It does not
            reach a device clock.
          </span>
        </label>
        {form.formState.errors.timezone && (
          <span className="field-error">{form.formState.errors.timezone.message}</span>
        )}

        <label>
          Student
          <select {...form.register("student")}>
            <option value="unknown">Not specified</option>
            <option value="yes">Yes - show Student Life</option>
            <option value="no">No</option>
          </select>
        </label>

        {saveProfile.isError && (
          <p className="error-banner" role="alert">
            {(saveProfile.error as Error).message}
          </p>
        )}
        {saveProfile.isSuccess && (
          <p className="muted" role="status">Saved.</p>
        )}

        <button className="btn primary" type="submit" disabled={saveProfile.isPending}>
          {saveProfile.isPending ? "Saving…" : "Save profile"}
        </button>
      </form>

      {/* --- Reminders --- */}
      <div className="card">
        <h2>
          <Bell size={16} aria-hidden /> Reminders
        </h2>
        <p className="muted">
          {remindersOn === 0
            ? "None of the five reminders are switched on."
            : `${remindersOn} of 5 reminders are switched on.`}{" "}
          {(preferences.quiet_start || preferences.quiet_end) &&
            `Quiet hours ${preferences.quiet_start ?? "-"} to ${preferences.quiet_end ?? "-"}.`}
        </p>
        <p className="muted">
          These gate reminders inside this app. No email, SMS or push is sent -
          see &quot;Email, SMS and push alerts&quot; below.
        </p>
        <Link className="btn" to="/app/notifications">
          Change reminder preferences
        </Link>
      </div>

      {/* --- Integrations --- */}
      <div className="card">
        <h2>
          <Plug size={16} aria-hidden /> Connected integrations
        </h2>
        <p className="legend">
          <span className="muted">What the labels mean: </span>
          {LEGEND.map((status) => (
            <span key={status}>
              <span className={`badge ${STATUS_META[status].tone}`}>
                {STATUS_META[status].label}
              </span>{" "}
              <span className="muted">{STATUS_TEXT[status]}</span>
            </span>
          ))}
        </p>

        {integrations.map((integration) => (
          <div className="integration-row" key={integration.key}>
            <div>
              <strong>{integration.label}</strong>
              <p>{integration.detail}</p>
              {integration.action && (
                <p className="integration-action">{integration.action}</p>
              )}
            </div>
            <span className={`badge ${STATUS_META[integration.status].tone}`}>
              {STATUS_META[integration.status].label}
            </span>
          </div>
        ))}
        <p className="muted">
          Not built yet, so not shown as a choice: appearance and language
          settings, cloud sync, and a password to reset.
        </p>
      </div>

      {/* --- Your data --- */}
      <div className="card">
        <h2>
          <Database size={16} aria-hidden /> Your data
        </h2>
        <div className="inline-stats">
          <div>
            <span className="stat-label">Rows in your account</span>
            <strong>{privacy.row_total}</strong>
            <span className="stat-note">
              {filled.length === 0
                ? "Nothing recorded yet"
                : `across ${filled.length} kind${filled.length === 1 ? "" : "s"}`}
            </span>
          </div>
          <div>
            <span className="stat-label">Stored on</span>
            <strong>{privacy.local_only ? "This machine" : "The app's database"}</strong>
            <span className="stat-note">
              {privacy.local_only
                ? "One database file; nothing is uploaded"
                : "This deployment is not the single-user desktop app"}
            </span>
          </div>
        </div>

        {filled.length > 0 ? (
          <ul className="stored-list">
            {filled.map((table) => (
              <li key={table.key}>
                {table.label} <span>{table.rows}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            Only the starter inventory categories are in place so far.
          </p>
        )}
        {emptyKinds > 0 && (
          <p className="muted">
            {emptyKinds} further kind{emptyKinds === 1 ? "" : "s"} of record are
            stored in the same table layout but hold nothing yet.
          </p>
        )}
        {privacy.excluded.map((table) => (
          <p className="muted" key={table.key}>
            <ShieldCheck size={13} aria-hidden /> {table.label}: {table.reason}
          </p>
        ))}
        {privacy.data_dir && (
          <p className="muted">
            <HardDrive size={13} aria-hidden /> Data folder:{" "}
            <code>{privacy.data_dir}</code>
          </p>
        )}

        <ul className="privacy-statement">
          {privacy.statement.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>

        <div className="btn-row">
          <button
            className="btn primary"
            onClick={() => exportData.mutate()}
            disabled={exportData.isPending}
          >
            <Download size={16} aria-hidden />
            {exportData.isPending ? "Building…" : "Download everything"}
          </button>
        </div>
        {exportMsg && <p className="muted" role="status">{exportMsg}</p>}
        <p className="muted">{exportNote}</p>
      </div>

      {/* --- Restore --- */}
      <RestoreCard tableLabels={tableLabels} />

      {/* --- Danger zone --- */}
      <div className="card danger-zone">
        <h2>
          <TriangleAlert size={16} aria-hidden /> Start again
        </h2>
        <p>
          This deletes every record in your account: items, prices, transactions,
          goals, savings, tasks, shopping lists, student records, conversations
          and saved net worth. It cannot be undone from inside the app.
        </p>
        <p className="muted">
          It keeps your sign-in and profile details, leaves your image files and
          the picture index where they are, and restores the starter inventory
          categories. Download an export first if you want a copy: an export you
          have already saved can be put back above.
        </p>

        {resetResult ? (
          <div className="reset-result" role="status">
            <strong>
              Deleted {resetResult.deleted_total} record
              {resetResult.deleted_total === 1 ? "" : "s"}.
            </strong>
            <ul className="stored-list">
              {Object.entries(resetResult.deleted)
                .filter(([, rows]) => rows > 0)
                .map(([key, rows]) => (
                  <li key={key}>
                    {tableLabels.get(key) ?? key} <span>{rows}</span>
                  </li>
                ))}
            </ul>
            <p className="muted">{resetResult.note}</p>
            <p className="muted">Kept: {resetResult.kept.join(", ")}.</p>
          </div>
        ) : (
          <div className="btn-row">
            <label className="confirm-field">
              Type RESET to confirm
              <input
                value={confirmWord}
                onChange={(e) => setConfirmWord(e.target.value)}
                placeholder="RESET"
                autoComplete="off"
              />
            </label>
            <button
              className="btn danger"
              onClick={() => resetAccount.mutate(confirmWord.trim().toUpperCase())}
              disabled={!canReset || resetAccount.isPending}
              title={canReset ? undefined : "Type RESET first"}
            >
              <Trash2 size={16} aria-hidden />
              {resetAccount.isPending ? "Deleting…" : "Delete my records"}
            </button>
          </div>
        )}
        {resetAccount.isError && (
          <p className="error-banner" role="alert">
            {(resetAccount.error as Error).message}
          </p>
        )}
      </div>
    </div>
  );
}
