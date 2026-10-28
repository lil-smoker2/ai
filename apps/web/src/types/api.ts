/**
 * Shared API contracts - mirrors apps/api schemas (docs/api-contracts.md).
 * All money values are integer minor units; never parse floats here.
 */

export interface User {
  id: number;
  email: string;
  full_name: string;
  currency: string;
  country: string;
  timezone: string;
  is_student: boolean | null;
  onboarded: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Page {
  total: number;
  page: number;
  page_size: number;
}

// --- Inventory ---
export interface InventoryCategory {
  id: number;
  name: string;
}

export interface InventoryItem {
  id: number;
  name: string;
  category_id: number;
  category_name: string | null;
  quantity_owned: number;
  target_quantity: number | null;
  unit: string | null;
  estimated_unit_cost_minor: number | null;
  price_verified: boolean;
  price_source: string | null;
  notes: string | null;
  image_asset_id: string | null;
  created_at: string;
  shortage: number;
  estimated_cost_to_target_minor: number | null;
  price_needed: boolean;
}

export interface ItemPage {
  items: InventoryItem[];
  page: Page;
}

// --- Money ---
export type AccountType =
  | "cash"
  | "mpesa"
  | "mshwari"
  | "bank"
  | "wallet"
  | "custom";
export type TransactionType = "income" | "expense" | "transfer";

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  // Identifiers the person typed for themselves. Null when that kind of
  // account has no such number, or when it was never recorded.
  mpesa_number: string | null;
  bank_name: string | null;
  account_number: string | null;
  is_synced: boolean;
  initialized: boolean;
  initial_balance_minor: number;
  created_at: string;
  balance_minor: number | null;
}

export interface Transaction {
  id: number;
  type: TransactionType;
  amount_minor: number;
  currency: string;
  occurred_on: string;
  category: string | null;
  description: string | null;
  from_account_id: number | null;
  to_account_id: number | null;
  goal_id: number | null;
  reference: string | null;
  reversed: boolean;
  reversal_of_id: number | null;
  created_at: string;
}

export interface TransactionPage {
  transactions: Transaction[];
  page: Page;
}

export interface BalanceSummary {
  total_available_minor: number | null;
  initialized_accounts: number;
  uninitialized_accounts: number;
}

export interface MonthSummary {
  income_minor: number;
  expense_minor: number;
  // Transfers are excluded from income/expenses by design.
  transfers_minor: number;
}

// --- Goals ---
export type GoalType = "money" | "quantity" | "obligation" | "custom";
export type GoalStatus = "active" | "paused" | "completed";
export type GoalPriority = "low" | "medium" | "high" | "critical";

export interface Goal {
  id: number;
  name: string;
  type: GoalType;
  status: GoalStatus;
  target_amount_minor: number | null;
  target_quantity: number | null;
  current_quantity: number | null;
  estimated_unit_cost_minor: number | null;
  deadline: string | null;
  priority: GoalPriority;
  inventory_item_id: number | null;
  notes: string | null;
  created_at: string;
  completed_at: string | null;
  amount_saved_minor: number;
  remaining_amount_minor: number | null;
  remaining_quantity: number | null;
  estimated_remaining_cost_minor: number | null;
  required_monthly_saving_minor: number | null;
  deadline_state: "ok" | "no_deadline" | "deadline_passed";
}

export interface Contribution {
  id: number;
  goal_id: number;
  amount_minor: number;
  occurred_on: string;
  account_id: number | null;
  transaction_id: number | null;
  note: string | null;
}

// --- Shopping ---
export type PriceSource = "estimate" | "verified";
export type ShoppingItemStatus = "needed" | "purchased";

export interface ShoppingList {
  id: number;
  name: string;
  notes: string | null;
  goal_id: number | null;
  created_at: string;
}

export interface ShoppingListPage {
  lists: ShoppingList[];
  page: Page;
}

export interface ShoppingItem {
  id: number;
  list_id: number;
  name: string;
  quantity_needed: number;
  estimated_unit_cost_minor: number | null;
  price_source: PriceSource;
  seller: string | null;
  delivery_cost_minor: number;
  transport_cost_minor: number;
  fees_minor: number;
  status: ShoppingItemStatus;
  inventory_item_id: number | null;
  goal_id: number | null;
  notes: string | null;
  created_at: string;
  // Computed server-side; null total + price_needed when the price is unknown.
  estimated_item_cost_minor: number | null;
  estimated_total_minor: number | null;
  price_needed: boolean;
}

export interface PurchaseRecord {
  id: number;
  shopping_item_id: number;
  quantity: number;
  amount_paid_minor: number;
  currency: string;
  occurred_on: string;
  transaction_id: number | null;
  added_inventory_quantity: number;
  idempotency_key: string;
  created_at: string;
}

// --- Savings & Earnings ---
export type IncomeFrequency = "daily" | "weekly" | "monthly" | "yearly" | "once";
export type IncomeReliability = "uncertain" | "likely" | "confirmed";
export type BusinessRecordType = "revenue" | "expense";

export interface IncomeSource {
  id: number;
  name: string;
  expected_amount_minor: number;
  frequency: IncomeFrequency;
  next_expected_date: string | null;
  reliability: IncomeReliability;
  active: boolean;
  notes: string | null;
  created_at: string;
  // Expected amount normalized to a per-month planning figure (not received).
  monthly_expected_minor: number;
}

export interface BusinessRecord {
  id: number;
  business_name: string;
  type: BusinessRecordType;
  amount_minor: number;
  category: string | null;
  occurred_on: string;
  transaction_id: number | null;
  notes: string | null;
  created_at: string;
}

export interface BusinessProfit {
  business_name: string;
  revenue_minor: number;
  expenses_minor: number;
  net_profit_minor: number;
}

export interface EarningsSummary {
  recorded_available_balance_minor: number | null;
  monthly_expected_income_minor: number;
  business_revenue_this_month_minor: number;
  business_expenses_this_month_minor: number;
  business_net_profit_this_month_minor: number;
  savings_contributed_this_month_minor: number;
  total_saved_in_goals_minor: number;
  outstanding_obligations_minor: number;
  // Null when no account balance is initialized (never a fake zero).
  available_for_planning_minor: number | null;
  assumptions: string[];
}

/** The ways money can be kept or put to work, as the API names them. */
export type VehicleKind =
  | "mpesa"
  | "bank"
  | "sacco"
  | "money_market"
  | "shares"
  | "betting"
  | "other";

/** Which way money moved, seen from the place holding it: "in" went in (saved,
 * used to buy, staked), "out" came back to you (withdrawn, cashed out, paid). */
export type VehicleFlowDirection = "in" | "out";

/**
 * A place money can sit, described by what you were told. `rate_percent` is a
 * percentage a year as quoted, and it only ever exists next to the date it was
 * checked: the app is offline and cannot know a platform's current rate. A
 * vehicle is not a balance - the money itself belongs to a Money-page account.
 */
export interface SavingsVehicle {
  id: number;
  name: string;
  kind: VehicleKind;
  url: string | null;
  rate_percent: number | null;
  rate_checked_on: string | null;
  units: number | null;
  value_minor: number | null;
  valued_on: string | null;
  notes: string | null;
  created_at: string;
  // Totals of the flow records. put_in / taken_out are 0 when nothing was ever
  // recorded; net_in stays null instead, because no record is not a zero.
  put_in_minor: number;
  taken_out_minor: number;
  net_in_minor: number | null;
  // Only stated when a valuation and records both exist.
  gain_minor: number | null;
}

export interface VehicleFlow {
  id: number;
  vehicle_id: number;
  direction: VehicleFlowDirection;
  amount_minor: number;
  occurred_on: string;
  note: string | null;
  created_at: string;
}

/** What the recorded rate would give on the amount you typed. Records nothing -
 * `assumptions` says out loud what the figure rests on. */
export interface Projection {
  amount_minor: number;
  months: number;
  rate_percent: number;
  rate_checked_on: string | null;
  interest_minor: number;
  total_minor: number;
  assumptions: string[];
}

// --- Assets (dynamic image system) ---
export interface AssetAnalysis {
  predicted_category: string | null;
  predicted_item_type: string | null;
  confidence: number;
  attributes: Record<string, unknown> | null;
  source: "folder" | "vision" | "manual";
}

export interface Asset {
  id: string;
  original_filename: string;
  category: string;
  format: string;
  width: number;
  height: number;
  size_bytes: number;
  status: "active" | "duplicate" | "corrupted" | "missing";
  duplicate_of: string | null;
  attribution: string | null;
  license: string | null;
  last_seen_at: string;
  analysis: AssetAnalysis | null;
}

export interface AssetPage {
  assets: Asset[];
  page: Page;
}

export interface ScanStatus {
  state: "idle" | "running" | "completed" | "failed";
  started_at: string | null;
  finished_at: string | null;
  files_seen: number;
  new: number;
  updated: number;
  duplicates: number;
  corrupted: number;
  removed: number;
  error: string | null;
}

// --- Dashboard ---
export interface DashboardSummary {
  total_available_minor: number | null;
  income_this_month_minor: number;
  expenses_this_month_minor: number;
  savings_this_month_minor: number;
  active_goals: number;
  outstanding_goal_amount_minor: number;
  distinct_inventory_items: number;
  items_below_target: number;
  estimated_shortage_cost_minor: number | null;
  price_needed_items: number;
  // Saved value of what is owned; null while some owned items lack a price.
  net_worth_minor: number | null;
}

// --- Tasks & Reminders ---
export type TaskStatus =
  | "proposed"
  | "pending"
  | "in_progress"
  | "completed"
  | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "critical";
export type TaskRecurrence = "none" | "daily" | "weekly" | "monthly" | "yearly";

export interface Task {
  id: number;
  title: string;
  description: string | null;
  due_on: string | null;
  due_time: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  goal_id: number | null;
  recurrence: TaskRecurrence;
  remind_before_days: number | null;
  created_at: string;
  completed_at: string | null;
  is_overdue: boolean;
}

// --- Student Life ---
export type FeeCategory = "tuition" | "registration" | "other";
export type FeeStatus = "unpaid" | "partial" | "paid";
export type HostelStatus = "unchecked" | "available" | "taken" | "booked";

export interface FeeObligation {
  id: number;
  name: string;
  category: FeeCategory;
  amount_due_minor: number;
  amount_paid_minor: number;
  due_on: string | null;
  reference: string | null;
  goal_id: number | null;
  notes: string | null;
  created_at: string;
  outstanding_minor: number;
  status: FeeStatus;
}

export interface FeePayment {
  id: number;
  fee_id: number;
  amount_minor: number;
  occurred_on: string;
  transaction_id: number | null;
  reference: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface HostelOption {
  id: number;
  name: string;
  location: string | null;
  monthly_rent_minor: number | null;
  deposit_minor: number | null;
  status: HostelStatus;
  facilities: string | null;
  booking_source: string | null;
  last_checked_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface FoodBudget {
  id: number;
  weekly_budget_minor: number | null;
  notes: string | null;
  updated_at: string;
  daily_estimate_minor: number | null;
}

export interface StudentSummary {
  total_fees_due_minor: number;
  total_fees_paid_minor: number;
  total_fees_outstanding_minor: number;
  overdue_fees_count: number;
  hostel_options_count: number;
}

// --- Notification preferences ---
export interface NotificationPreference {
  id: number;
  deadline_alerts: boolean;
  task_reminders: boolean;
  low_stock_warnings: boolean;
  savings_nudges: boolean;
  fee_due_alerts: boolean;
  quiet_start: string | null;
  quiet_end: string | null;
  updated_at: string;
}

// --- What needs attention today ---
// Derived from the user's own records on every request and never stored, so an
// alert disappears as soon as the thing behind it changes.
export type AlertKind = "deadline" | "task" | "fee" | "stock" | "savings";
export type AlertSeverity = "overdue" | "due" | "soon" | "attention";

export interface NotificationAlert {
  key: string;
  kind: AlertKind;
  severity: AlertSeverity;
  title: string;
  detail: string | null;
  /** Null means this alert holds no money, or the figure was never recorded. */
  amount_minor: number | null;
  /** What a period of saving would need to reach the target, when the alert is
   * about a rate rather than a sum. */
  period_amount_minor: number | null;
  period_label: string | null;
  due_on: string | null;
  days_out: number | null;
  link: string;
}

export interface AlertsResponse {
  generated_on: string;
  generated_at: string;
  /** The currency every *_minor figure below is in. */
  currency: string;
  alerts: NotificationAlert[];
  count: number;
  /** Kinds the user's own switches hid, so an empty list can say why. */
  hidden_by_preferences: AlertKind[];
  in_quiet_hours: boolean;
  quiet_ends_at: string | null;
  quiet_start: string | null;
  quiet_end: string | null;
}

// --- AI Assistant ---
export interface MetricItem {
  label: string;
  minor: number | null;
  text: string | null;
  hint: string | null;
}
export interface ListRow {
  heading: string;
  sub: string | null;
  badge: string | null;
  minor: number | null;
  lines: string[];
}
export type AssistantCard =
  | { kind: "metrics"; title: string; items: MetricItem[]; rows?: never }
  | { kind: "list"; title: string; rows: ListRow[]; items?: never };

export type ProposalStatus = "pending" | "confirmed" | "dismissed";
export interface ProposedAction {
  id: number;
  kind: string;
  title: string;
  payload: Record<string, unknown>;
  status: ProposalStatus;
  result: Record<string, unknown> | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AssistantMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  cards: AssistantCard[] | null;
  asset_id: string | null;
  created_at: string;
  proposal: ProposedAction | null;
}

export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail {
  conversation: ConversationSummary;
  messages: AssistantMessage[];
}

export interface SendResponse {
  conversation_id: number;
  user_message: AssistantMessage;
  assistant_message: AssistantMessage;
}

/** The optional local Qwen model. Never loaded by the app itself: the AI page
 * asks for it, so `state` starts at "unloaded" on every launch. */
export type AssistantModelState = "unloaded" | "loading" | "ready" | "failed";

export interface AssistantModelStatus {
  enabled: boolean;
  available: boolean;
  state: AssistantModelState;
  model_file: string | null;
  size_mb: number | null;
  threads: number;
  ctx: number;
  error: string | null;
}

// --- Reports ---
export interface ReportPeriod {
  date_from: string | null;
  date_to: string | null;
  account_id: number | null;
  account_name: string | null;
  category: string | null;
}
export interface CashFlow {
  income_minor: number;
  expense_minor: number;
  net_minor: number;
  transfers_minor: number;
  txn_count: number;
}
export interface CategorySpend {
  category: string;
  total_minor: number;
  count: number;
}
export interface BalancePoint {
  month: string;
  net_change_minor: number;
  running_balance_minor: number;
}
export interface BalanceHistory {
  available: boolean;
  starting_balance_minor: number | null;
  points: BalancePoint[];
  note: string | null;
}
export interface SavingsProgress {
  total_saved_in_goals_minor: number;
  saved_in_period_minor: number;
  active_goals: number;
  completed_goals: number;
}
export interface GoalProgress {
  id: number;
  name: string;
  type: string;
  status: string;
  percent: number | null;
  remaining_amount_minor: number | null;
  remaining_quantity: number | null;
}
export interface ShortageReport {
  items_below_target: number;
  price_needed_items: number;
  estimated_cost_minor: number | null;
}
export interface BusinessReport {
  revenue_minor: number;
  expenses_minor: number;
  net_profit_minor: number;
}
export interface ObligationItem {
  name: string;
  kind: string;
  due_on: string | null;
  outstanding_minor: number | null;
  status: string;
}
export interface ObligationsReport {
  outstanding_fees_minor: number;
  overdue_count: number;
  items: ObligationItem[];
}
export interface ReportSummary {
  period: ReportPeriod;
  currency: string;
  cash_flow: CashFlow;
  spending_by_category: CategorySpend[];
  balance_history: BalanceHistory;
  savings: SavingsProgress;
  goals: GoalProgress[];
  shortage: ShortageReport;
  business: BusinessReport;
  obligations: ObligationsReport;
  note: string;
}

// --- Net worth (value of what you own) ---
export interface ValuationLine {
  item_id: number;
  name: string;
  category_name: string | null;
  category_slug: string | null;
  quantity_owned: number;
  unit: string | null;
  target_quantity: number | null;
  needed_quantity: number;
  unit_cost_minor: number | null;
  price_verified: boolean;
  value_minor: number | null;
  to_target_minor: number | null;
  price_needed: boolean;
  image_asset_id: string | null;
}

export interface NetWorthSaved {
  on_date: string;
  net_worth_minor: number | null;
  priced_value_minor: number;
  valued_items: number;
  unpriced_items: number;
  complete: boolean;
  updated_at: string;
}

export interface Valuation {
  currency: string;
  lines: ValuationLine[];
  items: number;
  units_owned: number;
  units_needed: number;
  net_worth_minor: number | null;
  priced_value_minor: number;
  valued_items: number;
  unpriced_items: number;
  to_target_minor: number | null;
  replacement_total_minor: number | null;
  saved: NetWorthSaved | null;
  history: NetWorthSaved[];
  note: string;
}

// --- Settings, privacy and account ---

/** available = works now; on_demand = present but only runs when started;
 * manual = you do the work and the app records it; not_configured = built but
 * switched off; unavailable = no such connection exists in this product. */
export type IntegrationStatus =
  | "available"
  | "on_demand"
  | "manual"
  | "not_configured"
  | "unavailable";

export interface Integration {
  key: string;
  label: string;
  status: IntegrationStatus;
  detail: string;
  action: string | null;
}

export interface StoredTable {
  key: string;
  label: string;
  rows: number;
}

export interface ExcludedTable {
  key: string;
  label: string;
  reason: string;
}

export interface PrivacyInfo {
  local_only: boolean;
  /** The app's own data folder, and only in local desktop mode. */
  data_dir: string | null;
  stored: StoredTable[];
  row_total: number;
  excluded: ExcludedTable[];
  statement: string[];
}

export interface SettingsView {
  profile: User;
  preferences: NotificationPreference;
  integrations: Integration[];
  privacy: PrivacyInfo;
  export_note: string;
}

export interface ResetResult {
  deleted: Record<string, number>;
  deleted_total: number;
  kept: string[];
  reseeded: string[];
  note: string;
}

// A restore reads an archive the app wrote earlier and reports what bringing it
// back would mean, before anything is overwritten.
export interface RestorePreviewTable {
  key: string;
  label: string;
  archive_rows: number;
  current_rows: number;
}

export interface RestorePreview {
  /** When the archive was written, as the file states it. A backup's age is
   * part of deciding whether to trust it. */
  generated_at: string | null;
  currency_of_origin: string | null;
  current_currency: string;
  photo_links_kept: number;
  photo_links_cleared: number;
  archive_total: number;
  current_total: number;
  warnings: string[];
  tables: RestorePreviewTable[];
}

export interface RestoreResult {
  written: Record<string, number>;
  written_total: number;
  replaced: Record<string, number>;
  replaced_total: number;
  generated_at: string | null;
  currency: string;
  currency_changed_from: string | null;
  photo_links_kept: number;
  photo_links_cleared: number;
  warnings: string[];
  reseeded_categories: boolean;
  kept: string[];
  note: string;
}
