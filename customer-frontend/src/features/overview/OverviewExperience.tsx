import { ArrowRight, CalendarDays, ChevronRight, CircleHelp, Crown, Download, Gift, LoaderCircle, MessageCircle, MonitorSmartphone, ScanLine, ShieldCheck, Smartphone, UsersRound, Zap } from "lucide-react";
import { RouteSphere } from "../../components/visuals/RouteSphere";
import { useI18n } from "../../i18n";
import type { Overview, Section } from "../../types";
import "./overview-experience.css";

interface OverviewExperienceProps {
  data: Overview | null;
  loading: boolean;
  error: string | null;
  navigate: (section: Section) => void;
  notify: (message: string) => void;
}

export function OverviewExperience({ data, loading, error, navigate, notify }: OverviewExperienceProps) {
  const { locale, t } = useI18n();
  if (!data) return <div className="overview-state">{loading ? <LoaderCircle className="spin" /> : <CircleHelp />}<span>{loading ? t("Building your command center…", "Собираем ваш центр управления…") : error ?? t("Unable to load overview", "Не удалось загрузить главную")}</span></div>;

  const connected = data.vpn?.observed_status === "active";
  const end = data.subscription?.current_period_ends_at ?? null;
  const days = end ? Math.max(0, Math.ceil((new Date(end).getTime() - Date.now()) / 86_400_000)) : 0;
  const deviceLimit = data.subscription?.device_limit ?? 0;
  const devicePercent = Math.min(100, data.active_device_count / Math.max(1, deviceLimit) * 100);

  return <div className="command-overview">
    <section className={`command-hero ${connected ? "connected" : "paused"}`}>
      <div className="command-hero__copy">
        <span className="command-eyebrow"><i />{connected ? t("PRIVATE ROUTE ACTIVE", "ПРИВАТНЫЙ МАРШРУТ АКТИВЕН") : t("READY TO CONNECT", "ГОТОВО К ПОДКЛЮЧЕНИЮ")}</span>
        <h2>{connected ? t("Everything is in your orbit.", "Всё находится на вашей орбите.") : t("Bring your route back online.", "Верните маршрут в сеть.")}</h2>
        <p>{connected ? t("VLESS is synchronized. Your devices and access are under control.", "VLESS синхронизирован. Устройства и доступ находятся под контролем.") : t("Open your VLESS client or add a device to restore private access.", "Откройте VLESS-клиент или добавьте устройство, чтобы восстановить приватный доступ.")}</p>
        <div className="command-hero__actions"><button className="primary-button" onClick={() => navigate("devices")}><Download />{t("Connect a device", "Подключить устройство")}<ArrowRight /></button><button className="glass-button" onClick={() => notify(t("Route status refreshed", "Статус маршрута обновлён"))}><ScanLine />{t("Check route", "Проверить маршрут")}</button></div>
      </div>
      <div className="command-hero__sphere"><RouteSphere connected={connected} /><span className="sphere-tag sphere-tag--route"><ShieldCheck />VLESS <b>{connected ? t("Stable", "Стабилен") : t("Paused", "Пауза")}</b></span><span className="sphere-tag sphere-tag--devices"><MonitorSmartphone /><b>{data.active_device_count}</b>{t("devices", "устройства")}</span></div>
      <div className="command-hero__rail"><span><small>{t("ACCESS", "ДОСТУП")}</small><b>{data.subscription?.plan_name ?? t("No plan", "Нет тарифа")}</b></span><i /><span><small>{t("REMAINING", "ОСТАЛОСЬ")}</small><b>{days} {t("days", "дней")}</b></span><i /><span><small>{t("ROUTING", "МАРШРУТ")}</small><b>{t("Automatic", "Автоматический")}</b></span></div>
    </section>

    <section className="command-bento">
      <article className="command-access">
        <header><span><Crown /></span><div><p>{t("ACCESS TIMELINE", "СРОК ДОСТУПА")}</p><h3>{data.subscription?.plan_name ?? t("Choose a plan", "Выберите тариф")}</h3></div><button onClick={() => navigate("subscription")} aria-label={t("Open subscription", "Открыть подписку")}><ChevronRight /></button></header>
        <div className="access-number"><strong>{days}</strong><span>{t("days in your private orbit", "дней на приватной орбите")}</span></div>
        <div className="access-timeline"><i style={{ width: `${Math.min(100, days / 60 * 100)}%` }} /><b /></div>
        <footer><span><CalendarDays />{t("Valid until", "Действует до")}</span><b>{formatDate(end, locale)}</b></footer>
      </article>

      <article className="command-devices">
        <header><div><p>{t("TRUSTED PERIMETER", "ДОВЕРЕННЫЙ ПЕРИМЕТР")}</p><h3>{t("Your devices", "Ваши устройства")}</h3></div><button onClick={() => navigate("devices")}><Zap />{t("Manage", "Управлять")}</button></header>
        <div className="device-orbit-row"><div className="device-orbit-item active"><span><Smartphone /></span><b>iPhone</b><small>{t("Active", "Активно")}</small></div><div className="device-orbit-item"><span><MonitorSmartphone /></span><b>MacBook</b><small>{t("Synced", "В сети")}</small></div><button className="device-orbit-add" onClick={() => navigate("devices")}><span>+</span><b>{t("Add", "Добавить")}</b></button></div>
        <footer><div><span>{data.active_device_count} / {deviceLimit}</span><small>{t("slots in use", "слотов занято")}</small></div><div className="device-usage"><i style={{ width: `${devicePercent}%` }} /></div></footer>
      </article>

      <article className="command-family" onClick={() => navigate("family")} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter") navigate("family"); }}>
        <div className="command-family__constellation"><i /><span>HZ</span><span>A</span><span>M</span><b><UsersRound /></b></div>
        <div><p>{t("SHARED PROTECTION", "ОБЩАЯ ЗАЩИТА")}</p><h3>{data.family_group_name ?? t("Create your family orbit", "Создайте семейную орбиту")}</h3><span>{data.family_group_id ? t("Separate accounts in one protected perimeter.", "Отдельные аккаунты в едином защищённом периметре.") : t("Invite close people without sharing credentials.", "Пригласите близких без передачи данных для входа.")}</span></div><ChevronRight />
      </article>

      <article className="command-actions"><p>{t("NEXT BEST ACTIONS", "СЛЕДУЮЩИЕ ДЕЙСТВИЯ")}</p><button onClick={() => navigate("rewards")}><span className="violet"><Gift /></span><div><b>{t("Invite and earn days", "Приглашайте и получайте дни")}</b><small>{t("Share your private orbit", "Поделитесь приватной орбитой")}</small></div><ArrowRight /></button><button onClick={() => navigate("support")}><span className="pink"><MessageCircle /></span><div><b>{t("Talk to support", "Написать в поддержку")}</b><small>{data.open_ticket_count ? t(`${data.open_ticket_count} conversation needs you`, `${data.open_ticket_count} обращение ждёт вас`) : t("Usually replies in 5 minutes", "Обычно отвечает за 5 минут")}</small></div><ArrowRight /></button></article>
    </section>
  </div>;
}

function formatDate(value: string | null, locale: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}
