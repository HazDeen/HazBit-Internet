import { mockDevices, mockFamily, mockOverview, mockPayments, mockPlans, mockReferral, mockTicketDetails, mockTickets } from "../../customer-frontend/src/mock";
import type { AuthResponse, Device, FamilyGroup, Overview, Payment, Plan, PromoPreview, ReferralStatistics, Ticket, TicketDetail, TicketMessage, VpnConfig } from "../../shared/customer/types";
import { tg } from "./telegram";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const demoMode = import.meta.env.VITE_DEMO_MODE === "true";
let accessToken = sessionStorage.getItem("hazbit_tma_access_token");

const demo = {
  overview: structuredClone(mockOverview), plans: structuredClone(mockPlans), payments: structuredClone(mockPayments),
  devices: structuredClone(mockDevices), family: structuredClone(mockFamily), referral: structuredClone(mockReferral),
  tickets: structuredClone(mockTickets), details: structuredClone(mockTicketDetails),
};

function fingerprint() {
  const key = "hazbit_tma_fingerprint";
  let value = localStorage.getItem(key);
  if (!value) { value = `tma-${tg.platform}-${crypto.randomUUID()}`; localStorage.setItem(key, value); }
  return value;
}

function csrf() {
  const part = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("hazbit_csrf="));
  return part ? decodeURIComponent(part.split("=").slice(1).join("=")) : null;
}

async function refresh() {
  const token = csrf(); if (!token) return false;
  const response = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": token } });
  if (!response.ok) return false;
  const data = await response.json() as AuthResponse;
  accessToken = data.access_token; sessionStorage.setItem("hazbit_tma_access_token", data.access_token); return true;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (demoMode) { await new Promise((resolve) => setTimeout(resolve, 130)); return demoRequest<T>(path, init); }
  const request = () => fetch(`${API_URL}${path}`, { ...init, credentials: "include", headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), "X-Device-Fingerprint": fingerprint(), ...init.headers } });
  let response = await request();
  if (response.status === 401 && await refresh()) response = await request();
  if (!response.ok) { const problem = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(problem?.detail ?? `Request failed (${response.status})`); }
  return response.status === 204 ? undefined as T : await response.json() as T;
}

export async function authenticateTelegram() {
  if (demoMode) { accessToken = "telegram-demo"; return; }
  if (!tg.initData) throw new Error("Откройте Mini App внутри Telegram");
  const result = await api<AuthResponse>("/auth/telegram", { method: "POST", body: JSON.stringify({ init_data: tg.initData, device_fingerprint: fingerprint() }) });
  accessToken = result.access_token; sessionStorage.setItem("hazbit_tma_access_token", result.access_token);
}

export const hasSession = () => demoMode || Boolean(accessToken);
export const key = (scope: string) => `${scope}-${crypto.randomUUID()}`;

function demoRequest<T>(path: string, init: RequestInit): T {
  const route = path.split("?")[0]; const method = init.method ?? "GET"; const now = new Date().toISOString();
  const body = typeof init.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : {};
  if (route === "/portal/overview") return structuredClone(demo.overview) as T;
  if (route === "/portal/plans") return structuredClone(demo.plans) as T;
  if (route === "/portal/payments") return structuredClone(demo.payments) as T;
  if (route === "/devices" && method === "GET") return structuredClone(demo.devices) as T;
  if (route === "/family/group") return structuredClone(demo.family) as T;
  if (route === "/referrals/statistics") return structuredClone(demo.referral) as T;
  if (route === "/tickets" && method === "GET") return structuredClone(demo.tickets) as T;
  if (route === "/vpn/config") return { subscription_url: "https://sub.hazbit.app/c/telegram-demo" } as VpnConfig as T;
  if (route === "/promo-codes/preview" && method === "POST") {
    const code = String(body.code ?? "").toUpperCase(); if (code !== "WELCOME20") throw new Error("Промокод не найден");
    return { code, promo_type: "discount_percent", value: 20, starts_at: now, expires_at: null, plan_version_id: null, original_amount_minor: 79900, discount_amount_minor: 15980, final_amount_minor: 63920, currency: "RUB" } as PromoPreview as T;
  }
  if (route === "/payments/intents" && method === "POST") {
    const price = demo.plans.flatMap((plan) => plan.prices).find((item) => item.id === body.plan_price_id)!;
    const payment: Payment = { id: crypto.randomUUID(), plan_price_id: price.id, status: "pending_upload", amount_minor: price.amount_minor, currency: price.currency, expires_at: new Date(Date.now() + 3_600_000).toISOString(), uploaded_at: null, approved_at: null, rejection_reason: null, created_at: now };
    demo.payments.unshift(payment); return { ...payment, expected_amount_minor: payment.amount_minor, original_amount_minor: payment.amount_minor, discount_amount_minor: 0, expected_recipient: "HAZBIT VPN", version: 1, telegram_invoice_url: "https://t.me/$hazbit-demo-invoice" } as T;
  }
  if (route === "/devices" && method === "POST") {
    const device: Device = { id: crypto.randomUUID(), slot_number: demo.devices.length + 1, label: String(body.label), hwid: String(body.hwid), platform: String(body.platform), status: "pending", first_seen_at: now, last_seen_at: null };
    demo.devices.push(device); return { command_id: crypto.randomUUID(), device } as T;
  }
  const removeDevice = route.match(/^\/devices\/([^/]+)$/);
  if (removeDevice && method === "DELETE") { demo.devices = demo.devices.filter((item) => item.id !== removeDevice[1]); return undefined as T; }
  const invite = route.match(/^\/family\/groups\/([^/]+)\/invitations$/);
  if (invite && method === "POST") { const value = { id: crypto.randomUUID(), family_group_id: demo.family.id, invited_user_id: null, invited_email: String(body.invited_email), status: "pending", expires_at: new Date(Date.now() + 259_200_000).toISOString(), created_at: now }; demo.family.invitations.unshift(value); demo.family.pending_invitation_count += 1; return structuredClone(value) as T; }
  if (route === "/family/invitations/accept" && method === "POST") return structuredClone(demo.family) as T;
  const detail = route.match(/^\/tickets\/([^/]+)$/);
  if (detail && method === "GET") return structuredClone(demo.details[detail[1]]) as T;
  const message = route.match(/^\/tickets\/([^/]+)\/messages$/);
  if (message && method === "POST") { const target = demo.details[message[1]]; const value: TicketMessage = { id: crypto.randomUUID(), ticket_id: message[1], sender_user_id: demo.overview.user.id, message_type: "message", body: String(body.body), created_at: now }; target.messages.push(value); return structuredClone(value) as T; }
  throw new Error(`No Telegram demo route for ${method} ${route}`);
}

export type { Device, FamilyGroup, Overview, Payment, Plan, PromoPreview, ReferralStatistics, Ticket, TicketDetail };
