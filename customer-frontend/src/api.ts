import { mockDevices, mockFamily, mockOverview, mockPayments, mockPlans, mockReferral, mockTicketDetails, mockTickets, mockWallet } from "./mock";
import type { AuthResponse, Device, FamilyGroup, Payment, PromoPreview, RegistrationStartResponse, TelegramIdStartResponse, TelegramPendingResponse, TicketDetail, TicketMessage, Wallet } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const demoMode = import.meta.env.VITE_DEMO_MODE === "true";

const demoDb = {
  overview: structuredClone(mockOverview), plans: structuredClone(mockPlans), devices: structuredClone(mockDevices),
  payments: structuredClone(mockPayments), family: structuredClone(mockFamily), referral: structuredClone(mockReferral),
  tickets: structuredClone(mockTickets), ticketDetails: structuredClone(mockTicketDetails),
  wallet: structuredClone(mockWallet),
};

let accessToken = sessionStorage.getItem("hazbit_customer_access_token");
const fingerprintKey = "hazbit_customer_fingerprint";

export function hasSession() { return Boolean(accessToken); }
export function clearSession() { accessToken = null; sessionStorage.removeItem("hazbit_customer_access_token"); }
export function idempotencyKey(scope: string) { return `${scope}-${crypto.randomUUID()}`; }
export function deviceFingerprint() {
  let value = localStorage.getItem(fingerprintKey);
  if (!value) { value = `web-${crypto.randomUUID()}`; localStorage.setItem(fingerprintKey, value); }
  return value;
}

function storeAuth(response: AuthResponse) {
  accessToken = response.access_token;
  sessionStorage.setItem("hazbit_customer_access_token", response.access_token);
  return response.user;
}

function csrfToken(): string | null {
  const entry = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("hazbit_csrf="));
  return entry ? decodeURIComponent(entry.split("=").slice(1).join("=")) : null;
}

async function refresh(): Promise<boolean> {
  const csrf = csrfToken();
  if (!csrf) return false;
  const response = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf } });
  if (!response.ok) return false;
  const data = await response.json() as AuthResponse;
  accessToken = data.access_token; sessionStorage.setItem("hazbit_customer_access_token", data.access_token); return true;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (demoMode) { await new Promise((resolve) => window.setTimeout(resolve, 180)); return demoRequest<T>(path, init); }
  const request = () => {
    const form = init.body instanceof FormData;
    return fetch(`${API_URL}${path}`, {
      ...init, credentials: "include",
      headers: {
        ...(form ? {} : { "Content-Type": "application/json" }),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        "X-Device-Fingerprint": deviceFingerprint(),
        ...init.headers,
      },
    });
  };
  let response = await request();
  if (response.status === 401 && await refresh()) response = await request();
  if (!response.ok) {
    const problem = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(problem?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

function demoRequest<T>(path: string, init: RequestInit): T {
  const route = path.split("?")[0];
  const method = init.method ?? "GET";
  const body = typeof init.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {};
  const now = new Date().toISOString();

  if (route === "/portal/overview") return structuredClone(demoDb.overview) as T;
  if (route === "/portal/plans") return structuredClone(demoDb.plans) as T;
  if (route === "/catalog/plans") return structuredClone(demoDb.plans) as T;
  if (route === "/portal/payments") return structuredClone(demoDb.payments) as T;
  if (route === "/billing/wallet" && method === "GET") return structuredClone(demoDb.wallet) as T;
  if (route === "/billing/top-ups" && method === "POST") {
    const amount = Number(body.amount_minor);
    const topUp = { id: crypto.randomUUID(), provider: "platega", provider_transaction_id: crypto.randomUUID(), payment_method: Number(body.payment_method), status: "confirmed", amount_minor: amount, currency: String(body.currency ?? "RUB"), checkout_url: null, expires_at: new Date(Date.now() + 900_000).toISOString(), confirmed_at: now, cancelled_at: null, created_at: now };
    demoDb.wallet.balance_minor += amount;
    demoDb.wallet.top_ups.unshift(topUp);
    demoDb.wallet.transactions.unshift({ id: crypto.randomUUID(), transaction_type: "payment_credit", amount_minor: amount, currency: topUp.currency, description: "Пополнение баланса через Platega", created_at: now });
    return structuredClone(topUp) as T;
  }
  if (route === "/billing/purchases" && method === "POST") {
    const price = demoDb.plans.flatMap((plan) => plan.prices).find((item) => item.id === body.plan_price_id);
    if (!price) throw new Error("Тариф не найден");
    if (demoDb.wallet.balance_minor < price.amount_minor) throw new Error("Недостаточно средств на балансе");
    demoDb.wallet.balance_minor -= price.amount_minor;
    demoDb.wallet.auto_renew_enabled = Boolean(body.auto_renew);
    demoDb.wallet.auto_renew_plan_price_id = price.id;
    demoDb.wallet.transactions.unshift({ id: crypto.randomUUID(), transaction_type: "subscription_debit", amount_minor: -price.amount_minor, currency: price.currency, description: "Оплата тарифа Hazbit", created_at: now });
    return { transaction_id: crypto.randomUUID(), subscription_id: demoDb.overview.subscription?.id ?? crypto.randomUUID(), balance_minor: demoDb.wallet.balance_minor, currency: price.currency, current_period_ends_at: demoDb.overview.subscription?.current_period_ends_at ?? new Date(Date.now() + 2_592_000_000).toISOString(), auto_renew_enabled: Boolean(body.auto_renew) } as T;
  }
  if (route === "/billing/auto-renew" && method === "PATCH") {
    demoDb.wallet.auto_renew_enabled = Boolean(body.enabled);
    return structuredClone(demoDb.wallet) as T;
  }
  if (route === "/auth/email/start" && method === "POST") return { message: "Demo code sent" } as T;
  if (route === "/auth/password" && method === "POST") return { access_token: "customer-demo-token", token_type: "bearer", expires_in: 900, user: { id: demoDb.overview.user.id, display_name: demoDb.overview.user.public_name, email: String(body.email), telegram_user_id: demoDb.overview.user.telegram_user_id, roles: ["USER"] } } as T;
  if (route === "/auth/register/start" && method === "POST") return { message: "Demo code sent", registration_token: "demo-registration-token-000000", telegram_confirmation_url: body.telegram_user_id ? "https://t.me/example_bot?start=reg_demo" : null } as T;
  if ((route === "/auth/register/verify" || route === "/auth/register/complete") && method === "POST") {
    if (route.endsWith("verify") && String(body.code) !== "000000") throw new Error("Для демо используйте код 000000");
    return { access_token: "customer-demo-token", token_type: "bearer", expires_in: 900, user: { id: demoDb.overview.user.id, display_name: demoDb.overview.user.public_name, email: "demo@hazdeen.xyz", telegram_user_id: demoDb.overview.user.telegram_user_id, roles: ["USER"] } } as T;
  }
  if (route === "/auth/email/verify" && method === "POST") {
    if (String(body.code) !== "000000") throw new Error("Для демо используйте код 000000");
    return {
      access_token: "customer-demo-token",
      token_type: "bearer",
      expires_in: 900,
      user: { id: demoDb.overview.user.id, display_name: demoDb.overview.user.public_name, email: String(body.email), telegram_user_id: demoDb.overview.user.telegram_user_id, roles: ["USER"] },
    } as T;
  }
  if (route === "/auth/logout" && method === "POST") return undefined as T;
  if (route === "/devices" && method === "GET") return structuredClone(demoDb.devices) as T;
  if (route === "/vpn/config") return { subscription_url: "https://sub.hazdeen.xyz/c/demo-secure-token" } as T;
  if (route === "/family/group" && method === "GET") return structuredClone(demoDb.family) as T;
  if (route === "/family/groups" && method === "POST") {
    demoDb.family = {
      ...structuredClone(mockFamily),
      id: crypto.randomUUID(),
      subscription_id: String(body.subscription_id),
      name: String(body.name ?? "Family"),
      created_at: now,
      updated_at: now,
    };
    demoDb.overview.family_group_id = demoDb.family.id;
    demoDb.overview.family_group_name = demoDb.family.name;
    return structuredClone(demoDb.family) as T;
  }
  if (route === "/family/invitations") return { invitations: [] } as T;
  if (route === "/referrals/statistics") return structuredClone(demoDb.referral) as T;
  if (route === "/referrals/code" && method === "POST") return structuredClone(demoDb.referral.code) as T;
  if (route === "/tickets" && method === "GET") return structuredClone(demoDb.tickets) as T;

  if (route === "/devices" && method === "POST") {
    const device: Device = { id: crypto.randomUUID(), slot_number: demoDb.devices.length + 1, label: String(body.label ?? "New device"), hwid: String(body.hwid ?? "WEB-DEMO-HWID"), platform: String(body.platform ?? "Web"), status: "pending", first_seen_at: now, last_seen_at: null };
    demoDb.devices.push(device); demoDb.overview.active_device_count += 1;
    return { command_id: crypto.randomUUID(), status: "pending", device: structuredClone(device) } as T;
  }
  const deviceDelete = route.match(/^\/devices\/([^/]+)$/);
  if (deviceDelete && method === "DELETE") {
    const device = demoDb.devices.find((item) => item.id === deviceDelete[1]);
    if (!device) throw new Error("Device not found");
    device.status = "revoked"; demoDb.overview.active_device_count = Math.max(0, demoDb.overview.active_device_count - 1);
    return { command_id: crypto.randomUUID(), status: "pending" } as T;
  }

  const familyRename = route.match(/^\/family\/groups\/([^/]+)$/);
  if (familyRename && method === "PATCH") { demoDb.family.name = String(body.name); demoDb.overview.family_group_name = demoDb.family.name; return structuredClone(demoDb.family) as T; }
  const familyInvite = route.match(/^\/family\/groups\/([^/]+)\/invitations$/);
  if (familyInvite && method === "POST") {
    const invitation = { id: crypto.randomUUID(), family_group_id: demoDb.family.id, invited_user_id: null, invited_email: String(body.invited_email), status: "pending", expires_at: new Date(Date.now() + 72 * 3_600_000).toISOString(), created_at: now, invite_token: `demo-${crypto.randomUUID()}` };
    demoDb.family.invitations.unshift(invitation); demoDb.family.pending_invitation_count += 1; return structuredClone(invitation) as T;
  }
  const familyInviteDelete = route.match(/^\/family\/groups\/([^/]+)\/invitations\/([^/]+)$/);
  if (familyInviteDelete && method === "DELETE") {
    const invitation = demoDb.family.invitations.find((item) => item.id === familyInviteDelete[2]);
    if (!invitation) throw new Error("Invitation not found");
    invitation.status = "revoked"; demoDb.family.pending_invitation_count = demoDb.family.invitations.filter((item) => item.status === "pending").length; return structuredClone(invitation) as T;
  }
  const familyMemberDelete = route.match(/^\/family\/groups\/([^/]+)\/members\/([^/]+)$/);
  if (familyMemberDelete && method === "DELETE") {
    demoDb.family.members = demoDb.family.members.filter((item) => item.user_id !== familyMemberDelete[2]); demoDb.family.active_member_count = demoDb.family.members.length; return undefined as T;
  }

  if (route === "/promo-codes/preview" && method === "POST") {
    const code = String(body.code ?? "").toUpperCase();
    if (code !== "WELCOME20" && code !== "FAMILY7") throw new Error("Промокод не найден или больше не действует");
    const percent = code === "WELCOME20" ? 20 : 0;
    const preview: PromoPreview = { code, promo_type: percent ? "discount_percent" : "free_days", value: percent || 7, starts_at: now, expires_at: null, plan_version_id: null, original_amount_minor: percent ? 79900 : null, discount_amount_minor: percent ? 15980 : null, final_amount_minor: percent ? 63920 : null, currency: percent ? "RUB" : null };
    return preview as T;
  }
  if (route === "/promo-codes/redeem" && method === "POST") return { id: crypto.randomUUID(), code: String(body.code), promo_type: "free_days", value: 7, free_days: 7, redeemed_at: now } as T;

  if (route === "/payments/intents" && method === "POST") {
    const price = demoDb.plans.flatMap((plan) => plan.prices).find((item) => item.id === body.plan_price_id);
    if (!price) throw new Error("Plan price not found");
    const payment: Payment = { id: crypto.randomUUID(), plan_price_id: price.id, status: "pending_upload", amount_minor: price.amount_minor, currency: price.currency, expires_at: new Date(Date.now() + 3_600_000).toISOString(), uploaded_at: null, approved_at: null, rejection_reason: null, created_at: now };
    demoDb.payments.unshift(payment); return { ...structuredClone(payment), expected_amount_minor: payment.amount_minor, original_amount_minor: payment.amount_minor, discount_amount_minor: 0, expected_recipient: "HAZBIT VPN", version: 1 } as T;
  }
  const evidence = route.match(/^\/payments\/([^/]+)\/evidence$/);
  if (evidence && method === "POST") {
    const payment = demoDb.payments.find((item) => item.id === evidence[1]);
    if (!payment) throw new Error("Payment not found"); payment.status = "analyzing"; payment.uploaded_at = now;
    window.setTimeout(() => { payment.status = "approved"; payment.approved_at = new Date().toISOString(); }, 1300);
    return { payment: structuredClone(payment), evidence_id: crypto.randomUUID(), sha256: "demo" } as T;
  }

  if (route === "/tickets" && method === "POST") {
    const ticket = { id: crypto.randomUUID(), public_number: 1054 + demoDb.tickets.length, user_id: demoDb.overview.user.id, assigned_to_user_id: null, subject: String(body.subject), category: String(body.category ?? "general"), priority: "normal", status: "open", last_message_at: now, closed_at: null, version: 1, created_at: now, updated_at: now };
    const detail: TicketDetail = { ticket, messages: [{ id: crypto.randomUUID(), ticket_id: ticket.id, sender_user_id: demoDb.overview.user.id, message_type: "message", body: String(body.message), created_at: now }] };
    demoDb.tickets.unshift(ticket); demoDb.ticketDetails[ticket.id] = detail; demoDb.overview.open_ticket_count += 1; return structuredClone(detail) as T;
  }
  const ticketDetail = route.match(/^\/tickets\/([^/]+)$/);
  if (ticketDetail && method === "GET") { const value = demoDb.ticketDetails[ticketDetail[1]]; if (!value) throw new Error("Ticket not found"); return structuredClone(value) as T; }
  const ticketMessage = route.match(/^\/tickets\/([^/]+)\/messages$/);
  if (ticketMessage && method === "POST") {
    const detail = demoDb.ticketDetails[ticketMessage[1]]; if (!detail) throw new Error("Ticket not found");
    const message: TicketMessage = { id: crypto.randomUUID(), ticket_id: detail.ticket.id, sender_user_id: demoDb.overview.user.id, message_type: "message", body: String(body.body), created_at: now };
    detail.messages.push(message); detail.ticket.status = "open"; detail.ticket.last_message_at = now; return structuredClone(message) as T;
  }
  throw new Error(`No demo route for ${method} ${route}`);
}

export async function startEmailLogin(email: string) {
  await api("/auth/email/start", { method: "POST", body: JSON.stringify({ email, device_fingerprint: deviceFingerprint() }) });
}

export async function verifyEmailLogin(email: string, code: string) {
  const response = await api<AuthResponse>("/auth/email/verify", { method: "POST", body: JSON.stringify({ email, code, device_fingerprint: deviceFingerprint() }) });
  return storeAuth(response);
}

export async function loginWithPassword(email: string, password: string) {
  return storeAuth(await api<AuthResponse>("/auth/password", { method: "POST", body: JSON.stringify({ email, password, device_fingerprint: deviceFingerprint() }) }));
}

export async function startRegistration(input: { publicName: string; email: string; password: string; telegramUserId?: number }) {
  return api<RegistrationStartResponse>("/auth/register/start", { method: "POST", body: JSON.stringify({ public_name: input.publicName, email: input.email, password: input.password, telegram_user_id: input.telegramUserId, device_fingerprint: deviceFingerprint() }) });
}

export async function verifyRegistration(registrationToken: string, code: string) {
  const response = await api<AuthResponse | TelegramPendingResponse>("/auth/register/verify", { method: "POST", body: JSON.stringify({ registration_token: registrationToken, code, device_fingerprint: deviceFingerprint() }) });
  if ("access_token" in response) return { user: storeAuth(response), pending: null };
  return { user: null, pending: response.telegram_confirmation_url };
}

export async function completeRegistration(registrationToken: string) {
  const response = await api<AuthResponse | TelegramPendingResponse>("/auth/register/complete", { method: "POST", body: JSON.stringify({ registration_token: registrationToken, device_fingerprint: deviceFingerprint() }) });
  if ("access_token" in response) return { user: storeAuth(response), pending: null };
  return { user: null, pending: response.telegram_confirmation_url };
}

export async function loginWithGoogle(credential: string) {
  return storeAuth(await api<AuthResponse>("/auth/google", { method: "POST", body: JSON.stringify({ credential, device_fingerprint: deviceFingerprint() }) }));
}

export interface TelegramWidgetUser { id: number; first_name: string; last_name?: string; username?: string; photo_url?: string; auth_date: number; hash: string }
export async function loginWithTelegramWidget(user: TelegramWidgetUser) {
  return storeAuth(await api<AuthResponse>("/auth/telegram/widget", { method: "POST", body: JSON.stringify({ ...user, device_fingerprint: deviceFingerprint() }) }));
}

export async function startTelegramIdLogin(telegramUserId: number) {
  return api<TelegramIdStartResponse>("/auth/telegram-id/start", { method: "POST", body: JSON.stringify({ telegram_user_id: telegramUserId, device_fingerprint: deviceFingerprint() }) });
}

export async function verifyTelegramIdLogin(challengeToken: string) {
  const response = await api<AuthResponse | TelegramPendingResponse>("/auth/telegram-id/verify", { method: "POST", body: JSON.stringify({ challenge_token: challengeToken, device_fingerprint: deviceFingerprint() }) });
  if ("access_token" in response) return { user: storeAuth(response), pending: false };
  return { user: null, pending: true };
}

export async function logout() {
  const csrf = csrfToken();
  try {
    await api("/auth/logout", {
      method: "POST",
      headers: csrf ? { "X-CSRF-Token": csrf } : {},
    });
  } finally {
    clearSession();
  }
}

export async function uploadPaymentEvidence(paymentId: string, file: File) {
  const form = new FormData(); form.append("evidence", file);
  return api(`/payments/${paymentId}/evidence`, { method: "POST", body: form, headers: { "Idempotency-Key": idempotencyKey("evidence") } });
}
