import { ArrowRight, Crown, Gift, MessageCircle, MonitorSmartphone, ShieldCheck, Smartphone, UsersRound, WalletCards, Zap } from "lucide-react";
import type { Overview, Wallet } from "../../api";
import { CompactRouteSphere } from "../../components/CompactRouteSphere";

type Tr = (en: string, ru: string) => string;
type Tab = "home" | "plans" | "devices" | "family" | "more";

export function TelegramHome({ overview, wallet, displayName, tr, go, notify, onWallet }: { overview: Overview; wallet: Wallet | null; displayName: string; tr: Tr; go: (tab: Tab) => void; notify: (message: string) => void; onWallet: () => void }) {
  const end = overview.subscription?.current_period_ends_at;
  const days = end ? Math.max(0, Math.ceil((new Date(end).getTime() - Date.now()) / 86_400_000)) : 0;
  const connected = overview.vpn?.observed_status === "active";

  return <div className="orbit-home">
    <section className="orbit-welcome"><div><p>{tr("YOUR PRIVATE ORBIT", "ВАША ПРИВАТНАЯ ОРБИТА")}</p><h1>{tr("Good to see you", "Рады вас видеть")},<br />{displayName}</h1></div><span className={connected ? "is-online" : ""}><i />{connected ? tr("Protected", "Под защитой") : tr("Paused", "Пауза")}</span></section>

    <button className="orbit-wallet" onClick={onWallet}><span><WalletCards /></span><div><small>{tr("HAZBIT BALANCE", "БАЛАНС HAZBIT")}</small><strong>{wallet ? money(wallet.balance_minor, wallet.currency) : "—"}</strong><p>{wallet?.auto_renew_enabled ? tr("Automatic renewal is on", "Автопродление включено") : tr("Top up by SBP, card or crypto", "Пополнение по СБП, картой или криптовалютой")}</p></div><ArrowRight /></button>

    <section className={`orbit-route ${connected ? "connected" : "paused"}`}>
      <div className="orbit-route__sphere"><CompactRouteSphere connected={connected} label={tr("VLESS connection status", "Статус VLESS-подключения")} /><span><ShieldCheck />VLESS <b>{connected ? tr("Stable", "Стабилен") : tr("Paused", "Пауза")}</b></span></div>
      <div className="orbit-route__copy"><p><i />{connected ? tr("PRIVATE ROUTE ACTIVE", "ПРИВАТНЫЙ МАРШРУТ АКТИВЕН") : tr("READY TO CONNECT", "ГОТОВО К ПОДКЛЮЧЕНИЮ")}</p><h2>{connected ? tr("Everything is synchronized.", "Всё синхронизировано.") : tr("Connect your first device.", "Подключите первое устройство.")}</h2><span>{tr("Automatic routing · Hazbit VLESS", "Автоматический маршрут · Hazbit VLESS")}</span><button onClick={() => go("devices")}><Zap />{tr("Connect a device", "Подключить устройство")}<ArrowRight /></button></div>
    </section>

    <section className="orbit-metrics">
      <button onClick={() => go("plans")}><span className="blue"><Crown /></span><small>{tr("ACCESS", "ДОСТУП")}</small><b>{days}</b><em>{tr("days remaining", "дней осталось")}</em><i style={{ "--metric": `${Math.min(100, days / 60 * 100)}%` } as React.CSSProperties} /></button>
      <button onClick={() => go("devices")}><span className="violet"><MonitorSmartphone /></span><small>{tr("DEVICES", "УСТРОЙСТВА")}</small><b>{overview.active_device_count}<em> / {overview.subscription?.device_limit ?? 0}</em></b><div><Smartphone /><MonitorSmartphone /></div></button>
    </section>

    <button className="orbit-family" onClick={() => go("family")}><div className="orbit-family__people"><i /><span>HZ</span><span>A</span><span>M</span><b><UsersRound /></b></div><div><small>{tr("FAMILY ORBIT", "СЕМЕЙНАЯ ОРБИТА")}</small><strong>{overview.family_group_name ?? tr("Create a family", "Создать семью")}</strong><p>{tr("Separate accounts. One protected space.", "Разные аккаунты. Одно защищённое пространство.")}</p></div><ArrowRight /></button>

    <section className="orbit-next"><header><div><p>{tr("NEXT ACTIONS", "СЛЕДУЮЩИЕ ДЕЙСТВИЯ")}</p><h3>{tr("Keep your orbit moving", "Управляйте своей орбитой")}</h3></div><button onClick={() => notify(tr("Everything is synchronized", "Всё синхронизировано"))}><i />{tr("Live", "В сети")}</button></header><div><button onClick={() => go("more")}><span className="pink"><MessageCircle /></span><b>{tr("Support", "Поддержка")}</b><small>{overview.open_ticket_count ? `${overview.open_ticket_count} ${tr("open", "открыто")}` : tr("Ready to help", "Готовы помочь")}</small></button><button onClick={() => go("more")}><span className="violet"><Gift /></span><b>{tr("Rewards", "Бонусы")}</b><small>{tr("Invite friends", "Пригласить друзей")}</small></button></div></section>
  </div>;
}

const money = (minor: number, currency: string) => new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);
