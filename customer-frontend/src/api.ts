import { mockDevices, mockFamily, mockOverview, mockPayments, mockPlans, mockReferral, mockTicketDetails, mockTickets } from "./mock";
import type { AuthResponse, Device, FamilyGroup, Payment, PromoPreview, TicketDetail, TicketMessage } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const demoMode = import.meta.env.VITE_DEMO_MODE === "true";

const demoDb = {
  overview: structuredClone(mockOverview), plans: structuredClone(mockPlans), devices: structuredClone(mockDevices),
  payments: structuredClone(mockPayments), family: structuredClone(mockFamily), referral: structuredClone(mockReferral),
  tickets: structuredClone(mockTickets), ticketDetails: structuredClone(mockTicketDetails),
};

let accessToken = sessionStorage.getItem("hazbit_customer_access_token");
const fingerprintKey = "hazbit_customer_fingerprint";

export function hasSession() { return demoMode || Boolean(accessToken); }
export function clearSession() { accessToken = null; sessionStorage.removeItem("hazbit_customer_access_token"); }
export function idempotencyKey(scope: string) { return `${scope}-${crypto.randomUUID()}`; }
export function deviceFingerprint() {
  let value = localStorage.getItem(fingerprintKey);
  if (!value) { value = `web-${crypto.randomUUID()}`; localStorage.setItem(fingerprintKey, value); }
  return value;
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
  if (route === "/portal/payments") return structuredClone(demoDb.payments) as T;
  if (route === "/auth/logout" && method === "POST") return undefined as T;
  if (route === "/devices" && method === "GET") return structuredClone(demoDb.devices) as T;
  if (route === "/vpn/config") return { subscription_url: "https://sub.hazbit.app/c/demo-secure-token" } as T;
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
  accessToken = response.access_token; sessionStorage.setItem("hazbit_customer_access_token", response.access_token); return response.user;
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
