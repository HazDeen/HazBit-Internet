import {
  mockDashboard,
  mockDevices,
  mockFamilyGroups,
  mockPayments,
  mockPlans,
  mockPromos,
  mockSettings,
  mockRemnawaveNodes,
  mockSubscriptions,
  mockTickets,
  mockTicketDetails,
  mockUsers,
} from "./mock";
import type { AuthUser, StaffDirectory, StaffMember } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const demoMode = import.meta.env.VITE_DEMO_MODE === "true";

const demoDb = {
  users: structuredClone(mockUsers),
  payments: structuredClone(mockPayments),
  tickets: structuredClone(mockTickets),
  ticketDetails: structuredClone(mockTicketDetails),
  promos: structuredClone(mockPromos),
  plans: structuredClone(mockPlans),
  families: structuredClone(mockFamilyGroups),
  settings: structuredClone(mockSettings),
  nodes: structuredClone(mockRemnawaveNodes),
};

let accessToken = sessionStorage.getItem("hazbit_admin_access_token");
let currentUser = JSON.parse(sessionStorage.getItem("hazbit_admin_user") ?? "null") as AuthUser | null;

const demoUser: AuthUser = {
  id: "0192ca0f-5af7-7af5-98d6-72af6eb6fa01",
  display_name: "Hazbit Owner",
  email: "owner@hazdeen.xyz",
  telegram_user_id: 816402915,
  roles: ["super_admin"],
  permissions: [
    "dashboard.read", "users.read", "users.manage", "subscriptions.read",
    "subscriptions.manage", "payments.read", "payments.review", "tickets.read",
    "tickets.reply", "tickets.manage", "promotions.manage", "plans.manage",
    "families.manage", "vpn.read", "vpn.nodes.manage", "settings.read", "staff.manage",
  ],
};

const demoStaff: StaffDirectory = {
  members: [
    { user_id: demoUser.id, email: demoUser.email!, public_name: demoUser.display_name, status: "active", roles: ["super_admin"], permissions: [], telegram_linked: true, created_at: "2026-05-18T10:00:00Z" },
    { user_id: "0192ca0f-5af7-7af5-98d6-72af6eb6fa02", email: "support@hazdeen.xyz", public_name: "Hazbit Support", status: "active", roles: ["support"], permissions: [], telegram_linked: true, created_at: "2026-08-12T11:30:00Z" },
  ],
  invitations: [],
  role_presets: {
    super_admin: demoUser.permissions,
    admin: demoUser.permissions.filter((item) => item !== "staff.manage"),
    support: ["dashboard.read", "users.read", "tickets.read", "tickets.reply", "tickets.manage"],
    network: ["dashboard.read", "users.read", "subscriptions.read", "vpn.read", "vpn.nodes.manage"],
    finance: ["dashboard.read", "users.read", "subscriptions.read", "payments.read", "payments.review"],
    content: ["dashboard.read", "promotions.manage", "plans.manage"],
  },
  available_permissions: demoUser.permissions,
};

export function hasSession(): boolean {
  return demoMode || Boolean(accessToken && currentUser);
}

export function clearSession(): void {
  accessToken = null;
  sessionStorage.removeItem("hazbit_admin_access_token");
  currentUser = null;
  sessionStorage.removeItem("hazbit_admin_user");
}

export function getSessionUser(): AuthUser {
  return demoMode ? demoUser : currentUser ?? {
    id: "",
    display_name: null,
    email: null,
    telegram_user_id: null,
    roles: [],
    permissions: [],
  };
}

function csrfToken(): string | null {
  const entry = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("hazbit_csrf="));
  return entry ? decodeURIComponent(entry.split("=").slice(1).join("=")) : null;
}

async function refresh(): Promise<boolean> {
  const csrf = csrfToken();
  if (!csrf) return false;
  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  });
  if (!response.ok) return false;
  const data = (await response.json()) as { access_token: string };
  accessToken = data.access_token;
  sessionStorage.setItem("hazbit_admin_access_token", data.access_token);
  return true;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (demoMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    return demoRequest<T>(path, init);
  }

  const request = async () =>
    fetch(`${API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    });
  let response = await request();
  if (response.status === 401 && (await refresh())) response = await request();
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(problem?.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function demoRequest<T>(path: string, init: RequestInit): T {
  const route = path.split("?")[0];
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
  const now = new Date().toISOString();

  if (route === "/admin/staff/invitations" && method === "POST") {
    const invitation = {
      id: crypto.randomUUID(),
      email: String(body.email),
      roles: body.roles as string[],
      permissions: body.permissions as string[],
      expires_at: new Date(Date.now() + 72 * 3600_000).toISOString(),
      created_at: now,
    };
    demoStaff.invitations.unshift(invitation);
    return structuredClone(invitation) as T;
  }
  const staffInviteMutation = route.match(/^\/admin\/staff\/invitations\/([^/]+)$/);
  if (staffInviteMutation && method === "DELETE") {
    const index = demoStaff.invitations.findIndex((item) => item.id === staffInviteMutation[1]);
    if (index >= 0) demoStaff.invitations.splice(index, 1);
    return undefined as T;
  }

  const featureMutation = route.match(/^\/admin\/settings\/features\/([^/]+)$/);
  if (featureMutation && method === "PATCH") {
    const feature = demoDb.settings.features.find((item) => item.key === featureMutation[1]);
    if (!feature) throw new Error("Feature not found");
    feature.runtime_enabled = Boolean(body.enabled);
    feature.enabled = feature.configured && feature.runtime_enabled;
    return structuredClone(feature) as T;
  }

  const nodeMutation = route.match(/^\/admin\/remnawave\/nodes\/([^/]+)\/(enable|disable)$/);
  if (nodeMutation && method === "POST") {
    const node = demoDb.nodes.find((item) => item.uuid === nodeMutation[1]);
    if (!node) throw new Error("Node not found");
    node.is_disabled = nodeMutation[2] === "disable";
    node.is_connected = !node.is_disabled;
    node.last_status_change = now;
    return structuredClone(node) as T;
  }

  const paymentReview = route.match(/^\/admin\/payments\/([^/]+)\/review$/);
  if (paymentReview && method === "POST") {
    const payment = demoDb.payments.items.find((item) => item.id === paymentReview[1]);
    if (!payment) throw new Error("Payment not found");
    payment.status = body.decision === "rejected" ? "rejected" : "approved";
    payment.approved_at = payment.status === "approved" ? now : null;
    payment.version += 1;
    return structuredClone(payment) as T;
  }

  const ticketReply = route.match(/^\/admin\/tickets\/([^/]+)\/messages$/);
  if (ticketReply && method === "POST") {
    const detail = demoDb.ticketDetails[ticketReply[1]];
    if (!detail) throw new Error("Ticket not found");
    const message = {
      id: crypto.randomUUID(),
      ticket_id: detail.ticket.id,
      sender_user_id: "0192ca0f-5af7-7af5-98d6-72af6eb6fa01",
      message_type: String(body.message_type ?? "message"),
      body: String(body.body ?? ""),
      created_at: now,
    };
    detail.messages.push(message);
    detail.ticket.status = String(body.status_after ?? "waiting_user");
    detail.ticket.version += 1;
    Object.assign(demoDb.tickets.find((item) => item.id === detail.ticket.id) ?? {}, detail.ticket);
    return structuredClone(message) as T;
  }

  const ticketUpdate = route.match(/^\/admin\/tickets\/([^/]+)$/);
  if (ticketUpdate && method === "PATCH") {
    const detail = demoDb.ticketDetails[ticketUpdate[1]];
    if (!detail) throw new Error("Ticket not found");
    if (body.status) detail.ticket.status = String(body.status);
    if (body.priority) detail.ticket.priority = String(body.priority);
    detail.ticket.version += 1;
    Object.assign(demoDb.tickets.find((item) => item.id === detail.ticket.id) ?? {}, detail.ticket);
    return structuredClone(detail.ticket) as T;
  }

  if (route === "/admin/promo-codes" && method === "POST") {
    const promo = {
      id: crypto.randomUUID(),
      code: String(body.code ?? "NEWCODE").toUpperCase(),
      promo_type: String(body.promo_type ?? "discount_percent"),
      value: Number(body.value ?? 10),
      currency: body.promo_type === "free_days" ? null : String(body.currency ?? "RUB"),
      usage_limit: body.usage_limit == null ? null : Number(body.usage_limit),
      per_user_limit: Number(body.per_user_limit ?? 1),
      starts_at: String(body.starts_at ?? now),
      expires_at: body.expires_at ? String(body.expires_at) : null,
      is_active: true,
      plan_version_ids: Array.isArray(body.plan_version_ids) ? body.plan_version_ids as string[] : [],
      usage_count: 0,
    };
    demoDb.promos.unshift(promo);
    return structuredClone(promo) as T;
  }

  const promoMutation = route.match(/^\/admin\/promo-codes\/([^/]+)$/);
  if (promoMutation && (method === "PATCH" || method === "DELETE")) {
    const promo = demoDb.promos.find((item) => item.id === promoMutation[1]);
    if (!promo) throw new Error("Promo code not found");
    if (method === "DELETE") promo.is_active = false;
    else Object.assign(promo, body);
    return structuredClone(promo) as T;
  }

  if (route === "/admin/plans" && method === "POST") {
    const plan = buildDemoPlan(body, now);
    demoDb.plans.push(plan);
    return structuredClone(plan) as T;
  }

  const planVersion = route.match(/^\/admin\/plans\/([^/]+)\/versions$/);
  if (planVersion && method === "POST") {
    const plan = demoDb.plans.find((item) => item.id === planVersion[1]);
    if (!plan) throw new Error("Plan not found");
    plan.versions.unshift(buildDemoVersion(body, now, (plan.versions[0]?.version ?? 0) + 1));
    return structuredClone(plan) as T;
  }

  const planMutation = route.match(/^\/admin\/plans\/([^/]+)$/);
  if (planMutation && (method === "PATCH" || method === "DELETE")) {
    const plan = demoDb.plans.find((item) => item.id === planMutation[1]);
    if (!plan) throw new Error("Plan not found");
    if (method === "DELETE") plan.is_active = false;
    else Object.assign(plan, body);
    return structuredClone(plan) as T;
  }

  const userMutation = route.match(/^\/admin\/users\/([^/]+)\/(block|unblock)$/);
  if (userMutation && method === "POST") {
    const user = demoDb.users.items.find((item) => item.id === userMutation[1]);
    if (!user) throw new Error("User not found");
    user.status = userMutation[2] === "block" ? "blocked" : "active";
    return structuredClone(user) as T;
  }

  const subscriptionMutation = route.match(
    /^\/admin\/users\/([^/]+)\/subscription\/(extend|plan)$/,
  );
  if (subscriptionMutation && (method === "POST" || method === "PATCH")) {
    const user = demoDb.users.items.find((item) => item.id === subscriptionMutation[1]);
    if (!user?.subscription) throw new Error("Subscription not found");
    if (subscriptionMutation[2] === "extend") {
      const end = new Date(user.subscription.current_period_ends_at ?? now);
      end.setUTCDate(end.getUTCDate() + Number(body.days ?? 0));
      user.subscription.current_period_ends_at = end.toISOString();
    } else {
      const target = demoDb.plans.find((plan) =>
        plan.versions.some((version) => version.id === body.plan_version_id),
      );
      const version = target?.versions.find((item) => item.id === body.plan_version_id);
      if (target && version) {
        user.subscription.plan_version_id = version.id;
        user.subscription.plan_name = target.name;
        user.subscription.plan_slug = target.slug;
        user.subscription.device_limit = version.device_limit;
      }
    }
    user.subscription.version += 1;
    return structuredClone(user.subscription) as T;
  }

  const userDevices = route.match(/^\/admin\/users\/([^/]+)\/devices$/);
  if (userDevices && method === "GET") {
    const items = mockDevices.items.filter((device) => device.user_id === userDevices[1]);
    return structuredClone({ items, total: items.length, limit: 100, offset: 0 }) as T;
  }
  const ticketDetail = route.match(/^\/admin\/tickets\/([^/]+)$/);
  if (ticketDetail && method === "GET") {
    const detail = demoDb.ticketDetails[ticketDetail[1]];
    if (!detail) throw new Error("Ticket not found");
    return structuredClone(detail) as T;
  }

  const familyMemberMutation = route.match(
    /^\/admin\/family-groups\/([^/]+)\/members\/([^/]+)$/,
  );
  if (familyMemberMutation && method === "DELETE") {
    const group = demoDb.families.items.find((item) => item.id === familyMemberMutation[1]);
    if (!group) throw new Error("Family group not found");
    if (familyMemberMutation[2] === group.owner_user_id) {
      throw new Error("The family owner cannot be removed");
    }
    const memberIndex = group.members.findIndex(
      (member) => member.user_id === familyMemberMutation[2],
    );
    if (memberIndex < 0) throw new Error("Family member not found");
    group.members.splice(memberIndex, 1);
    group.active_member_count = group.members.length;
    return undefined as T;
  }

  const familyInvitationMutation = route.match(
    /^\/admin\/family-groups\/([^/]+)\/invitations\/([^/]+)$/,
  );
  if (familyInvitationMutation && method === "DELETE") {
    const group = demoDb.families.items.find((item) => item.id === familyInvitationMutation[1]);
    if (!group) throw new Error("Family group not found");
    const invitation = group.invitations.find(
      (item) => item.id === familyInvitationMutation[2],
    );
    if (!invitation) throw new Error("Family invitation not found");
    invitation.status = "revoked";
    group.pending_invitation_count = group.invitations.filter(
      (item) => item.status === "pending",
    ).length;
    return undefined as T;
  }

  const familyDetail = route.match(/^\/admin\/family-groups\/([^/]+)$/);
  if (familyDetail && method === "GET") {
    const group = demoDb.families.items.find((item) => item.id === familyDetail[1]);
    if (!group) throw new Error("Family group not found");
    return structuredClone(group) as T;
  }

  if (route === "/admin/users" && method === "GET") {
    const status = new URLSearchParams(path.split("?")[1] ?? "").get("status");
    const items = status
      ? demoDb.users.items.filter((user) => user.status === status)
      : demoDb.users.items;
    return structuredClone({ ...demoDb.users, items, total: items.length }) as T;
  }

  const routes: Record<string, unknown> = {
    "/admin/dashboard": mockDashboard,
    "/admin/users": demoDb.users,
    "/admin/subscriptions": mockSubscriptions,
    "/admin/payments": demoDb.payments,
    "/admin/tickets": demoDb.tickets,
    "/admin/promo-codes": demoDb.promos,
    "/admin/plans": demoDb.plans,
    "/admin/family-groups": demoDb.families,
    "/admin/vpn-devices": mockDevices,
    "/admin/settings": demoDb.settings,
    "/admin/remnawave/nodes": demoDb.nodes,
    "/admin/staff": demoStaff,
  };
  const value = routes[route];
  if (value === undefined) throw new Error(`No demo route for ${method} ${route}`);
  return structuredClone(value) as T;
}

function buildDemoPlan(body: Record<string, unknown>, now: string) {
  return {
    id: crypto.randomUUID(),
    slug: String(body.slug ?? "new-plan"),
    name: String(body.name ?? "New plan"),
    description: body.description ? String(body.description) : null,
    is_active: true,
    sort_order: Number(body.sort_order ?? demoDb.plans.length),
    versions: [buildDemoVersion(body, now, 1)],
  };
}

function buildDemoVersion(body: Record<string, unknown>, now: string, version: number) {
  const rawPrices = Array.isArray(body.prices) ? body.prices as Record<string, unknown>[] : [];
  return {
    id: crypto.randomUUID(),
    version,
    device_limit: Number(body.device_limit ?? 3),
    family_member_limit: Number(body.family_member_limit ?? 0),
    traffic_limit_bytes: body.traffic_limit_bytes == null ? null : Number(body.traffic_limit_bytes),
    valid_from: now,
    valid_until: null,
    prices: rawPrices.map((price) => ({
      id: crypto.randomUUID(),
      term_months: Number(price.term_months ?? 1),
      duration_days: Number(price.duration_days ?? 30),
      currency: String(price.currency ?? "RUB"),
      amount_minor: Number(price.amount_minor ?? 0),
      is_active: true,
    })),
  };
}

export async function startEmailLogin(email: string): Promise<void> {
  await api("/auth/email/start", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function verifyEmailLogin(
  email: string, code: string, options: { allowUser?: boolean } = {},
): Promise<void> {
  const response = await api<{
    access_token: string;
    user: AuthUser;
  }>("/auth/email/verify", {
    method: "POST",
    body: JSON.stringify({ email, code }),
  });
  if (!options.allowUser && !response.user.permissions.some((value) => value === "dashboard.read")) {
    throw new Error("This account does not have administrator access.");
  }
  accessToken = response.access_token;
  sessionStorage.setItem("hazbit_admin_access_token", response.access_token);
  currentUser = response.user;
  sessionStorage.setItem("hazbit_admin_user", JSON.stringify(response.user));
}

export async function acceptStaffInvitation(token: string): Promise<void> {
  await api<StaffMember>("/admin/staff/invitations/accept", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
  currentUser = await api<AuthUser>("/auth/me");
  sessionStorage.setItem("hazbit_admin_user", JSON.stringify(currentUser));
}
