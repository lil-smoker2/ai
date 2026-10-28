/** Savings & Earnings page: income sources, business records, savings
 * contributions, a forecast and the places money can sit.
 *
 * Expected income is clearly a planning figure, never counted as received; the
 * forecast states its assumptions.
 *
 * The places are named by the person, and so is every rate: LifeSmart has no
 * connection to Safaricom, to a bank, to the NSE or to a betting site, so a
 * percentage only ever stands with the date it was checked. The Save button
 * plans without recording anything, and a bet is kept apart from all of it -
 * what it cost can be recorded, what it will return cannot be projected. */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import type { FieldErrors, UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { api } from "../services/api";
import { formatMinor } from "../lib/money";
import type {
  BusinessProfit,
  BusinessRecord,
  BusinessRecordType,
  Contribution,
  EarningsSummary,
  Goal,
  IncomeFrequency,
  IncomeReliability,
  IncomeSource,
  Projection,
  SavingsVehicle,
  VehicleFlow,
  VehicleFlowDirection,
  VehicleKind,
} from "../types/api";

type EarningsTab = "overview" | "income" | "business" | "places";

const TAB_LABELS: Record<EarningsTab, string> = {
  overview: "Overview",
  income: "Income sources",
  business: "Business",
  places: "Places to save",
};

const FREQUENCIES: IncomeFrequency[] = ["daily", "weekly", "monthly", "yearly", "once"];
const RELIABILITY: IncomeReliability[] = ["uncertain", "likely", "confirmed"];

const toMinor = (v: string) =>
  v.trim() === "" ? null : Math.round(Number(v) * 100);

/** Today as the API wants a date, for a record dated when it is made. */
const todayISO = () => new Date().toISOString().slice(0, 10);

interface IncomeValues {
  name: string;
  expected_amount: string;
  frequency: IncomeFrequency;
  next_expected_date: string;
  reliability: IncomeReliability;
}

interface BusinessValues {
  business_name: string;
  type: BusinessRecordType;
  amount: string;
  category: string;
  occurred_on: string;
}

// --- Places money can sit ---------------------------------------------------

/** The ways money is kept or put to work. No platform is named and no rate is
 * prefilled: the app cannot know what any of them pays today, and a number it
 * supplied would read as a fact about that platform. */
const VEHICLE_KINDS: { value: VehicleKind; label: string; hint: string }[] = [
  {
    value: "mpesa",
    label: "M-PESA product",
    hint: "A savings or credit product sitting on your M-PESA line. Type the name the app shows you, and the percentage it quoted you.",
  },
  {
    value: "bank",
    label: "Bank",
    hint: "A bank savings or fixed-deposit account. The rate is the one the branch or the app told you.",
  },
  {
    value: "sacco",
    label: "SACCO",
    hint: "A cooperative account. Dividends are usually declared at year end, so record the rate you were quoted rather than a guess.",
  },
  {
    value: "money_market",
    label: "Money market",
    hint: "A money-market or unit-trust fund. Its return moves, so the date you checked matters as much as the figure.",
  },
  {
    value: "shares",
    label: "Shares",
    hint: "Units you own. No annual rate is quoted on a share, so you record what you paid and what it was worth the day you last looked.",
  },
  {
    value: "betting",
    label: "Betting",
    hint: "A betting site or a crash game. Nothing here can say what it returns, so it gets a link and a record of what it cost - never a projected profit.",
  },
  {
    value: "other",
    label: "Other",
    hint: "Any other place money sits that you keep track of by hand.",
  },
];
const KIND_LABEL = new Map(VEHICLE_KINDS.map((k) => [k.value, k.label]));
const KIND_HINT = new Map(VEHICLE_KINDS.map((k) => [k.value, k.hint]));

/** Which figures a kind of place can carry. The API applies the same split and
 * refuses a rate with no date, so a card cannot be saved in a state the server
 * would reject. */
const INTEREST_KINDS: VehicleKind[] = ["mpesa", "bank", "sacco", "money_market", "other"];
const HOLDING_KINDS: VehicleKind[] = ["shares"];
const RISK_KINDS: VehicleKind[] = ["betting"];

/** What money going in and coming back is called, in that kind of place's own
 * words - a stake is not a saving and a sale is not a withdrawal. */
const FLOW_LABELS: Record<VehicleKind, { in: string; out: string }> = {
  mpesa: { in: "Saved in", out: "Withdrew" },
  bank: { in: "Deposited", out: "Withdrew" },
  sacco: { in: "Contribution", out: "Withdrew" },
  money_market: { in: "Invested", out: "Cashed out" },
  shares: { in: "Bought for", out: "Sold for" },
  betting: { in: "Staked", out: "Paid out to me" },
  other: { in: "Put in", out: "Took out" },
};

// A percentage exactly as quoted: 10.75 means 10.75% a year, and nothing over
// 100 is a rate a platform quotes for a year.
const PERCENT = /^\d{1,3}(\.\d{1,2})?$/;
function percent(raw: string): number | null {
  const cleaned = raw.trim().replace(/[\s%]/g, "");
  if (!PERCENT.test(cleaned)) return null;
  const value = Number(cleaned);
  return value > 0 && value <= 100 ? value : null;
}

// Units of a holding: 120, or 12.5. Digits and a fraction, nothing else.
const UNITS = /^\d{1,8}(\.\d{1,4})?$/;
function unitsOf(raw: string): number | null {
  const cleaned = raw.trim();
  return UNITS.test(cleaned) && Number(cleaned) > 0 ? Number(cleaned) : null;
}

/** Only http(s), and no spaces: this address is handed to the real browser. */
const LINK = /^https?:\/\/\S+$/;

interface VehicleValues {
  name: string;
  kind: VehicleKind;
  url: string;
  rate: string;
  rate_on: string;
  units: string;
  value: string;
  value_on: string;
  notes: string;
}

const BLANK_VEHICLE: VehicleValues = {
  name: "",
  kind: "mpesa",
  url: "",
  rate: "",
  rate_on: "",
  units: "",
  value: "",
  value_on: "",
  notes: "",
};

interface FlowValues {
  direction: VehicleFlowDirection;
  amount: string;
  occurred_on: string;
  note: string;
}

const BLANK_FLOW: FlowValues = {
  direction: "in",
  amount: "",
  occurred_on: todayISO(),
  note: "",
};

const vehicleNameRule = { required: "Name the place money sits" };
const linkRule = {
  validate: (v: string) =>
    v.trim() === "" || LINK.test(v.trim()) ||
    "A full web address starting with https://, or leave it empty",
};
const rateRule = {
  validate: (v: string) =>
    v.trim() === "" || percent(v) !== null || "Enter the percentage as it was quoted, like 10.75",
};
// Cross-field, because a rate and its date are one figure: the API refuses the
// percentage on its own, so asking for the date here saves a rejected save.
const rateDateRule = {
  validate: (v: string, values: VehicleValues) =>
    values.rate.trim() === "" || !!v ||
    "Say when you checked that rate. LifeSmart cannot look a platform's rate up.",
};
const unitsRule = {
  validate: (v: string) =>
    v.trim() === "" || unitsOf(v) !== null || "How many units? Digits only, like 120 or 12.5",
};
const valueRule = {
  validate: (v: string) =>
    v.trim() === "" || toMinor(v) !== null || "Enter an amount like 4500 or 4500.50",
};
const valueDateRule = {
  validate: (v: string, values: VehicleValues) =>
    values.value.trim() === "" || !!v ||
    "Say what day it was worth that. A price without a date is a guess about today.",
};
/** A plan needs money and a span, both typed plainly. */
const positiveAmount = (v: string) =>
  (toMinor(v) ?? 0) > 0 || "Enter an amount bigger than zero, like 1000 or 1000.50";
const monthsRule = (v: string) => {
  const n = Number(v);
  return (Number.isInteger(n) && n >= 1 && n <= 600) || "How long? Whole months, between 1 and 600.";
};

/** A stored card back into the form, so Edit shows what is really stored. */
function vehicleValues(v: SavingsVehicle): VehicleValues {
  return {
    name: v.name,
    kind: v.kind,
    url: v.url ?? "",
    rate: v.rate_percent === null ? "" : String(v.rate_percent),
    rate_on: v.rate_checked_on ?? "",
    units: v.units === null ? "" : String(v.units),
    value: v.value_minor === null ? "" : String(v.value_minor / 100),
    value_on: v.valued_on ?? "",
    notes: v.notes ?? "",
  };
}

/** The card as the API wants it: only what this kind of place can carry, the
 * rest sent as null. Putting a rate on a bet would be a lie, so none is sent. */
function vehiclePayload(v: VehicleValues) {
  const interest = INTEREST_KINDS.includes(v.kind);
  const holding = HOLDING_KINDS.includes(v.kind);
  const hasRate = interest && v.rate.trim() !== "";
  const hasValue = holding && v.value.trim() !== "";
  return {
    name: v.name.trim(),
    kind: v.kind,
    url: v.url.trim() || null,
    rate_percent: hasRate ? percent(v.rate) : null,
    rate_checked_on: hasRate && v.rate_on ? v.rate_on : null,
    units: holding && v.units.trim() !== "" ? unitsOf(v.units) : null,
    value_minor: hasValue ? toMinor(v.value) : null,
    valued_on: hasValue && v.value_on ? v.value_on : null,
    notes: v.notes.trim() || null,
  };
}

/** The rate or valuation line under a place's name. */
function termsLine(v: SavingsVehicle): string {
  if (RISK_KINDS.includes(v.kind)) return "a bet, not savings - nothing is projected from it";
  if (HOLDING_KINDS.includes(v.kind)) {
    return [
      v.units ? `${v.units} units` : "units not recorded",
      v.value_minor === null
        ? "no value recorded"
        : `worth ${formatMinor(v.value_minor)} on ${v.valued_on}`,
    ].join(" · ");
  }
  return v.rate_percent === null
    ? "no rate recorded yet - type the percentage the platform quoted you"
    : `${v.rate_percent}% a year, checked ${v.rate_checked_on}`;
}

/** What the person says went in and came back, without claiming any of it is
 * worth anything now. */
function recordsLine(v: SavingsVehicle): string {
  if (v.net_in_minor === null) return "no records against it yet";
  const labels = FLOW_LABELS[v.kind];
  const parts = [
    `${labels.in} ${formatMinor(v.put_in_minor)}`,
    `${labels.out} ${formatMinor(v.taken_out_minor)}`,
  ];
  if (RISK_KINDS.includes(v.kind)) {
    // For a bet the difference is a cost, not a balance held somewhere.
    parts.push(
      v.net_in_minor >= 0
        ? `${formatMinor(v.net_in_minor)} more staked than paid out`
        : `${formatMinor(-v.net_in_minor)} more paid out than staked`,
    );
  } else {
    parts.push(
      v.net_in_minor >= 0
        ? `${formatMinor(v.net_in_minor)} still in there`
        : `${formatMinor(-v.net_in_minor)} more came back than went in`,
    );
  }
  if (v.gain_minor !== null) {
    parts.push(
      v.gain_minor >= 0
        ? `${formatMinor(v.gain_minor)} more than what went in`
        : `${formatMinor(-v.gain_minor)} less than what went in`,
    );
  }
  return parts.join(" · ");
}

/** The figures one place can carry, and only those.
 *
 * Shared by the Add card and the editor under a card, so the same percentage
 * cannot be asked, worded or judged two different ways - the same reason the
 * API runs one set of rules for both. */
function VehicleFields({
  form,
  errors,
}: {
  form: UseFormReturn<VehicleValues>;
  errors: FieldErrors<VehicleValues>;
}) {
  const kind = form.watch("kind");
  const interest = INTEREST_KINDS.includes(kind);
  const holding = HOLDING_KINDS.includes(kind);
  const risk = RISK_KINDS.includes(kind);
  return (
    <>
      <div className="btn-row">
        <label>
          Name
          <input
            placeholder="what the platform calls itself"
            {...form.register("name", vehicleNameRule)}
          />
          {errors.name && <span className="field-error">{errors.name.message}</span>}
        </label>
        <label>
          Kind of place
          <select {...form.register("kind")}>
            {VEHICLE_KINDS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="field-hint">{KIND_HINT.get(kind)}</p>
      <label>
        Link (optional)
        <input
          placeholder="https:// as it appears in your browser"
          {...form.register("url", linkRule)}
        />
        {errors.url && <span className="field-error">{errors.url.message}</span>}
      </label>
      {interest && (
        <div className="btn-row">
          <label>
            Interest rate, % a year
            <input
              type="text"
              inputMode="decimal"
              placeholder="as quoted to you"
              {...form.register("rate", rateRule)}
            />
            {errors.rate && <span className="field-error">{errors.rate.message}</span>}
          </label>
          <label>
            Rate checked on
            <input type="date" {...form.register("rate_on", rateDateRule)} />
            {errors.rate_on && <span className="field-error">{errors.rate_on.message}</span>}
          </label>
        </div>
      )}
      {holding && (
        <div className="btn-row">
          <label>
            Units you hold
            <input
              type="text"
              inputMode="decimal"
              placeholder="120"
              {...form.register("units", unitsRule)}
            />
            {errors.units && <span className="field-error">{errors.units.message}</span>}
          </label>
          <label>
            What they are worth (KES)
            <input
              type="text"
              inputMode="decimal"
              placeholder="4500 or 4500.50"
              {...form.register("value", valueRule)}
            />
            {errors.value && <span className="field-error">{errors.value.message}</span>}
          </label>
          <label>
            Valued on
            <input type="date" {...form.register("value_on", valueDateRule)} />
            {errors.value_on && <span className="field-error">{errors.value_on.message}</span>}
          </label>
        </div>
      )}
      {risk && (
        <p className="field-hint">
          No rate is offered here. A bet has no return anyone can state, so what
          it cost you is the only figure kept - record it once this is added.
        </p>
      )}
      <label>
        Notes (optional)
        <input
          placeholder="anything you want the card to remind you of"
          {...form.register("notes")}
        />
      </label>
    </>
  );
}

export function EarningsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<EarningsTab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [contribGoal, setContribGoal] = useState<number | null>(null);

  const summary = useQuery({
    queryKey: ["earnings-summary"],
    queryFn: () => api<EarningsSummary>("/api/earnings/summary"),
  });
  const income = useQuery({
    queryKey: ["income-sources"],
    queryFn: () => api<IncomeSource[]>("/api/earnings/income-sources"),
  });
  const business = useQuery({
    queryKey: ["business-records"],
    queryFn: () => api<BusinessRecord[]>("/api/earnings/business"),
  });
  const profit = useQuery({
    queryKey: ["business-profit"],
    queryFn: () => api<BusinessProfit[]>("/api/earnings/business/profit"),
  });
  const goals = useQuery({
    queryKey: ["goals"],
    queryFn: () => api<Goal[]>("/api/goals"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["earnings-summary"] });
    queryClient.invalidateQueries({ queryKey: ["income-sources"] });
    queryClient.invalidateQueries({ queryKey: ["business-records"] });
    queryClient.invalidateQueries({ queryKey: ["business-profit"] });
    queryClient.invalidateQueries({ queryKey: ["goals"] });
  };

  const incomeForm = useForm<IncomeValues>({
    defaultValues: { frequency: "monthly", reliability: "likely" },
  });
  const addIncome = useMutation({
    mutationFn: (v: IncomeValues) => {
      const amount = toMinor(v.expected_amount);
      if (amount === null || amount <= 0) throw new Error("Enter an expected amount");
      return api<IncomeSource>("/api/earnings/income-sources", {
        body: {
          name: v.name,
          expected_amount_minor: amount,
          frequency: v.frequency,
          reliability: v.reliability,
          next_expected_date: v.next_expected_date || null,
        },
      });
    },
    onSuccess: () => {
      refresh();
      incomeForm.reset();
      setTab("overview");
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const toggleIncome = useMutation({
    mutationFn: (v: { id: number; active: boolean }) =>
      api<IncomeSource>(`/api/earnings/income-sources/${v.id}`, {
        method: "PUT",
        body: { active: v.active },
      }),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  const businessForm = useForm<BusinessValues>({
    defaultValues: { type: "revenue" },
  });
  const addBusiness = useMutation({
    mutationFn: (v: BusinessValues) => {
      const amount = toMinor(v.amount);
      if (amount === null || amount <= 0) throw new Error("Enter an amount");
      return api<BusinessRecord>("/api/earnings/business", {
        body: {
          business_name: v.business_name,
          type: v.type,
          amount_minor: amount,
          category: v.category || null,
          occurred_on: v.occurred_on || null,
        },
      });
    },
    onSuccess: () => {
      refresh();
      businessForm.reset();
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const contribForm = useForm<{ amount: string }>();
  const contribute = useMutation({
    mutationFn: (v: { amount: string; goalId: number }) => {
      const amount = toMinor(v.amount);
      if (amount === null || amount <= 0) throw new Error("Enter a contribution amount");
      return api<Contribution>(`/api/goals/${v.goalId}/contributions`, {
        body: { amount_minor: amount },
      });
    },
    onSuccess: () => {
      refresh();
      setContribGoal(null);
      contribForm.reset();
      setError(null);
    },
    onError: (e) => setError(e.message),
  });

  const s = summary.data;

  // --- Places to save: cards, plans and the records against them ---
  const vehicles = useQuery({
    queryKey: ["savings-vehicles"],
    queryFn: () => api<SavingsVehicle[]>("/api/earnings/vehicles"),
  });

  const vehicleForm = useForm<VehicleValues>({ defaultValues: BLANK_VEHICLE });
  const {
    formState: { errors: addVehicleErrors },
  } = vehicleForm;

  const editVehicleForm = useForm<VehicleValues>({ defaultValues: BLANK_VEHICLE });
  const {
    formState: { errors: editVehicleErrors },
  } = editVehicleForm;

  // One card is open in each panel at a time, the same way an account is edited
  // in place: the panels belong to the card they were opened from.
  const [editingVehicleId, setEditingVehicleId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [flowVehicleId, setFlowVehicleId] = useState<number | null>(null);

  const projectForm = useForm<{ amount: string; months: string }>({
    defaultValues: { amount: "", months: "12" },
  });
  const {
    formState: { errors: projectErrors },
  } = projectForm;

  const flowForm = useForm<FlowValues>({ defaultValues: BLANK_FLOW });
  const {
    formState: { errors: flowErrors },
  } = flowForm;

  const flows = useQuery({
    queryKey: ["vehicle-flows", flowVehicleId],
    queryFn: () =>
      api<VehicleFlow[]>(`/api/earnings/vehicles/${flowVehicleId}/flows`),
    enabled: flowVehicleId !== null,
  });

  const closeVehicleEditor = () => {
    setEditingVehicleId(null);
    editVehicleForm.reset(BLANK_VEHICLE);
  };

  const refreshVehicles = () => {
    queryClient.invalidateQueries({ queryKey: ["savings-vehicles"] });
    queryClient.invalidateQueries({ queryKey: ["vehicle-flows"] });
  };

  const addVehicle = useMutation({
    mutationFn: (v: VehicleValues) =>
      api<SavingsVehicle>("/api/earnings/vehicles", { body: vehiclePayload(v) }),
    onSuccess: () => {
      vehicleForm.reset(BLANK_VEHICLE);
      setError(null);
      refreshVehicles();
    },
    onError: (e) => setError(e.message),
  });

  const saveVehicle = useMutation({
    mutationFn: (v: { id: number; values: VehicleValues }) =>
      api<SavingsVehicle>(`/api/earnings/vehicles/${v.id}`, {
        method: "PUT",
        body: vehiclePayload(v.values),
      }),
    onSuccess: () => {
      closeVehicleEditor();
      setError(null);
      refreshVehicles();
    },
    onError: (e) => setError(e.message),
  });

  const deleteVehicle = useMutation({
    mutationFn: (id: number) =>
      api(`/api/earnings/vehicles/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      closeVehicleEditor();
      setProjectId(null);
      setFlowVehicleId(null);
      setProjection(null);
      setError(null);
      refreshVehicles();
    },
    // A card with records on it is refused by the API, and its own words about
    // why are more useful than anything this page could write, so they show.
    onError: (e) => setError(e.message),
  });

  const projectVehicle = useMutation({
    mutationFn: (v: { id: number; values: { amount: string; months: string } }) => {
      const amount = toMinor(v.values.amount);
      if (amount === null || amount <= 0) {
        throw new Error("Enter how much you would save, like 1000 or 1000.50");
      }
      const months = Number(v.values.months);
      if (!Number.isInteger(months) || months < 1 || months > 600) {
        throw new Error("How long? Whole months, between 1 and 600.");
      }
      return api<Projection>(`/api/earnings/vehicles/${v.id}/project`, {
        body: { amount_minor: amount, months },
      });
    },
    onSuccess: (p) => {
      setProjection(p);
      setError(null);
    },
    onError: (e) => {
      // A refused plan shows its own reason in the banner: no rate recorded,
      // or a bet there is no rate to be recorded on.
      setProjection(null);
      setError(e.message);
    },
  });

  const addFlow = useMutation({
    mutationFn: (v: { id: number; values: FlowValues }) => {
      const amount = toMinor(v.values.amount);
      if (amount === null || amount <= 0) {
        throw new Error("Enter an amount bigger than zero, like 100 or 100.50");
      }
      return api<VehicleFlow>(`/api/earnings/vehicles/${v.id}/flows`, {
        body: {
          direction: v.values.direction,
          amount_minor: amount,
          occurred_on: v.values.occurred_on,
          note: v.values.note.trim() || null,
        },
      });
    },
    onSuccess: () => {
      flowForm.reset({ ...BLANK_FLOW, occurred_on: flowForm.getValues("occurred_on") });
      setError(null);
      refreshVehicles();
    },
    onError: (e) => setError(e.message),
  });

  const removeFlow = useMutation({
    mutationFn: (id: number) =>
      api(`/api/earnings/vehicle-flows/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      refreshVehicles();
    },
    onError: (e) => setError(e.message),
  });

  const startEditVehicle = (v: SavingsVehicle) => {
    setProjectId(null);
    setFlowVehicleId(null);
    setProjection(null);
    setError(null);
    editVehicleForm.reset(vehicleValues(v));
    setEditingVehicleId(v.id);
  };

  const startProject = (v: SavingsVehicle) => {
    setEditingVehicleId(null);
    setFlowVehicleId(null);
    setProjection(null);
    setError(null);
    projectForm.reset({ amount: "", months: "12" });
    setProjectId(v.id);
  };

  const startFlows = (v: SavingsVehicle) => {
    setEditingVehicleId(null);
    setProjectId(null);
    setProjection(null);
    setError(null);
    flowForm.reset(BLANK_FLOW);
    setFlowVehicleId(v.id);
  };

  return (
    <div>
      <div className="page-header">
        <h1>Savings &amp; Earnings</h1>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}

      <div className="tabs" role="tablist">
        {(Object.keys(TAB_LABELS) as EarningsTab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "tab-btn active" : "tab-btn"}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="stat-grid">
            <div className="card stat-card">
              <span className="stat-label">Recorded balance</span>
              <strong>{s ? formatMinor(s.recorded_available_balance_minor) : "—"}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Expected income / month</span>
              <strong>{formatMinor(s?.monthly_expected_income_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Business net (this month)</span>
              <strong>{formatMinor(s?.business_net_profit_this_month_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Saved toward goals</span>
              <strong>{formatMinor(s?.total_saved_in_goals_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Outstanding obligations</span>
              <strong>{formatMinor(s?.outstanding_obligations_minor)}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Available for planning</span>
              <strong>
                {s?.available_for_planning_minor === null ||
                s?.available_for_planning_minor === undefined
                  ? "Not enough data"
                  : formatMinor(s.available_for_planning_minor)}
              </strong>
            </div>
          </div>
          <p className="muted">
            “Available for planning” is an estimate — recorded balance plus
            expected recurring income minus outstanding goal obligations. It is
            not a bank balance, and expected income is never counted as received.
          </p>
          {s && s.assumptions.length > 0 && (
            <div className="card">
              <h2>Forecast assumptions</h2>
              <ul className="muted">
                {s.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="card">
            <h2>Fund a savings goal</h2>
            {(goals.data ?? [])
              .filter((g) => g.status === "active" && g.type === "money")
              .map((g) => (
                <div key={g.id} className="list-row">
                  <span>
                    <strong>{g.name}</strong>{" "}
                    <span className="muted">
                      {formatMinor(g.amount_saved_minor)} of{" "}
                      {formatMinor(g.target_amount_minor)}
                    </span>
                  </span>
                  {contribGoal === g.id ? (
                    <form
                      className="btn-row"
                      onSubmit={contribForm.handleSubmit((v) =>
                        contribute.mutate({ amount: v.amount, goalId: g.id }),
                      )}
                    >
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        placeholder="KES"
                        autoFocus
                        {...contribForm.register("amount", { required: true })}
                      />
                      <button className="btn primary" type="submit" disabled={contribute.isPending}>
                        Record
                      </button>
                      <button className="btn ghost" type="button" onClick={() => setContribGoal(null)}>
                        Cancel
                      </button>
                    </form>
                  ) : (
                    <button className="btn small" onClick={() => setContribGoal(g.id)}>
                      Add contribution
                    </button>
                  )}
                </div>
              ))}
            {(goals.data ?? []).filter((g) => g.status === "active" && g.type === "money")
              .length === 0 && (
              <p className="muted">No active money goals. Create one under Goals.</p>
            )}
          </div>
        </>
      )}

      {tab === "income" && (
        <>
          <form
            className="card auth-form"
            onSubmit={incomeForm.handleSubmit((v) => addIncome.mutate(v))}
          >
            <h2>Add income source</h2>
            <p className="muted">
              Expected amounts are used only for planning - they are never
              recorded as money you already have.
            </p>
            <label>
              Name
              <input {...incomeForm.register("name", { required: true })} />
            </label>
            <div className="btn-row">
              <label>
                Expected amount (KES)
                <input type="number" min="0.01" step="0.01" {...incomeForm.register("expected_amount", { required: true })} />
              </label>
              <label>
                Frequency
                <select {...incomeForm.register("frequency")}>
                  {FREQUENCIES.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </label>
              <label>
                Reliability
                <select {...incomeForm.register("reliability")}>
                  {RELIABILITY.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label>
                Next expected (optional)
                <input type="date" {...incomeForm.register("next_expected_date")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addIncome.isPending}>
              <Plus size={16} aria-hidden /> Add Source
            </button>
          </form>

          <div className="card">
            <h2>Income sources</h2>
            {(income.data ?? []).map((src) => (
              <div key={src.id} className="list-row">
                <span>
                  <strong>{src.name}</strong>{" "}
                  <span className="badge">{src.frequency}</span>{" "}
                  <span className="badge">{src.reliability}</span>{" "}
                  {!src.active && <span className="badge warn">inactive</span>}
                  <span className="muted"> · {formatMinor(src.monthly_expected_minor)}/mo expected</span>
                </span>
                <button
                  className="btn ghost small"
                  onClick={() => toggleIncome.mutate({ id: src.id, active: !src.active })}
                >
                  {src.active ? "Deactivate" : "Activate"}
                </button>
              </div>
            ))}
            {income.data?.length === 0 && <p className="muted">No income sources yet.</p>}
          </div>
        </>
      )}

      {tab === "business" && (
        <>
          <form
            className="card auth-form"
            onSubmit={businessForm.handleSubmit((v) => addBusiness.mutate(v))}
          >
            <h2>Record business entry</h2>
            <div className="btn-row">
              <label>
                Business
                <input {...businessForm.register("business_name", { required: true })} />
              </label>
              <label>
                Type
                <select {...businessForm.register("type")}>
                  <option value="revenue">Revenue</option>
                  <option value="expense">Expense</option>
                </select>
              </label>
              <label>
                Amount (KES)
                <input type="number" min="0.01" step="0.01" {...businessForm.register("amount", { required: true })} />
              </label>
              <label>
                Category (optional)
                <input placeholder="e.g. direct cost, stock" {...businessForm.register("category")} />
              </label>
              <label>
                Date
                <input type="date" {...businessForm.register("occurred_on")} />
              </label>
            </div>
            <button className="btn primary" type="submit" disabled={addBusiness.isPending}>
              <Plus size={16} aria-hidden /> Record Entry
            </button>
          </form>

          <div className="card">
            <h2>Net profit by business</h2>
            {(profit.data ?? []).map((p) => (
              <div key={p.business_name} className="list-row">
                <span><strong>{p.business_name}</strong></span>
                <span>
                  {formatMinor(p.revenue_minor)} revenue − {formatMinor(p.expenses_minor)} costs ={" "}
                  <strong>{formatMinor(p.net_profit_minor)}</strong>
                </span>
              </div>
            ))}
            {profit.data?.length === 0 && <p className="muted">No business records yet.</p>}
          </div>

          <div className="card">
            <h2>Recent entries</h2>
            {(business.data ?? []).map((r) => (
              <div key={r.id} className="list-row">
                <span>
                  <span className={`badge ${r.type === "revenue" ? "income" : "expense"}`}>{r.type}</span>{" "}
                  <strong>{r.business_name}</strong>
                  {r.category ? ` · ${r.category}` : ""}
                  <span className="muted"> · {r.occurred_on}</span>
                </span>
                <span>{formatMinor(r.amount_minor)}</span>
              </div>
            ))}
            {business.data?.length === 0 && <p className="muted">Nothing recorded yet.</p>}
          </div>
        </>
      )}

      {tab === "places" && (
        <>
          <div className="card">
            <h2>Places money can sit</h2>
            <p className="muted">
              LifeSmart is not connected to Safaricom, to any bank, to the NSE or
              to a betting site, so it cannot know what anything pays today.
              Every percentage here is one you were told, kept with the day you
              were told it. A place is not a balance: money is only ever where
              the Money page puts it.
            </p>
            {(vehicles.data ?? []).map((v) => (
              <div key={v.id} className="vehicle-item">
                <div className="list-row">
                  <span>
                    <strong>{v.name}</strong>{" "}
                    <span className="badge">{KIND_LABEL.get(v.kind) ?? v.kind}</span>
                    <span className="account-id">{termsLine(v)}</span>
                    <span className="account-id">{recordsLine(v)}</span>
                  </span>
                  <span>
                    {v.url && (
                      <a
                        className="site-link"
                        href={v.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open {v.name}
                      </a>
                    )}{" "}
                    {INTEREST_KINDS.includes(v.kind) && (
                      <button
                        className="btn small"
                        type="button"
                        onClick={() => startProject(v)}
                      >
                        Save
                      </button>
                    )}{" "}
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={() => startFlows(v)}
                    >
                      Records
                    </button>{" "}
                    {editingVehicleId !== v.id && (
                      <button
                        className="btn ghost small"
                        type="button"
                        onClick={() => startEditVehicle(v)}
                      >
                        Edit
                      </button>
                    )}
                  </span>
                </div>

                {/* What saving here would give. Plans only - the button that
                    pressed it says so, and so does every figure under it. */}
                {projectId === v.id && (
                  <form
                    className="vehicle-panel auth-form"
                    onSubmit={projectForm.handleSubmit((vals) =>
                      projectVehicle.mutate({ id: v.id, values: vals })
                    )}
                  >
                    {v.rate_percent === null ? (
                      <p className="field-hint">
                        No rate is recorded for {v.name}, so there is nothing to
                        work from. LifeSmart cannot look it up.{" "}
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => startEditVehicle(v)}
                        >
                          Enter the rate it quoted you
                        </button>
                      </p>
                    ) : (
                      <p className="field-hint">
                        Working from {v.rate_percent}% a year you recorded
                        {v.rate_checked_on ? ` on ${v.rate_checked_on}` : ""}.
                        Nothing is saved and no money moves by pressing this.
                        When you do save it, record the transfer on the Money
                        page so your balance agrees.
                      </p>
                    )}
                    <div className="btn-row">
                      <label>
                        How much are you saving? (KES)
                        <input
                          type="text"
                          inputMode="decimal"
                          placeholder="1000 or 1000.50"
                          {...projectForm.register("amount", { validate: positiveAmount })}
                        />
                        {projectErrors.amount && (
                          <span className="field-error">{projectErrors.amount.message}</span>
                        )}
                      </label>
                      <label>
                        For how long? (months)
                        <input
                          type="text"
                          inputMode="numeric"
                          placeholder="12"
                          {...projectForm.register("months", { validate: monthsRule })}
                        />
                        {projectErrors.months && (
                          <span className="field-error">{projectErrors.months.message}</span>
                        )}
                      </label>
                    </div>
                    <div className="btn-row">
                      <button
                        className="btn primary"
                        type="submit"
                        disabled={projectVehicle.isPending || v.rate_percent === null}
                      >
                        Show what it would give
                      </button>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => {
                          setProjectId(null);
                          setProjection(null);
                        }}
                      >
                        Close
                      </button>
                    </div>
                    {projection && (
                      <div className="projection-result">
                        <p>
                          <strong>{formatMinor(projection.interest_minor)}</strong>{" "}
                          in interest on {formatMinor(projection.amount_minor)}, so
                          about{" "}
                          <strong>{formatMinor(projection.total_minor)}</strong> back
                          after {projection.months}{" "}
                          {projection.months === 1 ? "month" : "months"}.
                        </p>
                        <p className="field-hint">What that figure rests on:</p>
                        <ul className="assumption-list">
                          {projection.assumptions.map((a) => (
                            <li key={a}>{a}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </form>
                )}

                {/* What the person says really went in and came back. */}
                {flowVehicleId === v.id && (
                  <div className="vehicle-panel">
                    <p className="field-hint">
                      {RISK_KINDS.includes(v.kind)
                        ? "What you staked and what was paid out to you, so the cost of it is on the record. No account balance moves here - the Money page is where a transfer is real."
                        : "What you really put in and took out, kept as a note against this place. No account balance moves here: writing the same transfer on the Money page too would count the money twice."}
                    </p>
                    <form
                      className="auth-form"
                      onSubmit={flowForm.handleSubmit((vals) =>
                        addFlow.mutate({ id: v.id, values: vals })
                      )}
                    >
                      <div className="btn-row">
                        <label>
                          Which way
                          <select {...flowForm.register("direction")}>
                            <option value="in">{FLOW_LABELS[v.kind].in}</option>
                            <option value="out">{FLOW_LABELS[v.kind].out}</option>
                          </select>
                        </label>
                        <label>
                          Amount (KES)
                          <input
                            type="text"
                            inputMode="decimal"
                            placeholder="100 or 100.50"
                            {...flowForm.register("amount", { validate: positiveAmount })}
                          />
                          {flowErrors.amount && (
                            <span className="field-error">{flowErrors.amount.message}</span>
                          )}
                        </label>
                        <label>
                          Date
                          <input
                            type="date"
                            {...flowForm.register("occurred_on", { required: "Which day?" })}
                          />
                        </label>
                        <label>
                          Note (optional)
                          <input
                            placeholder="e.g. from the January salary"
                            {...flowForm.register("note")}
                          />
                        </label>
                      </div>
                      <button
                        className="btn primary small"
                        type="submit"
                        disabled={addFlow.isPending}
                      >
                        <Plus size={16} aria-hidden /> Add record
                      </button>
                    </form>
                    {(flows.data ?? []).map((f) => (
                      <div key={f.id} className="list-row">
                        <span>
                          <span
                            className={`badge ${f.direction === "in" ? "income" : "expense"}`}
                          >
                            {f.direction === "in"
                              ? FLOW_LABELS[v.kind].in
                              : FLOW_LABELS[v.kind].out}
                          </span>{" "}
                          <strong>{formatMinor(f.amount_minor)}</strong>
                          <span className="muted">
                            {" "}· {f.occurred_on}
                            {f.note ? ` · ${f.note}` : ""}
                          </span>
                        </span>
                        <button
                          className="btn ghost small"
                          type="button"
                          onClick={() => removeFlow.mutate(f.id)}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    {flows.data?.length === 0 && (
                      <p className="muted">Nothing recorded against {v.name} yet.</p>
                    )}
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={() => setFlowVehicleId(null)}
                    >
                      Close
                    </button>
                  </div>
                )}

                {/* The card corrected in place. Sending the whole form again is
                    deliberate: a rate cleared here is really gone. */}
                {editingVehicleId === v.id && (
                  <form
                    className="vehicle-panel auth-form"
                    onSubmit={editVehicleForm.handleSubmit((vals) =>
                      saveVehicle.mutate({ id: v.id, values: vals })
                    )}
                  >
                    <p className="field-hint">
                      Correct what you were told, or what you hold. The records
                      against {v.name} stay exactly as they are.
                    </p>
                    <VehicleFields form={editVehicleForm} errors={editVehicleErrors} />
                    <div className="btn-row">
                      <button
                        className="btn primary"
                        type="submit"
                        disabled={saveVehicle.isPending}
                      >
                        Save changes
                      </button>
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={closeVehicleEditor}
                      >
                        Cancel
                      </button>
                      <button
                        className="btn danger"
                        type="button"
                        disabled={deleteVehicle.isPending}
                        onClick={() => deleteVehicle.mutate(v.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </form>
                )}
              </div>
            ))}
            {vehicles.data?.length === 0 && (
              <p className="muted">No places added yet. Add one below.</p>
            )}
          </div>

          <form
            className="card auth-form"
            onSubmit={vehicleForm.handleSubmit((vals) => addVehicle.mutate(vals))}
          >
            <h2>Add a place</h2>
            <p className="muted">
              Name it as the platform does, and type the percentage exactly as it
              was quoted to you. Nothing here verifies a rate, and adding a place
              does not move any money - it only lets you ask what saving there
              would give.
            </p>
            <VehicleFields form={vehicleForm} errors={addVehicleErrors} />
            <button className="btn primary" type="submit" disabled={addVehicle.isPending}>
              <Plus size={16} aria-hidden /> Add Place
            </button>
          </form>
        </>
      )}
    </div>
  );
}
