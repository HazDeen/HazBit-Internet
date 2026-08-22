import type { Device, FamilyGroup, Overview, Payment, Plan, ReferralStatistics, Ticket, TicketDetail } from "./types";

const day = 86_400_000;
const now = Date.now();
const iso = (offset: number) => new Date(now + offset * day).toISOString();

export const mockOverview: Overview = {
  user: {
    id: "0192ca0f-5af7-7af5-98d6-72af6eb6f101",
    public_name: "Амина",
    email: "amina@northmail.io",
    telegram_user_id: 816402915,
    telegram_username: "amina_north",
    locale: "ru",
    created_at: iso(-96),
  },
  subscription: {
    id: "0192bc30-1111-7000-9000-000000000001",
    status: "active",
    source: "purchase",
    plan_version_id: "0192bc20-1111-7000-9000-000000000003",
    plan_slug: "family",
    plan_name: "Family",
    starts_at: iso(-18),
    current_period_ends_at: iso(42),
    device_limit: 10,
    family_member_limit: 5,
  },
  vpn: { desired_status: "active", observed_status: "active", expires_at: iso(42), provisioning: false },
  active_device_count: 3,
  open_ticket_count: 1,
  family_group_id: "0192fb10-1111-7000-9000-000000000001",
  family_group_name: "North household",
};

export const mockPlans: Plan[] = [
  {
    id: "0192ba10-1111-7000-9000-000000000001", slug: "basic", name: "Basic",
    description: "Private access for one person and everyday browsing.", plan_version_id: "0192bc20-1111-7000-9000-000000000001",
    device_limit: 3, family_member_limit: 0, traffic_limit_bytes: null,
    prices: [{ id: "0192bd10-1111-7000-9000-000000000001", term_months: 1, duration_days: 30, currency: "RUB", amount_minor: 29900 }, { id: "0192bd10-1111-7000-9000-000000000002", term_months: 12, duration_days: 365, currency: "RUB", amount_minor: 249900 }],
  },
  {
    id: "0192ba10-1111-7000-9000-000000000002", slug: "premium", name: "Premium",
    description: "More devices, faster routing priority and advanced protection.", plan_version_id: "0192bc20-1111-7000-9000-000000000002",
    device_limit: 5, family_member_limit: 0, traffic_limit_bytes: null,
    prices: [{ id: "0192bd10-1111-7000-9000-000000000003", term_months: 1, duration_days: 30, currency: "RUB", amount_minor: 49900 }, { id: "0192bd10-1111-7000-9000-000000000004", term_months: 12, duration_days: 365, currency: "RUB", amount_minor: 419900 }],
  },
  {
    id: "0192ba10-1111-7000-9000-000000000003", slug: "family", name: "Family",
    description: "One secure perimeter for the people and devices close to you.", plan_version_id: "0192bc20-1111-7000-9000-000000000003",
    device_limit: 10, family_member_limit: 5, traffic_limit_bytes: null,
    prices: [{ id: "0192bd10-1111-7000-9000-000000000005", term_months: 1, duration_days: 30, currency: "RUB", amount_minor: 79900 }, { id: "0192bd10-1111-7000-9000-000000000006", term_months: 12, duration_days: 365, currency: "RUB", amount_minor: 679900 }],
  },
];

export const mockDevices: Device[] = [
  { id: "0192de10-1111-7000-9000-000000000001", slot_number: 1, label: "Amina’s MacBook", hwid: "7C9A-E12F-40B8", platform: "macOS", status: "active", first_seen_at: iso(-72), last_seen_at: new Date(now - 4 * 60_000).toISOString() },
  { id: "0192de10-1111-7000-9000-000000000002", slot_number: 2, label: "iPhone 15", hwid: "A113-9BC0-22F4", platform: "iOS", status: "active", first_seen_at: iso(-61), last_seen_at: new Date(now - 17 * 60_000).toISOString() },
  { id: "0192de10-1111-7000-9000-000000000003", slot_number: 3, label: "Home TV", hwid: "TV88-10AC-9931", platform: "Android TV", status: "pending", first_seen_at: iso(-2), last_seen_at: null },
];

export const mockPayments: Payment[] = [
  { id: "0192ed90-1111-7000-9000-000000000001", plan_price_id: mockPlans[2].prices[0].id, status: "activated", amount_minor: 79900, currency: "RUB", expires_at: iso(-17), uploaded_at: iso(-18), approved_at: iso(-18), rejection_reason: null, created_at: iso(-18) },
  { id: "0192ed90-1111-7000-9000-000000000002", plan_price_id: mockPlans[1].prices[0].id, status: "approved", amount_minor: 49900, currency: "RUB", expires_at: iso(-48), uploaded_at: iso(-49), approved_at: iso(-49), rejection_reason: null, created_at: iso(-49) },
];

export const mockFamily: FamilyGroup = {
  id: "0192fb10-1111-7000-9000-000000000001", owner_user_id: mockOverview.user.id, subscription_id: mockOverview.subscription!.id,
  name: "North household", status: "active", member_limit: 5, active_member_count: 3, pending_invitation_count: 1, device_limit: 10, active_device_count: 7,
  members: [
    { id: "0192fc10-1111-7000-9000-000000000001", user_id: mockOverview.user.id, email: mockOverview.user.email, role: "owner", joined_at: iso(-18) },
    { id: "0192fc10-1111-7000-9000-000000000002", user_id: "0192ca0f-5af7-7af5-98d6-72af6eb6f102", email: "timur@relay.one", role: "member", joined_at: iso(-14) },
    { id: "0192fc10-1111-7000-9000-000000000003", user_id: "0192ca0f-5af7-7af5-98d6-72af6eb6f103", email: "sofia@madeup.studio", role: "member", joined_at: iso(-9) },
  ],
  invitations: [{ id: "0192fd10-1111-7000-9000-000000000001", family_group_id: "0192fb10-1111-7000-9000-000000000001", invited_user_id: null, invited_email: "daria@example.com", status: "pending", expires_at: iso(2), created_at: iso(-1) }],
  created_at: iso(-18), updated_at: iso(-1),
};

export const mockReferral: ReferralStatistics = {
  code: { code: "AMINA7HQ", share_url: "https://hazbit.app/r/AMINA7HQ", status: "active", usage_limit: null, expires_at: null },
  total: 8, attributed: 1, qualified: 1, rewarded: 6, rejected: 0, pending_referrer_days: 5, granted_referrer_days: 30, referred_by_status: null, referred_reward_days: 0,
};

export const mockTickets: Ticket[] = [
  { id: "0192aa10-1111-7000-9000-000000000001", public_number: 1048, user_id: mockOverview.user.id, assigned_to_user_id: null, subject: "WireGuard profile disconnects on iOS", category: "connection", priority: "high", status: "waiting_user", last_message_at: new Date(now - 9 * 60_000).toISOString(), closed_at: null, version: 3, created_at: iso(-1), updated_at: new Date(now - 9 * 60_000).toISOString() },
  { id: "0192aa10-1111-7000-9000-000000000002", public_number: 1019, user_id: mockOverview.user.id, assigned_to_user_id: null, subject: "Payment receipt review", category: "payment", priority: "normal", status: "closed", last_message_at: iso(-21), closed_at: iso(-21), version: 4, created_at: iso(-22), updated_at: iso(-21) },
];

export const mockTicketDetails: Record<string, TicketDetail> = {
  [mockTickets[0].id]: { ticket: mockTickets[0], messages: [
    { id: "0192ab10-1111-7000-9000-000000000001", ticket_id: mockTickets[0].id, sender_user_id: mockOverview.user.id, message_type: "message", body: "The VPN profile disconnects every few minutes on my iPhone. I already reinstalled it.", created_at: iso(-1) },
    { id: "0192ab10-1111-7000-9000-000000000002", ticket_id: mockTickets[0].id, sender_user_id: null, message_type: "message", body: "Thanks — we refreshed your device session. Please reconnect once and tell us if it remains stable.", created_at: new Date(now - 9 * 60_000).toISOString() },
  ] },
  [mockTickets[1].id]: { ticket: mockTickets[1], messages: [{ id: "0192ab10-1111-7000-9000-000000000003", ticket_id: mockTickets[1].id, sender_user_id: null, message_type: "message", body: "Your payment was approved and the subscription was extended.", created_at: iso(-21) }] },
};
