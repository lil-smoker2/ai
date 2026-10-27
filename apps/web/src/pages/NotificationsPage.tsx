/** Notification preferences: choose which in-app nudges LifeSmart surfaces.
 * Local-first, so these gate the app's own reminders only. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { api } from "../services/api";
import type { NotificationPreference } from "../types/api";

const TOGGLES: { key: keyof NotificationPreference; label: string }[] = [
  { key: "deadline_alerts", label: "Goal & task deadline alerts" },
  { key: "task_reminders", label: "Task reminders" },
  { key: "fee_due_alerts", label: "Fee due alerts" },
  { key: "low_stock_warnings", label: "Low-stock warnings" },
  { key: "savings_nudges", label: "Savings nudges" },
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notification-preferences"] }),
  });

  return (
    <div>
      <div className="page-header">
        <h1>Notifications</h1>
      </div>

      {prefs.isPending && <p className="muted">Loading…</p>}

      {prefs.data && (
        <form className="card auth-form" onSubmit={form.handleSubmit((v) => save.mutate(v))}>
          <h2>What should LifeSmart remind me about?</h2>
          <p className="muted">
            These control in-app reminders only. No external email or push is sent.
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
