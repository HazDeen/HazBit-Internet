export type Section = "overview" | "subscription" | "billing" | "devices" | "family" | "rewards" | "support" | "profile";
export type Locale = "ru" | "en";
export type Theme = "dark" | "light";

export interface Identity { id: string; public_name: string | null; email: string | null; telegram_user_id: number | null; telegram_username: string | null; locale: string; created_at: string }
export interface Subscription { id: string; status: string; source: string; plan_version_id: string; plan_slug: string; plan_name: string; starts_at: string | null; current_period_ends_at: string | null; device_limit: number; family_member_limit: number }
export interface Overview { user: Identity; subscription: Subscription | null; vpn: { desired_status: string; observed_status: string | null; expires_at: string | null; provisioning: boolean } | null; active_device_count: number; open_ticket_count: number; family_group_id: string | null; family_group_name: string | null }
export interface PlanPrice { id: string; term_months: number; duration_days: number; currency: string; amount_minor: number }
export interface Plan { id: string; slug: string; name: string; description: string | null; plan_version_id: string; device_limit: number; family_member_limit: number; traffic_limit_bytes: number | null; prices: PlanPrice[] }
export interface Device { id: string; slot_number: number; label: string | null; hwid: string | null; platform: string | null; status: string; first_seen_at: string | null; last_seen_at: string | null }
export interface Payment { id: string; plan_price_id: string; status: string; amount_minor: number; currency: string; expires_at: string; uploaded_at: string | null; approved_at: string | null; rejection_reason: string | null; created_at: string }
export interface VpnConfig { subscription_url: string }
export interface FamilyMember { id: string; user_id: string; email: string | null; role: "owner" | "member"; joined_at: string }
export interface FamilyInvitation { id: string; family_group_id: string; invited_user_id: string | null; invited_email: string | null; status: string; expires_at: string; created_at: string; invite_token?: string | null }
export interface FamilyGroup { id: string; owner_user_id: string; subscription_id: string; name: string; status: string; member_limit: number; active_member_count: number; pending_invitation_count: number; device_limit: number; active_device_count: number; members: FamilyMember[]; invitations: FamilyInvitation[]; created_at: string; updated_at: string }
export interface FamilyInbox { invitations: FamilyInvitation[] }
export interface ReferralStatistics { code: { code: string; share_url: string; status: string; usage_limit: number | null; expires_at: string | null } | null; total: number; attributed: number; qualified: number; rewarded: number; rejected: number; pending_referrer_days: number; granted_referrer_days: number; referred_by_status: string | null; referred_reward_days: number }
export interface PromoPreview { code: string; promo_type: string; value: number; starts_at: string; expires_at: string | null; plan_version_id: string | null; original_amount_minor: number | null; discount_amount_minor: number | null; final_amount_minor: number | null; currency: string | null }
export interface Ticket { id: string; public_number: number; user_id: string; assigned_to_user_id: string | null; subject: string; category: string; priority: string; status: string; last_message_at: string; closed_at: string | null; version: number; created_at: string; updated_at: string }
export interface TicketMessage { id: string; ticket_id: string; sender_user_id: string | null; message_type: string; body: string; created_at: string }
export interface TicketDetail { ticket: Ticket; messages: TicketMessage[] }
export interface AuthUser { id: string; display_name: string | null; email: string | null; telegram_user_id: number | null; roles: string[] }
export interface AuthResponse { access_token: string; token_type: string; expires_in: number; user: AuthUser }
export interface RegistrationStartResponse { message: string; registration_token: string; telegram_confirmation_url: string | null }
export interface TelegramPendingResponse { status: "telegram_confirmation_required"; telegram_confirmation_url: string }
export interface TelegramIdStartResponse { challenge_token: string; confirmation_url: string; expires_in: number }
export interface WalletTopUp { id: string; provider: string; provider_transaction_id: string | null; payment_method: number; status: string; amount_minor: number; currency: string; checkout_url: string | null; expires_at: string | null; confirmed_at: string | null; cancelled_at: string | null; created_at: string }
export interface WalletTransaction { id: string; transaction_type: string; amount_minor: number; currency: string; description: string | null; created_at: string }
export interface Wallet { balance_minor: number; currency: string; auto_renew_enabled: boolean; auto_renew_plan_price_id: string | null; next_renewal_at: string | null; last_renewal_failure: string | null; top_ups: WalletTopUp[]; transactions: WalletTransaction[] }
export interface WalletPurchase { transaction_id: string; subscription_id: string; balance_minor: number; currency: string; current_period_ends_at: string; auto_renew_enabled: boolean }
