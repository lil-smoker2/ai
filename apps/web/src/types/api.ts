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
export type AccountType = "cash" | "mpesa" | "bank" | "wallet" | "custom";
export type TransactionType = "income" | "expense" | "transfer";

export interface Account {
  id: number;
  name: string;
  type: AccountType;
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
