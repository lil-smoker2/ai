/** What needs attention today, and the switches that decide what counts.
 *
 * The list is computed by the app from the records already saved: no alert is
 * stored anywhere, so completing a task, paying a fee or restocking an item
 * makes its entry disappear on the next load rather than lingering as an unread
 * message. The switches below are what that computation reads - the only thing
 * they have ever controlled. Nothing here sends email or push.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { BellRing, RefreshCw } from "lucide-react";
import { api } from "../services/api";
import { AlertRow, KIND_LABELS } from "../features/notifications/AlertRow";
import type {
  NotificationPreference,
  AlertsResponse,
} from "../types/api";

const TOGGLES: { key: keyof NotificationPreference; label: string }[] = [
  { key: "deadline_alerts", label: "Goal deadline alerts" },
  { key: "task_reminders", label: "Task reminders" },
  { key: "fee_due_alerts", label: "Fee due alerts" },
  { key: "low_stock_warnings", label: "Low-stock warnings" },
  { key: "savings_nudges", label: "Savings pace nudges" },
];

interface FormValues {
  deadline_alerts: boolean;
  task_reminders: boolean;
  fee_due_alerts: boolean;
  low_stock_warnings: boolean;
  savings_nudges: boolean;
  quiet_start: string;
  quiet_end: string;
}

function AttentionList() {
  const alerts = useQuery({
    queryKey: ["notification-alerts"],
    queryFn: () => api<AlertsResponse>("/api/notifications/alerts"),
  });

  if (alerts.isPending) return <p className="muted">Checking your records…</p>;
  if (alerts.isError) {
    return (
      <p className="error-banner" role="alert">
        {(alerts.error as Error).message}
      </p>
    );
  }

  const data = alerts.data;
  // A response that is not the shape expected (an older server, a stubbed
  // fetch) says so instead of rendering an empty list, which would read as
  // "all clear" when it actually means "unknown".
  if (!data || !Array.isArray(data.alerts)) {
    return <p className="muted">The app could not read what needs attention.</p>;
  }

  return (
    <div className="card">
      <div className="btn-row spaced">
        <h2>
          <BellRing size={16} aria-hidden /> What needs attention today
        </h2>
        <button
          className="btn small ghost"
          onClick={() => alerts.refetch()}
          disabled={alerts.isFetching}
        >
          <RefreshCw size={14} aria-hidden /> {alerts.isFetching ? "Checking…" : "Check again"}
        </button>
      </div>
      <p className="muted">
        Built from your saved records as at {data.generated_on}
        {data.in_quiet_hours && data.quiet_ends_at
          ? ` · quiet hours until ${data.quiet_ends_at}, so the sidebar shows no count`
          : ""}
        .
      </p>

      {data.count === 0 ? (
        <p className="muted">
          {data.hidden_by_preferences.length > 0
            ? `Nothing needs you right now. ${data.hidden_by_preferences
                .map((k) => KIND_LABELS[k])
                .join(", ")} are switched off below, so their alerts are not shown.`
            : "Nothing in your records needs attention today. This list is built from what you have saved, so a deadline you never recorded cannot appear in it."}
        </p>
      ) : (
        data.alerts.map((alert) => (
          <AlertRow key={alert.key} alert={alert} currency={data.currency} />
        ))
      )}
    </div>
  );
}

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const prefs = useQuery({
    queryKey: ["notification-preferences"],
    queryFn: () => api<NotificationPreference>("/api/notifications/preferences"),
  });

  const form = useForm<FormValues>({ values: (prefs.data as FormValues) ?? undefined });

  const save = useMutation({
    mutationFn: (v: FormValues) =>
      api<NotificationPreference>("/api/notifications/preferences", {
        method: "PUT",
        body: {
          deadline_alerts: v.deadline_alerts,
          task_reminders: v.task_reminders,
          fee_due_alerts: v.fee_due_alerts,
          low_stock_warnings: v.low_stock_warnings,
          savings_nudges: v.savings_nudges,
          quiet_start: v.quiet_start || null,
          quiet_end: v.quiet_end || null,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notification-preferences"] });
      // The switches decide what the list may contain, so saving them changes it.
      queryClient.invalidateQueries({ queryKey: ["notification-alerts"] });
    },
  });

  return (
    <div>
      <div className="page-header">
        <h1>Notifications</h1>
      </div>

      <AttentionList />

      {prefs.isPending && <p className="muted">Loading…</p>}

      {prefs.data && (
        <form className="card auth-form" onSubmit={form.handleSubmit((v) => save.mutate(v))}>
          <h2>What should LifeSmart remind me about?</h2>
          <p className="muted">
            These control the list above and nothing else. No external email or push is
            sent, because this app does not leave your machine.
          </p>
          {TOGGLES.map(({ key, label }) => (
            <label key={key} className="field-inline">
              <input type="checkbox" {...form.register(key as keyof FormValues)} />
              {label}
            </label>
          ))}

          <div className="btn-row">
            <label>
              Quiet hours start (optional)
              <input type="time" {...form.register("quiet_start")} />
            </label>
            <label>
              Quiet hours end (optional)
              <input type="time" {...form.register("quiet_end")} />
            </label>
          </div>
          <p className="field-hint">
            Quiet hours only hide the count in the sidebar. The list above stays readable,
            because nothing interrupts you on this app anyway.
          </p>

          {save.isError && (
            <p className="error-banner" role="alert">{(save.error as Error).message}</p>
          )}
          {save.isSuccess && <p className="muted">Saved.</p>}

          <button className="btn primary" type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save preferences"}
          </button>
        </form>
      )}
    </div>
  );
}
