import {
  Activity,
  ArrowRight,
  Archive,
  BadgePercent,
  Ban,
  Bell,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Cpu,
  Clock3,
  CreditCard,
  Gauge,
  Headphones,
  HeartHandshake,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Languages,
  LifeBuoy,
  LoaderCircle,
  LogOut,
  MailPlus,
  MessageSquareText,
  MonitorSmartphone,
  MoreHorizontal,
  Network,
  PackageOpen,
  Pencil,
  Plus,
  RefreshCw,
  Radio,
  Search,
  Send,
  ServerCog,
  Settings,
  ShieldCheck,
  Smartphone,
  Sparkles,
  TicketCheck,
  Trash2,
  UserRound,
  UserCog,
  ShieldPlus,
  UserMinus,
  Users,
  WalletCards,
  X,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  acceptStaffInvitation,
  clearSession,
  demoMode,
  getSessionUser,
  hasSession,
  startEmailLogin,
  verifyEmailLogin,
} from "./api";
import { LocaleProvider, useI18n } from "./i18n";
import { StaffPage } from "./features/staff/StaffPage";
import { useResource, type LoadState } from "./hooks/useResource";
import type {
  DashboardData,
  Device,
  FamilyGroup,
  Page,
  Payment,
  Plan,
  PromoCode,
  Section,
  SettingsData,
  FeatureControl,
  RemnawaveNode,
  Subscription,
  Ticket,
  TicketDetail,
  User,
} from "./types";

const sectionMeta: Record<Section, { label: string; eyebrow: string; icon: LucideIcon }> = {
  dashboard: { label: "Dashboard", eyebrow: "Network overview", icon: LayoutDashboard },
  users: { label: "Users", eyebrow: "Identity & access", icon: Users },
  subscriptions: { label: "Subscriptions", eyebrow: "Entitlements", icon: WalletCards },
  payments: { label: "Payments", eyebrow: "Revenue operations", icon: CreditCard },
  tickets: { label: "Tickets", eyebrow: "Support queue", icon: LifeBuoy },
  "promo-codes": { label: "Promo Codes", eyebrow: "Campaigns", icon: BadgePercent },
  plans: { label: "Plans", eyebrow: "Product catalog", icon: PackageOpen },
  "family-groups": { label: "Family Groups", eyebrow: "Shared access", icon: HeartHandshake },
  "vpn-devices": { label: "VPN Devices", eyebrow: "Fleet inventory", icon: MonitorSmartphone },
  settings: { label: "Settings", eyebrow: "Platform policy", icon: Settings },
  team: { label: "Team", eyebrow: "Roles & permissions", icon: UserCog },
};

const sectionPermission: Partial<Record<Section, string>> = {
  dashboard: "dashboard.read", users: "users.read", subscriptions: "subscriptions.read",
  payments: "payments.read", tickets: "tickets.read", "promo-codes": "promotions.manage",
  plans: "plans.manage", "family-groups": "families.manage", "vpn-devices": "vpn.read",
  settings: "settings.read", team: "staff.manage",
};

const currentInvitationToken = () => {
  const hash = window.location.hash.slice(1);
  if (!hash.startsWith("staff-invite")) return null;
  return new URLSearchParams(hash.split("?")[1] ?? "").get("token");
};

function App() {
  const [authenticated, setAuthenticated] = useState(hasSession());
  const [invitationToken, setInvitationToken] = useState(currentInvitationToken());
  const invitationAccepted = useCallback(() => {
    window.location.hash = "team";
    setInvitationToken(null);
  }, []);
  return (
    <LocaleProvider>
      {!authenticated
        ? <Login invitationToken={invitationToken} onAuthenticated={() => { setAuthenticated(true); setInvitationToken(null); }} />
        : invitationToken
          ? <StaffInviteActivation token={invitationToken} onAccepted={invitationAccepted} />
        : <AdminApp onLogout={() => setAuthenticated(false)} />}
    </LocaleProvider>
  );
}

function Login({ onAuthenticated, invitationToken }: { onAuthenticated: () => void; invitationToken: string | null }) {
  const { locale, t } = useI18n();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (phase === "email") {
        await startEmailLogin(email);
        setPhase("code");
      } else {
        await verifyEmailLogin(email, code, { allowUser: Boolean(invitationToken) });
        if (invitationToken) {
          await acceptStaffInvitation(invitationToken);
          window.location.hash = "team";
        }
        onAuthenticated();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("Authentication failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-story" aria-label={t("Hazbit platform status")}>
        <Brand />
        <div className="login-copy">
          <div className="signal-tag"><span /> {t("Protected operations channel")}</div>
          <h1>{locale === "ru" ? <>Управляйте сетью.<br />Поддерживайте стабильный сигнал.</> : <>Control the network.<br />Keep the signal clean.</>}</h1>
          <p>{t("One console for users, revenue, support and the VPN fleet—built for calm, accountable operations.")}</p>
        </div>
        <div className="login-grid" aria-hidden="true">
          {Array.from({ length: 48 }).map((_, index) => <i key={index} />)}
        </div>
        <div className="login-status">
          <span><Activity size={15} /> {t("API online")}</span>
          <span><ShieldCheck size={15} /> {t("RBAC enforced")}</span>
          <span>MSK · UTC+3</span>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-language"><LanguageSwitch /></div>
        <form className="login-card" onSubmit={submit}>
          <div className="login-icon"><KeyRound size={22} /></div>
          <p className="overline">{t(invitationToken ? "Team invitation" : "Administrator access")}</p>
          <h2>{t(phase === "email" ? "Sign in to Hazbit" : "Check your inbox")}</h2>
          <p className="muted">
            {phase === "email"
              ? t("Use an email assigned to an admin or super admin role.")
              : `${t("Enter the one-time code sent to")} ${email}.`}
          </p>
          {phase === "email" ? (
            <label className="field-label">
              {t("Work email")}
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="admin@hazdeen.xyz"
                autoComplete="email"
                required
              />
            </label>
          ) : (
            <label className="field-label">
              {t("Verification code")}
              <input
                className="otp-input"
                inputMode="numeric"
                pattern="[0-9]{6,8}"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                placeholder="000000"
                autoComplete="one-time-code"
                autoFocus
                required
              />
            </label>
          )}
          {error && <div className="inline-error">{error}</div>}
          <button className="primary-button login-submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={18} /> : t(phase === "email" ? "Send secure code" : "Open dashboard")}
            {!busy && <ArrowRight size={17} />}
          </button>
          {phase === "code" && (
            <button type="button" className="text-button" onClick={() => setPhase("email")}>
              {t("Use another email")}
            </button>
          )}
          <p className="login-footnote">{t("Short-lived JWT · rotating session · audited access")}</p>
        </form>
      </section>
    </main>
  );
}

function StaffInviteActivation({ token, onAccepted }: { token: string; onAccepted: () => void }) {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    acceptStaffInvitation(token).then(onAccepted).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : t("Invitation could not be accepted"));
    });
  }, [onAccepted, t, token]);
  return <main className="invite-activation"><section className="login-card"><div className="login-icon"><ShieldPlus size={22} /></div><p className="overline">{t("Team invitation")}</p><h2>{t("Activating secure access")}</h2>{error ? <div className="inline-error">{error}</div> : <><LoaderCircle className="spin" size={24} /><p className="muted">{t("Checking the invitation and applying permissions…")}</p></>}</section></main>;
}

function AdminApp({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const sessionUser = getSessionUser();
  const canOpen = (key: Section) => demoMode || !sectionPermission[key] || sessionUser.permissions.includes(sectionPermission[key]!);
  const [section, setSection] = useState<Section>(() => {
    const hash = window.location.hash.slice(1) as Section;
    return hash in sectionMeta && canOpen(hash) ? hash : "dashboard";
  });
  const [toast, setToast] = useState<string | null>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const navigate = (value: Section) => {
    if (!canOpen(value)) return;
    setSection(value);
    window.location.hash = value;
  };
  const notify = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 3200);
  }, []);
  const logout = () => {
    clearSession();
    onLogout();
  };

  return (
    <div className="app-shell">
      <header className="control-header">
        <Brand />
        <div className="control-context"><p>{t(sectionMeta[section].eyebrow)}</p><h1>{t(sectionMeta[section].label)}</h1></div>
        <div className="topbar-actions">
          {demoMode && <span className="demo-badge"><Sparkles size={13} /> {t("Demo data")}</span>}
          <LanguageSwitch />
          <button className="icon-button notification-button" aria-label={t("Notifications")} aria-expanded={notificationsOpen} onClick={() => setNotificationsOpen((value) => !value)}><Bell size={18} /><i /></button>
          <span className="operator-state"><i /> {t("Operator online")}</span>
          <button className="control-profile" onClick={logout} aria-label={t("Log out")}><span className="avatar">{initials(sessionUser.email)}</span><span><b>{sessionUser.display_name ?? sessionUser.email ?? "Hazbit Admin"}</b><small>{t(title(sessionUser.roles[0] ?? "staff"))}</small></span><LogOut size={15} /></button>
        </div>
      </header>
      <nav className="control-nav" aria-label={t("Admin sections")}>
          {(Object.entries(sectionMeta) as [Section, (typeof sectionMeta)[Section]][]).filter(([key]) => canOpen(key)).map(([key, item]) => {
            const Icon = item.icon;
            return (
              <button key={key} className={section === key ? "control-nav-item active" : "control-nav-item"} onClick={() => navigate(key)}>
                <Icon size={18} strokeWidth={1.8} /><span>{t(item.label)}</span>
                {key === "tickets" && <b>23</b>}
              </button>
            );
          })}
      </nav>
      <main className="workspace">
        <section className="content">
          {section === "dashboard" && <DashboardPage navigate={navigate} />}
          {section === "users" && <UsersPage notify={notify} />}
          {section === "subscriptions" && <SubscriptionsPage />}
          {section === "payments" && <PaymentsPage notify={notify} />}
          {section === "tickets" && <TicketsPage />}
          {section === "promo-codes" && <PromoPage notify={notify} />}
          {section === "plans" && <PlansPage notify={notify} />}
          {section === "family-groups" && <FamilyGroupsPage />}
          {section === "vpn-devices" && <DevicesPage />}
          {section === "settings" && <SettingsPage />}
          {section === "team" && <StaffPage notify={notify} />}
        </section>
      </main>
      {notificationsOpen && <NotificationCenter navigate={navigate} onClose={() => setNotificationsOpen(false)} />}
      {toast && <div className="toast"><Check size={17} />{toast}</div>}
    </div>
  );
}

function Brand() {
  return <div className="brand"><span className="brand-mark"><i /><i /><i /></span><span>HAZBIT<small>CONTROL</small></span></div>;
}

function LanguageSwitch() {
  const { locale, setLocale } = useI18n();
  return (
    <div className="language-switch" role="group" aria-label={locale === "ru" ? "Язык интерфейса" : "Interface language"}>
      <Languages size={14} aria-hidden="true" />
      {(["ru", "en"] as const).map((value) => (
        <button
          key={value}
          className={locale === value ? "active" : ""}
          aria-pressed={locale === value}
          onClick={() => setLocale(value)}
        >
          {value.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function NotificationCenter({ navigate, onClose }: { navigate: (section: Section) => void; onClose: () => void }) {
  const { locale, t } = useI18n();
  const dashboard = useResource<DashboardData>("/admin/dashboard");
  const open = (section: Section) => { navigate(section); onClose(); };
  const signals = dashboard.data;
  return <><button className="notification-scrim" onClick={onClose} aria-label={t("Close notifications")} /><aside className="notification-center"><header><div><p className="overline">{t("Operations inbox")}</p><h2>{t("Notifications")}</h2></div><button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={17} /></button></header><div className="notification-list"><button onClick={() => open("payments")}><span className="notification-icon amber"><CreditCard size={17} /></span><div><b>{locale === "ru" ? `${signals?.pending_payments ?? "—"} платежей требуют проверки` : `${signals?.pending_payments ?? "—"} payments need review`}</b><small>{locale === "ru" ? "Уверенность Gemini требует решения оператора" : "Gemini confidence requires an operator decision"}</small></div><ChevronRight size={16} /></button><button onClick={() => open("tickets")}><span className="notification-icon red"><MessageSquareText size={17} /></span><div><b>{locale === "ru" ? `${signals?.open_tickets ?? "—"} открытых обращений` : `${signals?.open_tickets ?? "—"} open support conversations`}</b><small>{locale === "ru" ? "Откройте очередь для проверки времени ответа" : "Open the queue to review response times"}</small></div><ChevronRight size={16} /></button><button onClick={() => open("family-groups")}><span className="notification-icon blue"><HeartHandshake size={17} /></span><div><b>{locale === "ru" ? "Операции семейных групп" : "Family group operations"}</b><small>{locale === "ru" ? "Участники, лимиты и состояние подписки" : "Review membership, capacity and subscription state"}</small></div><ChevronRight size={16} /></button><button onClick={() => open("vpn-devices")}><span className="notification-icon teal"><Network size={17} /></span><div><b>{locale === "ru" ? `${signals?.active_vpn_accounts ?? "—"} активных VPN-аккаунтов` : `${signals?.active_vpn_accounts ?? "—"} VPN accounts active`}</b><small>{locale === "ru" ? "Откройте парк для проверки синхронизации" : "Open the fleet to inspect desired and observed state"}</small></div><ChevronRight size={16} /></button></div><footer><span className="live-dot" /> {locale === "ru" ? (dashboard.loading ? "Обновляем сигналы" : "Сигналы обновляются в реальном времени") : (dashboard.loading ? "Refreshing operational signals" : "Live operational signals")}</footer></aside></>;
}

function DashboardPage({ navigate }: { navigate: (section: Section) => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<DashboardData>("/admin/dashboard");
  if (!resource.data) return <ResourceState {...resource} />;
  const data = resource.data;
  const cards = [
    { label: t("Active subscriptions"), value: data.active_subscriptions.toLocaleString(locale === "ru" ? "ru-RU" : "en-US"), note: locale === "ru" ? `${data.active_users.toLocaleString("ru-RU")} активных пользователей` : `${data.active_users.toLocaleString()} active users`, icon: ShieldCheck, tone: "teal" },
    { label: t("Revenue this month"), value: money(data.monthly_revenue_minor, data.revenue_currency), note: t("Approved transfers"), icon: CircleDollarSign, tone: "ink" },
    { label: t("Open tickets"), value: data.open_tickets.toLocaleString(locale === "ru" ? "ru-RU" : "en-US"), note: locale === "ru" ? `${data.pending_payments} платежей требуют внимания` : `${data.pending_payments} payments need attention`, icon: Headphones, tone: "amber" },
    { label: t("VPN accounts online"), value: data.active_vpn_accounts.toLocaleString(locale === "ru" ? "ru-RU" : "en-US"), note: t("Desired state: active"), icon: Network, tone: "blue" },
  ];
  return (
    <div className="page-stack dashboard-page">
      <section className="pulse-strip">
        <div><span className="live-dot" /><b>{t("Network pulse")}</b><small>{t("All core services are responding normally")}</small></div>
        <div className="pulse-nodes" aria-hidden="true">{Array.from({ length: 18 }).map((_, index) => <i key={index} style={{ height: `${8 + ((index * 13) % 25)}px` }} />)}</div>
        <button onClick={() => navigate("settings")}>{t("View system settings")} <ArrowRight size={15} /></button>
      </section>
      <div className="metric-grid">
        {cards.map(({ label, value, note, icon: Icon, tone }) => (
          <article className={`metric-card ${tone}`} key={label}><div className="metric-icon"><Icon size={19} /></div><p>{label}</p><strong>{value}</strong><small>{note}</small></article>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel revenue-panel">
          <PanelHeader eyebrow="7 day movement" title="Revenue signal" action={<button className="quiet-button" onClick={() => navigate("payments")}>{t("Open payments")} <ChevronRight size={15} /></button>} />
          <div className="chart-summary"><strong>{money(data.trend.reduce((sum, point) => sum + point.payments_minor, 0), data.revenue_currency)}</strong><span><i /> {t("+12.4% vs previous 7 days")}</span></div>
          <TrendChart points={data.trend.map((point) => point.payments_minor)} labels={data.trend.map((point) => point.date)} />
        </section>
        <section className="panel attention-panel">
          <PanelHeader eyebrow="Operations queue" title="Needs attention" />
          <button onClick={() => navigate("payments")}><span className="attention-icon payment"><CreditCard size={18} /></span><span><b>{locale === "ru" ? `${data.pending_payments} платежей на проверке` : `${data.pending_payments} payment reviews`}</b><small>{locale === "ru" ? "Gemini требует решения оператора" : "Gemini requires operator decision"}</small></span><ChevronRight size={17} /></button>
          <button onClick={() => navigate("tickets")}><span className="attention-icon ticket"><MessageSquareText size={18} /></span><span><b>{locale === "ru" ? `${data.open_tickets} тикетов поддержки` : `${data.open_tickets} support tickets`}</b><small>{locale === "ru" ? "4 с высоким или срочным приоритетом" : "4 marked high or urgent"}</small></span><ChevronRight size={17} /></button>
          <button onClick={() => navigate("promo-codes")}><span className="attention-icon promo"><BadgePercent size={18} /></span><span><b>{locale === "ru" ? `${data.active_promo_codes} активных кампаний` : `${data.active_promo_codes} live campaigns`}</b><small>{locale === "ru" ? "2 завершатся в течение 14 дней" : "2 expire within 14 days"}</small></span><ChevronRight size={17} /></button>
        </section>
      </div>
      <div className="dashboard-grid lower">
        <section className="panel acquisition-panel">
          <PanelHeader eyebrow="Identity growth" title="New users" action={<span className="panel-total">{data.total_users.toLocaleString(locale === "ru" ? "ru-RU" : "en-US")} {locale === "ru" ? "всего" : "total"}</span>} />
          <div className="bar-chart">{data.trend.map((point) => <div key={point.date}><i style={{ height: `${Math.max(12, point.users * 2.1)}px` }} /><span>{new Date(point.date).toLocaleDateString(locale === "ru" ? "ru-RU" : "en", { weekday: "short" })}</span></div>)}</div>
        </section>
        <section className="panel fleet-panel">
          <PanelHeader eyebrow="Remnawave projection" title="Fleet state" />
          <div className="fleet-number"><strong>{data.active_vpn_accounts.toLocaleString(locale === "ru" ? "ru-RU" : "en-US")}</strong><span>{t("active accounts")}</span></div>
          <div className="fleet-track"><i style={{ width: "92%" }} /></div>
          <div className="fleet-legend"><span><i className="active" /> {t("Synced")} 92%</span><span><i className="pending" /> {t("Pending")} 6%</span><span><i className="issue" /> {t("Attention")} 2%</span></div>
        </section>
      </div>
    </div>
  );
}

function UsersPage({ notify }: { notify: (message: string) => void }) {
  const { locale, t } = useI18n();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const path = `/admin/users${status === "all" ? "" : `?status=${status}`}`;
  const resource = useResource<Page<User>>(path);
  const [selected, setSelected] = useState<User | null>(null);
  const [action, setAction] = useState<"block" | "extend" | "plan" | null>(null);
  const filtered = useMemo(() => {
    const items = resource.data?.items ?? [];
    const needle = search.toLowerCase().trim();
    if (!needle) return items;
    return items.filter((user) => [user.id, user.email, user.telegram_username, String(user.telegram_id ?? "")].some((value) => value?.toLowerCase().includes(needle)));
  }, [resource.data, search]);

  const execute = async (payload: Record<string, unknown>) => {
    if (!selected || !action) return;
    const path = action === "block" ? `/admin/users/${selected.id}/${selected.status === "blocked" ? "unblock" : "block"}` : action === "extend" ? `/admin/users/${selected.id}/subscription/extend` : `/admin/users/${selected.id}/subscription/plan`;
    await api(path, { method: action === "plan" ? "PATCH" : "POST", body: JSON.stringify(payload) });
    notify(t(action === "block" ? "User access updated" : action === "extend" ? "Subscription extended" : "Plan changed"));
    setAction(null);
    resource.reload();
  };

  return (
    <div className="page-stack">
      <section className="page-intro"><div><p>{t("Directory")}</p><h2>{resource.data?.total.toLocaleString(locale === "ru" ? "ru-RU" : "en-US") ?? "—"} {t("registered users")}</h2><span>{t("Identity, entitlement and payment context in one operational view.")}</span></div><button className="quiet-button" onClick={resource.reload}><RefreshCw size={15} /> {t("Refresh")}</button></section>
      <section className="panel table-panel">
        <div className="table-toolbar"><label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search email, ID or Telegram")} /></label><div className="segmented">{["all", "active", "blocked"].map((value) => <button key={value} className={status === value ? "active" : ""} onClick={() => setStatus(value)}>{t(title(value))}</button>)}</div></div>
        {!resource.data ? <ResourceState {...resource} /> : (
          <div className="table-scroll"><table><thead><tr>{["ID", "Email", "Telegram ID", "Subscription", "Devices", "Trial", "Payments", "Status"].map((column) => <th key={column}>{t(column)}</th>)}<th><span className="sr-only">{t("Actions")}</span></th></tr></thead><tbody>
            {filtered.map((user) => <tr key={user.id} onClick={() => setSelected(user)}><td><span className="mono id-cell" title={user.id}>{shortId(user.id)}</span></td><td><div className="identity-cell"><span>{initials(user.email)}</span><div><b>{user.email ?? t("No email")}</b></div></div></td><td><span className="mono">{user.telegram_id ?? "—"}</span></td><td>{user.subscription ? <div className="stacked-cell"><b>{t(user.subscription.plan_name)}</b><small>{locale === "ru" ? "до" : "until"} {localizedShortDate(user.subscription.current_period_ends_at, locale)}</small></div> : <span className="muted">{t("No subscription")}</span>}</td><td><span className="device-count"><Smartphone size={14} /> {user.devices}</span></td><td>{user.trial ? <Status value="used" /> : <span className="muted">{t("No")}</span>}</td><td><div className="stacked-cell"><b>{money(user.paid_total_minor, "RUB")}</b><small>{locale === "ru" ? `${user.approved_payments} подтверждено` : `${user.approved_payments} approved`}</small></div></td><td><Status value={user.status} /></td><td><button className="icon-button row-menu" aria-label={`${locale === "ru" ? "Действия для" : "Actions for"} ${user.email}`}><MoreHorizontal size={17} /></button></td></tr>)}
          </tbody></table></div>
        )}
      </section>
      {selected && <UserDrawer user={selected} onClose={() => setSelected(null)} onAction={setAction} />}
      {selected && action && <ActionDialog action={action} user={selected} onClose={() => setAction(null)} onSubmit={execute} />}
    </div>
  );
}

function UserDrawer({ user, onClose, onAction }: { user: User; onClose: () => void; onAction: (action: "block" | "extend" | "plan") => void }) {
  const { locale, t } = useI18n();
  const devices = useResource<Page<Device>>(`/admin/users/${user.id}/devices`);
  return <><button className="drawer-scrim" onClick={onClose} aria-label={t("Close user details")} /><aside className="drawer"><header><div className="drawer-avatar">{initials(user.email)}</div><div><p>{t("User profile")}</p><h2>{user.email ?? t("No email")}</h2><Status value={user.status} /></div><button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={19} /></button></header><div className="drawer-body"><section className="detail-block"><h3>{t("Identity")}</h3><Detail label="User ID" value={user.id} mono /><Detail label="Telegram" value={user.telegram_id ? `${user.telegram_id}${user.telegram_username ? ` · @${user.telegram_username}` : ""}` : t("Not linked")} /><Detail label="Joined" value={localizedLongDate(user.created_at, locale)} /></section><section className="detail-block"><h3>{t("Subscription")}</h3>{user.subscription ? <><div className="plan-banner"><div><span>{t(user.subscription.plan_name)}</span><strong>{user.subscription.device_limit} {t("Devices").toLowerCase()}</strong></div><Status value={user.subscription.status} /></div><Detail label="Valid until" value={localizedLongDate(user.subscription.current_period_ends_at, locale)} /><Detail label="Source" value={t(title(user.subscription.source))} /></> : <div className="empty-inline">{t("No active entitlement")}</div>}</section><section className="detail-block"><h3>{t("Usage & payments")}</h3><div className="mini-metrics"><div><strong>{user.devices}</strong><span>{t("Devices")}</span></div><div><strong>{user.approved_payments}</strong><span>{t("Payments")}</span></div><div><strong>{user.trial ? t("Used") : t("No")}</strong><span>{t("Trial")}</span></div></div></section><section className="detail-block"><h3>{t("VPN devices")}</h3>{devices.loading ? <div className="empty-inline">{t("Loading device inventory…")}</div> : devices.data?.items.length ? <div className="drawer-device-list">{devices.data.items.map((device) => <div key={device.id}><span><Smartphone size={15} /></span><div><b>{device.label ? t(device.label) : `${t("Slot")} ${device.slot_number}`}</b><small>{device.platform ?? t("Unknown platform")} · {device.external_hwid ?? t("HWID pending")}</small></div><Status value={device.status} /></div>)}</div> : <div className="empty-inline">{t("No VPN devices")}</div>}</section></div><footer><button className="danger-button" onClick={() => onAction("block")}><Ban size={15} /> {t(user.status === "blocked" ? "Unblock user" : "Block user")}</button><button className="quiet-button" disabled={!user.subscription} onClick={() => onAction("extend")}><Clock3 size={15} /> {t("Extend")}</button><button className="primary-button" disabled={!user.subscription} onClick={() => onAction("plan")}><RefreshCw size={15} /> {t("Change plan")}</button></footer></aside></>;
}

function ActionDialog({ action, user, onClose, onSubmit }: { action: "block" | "extend" | "plan"; user: User; onClose: () => void; onSubmit: (payload: Record<string, unknown>) => Promise<void> }) {
  const { locale, t } = useI18n();
  const [reason, setReason] = useState("");
  const [days, setDays] = useState(30);
  const [plan, setPlan] = useState("0192bc20-1111-7000-9000-000000000002");
  const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); try { await onSubmit(action === "extend" ? { days, reason } : action === "plan" ? { plan_version_id: plan, reason } : { reason }); } finally { setBusy(false); } };
  const heading = action === "block" ? t(user.status === "blocked" ? "Unblock user" : "Block user") : action === "extend" ? t("Extend subscription") : t("Change plan");
  return <div className="modal-layer"><button className="modal-scrim" onClick={onClose} aria-label={locale === "ru" ? "Закрыть диалог" : "Close dialog"} /><form className="modal" onSubmit={submit}><div className={`modal-symbol ${action}`} >{action === "block" ? <Ban size={20} /> : action === "extend" ? <Clock3 size={20} /> : <RefreshCw size={20} />}</div><p className="overline">{t("Admin action")}</p><h2>{heading}</h2><p className="muted">{user.email} · {shortId(user.id)}</p>{action === "extend" && <label className="field-label">{t("Days")}<input type="number" min="1" max="365" value={days} onChange={(event) => setDays(Number(event.target.value))} /></label>}{action === "plan" && <label className="field-label">{t("Target plan")}<select value={plan} onChange={(event) => setPlan(event.target.value)}><option value="0192bc20-1111-7000-9000-000000000001">{t("Basic")} · v1</option><option value="0192bc20-1111-7000-9000-000000000002">{t("Premium")} · v1</option><option value="0192bc20-1111-7000-9000-000000000003">{t("Family")} · v1</option></select></label>}<label className="field-label">{t("Audit reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder={t("Explain why this change is required")} minLength={3} required /></label><footer><button type="button" className="quiet-button" onClick={onClose}>{t("Cancel")}</button><button className={action === "block" ? "danger-button" : "primary-button"} disabled={busy}>{busy && <LoaderCircle className="spin" size={16} />} {t("Confirm action")}</button></footer></form></div>;
}

function SubscriptionsPage() {
  const { locale, t } = useI18n();
  const resource = useResource<Page<Subscription>>("/admin/subscriptions");
  return <CollectionPage title="Subscription ledger" note="Commercial entitlement state and Remnawave projection." resource={resource} columns={["Owner", "Plan", "Status", "Source", "Expires", "VPN"]} render={(item) => <tr key={item.id}><td><div className="stacked-cell"><b>{item.owner_email ?? t("No email")}</b><small>{shortId(item.owner_user_id ?? "")}</small></div></td><td><b>{t(item.plan_name)}</b></td><td><Status value={item.status} /></td><td>{t(title(item.source))}</td><td>{localizedLongDate(item.current_period_ends_at, locale)}</td><td><Status value={item.vpn_status ?? "not provisioned"} /></td></tr>} />;
}

function PaymentsPage({ notify }: { notify: (message: string) => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<Page<Payment>>("/admin/payments");
  const [selected, setSelected] = useState<Payment | null>(null);
  const decide = async (decision: "approved" | "rejected", reason: string) => {
    if (!selected) return;
    await api(`/admin/payments/${selected.id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reason, expected_version: selected.version }),
    });
    notify(t(decision === "approved" ? "Payment approved and queued for activation" : "Payment rejected"));
    setSelected(null);
    resource.reload();
  };
  return <><CollectionPage title="Payment operations" note="Gemini extraction, deterministic review and immutable ledger posting." resource={resource} columns={["Payment", "User", "Amount", "Created", "Status", "Approved", "Action"]} render={(item) => <tr key={item.id}><td><span className="mono">{shortId(item.id)}</span></td><td><span className="mono">{shortId(item.user_id)}</span></td><td><b>{money(item.amount_minor, item.currency)}</b></td><td>{localizedLongDate(item.created_at, locale)}</td><td><Status value={item.status} /></td><td>{item.approved_at ? localizedLongDate(item.approved_at, locale) : "—"}</td><td>{item.status === "manual_review" ? <button className="approve-button" onClick={() => setSelected(item)}><Check size={14} /> {t("Review")}</button> : <button className="icon-button row-menu" aria-label={`${t("Payment actions")} ${shortId(item.id)}`} onClick={() => setSelected(item)}><MoreHorizontal size={17} /></button>}</td></tr>} />{selected && <PaymentDialog payment={selected} onClose={() => setSelected(null)} onDecision={decide} />}</>;
}

function PaymentDialog({ payment, onClose, onDecision }: { payment: Payment; onClose: () => void; onDecision: (decision: "approved" | "rejected", reason: string) => Promise<void> }) {
  const { locale, t } = useI18n();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const decide = async (decision: "approved" | "rejected") => { setBusy(true); setError(null); try { await onDecision(decision, reason || (decision === "approved" ? "Receipt verified by operator" : "Receipt rejected by operator")); } catch (value) { setError(value instanceof Error ? value.message : t("Payment action failed")); } finally { setBusy(false); } };
  return <div className="modal-layer"><button className="modal-scrim" onClick={onClose} aria-label={t("Close payment")} /><section className="modal operational-modal"><header><div><p className="overline">{t("Payment review")}</p><h2>{money(payment.amount_minor, payment.currency)}</h2></div><button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button></header><div className="operational-summary"><Detail label="Payment ID" value={payment.id} mono /><Detail label="User ID" value={payment.user_id} mono /><Detail label="Plan price" value={payment.plan_price_id} mono /><Detail label="Created" value={localizedLongDate(payment.created_at, locale)} /><Detail label="Version" value={`v${payment.version}`} /><div className="detail-row"><span>{t("Status")}</span><Status value={payment.status} /></div></div>{payment.status === "manual_review" ? <><label className="field-label">{t("Decision reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder={t("Operator note for the immutable review record")} /></label>{error && <div className="inline-error">{error}</div>}<footer><button className="danger-button" disabled={busy} onClick={() => decide("rejected")}><X size={15} /> {t("Reject")}</button><button className="primary-button" disabled={busy} onClick={() => decide("approved")}><Check size={15} /> {t("Approve payment")}</button></footer></> : <div className="decision-complete"><Status value={payment.status} /><span>{t("This decision is already committed. Use the audit trail for details.")}</span></div>}</section></div>;
}

function TicketsPage() {
  const { locale, t } = useI18n();
  const resource = useResource<Ticket[]>("/admin/tickets");
  const [selected, setSelected] = useState<Ticket | null>(null);
  const wrapped: LoadState<Page<Ticket>> = { data: resource.data ? { items: resource.data, total: resource.data.length, limit: 100, offset: 0 } : null, loading: resource.loading, error: resource.error };
  return <><CollectionPage title="Support queue" note="Open a ticket to read the conversation, reply and change its state." resource={{ ...wrapped, reload: resource.reload }} columns={["Ticket", "Subject", "Category", "Priority", "Status", "Waiting"]} render={(item) => <tr className="clickable-row" key={item.id} onClick={() => setSelected(item)}><td><b className="ticket-number">#{item.public_number}</b></td><td><div className="stacked-cell"><b>{t(item.subject)}</b><small>{shortId(item.user_id)}</small></div></td><td>{t(title(item.category))}</td><td><Status value={item.priority} /></td><td><Status value={item.status} /></td><td>{localizedRelativeTime(item.last_message_at, locale)}</td></tr>} />{selected && <TicketChatDialog ticket={selected} onClose={() => setSelected(null)} onChanged={resource.reload} />}</>;
}

function TicketChatDialog({ ticket, onClose, onChanged }: { ticket: Ticket; onClose: () => void; onChanged: () => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<TicketDetail>(`/admin/tickets/${ticket.id}`);
  const [body, setBody] = useState("");
  const [note, setNote] = useState(false);
  const [busy, setBusy] = useState(false);
  const send = async (event: React.FormEvent) => { event.preventDefault(); if (!body.trim()) return; setBusy(true); try { await api(`/admin/tickets/${ticket.id}/messages`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ body, message_type: note ? "internal_note" : "message", status_after: note ? undefined : "waiting_user" }) }); setBody(""); resource.reload(); onChanged(); } finally { setBusy(false); } };
  const changeStatus = async (status: string) => { const current = resource.data?.ticket; if (!current) return; await api(`/admin/tickets/${ticket.id}`, { method: "PATCH", body: JSON.stringify({ status, expected_version: current.version, reason: `Status changed to ${status} in admin dashboard` }) }); resource.reload(); onChanged(); };
  return <div className="modal-layer ticket-layer"><button className="modal-scrim" onClick={onClose} aria-label={t("Close ticket chat")} /><section className="ticket-dialog"><header><div><p className="overline">{t("Ticket")} #{ticket.public_number}</p><h2>{t(ticket.subject)}</h2><div className="ticket-meta"><Status value={resource.data?.ticket.status ?? ticket.status} /><Status value={ticket.priority} /><span>{t(title(ticket.category))}</span></div></div><button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={19} /></button></header>{!resource.data ? <ResourceState {...resource} /> : <><div className="conversation">{resource.data.messages.map((message) => <article className={`message ${message.sender_user_id === ticket.user_id ? "customer" : "operator"} ${message.message_type === "internal_note" ? "note" : ""}`} key={message.id}><div><b>{t(message.message_type === "internal_note" ? "Internal note" : message.sender_user_id === ticket.user_id ? "Customer" : "Hazbit support")}</b><time>{localizedRelativeTime(message.created_at, locale)}</time></div><p>{t(message.body)}</p></article>)}</div><form className="reply-box" onSubmit={send}><div className={`composer-shell ${note ? "internal" : ""}`}><textarea aria-label={t(note ? "Write a private note for staff…" : "Reply to the customer…")} value={body} onChange={(event) => setBody(event.target.value)} placeholder={t(note ? "Write a private note for staff…" : "Reply to the customer…")} /><div className="composer-toolbar"><label className="note-toggle"><input type="checkbox" checked={note} onChange={(event) => setNote(event.target.checked)} /><span className="checkmark"><Check size={11} /></span><span>{t("Internal note")}</span></label><span className="composer-hint">{t(note ? "Private staff note" : "Visible to customer")}</span><div className="composer-actions"><label className="status-select"><span>{t("Status")}</span><select aria-label={t("Ticket status")} value={resource.data.ticket.status} onChange={(event) => changeStatus(event.target.value)}><option value="open">{t("Open")}</option><option value="in_progress">{t("In progress")}</option><option value="waiting_user">{t("Waiting user")}</option><option value="closed">{t("Closed")}</option></select></label><button className="send-button" disabled={busy || !body.trim()}><Send size={16} /> {busy ? t("Sending…") : t("Send")}</button></div></div></div></form></>}</section></div>;
}

function PromoPage({ notify }: { notify: (message: string) => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<PromoCode[]>("/admin/promo-codes");
  const [editing, setEditing] = useState<PromoCode | "new" | null>(null);
  if (!resource.data) return <ResourceState {...resource} />;
  const saved = () => { setEditing(null); resource.reload(); notify(t("Promo code saved")); };
  return <div className="page-stack"><section className="page-intro"><div><p>{t("Campaign controls")}</p><h2>{resource.data.filter((promo) => promo.is_active).length} {t("active promo codes")}</h2><span>{t("Discount liability and free-day grants with strict usage limits.")}</span></div><button className="primary-button" onClick={() => setEditing("new")}><Plus size={15} /> {t("Add promo code")}</button></section><div className="promo-grid">{resource.data.map((promo) => { const usage = promo.usage_limit ? Math.round((promo.usage_count / promo.usage_limit) * 100) : 0; return <article className={`promo-card ${!promo.is_active ? "inactive-card" : ""}`} key={promo.id}><header><span className="promo-code">{promo.code}</span><div className="card-actions"><Status value={promo.is_active ? "active" : "inactive"} /><button className="icon-button" aria-label={`${t("Edit promo code")} ${promo.code}`} onClick={() => setEditing(promo)}><Pencil size={15} /></button></div></header><div className="promo-value"><strong>{promo.promo_type === "discount_percent" ? `${promo.value}%` : promo.value}</strong><span>{t(promo.promo_type === "discount_percent" ? "discount" : "free days")}</span></div><div className="usage-line"><span>{t("Usage")}</span><b>{promo.usage_count} / {promo.usage_limit ?? "∞"}</b></div><div className="usage-track"><i style={{ width: `${usage}%` }} /></div><footer><span>{t("Per user")}: {promo.per_user_limit}</span><span>{t("Ends")} {localizedShortDate(promo.expires_at, locale)}</span></footer></article>; })}</div>{editing && <PromoEditor promo={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={saved} />}</div>;
}

function PromoEditor({ promo, onClose, onSaved }: { promo: PromoCode | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const [code, setCode] = useState(promo?.code ?? "");
  const [promoType, setPromoType] = useState(promo?.promo_type ?? "discount_percent");
  const [value, setValue] = useState(promo?.value ?? 20);
  const [usageLimit, setUsageLimit] = useState(promo?.usage_limit ?? 100);
  const [perUser, setPerUser] = useState(promo?.per_user_limit ?? 1);
  const [expires, setExpires] = useState(promo?.expires_at?.slice(0, 10) ?? "");
  const [active, setActive] = useState(promo?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { const body = promo ? { usage_limit: usageLimit, expires_at: expires ? new Date(`${expires}T23:59:59Z`).toISOString() : null, is_active: active } : { code, promo_type: promoType, value, currency: promoType === "discount_percent" ? "RUB" : null, usage_limit: usageLimit, per_user_limit: perUser, starts_at: new Date().toISOString(), expires_at: expires ? new Date(`${expires}T23:59:59Z`).toISOString() : null, plan_version_ids: [] }; await api(promo ? `/admin/promo-codes/${promo.id}` : "/admin/promo-codes", { method: promo ? "PATCH" : "POST", body: JSON.stringify(body) }); onSaved(); } catch (reason) { setError(reason instanceof Error ? reason.message : t("Unable to save promo code")); } finally { setBusy(false); } };
  const archive = async () => { if (!promo) return; setBusy(true); try { await api(`/admin/promo-codes/${promo.id}`, { method: "DELETE", body: JSON.stringify({ reason: "Archived from admin dashboard" }) }); onSaved(); } finally { setBusy(false); } };
  return <div className="modal-layer"><button className="modal-scrim" onClick={onClose} aria-label={t("Close promo editor")} /><form className="modal editor-modal" onSubmit={save}><header><div><p className="overline">{t("Campaign editor")}</p><h2>{promo ? `${t("Edit promo code")} ${promo.code}` : t("New promo code")}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button></header>{promo && <p className="immutable-note">{t("Code, type and value remain immutable after creation so existing redemptions stay auditable.")}</p>}<div className="form-grid"><label className="field-label">{t("Code")}<input value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} disabled={Boolean(promo)} required /></label><label className="field-label">{t("Type")}<select value={promoType} onChange={(event) => setPromoType(event.target.value)} disabled={Boolean(promo)}><option value="discount_percent">{t("Discount percent")}</option><option value="free_days">{t("Free days")}</option></select></label><label className="field-label">{t("Value")}<input type="number" min="1" value={value} onChange={(event) => setValue(Number(event.target.value))} disabled={Boolean(promo)} /></label><label className="field-label">{t("Usage limit")}<input type="number" min="1" value={usageLimit} onChange={(event) => setUsageLimit(Number(event.target.value))} /></label><label className="field-label">{t("Per-user limit")}<input type="number" min="1" value={perUser} onChange={(event) => setPerUser(Number(event.target.value))} disabled={Boolean(promo)} /></label><label className="field-label">{t("Expires")}<input type="date" value={expires} onChange={(event) => setExpires(event.target.value)} /></label></div>{promo && <label className="switch-row"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /><span>{t("Campaign active")}</span></label>}{error && <div className="inline-error">{error}</div>}<footer>{promo && <button type="button" className="danger-button" onClick={archive} disabled={busy}><Trash2 size={15} /> {t("Delete")}</button>}<span /><button type="button" className="quiet-button" onClick={onClose}>{t("Cancel")}</button><button className="primary-button" disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} {t("Save promo")}</button></footer></form></div>;
}

function PlansPage({ notify }: { notify: (message: string) => void }) {
  const { t } = useI18n();
  const resource = useResource<Plan[]>("/admin/plans");
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  if (!resource.data) return <ResourceState {...resource} />;
  const saved = () => { setEditing(null); resource.reload(); notify(t("Plan catalog updated")); };
  return <div className="page-stack"><section className="page-intro"><div><p>{t("Product catalog")}</p><h2>{t("Plans & entitlement policy")}</h2><span>{t("Edits create immutable versions so historical subscriptions remain explainable.")}</span></div><button className="primary-button" onClick={() => setEditing("new")}><Plus size={15} /> {t("Add plan")}</button></section><div className="plan-grid">{resource.data.map((plan, index) => { const version = plan.versions[0]; const price = version?.prices.find((value) => value.is_active); return <article className={`plan-card plan-${index} ${!plan.is_active ? "inactive-card" : ""}`} key={plan.id}><header><div><p>0{index + 1} / {plan.slug}</p><h3>{t(plan.name)}</h3></div><div className="card-actions"><Status value={plan.is_active ? "active" : "inactive"} /><button className="icon-button" aria-label={`${t("Edit plan")} ${t(plan.name)}`} onClick={() => setEditing(plan)}><Pencil size={15} /></button></div></header><p>{t(plan.description)}</p><div className="plan-price"><strong>{price ? money(price.amount_minor, price.currency) : t("Custom")}</strong><span>{price ? `/ ${price.term_months} ${t("mo")}` : t("contact sales")}</span></div><ul><li><Check size={15} /> {version?.device_limit ?? 0} {t("VPN devices")}</li><li><Check size={15} /> {version?.family_member_limit ? `${version.family_member_limit} ${t("Family members").toLowerCase()}` : t("Personal access")}</li><li><Check size={15} /> {t("Version")} {version?.version ?? "—"}</li></ul><footer><span>{t("Catalog order")} {plan.sort_order}</span><b>v{version?.version ?? "—"}</b></footer></article>; })}</div>{editing && <PlanEditor plan={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={saved} />}</div>;
}

function PlanEditor({ plan, onClose, onSaved }: { plan: Plan | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const version = plan?.versions[0];
  const price = version?.prices.find((item) => item.is_active);
  const [slug, setSlug] = useState(plan?.slug ?? "");
  const [name, setName] = useState(plan?.name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [devices, setDevices] = useState(version?.device_limit ?? 3);
  const [members, setMembers] = useState(version?.family_member_limit ?? 0);
  const [term, setTerm] = useState(price?.term_months ?? 1);
  const [duration, setDuration] = useState(price?.duration_days ?? 30);
  const [amount, setAmount] = useState((price?.amount_minor ?? 49900) / 100);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const versionPayload = { device_limit: devices, family_member_limit: members, traffic_limit_bytes: null, prices: [{ term_months: term, duration_days: duration, currency: "RUB", amount_minor: Math.round(amount * 100) }], reason };
  const save = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { if (plan) { await api(`/admin/plans/${plan.id}`, { method: "PATCH", body: JSON.stringify({ name, description, reason }) }); await api(`/admin/plans/${plan.id}/versions`, { method: "POST", body: JSON.stringify(versionPayload) }); } else { await api("/admin/plans", { method: "POST", body: JSON.stringify({ slug, name, description, sort_order: 100, ...versionPayload }) }); } onSaved(); } catch (value) { setError(value instanceof Error ? value.message : t("Unable to save plan")); } finally { setBusy(false); } };
  const archive = async () => { if (!plan) return; setBusy(true); try { await api(`/admin/plans/${plan.id}`, { method: "DELETE", body: JSON.stringify({ reason: reason || "Archived from admin dashboard" }) }); onSaved(); } catch (value) { setError(value instanceof Error ? value.message : t("Unable to delete plan")); } finally { setBusy(false); } };
  return <div className="modal-layer"><button className="modal-scrim" onClick={onClose} aria-label={t("Close plan editor")} /><form className="modal editor-modal plan-editor" onSubmit={save}><header><div><p className="overline">{t("Product catalog")}</p><h2>{plan ? `${t("Edit plan")} ${plan.name}` : t("New VPN plan")}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button></header>{plan && <p className="immutable-note">{t("Saving entitlement or price changes publishes a new version. Existing subscriptions keep their original snapshot.")}</p>}<div className="form-grid"><label className="field-label">{t("Slug")}<input value={slug} onChange={(event) => setSlug(event.target.value.toLowerCase())} disabled={Boolean(plan)} pattern="[a-z0-9-]+" required /></label><label className="field-label">{t("Name")}<input value={name} onChange={(event) => setName(event.target.value)} required /></label><label className="field-label span-2">{t("Description")}<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label><label className="field-label">{t("VPN devices")}<input type="number" min="1" value={devices} onChange={(event) => setDevices(Number(event.target.value))} /></label><label className="field-label">{t("Family members")}<input type="number" min="0" value={members} onChange={(event) => setMembers(Number(event.target.value))} /></label><label className="field-label">{t("Term")}<select value={term} onChange={(event) => setTerm(Number(event.target.value))}><option value="1">{t("1 month")}</option><option value="3">{t("3 months")}</option><option value="6">{t("6 months")}</option><option value="12">{t("12 months")}</option></select></label><label className="field-label">{t("Duration, days")}<input type="number" min="1" value={duration} onChange={(event) => setDuration(Number(event.target.value))} /></label><label className="field-label">{t("Price, ₽")}<input type="number" min="0" value={amount} onChange={(event) => setAmount(Number(event.target.value))} /></label><label className="field-label">{t("Audit reason")}<input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required /></label></div>{error && <div className="inline-error">{error}</div>}<footer>{plan && <button type="button" className="danger-button" onClick={archive} disabled={busy}><Archive size={15} /> {t("Delete plan")}</button>}<span /><button type="button" className="quiet-button" onClick={onClose}>{t("Cancel")}</button><button className="primary-button" disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} {t(plan ? "Publish new version" : "Create plan")}</button></footer></form></div>;
}

function FamilyGroupsPage() {
  const { t } = useI18n();
  const resource = useResource<Page<FamilyGroup>>("/admin/family-groups");
  const [selected, setSelected] = useState<FamilyGroup | null>(null);
  return <>
    <CollectionPage
      title="Family groups"
      note="Owners, shared entitlements and active household members."
      resource={resource}
      columns={["Group", "Owner", "Plan", "Members", "Invites", "Status"]}
      render={(item) => (
        <tr className="clickable-row" key={item.id} onClick={() => setSelected(item)}>
          <td><div className="identity-cell device"><span><HeartHandshake size={16} /></span><div><b>{t(item.name)}</b><small>{shortId(item.id)}</small></div></div></td>
          <td><div className="stacked-cell"><b>{item.owner_email ?? t("No email")}</b><small>{shortId(item.owner_user_id)}</small></div></td>
          <td><b>{t(item.plan_name)}</b></td>
          <td><span className="member-count">{item.active_member_count} / {item.member_limit}</span></td>
          <td><span className="member-count">{item.pending_invitation_count ?? 0}</span></td>
          <td><Status value={item.status} /></td>
        </tr>
      )}
    />
    {selected && <FamilyDialog groupId={selected.id} fallback={selected} onClose={() => setSelected(null)} onChanged={resource.reload} />}
  </>;
}

function FamilyDialog({ groupId, fallback, onClose, onChanged }: { groupId: string; fallback: FamilyGroup; onClose: () => void; onChanged: () => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<FamilyGroup>(`/admin/family-groups/${groupId}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const group = resource.data ?? fallback;
  const invitations = group.invitations ?? [];
  const pending = invitations.filter((item) => item.status === "pending");
  const memberPercent = Math.min(100, (group.active_member_count / Math.max(1, group.member_limit)) * 100);
  const devicePercent = Math.min(100, ((group.active_device_count ?? 0) / Math.max(1, group.device_limit ?? 1)) * 100);
  const update = async (path: string, message: string) => {
    setBusy(path); setError(null); setNotice(null);
    try {
      await api(path, { method: "DELETE", body: JSON.stringify({ reason: t("Administrative intervention from Family operations") }) });
      setNotice(t(message));
      resource.reload();
      onChanged();
    } catch (value) {
      setError(value instanceof Error ? value.message : t("Unable to update family group"));
    } finally { setBusy(null); }
  };
  return <div className="modal-layer family-layer">
    <button className="modal-scrim" onClick={onClose} aria-label={t("Close family group")} />
    <section className="modal operational-modal family-dialog family-command-center">
      <header>
        <div><p className="overline">{t("Family operations")}</p><h2>{t(group.name)}</h2><div className="family-header-meta"><Status value={group.status} /><span><ShieldCheck size={13} /> {t("Projected to Remnawave")}</span></div></div>
        <button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button>
      </header>
      <div className="family-overview">
        <div><span>{t("Owner")}</span><b>{group.owner_email ?? shortId(group.owner_user_id)}</b></div>
        <div><span>{t("Plan")}</span><b>{t(group.plan_name)}</b></div>
        <div><span>{t("Subscription")}</span><Status value={group.subscription_status} /></div>
        <div><span>{t("Pending invitations")}</span><b>{pending.length}</b></div>
      </div>
      <section className="family-capacity">
        <div className="capacity-heading"><div><p className="overline">{t("Family capacity")}</p><h3>{group.active_member_count} / {group.member_limit} {t("seats used")}</h3></div><Users size={22} /></div>
        <div className="capacity-grid">
          <div><span><b>{t("Member seats")}</b><small>{group.active_member_count} / {group.member_limit}</small></span><div className="capacity-track"><i style={{ width: `${memberPercent}%` }} /></div></div>
          <div><span><b>{t("Device allowance")}</b><small>{group.active_device_count ?? 0} / {group.device_limit ?? 0}</small></span><div className="capacity-track device"><i style={{ width: `${devicePercent}%` }} /></div></div>
        </div>
      </section>
      {notice && <div className="inline-success"><Check size={15} /> {notice}</div>}
      {error && <div className="inline-error">{error}</div>}
      <div className="family-detail-grid">
        <section>
          <div className="family-section-head"><div><p className="overline">{t("Active members")}</p><h3>{locale === "ru" ? countNounRu(group.active_member_count, "участник", "участника", "участников") : `${group.active_member_count} ${group.active_member_count === 1 ? "member" : "members"}`}</h3></div></div>
          <div className="member-list family-member-list">{resource.loading ? <div className="empty-inline">{t("Loading members…")}</div> : group.members.map((member) => { const owner = member.user_id === group.owner_user_id; const path = `/admin/family-groups/${group.id}/members/${member.user_id}`; return <div key={member.id}><span className="avatar">{initials(member.email)}</span><div><b>{member.email ?? t("No email")}</b><small>{owner ? t("Owner seat") : `${t("Joined")} ${localizedShortDate(member.joined_at, locale)}`}</small></div>{owner ? <span className="family-role">{t("Owner")}</span> : <button className="icon-button family-remove" disabled={busy === path} aria-label={`${t("Remove member")} ${member.email ?? member.user_id}`} onClick={() => update(path, "Member removed and VPN access queued for disablement.")}>{busy === path ? <LoaderCircle className="spin" size={15} /> : <UserMinus size={15} />}</button>}</div>; })}</div>
        </section>
        <section>
          <div className="family-section-head"><div><p className="overline">{t("Pending invitations")}</p><h3>{locale === "ru" ? countNounRu(pending.length, "приглашение", "приглашения", "приглашений") : `${pending.length} ${pending.length === 1 ? "invite" : "invites"}`}</h3></div></div>
          <div className="invitation-list">{pending.length ? pending.map((invitation) => { const path = `/admin/family-groups/${group.id}/invitations/${invitation.id}`; return <div key={invitation.id}><span className="invitation-icon"><MailPlus size={16} /></span><div><b>{invitation.invited_email ?? shortId(invitation.invited_user_id ?? "")}</b><small>{t("Valid until")} {localizedShortDate(invitation.expires_at, locale)}</small></div><button className="icon-button family-remove" disabled={busy === path} aria-label={`${t("Revoke invitation")} ${invitation.invited_email ?? ""}`} onClick={() => update(path, "Invitation revoked.")}>{busy === path ? <LoaderCircle className="spin" size={15} /> : <X size={15} />}</button></div>; }) : <div className="family-empty"><CheckCircle2 size={20} /><span>{t("No pending invitations")}</span></div>}</div>
        </section>
      </div>
      <footer><span className="muted"><Network size={14} /> {t("Membership changes belong to the customer Family flow and remain audit-controlled.")}</span><button className="quiet-button" onClick={onClose}>{t("Close")}</button></footer>
    </section>
  </div>;
}

function DevicesPage() {
  const { locale, t } = useI18n();
  const resource = useResource<Page<Device>>("/admin/vpn-devices");
  return <CollectionPage title="VPN device fleet" note="Reserved slots and observed HWIDs projected from Remnawave." resource={resource} columns={["Device", "Platform", "User", "Slot", "HWID", "Last seen", "Status"]} render={(item) => <tr key={item.id}><td><div className="identity-cell device"><span><Smartphone size={17} /></span><div><b>{item.label ? t(item.label) : t("Unnamed device")}</b><small>{shortId(item.id)}</small></div></div></td><td>{item.platform ?? t("Unknown")}</td><td><span className="mono">{shortId(item.user_id)}</span></td><td>#{item.slot_number}</td><td><span className="mono">{item.external_hwid ?? t("Pending")}</span></td><td>{item.last_seen_at ? localizedRelativeTime(item.last_seen_at, locale) : t("Never")}</td><td><Status value={item.status} /></td></tr>} />;
}

function SettingsPage() {
  const { locale, t } = useI18n();
  const resource = useResource<SettingsData>("/admin/settings");
  const nodes = useResource<RemnawaveNode[]>("/admin/remnawave/nodes");
  const [action, setAction] = useState<{ type: "feature"; item: FeatureControl } | { type: "node"; item: RemnawaveNode } | null>(null);
  if (!resource.data) return <ResourceState {...resource} />;
  const data = resource.data;
  const groups = [
    { title: "Runtime", icon: ServerCog, values: [["Environment", data.environment], ["API version", data.app_version], ["Log level", data.log_level]] },
    { title: "Payment intelligence", icon: Sparkles, values: [["Gemini model", data.payment_ai_model], ["Prompt contract", data.payment_prompt_version], ["Decision mode", "Deterministic rules"]] },
    { title: "VPN integration", icon: Network, values: [["Adapter", data.remnawave_adapter_url], ["Provisioning", "Durable command queue"], ["Reconciliation", "Enabled"]] },
    { title: "Growth policy", icon: Gauge, values: [["Referral reward", locale === "ru" ? `+${data.referrer_days} дн.` : `+${data.referrer_days} days`], ["Referred trial", locale === "ru" ? `${data.referral_days} дн.` : `${data.referral_days} days`], ["Default promo plan", data.default_promo_plan]] },
    { title: "Support limits", icon: TicketCheck, values: [["Tickets / day", String(data.support_create_limit_per_day)], ["Messages / hour", String(data.support_message_limit_per_hour)], ["Internal notes", "Staff only"]] },
  ];
  const completeAction = async (reason: string) => {
    if (!action) return;
    if (action.type === "feature") {
      await api(`/admin/settings/features/${action.item.key}`, { method: "PATCH", body: JSON.stringify({ enabled: !action.item.enabled, reason }) });
      resource.reload();
    } else {
      const operation = action.item.is_disabled ? "enable" : "disable";
      await api(`/admin/remnawave/nodes/${action.item.uuid}/${operation}`, { method: "POST", body: JSON.stringify({ reason }) });
      nodes.reload();
    }
    setAction(null);
  };
  return <div className="page-stack control-settings">
    <section className="settings-hero"><div><span className="live-dot" /> {t("Operations control")}</div><h2>{locale === "ru" ? "Управление сервисами и VLESS-инфраструктурой." : "Services and VLESS infrastructure, under control."}</h2><p>{locale === "ru" ? "ENV определяет доступность, Control — временную операционную паузу. Секреты никогда не отображаются в браузере." : "ENV defines availability; Control can apply a temporary operational pause. Secrets never reach the browser."}</p></section>
    <section className="control-section">
      <PanelHeader eyebrow="Service control" title="Runtime modules" action={<span className="control-legend"><i /> {data.features.filter((item) => item.enabled).length}/{data.features.length} {t("active")}</span>} />
      <div className="feature-control-grid">{data.features.map((feature) => <article className={`feature-control-card ${feature.enabled ? "enabled" : "paused"}`} key={feature.key}><span className="feature-icon">{feature.key === "billing" ? <CreditCard size={18} /> : feature.key === "support" ? <Headphones size={18} /> : feature.key === "telegram_bots" ? <Send size={18} /> : feature.key === "vpn_provisioning" ? <Network size={18} /> : <Sparkles size={18} />}</span><div><b>{t(feature.label)}</b><small>{t(feature.description)}</small><em>{feature.configured ? (feature.enabled ? t("Available") : t("Paused in Control")) : t("Disabled by ENV")}</em></div><button className={`control-switch ${feature.enabled ? "on" : ""}`} disabled={!feature.configured} aria-pressed={feature.enabled} aria-label={`${t(feature.label)}: ${feature.enabled ? t("enabled") : t("disabled")}`} onClick={() => setAction({ type: "feature", item: feature })}><i /></button></article>)}</div>
    </section>
    <section className="control-section node-section">
      <PanelHeader eyebrow="Remnawave infrastructure" title="VLESS server nodes" action={<button className="quiet-button" onClick={nodes.reload}><RefreshCw size={15} /> {t("Refresh")}</button>} />
      {!nodes.data ? <ResourceState {...nodes} /> : <div className="node-grid">{nodes.data.map((node) => { const memory = node.memory_total_bytes ? Math.round(((node.memory_used_bytes ?? 0) / node.memory_total_bytes) * 100) : 0; return <article className={`node-card ${node.is_disabled ? "disabled" : node.is_connected ? "online" : "offline"}`} key={node.uuid}><header><span className="node-country">{countryFlag(node.country_code)}</span><div><h3>{node.name}</h3><p>{node.address}</p></div><Status value={node.is_disabled ? "disabled" : node.is_connected ? "online" : node.is_connecting ? "connecting" : "offline"} /></header><div className="node-metrics"><span><Users size={16} /><small>{t("Online")}</small><b>{node.users_online}</b></span><span><Cpu size={16} /><small>Load</small><b>{node.load_average[0]?.toFixed(2) ?? "—"}</b></span><span><HardDrive size={16} /><small>RAM</small><b>{memory}%</b></span><span><Radio size={16} /><small>TX</small><b>{rate(node.tx_bytes_per_second)}</b></span></div><div className="node-progress"><span><i style={{ width: `${Math.min(memory, 100)}%` }} /></span><small>Xray {node.xray_version ?? "—"} · {uptime(node.xray_uptime, locale)}</small></div><footer><span className="mono">{shortId(node.uuid)}</span><button className={node.is_disabled ? "primary-button" : "danger-button"} onClick={() => setAction({ type: "node", item: node })}>{node.is_disabled ? <><CheckCircle2 size={14} /> {t("Enable node")}</> : <><Ban size={14} /> {t("Disable node")}</>}</button></footer></article>; })}</div>}
    </section>
    <div className="settings-grid">{groups.map(({ title: heading, icon: Icon, values }) => <section className="panel settings-card" key={heading}><header><span><Icon size={18} /></span><h3>{t(heading)}</h3></header>{values.map(([label, value]) => <div className="setting-row" key={label}><span>{t(label)}</span><b>{label === "Default promo plan" ? t(title(value)) : t(value)}</b></div>)}</section>)}</div>
    {action && <ControlActionDialog action={action} onClose={() => setAction(null)} onConfirm={completeAction} />}
  </div>;
}

function ControlActionDialog({ action, onClose, onConfirm }: { action: { type: "feature"; item: FeatureControl } | { type: "node"; item: RemnawaveNode }; onClose: () => void; onConfirm: (reason: string) => Promise<void> }) {
  const { locale, t } = useI18n(); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const disabling = action.type === "feature" ? action.item.enabled : !action.item.is_disabled;
  const name = action.type === "node" ? action.item.name : action.item.label;
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(null); try { await onConfirm(reason); } catch (value) { setError(value instanceof Error ? value.message : t("Operation failed")); setBusy(false); } };
  return <div className="modal-layer"><button className="modal-scrim" onClick={onClose} aria-label={t("Close dialog")} /><form className="modal control-action-modal" onSubmit={submit}><div className={`modal-symbol ${disabling ? "block" : ""}`}>{disabling ? <Ban size={20} /> : <CheckCircle2 size={20} />}</div><p className="overline">{action.type === "node" ? "Remnawave node" : t("Service control")}</p><h2>{locale === "ru" ? `${disabling ? "Отключить" : "Включить"} «${name}»?` : `${disabling ? "Disable" : "Enable"} “${name}”?`}</h2><p className="muted">{locale === "ru" ? "Изменение применяется сразу и будет записано в журнал аудита." : "The change takes effect immediately and is written to the audit log."}</p><label className="field-label">{t("Audit reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} placeholder={locale === "ru" ? "Почему требуется это изменение" : "Why this change is required"} required /></label>{error && <div className="inline-error">{error}</div>}<footer><button type="button" className="quiet-button" onClick={onClose}>{t("Cancel")}</button><button className={disabling ? "danger-button" : "primary-button"} disabled={busy}>{busy && <LoaderCircle className="spin" size={15} />}{t("Confirm action")}</button></footer></form></div>;
}

function CollectionPage<T>({ title: heading, note, resource, columns, render }: { title: string; note: string; resource: LoadState<Page<T>> & { reload: () => void }; columns: string[]; render: (item: T) => React.ReactNode }) {
  const { locale, t } = useI18n();
  return <div className="page-stack"><section className="page-intro"><div><p>{t("Operations index")}</p><h2>{t(heading)}</h2><span>{t(note)}</span></div><button className="quiet-button" onClick={resource.reload}><RefreshCw size={15} /> {t("Refresh")}</button></section><section className="panel table-panel">{!resource.data ? <ResourceState {...resource} /> : <><div className="table-summary"><span><b>{resource.data.total.toLocaleString(locale === "ru" ? "ru-RU" : "en-US")}</b> {t("records")}</span><small>{locale === "ru" ? `Показано ${resource.data.items.length} последних` : `Showing ${resource.data.items.length} ${t("most recent")}`}</small></div><div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column}>{t(column)}</th>)}</tr></thead><tbody>{resource.data.items.map(render)}</tbody></table></div></>}</section></div>;
}

function ResourceState<T>({ loading, error }: LoadState<T>) {
  const { t } = useI18n();
  if (loading) return <div className="resource-state"><LoaderCircle className="spin" size={22} /><b>{t("Loading operational data")}</b><span>{t("Reading the latest committed state…")}</span></div>;
  return <div className="resource-state error"><ServerCog size={23} /><b>{t("Data unavailable")}</b><span>{error ?? t("The service did not return a response.")}</span></div>;
}

function PanelHeader({ eyebrow, title: heading, action }: { eyebrow: string; title: string; action?: React.ReactNode }) { const { t } = useI18n(); return <header className="panel-header"><div><p>{t(eyebrow)}</p><h3>{t(heading)}</h3></div>{action}</header>; }
function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) { const { t } = useI18n(); return <div className="detail-row"><span>{t(label)}</span><b className={mono ? "mono" : ""}>{value}</b></div>; }
function Status({ value }: { value: string }) { const { t } = useI18n(); return <span className={`status status-${value.replaceAll("_", "-")}`}><i />{t(title(value))}</span>; }

function TrendChart({ points, labels }: { points: number[]; labels: string[] }) {
  const { locale, t } = useI18n();
  const width = 680, height = 190, pad = 12;
  const max = Math.max(...points, 1), min = Math.min(...points, 0);
  const coords = points.map((point, index) => `${pad + index * ((width - pad * 2) / Math.max(1, points.length - 1))},${height - pad - ((point - min) / Math.max(1, max - min)) * (height - pad * 2)}`);
  return <div className="trend-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t("Seven day payment trend")}><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1ba984" stopOpacity=".24" /><stop offset="100%" stopColor="#1ba984" stopOpacity="0" /></linearGradient></defs><path d={`M ${coords[0]} L ${coords.join(" L ")} L ${width - pad},${height} L ${pad},${height} Z`} fill="url(#area)" /><polyline points={coords.join(" ")} fill="none" stroke="#168b70" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />{coords.map((coord, index) => { const [cx, cy] = coord.split(","); return <circle key={labels[index]} cx={cx} cy={cy} r="4" fill="#f7faf8" stroke="#168b70" strokeWidth="2" />; })}</svg><div className="chart-labels">{labels.map((label) => <span key={label}>{new Date(label).toLocaleDateString(locale === "ru" ? "ru-RU" : "en", { weekday: "short" })}</span>)}</div></div>;
}

const title = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
const shortId = (value: string) => value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
const initials = (email: string | null) => email ? email.split("@")[0].split(/[._-]/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") : "U";
const money = (minor: number, currency: string) => new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);
const countryFlag = (code: string) => code.length === 2 ? String.fromCodePoint(...code.toUpperCase().split("").map((char) => 127397 + char.charCodeAt(0))) : "🌐";
const rate = (bytes: number | null) => bytes == null ? "—" : bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB/s` : `${Math.round(bytes / 1_000)} KB/s`;
const uptime = (seconds: number, locale: "en" | "ru") => { const days = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); return locale === "ru" ? `${days} д ${hours} ч` : `${days}d ${hours}h`; };
const localizedShortDate = (value: string | null, locale: "en" | "ru") => value ? new Date(value).toLocaleDateString(locale === "ru" ? "ru-RU" : "en", { day: "2-digit", month: "short" }) : "—";
const localizedLongDate = (value: string | null, locale: "en" | "ru") => value ? new Date(value).toLocaleDateString(locale === "ru" ? "ru-RU" : "en", { day: "2-digit", month: "short", year: "numeric" }) : "—";
const localizedRelativeTime = (value: string, locale: "en" | "ru") => { const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60_000)); if (locale === "ru") return minutes < 60 ? `${minutes} мин. назад` : minutes < 1440 ? `${Math.round(minutes / 60)} ч назад` : `${Math.round(minutes / 1440)} дн. назад`; return minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.round(minutes / 60)}h ago` : `${Math.round(minutes / 1440)}d ago`; };
const countNounRu = (count: number, one: string, few: string, many: string) => { const mod100 = count % 100; const mod10 = count % 10; const noun = mod100 >= 11 && mod100 <= 14 ? many : mod10 === 1 ? one : mod10 >= 2 && mod10 <= 4 ? few : many; return `${count} ${noun}`; };

export default App;
