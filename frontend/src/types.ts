export type Section =
  | "dashboard"
  | "users"
  | "subscriptions"
  | "payments"
  | "tickets"
  | "promo-codes"
  | "plans"
  | "family-groups"
  | "vpn-devices"
  | "team"
  | "settings";

export interface AuthUser {
  id: string;
  display_name: string | null;
  email: string | null;
  telegram_user_id: number | null;
  roles: string[];
  permissions: string[];
}

export interface StaffMember {
  user_id: string;
  email: string;
  public_name: string | null;
  status: string;
  roles: string[];
  permissions: string[];
  telegram_linked: boolean;
  created_at: string;
}

export interface StaffInvitation {
  id: string;
  email: string;
  roles: string[];
  permissions: string[];
  expires_at: string;
  created_at: string;
}

export interface StaffDirectory {
  members: StaffMember[];
  invitations: StaffInvitation[];
  role_presets: Record<string, string[]>;
  available_permissions: string[];
}

export interface TrendPoint {
  date: string;
  users: number;
  payments_minor: number;
}

export interface DashboardData {
  total_users: number;
  active_users: number;
  active_subscriptions: number;
  monthly_revenue_minor: number;
  revenue_currency: string;
  open_tickets: number;
  pending_payments: number;
  active_vpn_accounts: number;
  active_promo_codes: number;
  trend: TrendPoint[];
}

export interface Subscription {
  id: string;
  owner_user_id?: string;
  owner_email?: string | null;
  plan_version_id: string;
  plan_slug: string;
  plan_name: string;
  status: string;
  source: string;
  starts_at: string | null;
  current_period_ends_at: string | null;
  device_limit: number;
  version: number;
  vpn_status?: string | null;
}

export interface User {
  id: string;
  email: string | null;
  telegram_id: number | null;
  telegram_username: string | null;
  status: string;
  created_at: string;
  subscription: Subscription | null;
  devices: number;
  trial: boolean;
  approved_payments: number;
  paid_total_minor: number;
}

export interface Device {
  id: string;
  user_id: string;
  vpn_account_id: string;
  slot_number: number;
  label: string | null;
  external_hwid: string | null;
  platform: string | null;
  status: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface Payment {
  id: string;
  user_id: string;
  status: string;
  amount_minor: number;
  currency: string;
  plan_price_id: string;
  created_at: string;
  approved_at: string | null;
  version: number;
}

export interface Ticket {
  id: string;
  public_number: number;
  user_id: string;
  assigned_to_user_id: string | null;
  subject: string;
  category: string;
  priority: string;
  status: string;
  last_message_at: string;
  closed_at: string | null;
  version: number;
  created_at: string;
}

export interface TicketMessage {
  id: string;
  ticket_id: string;
  sender_user_id: string | null;
  message_type: string;
  body: string;
  created_at: string;
}

export interface TicketDetail {
  ticket: Ticket;
  messages: TicketMessage[];
}

export interface PromoCode {
  id: string;
  code: string;
  promo_type: string;
  value: number;
  currency: string | null;
  usage_limit: number | null;
  per_user_limit: number;
  starts_at: string;
  expires_at: string | null;
  is_active: boolean;
  plan_version_ids: string[];
  usage_count: number;
}

export interface PlanPrice {
  id: string;
  term_months: number;
  duration_days: number;
  currency: string;
  amount_minor: number;
  is_active: boolean;
}

export interface PlanVersion {
  id: string;
  version: number;
  device_limit: number;
  family_member_limit: number;
  traffic_limit_bytes: number | null;
  valid_from: string;
  valid_until: string | null;
  prices: PlanPrice[];
}

export interface Plan {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  is_active: boolean;
  sort_order: number;
  versions: PlanVersion[];
}

export interface FamilyMember {
  id: string;
  user_id: string;
  email: string | null;
  joined_at: string;
}

export interface FamilyInvitation {
  id: string;
  invited_user_id: string | null;
  invited_email: string | null;
  status: string;
  expires_at: string;
  created_at: string;
}

export interface FamilyGroup {
  id: string;
  owner_user_id: string;
  owner_email: string | null;
  subscription_id: string;
  plan_name: string;
  subscription_status: string;
  name: string;
  status: string;
  member_limit: number;
  active_member_count: number;
  pending_invitation_count: number;
  device_limit: number;
  active_device_count: number;
  created_at: string;
  members: FamilyMember[];
  invitations: FamilyInvitation[];
}

export interface SettingsData {
  environment: string;
  app_version: string;
  log_level: string;
  payment_ai_model: string;
  payment_prompt_version: string;
  remnawave_adapter_url: string;
  referral_days: number;
  referrer_days: number;
  default_promo_plan: string;
  support_create_limit_per_day: number;
  support_message_limit_per_hour: number;
  features: FeatureControl[];
}

export interface FeatureControl {
  key: string;
  label: string;
  description: string;
  configured: boolean;
  runtime_enabled: boolean;
  enabled: boolean;
}

export interface RemnawaveNode {
  uuid: string;
  name: string;
  address: string;
  country_code: string;
  is_connected: boolean;
  is_disabled: boolean;
  is_connecting: boolean;
  last_status_change: string | null;
  last_status_message: string | null;
  users_online: number;
  traffic_used_bytes: number | null;
  traffic_limit_bytes: number | null;
  xray_uptime: number;
  cpu_count: number | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  load_average: number[];
  rx_bytes_per_second: number | null;
  tx_bytes_per_second: number | null;
  xray_version: string | null;
  node_version: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
