import { useEffect, useState } from "react";
import { ArrowDown, ArrowRight, Check, Crown, Globe2, Laptop, MonitorSmartphone, Play, ShieldCheck, Smartphone, Sparkles, UserPlus, UsersRound, Zap } from "lucide-react";
import { api } from "../../api";
import { PublicHeader } from "../../components/layout/PublicHeader";
import { RouteSphere } from "../../components/visuals/RouteSphere";
import { useI18n } from "../../i18n";
import type { Plan, Theme } from "../../types";
import "./landing.css";

interface LandingPageProps {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  authenticated: boolean;
  onConnect: () => void;
  onPortal: () => void;
}

const steps = [
  { number: "01", icon: UserPlus, en: "Create an account", ru: "Создайте аккаунт", enText: "Choose password, Google or Telegram and verify your email.", ruText: "Выберите пароль, Google или Telegram и подтвердите почту." },
  { number: "02", icon: MonitorSmartphone, en: "Add a device", ru: "Добавьте устройство", enText: "Copy the private link to your VLESS client.", ruText: "Откройте приватную ссылку в VLESS-клиенте." },
  { number: "03", icon: ShieldCheck, en: "Stay protected", ru: "Оставайтесь под защитой", enText: "Hazbit keeps access, devices and family in sync.", ruText: "Hazbit синхронизирует доступ, устройства и семью." },
];

export function LandingPage({ theme, onThemeChange, authenticated, onConnect, onPortal }: LandingPageProps) {
  const { t } = useI18n();
  const [plans, setPlans] = useState<Plan[]>([]);
  useEffect(() => { let active = true; api<Plan[]>("/catalog/plans").then((value) => { if (active) setPlans(value); }).catch(() => undefined); return () => { active = false; }; }, []);
  const primaryAction = authenticated ? onPortal : onConnect;
  return <main className="public-page" id="top">
    <div className="public-page__mesh" />
    <PublicHeader theme={theme} onThemeChange={onThemeChange} authenticated={authenticated} onAccountAction={primaryAction} />

    <section className="public-hero" aria-labelledby="public-hero-title">
      <div className="public-hero__copy">
        <span className="public-kicker"><i />{t("PRIVATE INTERNET, WITHOUT THE NOISE", "ПРИВАТНЫЙ ИНТЕРНЕТ БЕЗ ЛИШНЕГО ШУМА")}</span>
        <h1 id="public-hero-title">{t("Your internet. In your orbit.", "Ваш интернет. На вашей орбите.")}</h1>
        <p>{t("Hazbit brings private VLESS access, every device and the people close to you into one calm space.", "Hazbit объединяет приватный VLESS-доступ, все устройства и близких людей в одном спокойном пространстве.")}</p>
        <div className="public-hero__actions">
          <button className="public-primary" onClick={primaryAction}><Zap size={17} />{authenticated ? t("Open client panel", "Открыть панель клиента") : t("Connect Hazbit", "Подключить Hazbit")}<ArrowRight size={17} /></button>
          <a className="public-secondary" href="#how"><Play size={15} />{t("How it works", "Как это работает")}</a>
        </div>
        <div className="public-hero__trust"><span><Check />VLESS</span><span><Check />{t("Flexible secure sign-in", "Гибкий защищённый вход")}</span><span><Check />{t("Family ready", "Для всей семьи")}</span></div>
      </div>
      <div className="public-hero__visual">
        <div className="public-orbit-caption public-orbit-caption--top"><span />{t("Private route", "Приватный маршрут")}<b>{t("Active", "Активен")}</b></div>
        <RouteSphere label={t("Animated VLESS route sphere", "Анимированная сфера VLESS-маршрута")} />
        <div className="public-orbit-caption public-orbit-caption--bottom"><div><Smartphone /><Laptop /></div><span>{t("All devices in sync", "Все устройства синхронизированы")}</span></div>
      </div>
      <a className="public-scroll" href="#how" aria-label={t("Scroll to how it works", "Перейти к описанию")}><ArrowDown /></a>
    </section>

    <section className="public-proof" aria-label={t("Hazbit capabilities", "Возможности Hazbit")}>
      <span>{t("One private perimeter", "Единый приватный периметр")}</span><i />
      <span>{t("Desktop + mobile", "Компьютер + телефон")}</span><i />
      <span>{t("Live device control", "Контроль устройств")}</span><i />
      <span>{t("Human support", "Живая поддержка")}</span>
    </section>

    <section className="public-section public-how" id="how">
      <header className="public-section__head"><div><span>{t("THREE SIMPLE STEPS", "ТРИ ПРОСТЫХ ШАГА")}</span><h2>{t("From email to private route in minutes.", "От почты до приватного маршрута за несколько минут.")}</h2></div><p>{t("No complicated account setup. Hazbit guides every action and keeps technical details out of the way.", "Без сложной настройки аккаунта. Hazbit проведёт по шагам и не перегрузит техническими деталями.")}</p></header>
      <div className="public-steps">{steps.map(({ number, icon: Icon, en, ru, enText, ruText }) => <article key={number}><div><span>{number}</span><Icon /></div><h3>{t(en, ru)}</h3><p>{t(enText, ruText)}</p><i /></article>)}</div>
    </section>

    <section className="public-section public-possibilities" id="possibilities">
      <div className="public-command-visual">
        <div className="command-window">
          <header><span><i /><i /><i /></span><b>HAZBIT CONTROL</b><em>{t("Protected", "Под защитой")}</em></header>
          <div className="command-window__body"><aside><i className="active" /><i /><i /><i /></aside><section><div className="command-route"><RouteSphere compact /><span><small>{t("ROUTE STATUS", "СТАТУС МАРШРУТА")}</small><b>{t("Stable", "Стабилен")}</b></span></div><div className="command-metrics"><span><small>{t("Devices", "Устройства")}</small><b>4 / 5</b></span><span><small>{t("Access", "Доступ")}</small><b>42 {t("days", "дня")}</b></span><span><small>{t("Family", "Семья")}</small><b>3 {t("people", "человека")}</b></span></div></section></div>
        </div>
      </div>
      <div className="public-possibilities__copy"><span className="public-kicker"><Sparkles />{t("ONE CONTROL CENTER", "ЕДИНЫЙ ЦЕНТР УПРАВЛЕНИЯ")}</span><h2>{t("See what matters. Control it instantly.", "Видеть главное. Управлять мгновенно.")}</h2><p>{t("Subscription, devices, payments, support and family access stay connected — without turning your account into a settings maze.", "Подписка, устройства, платежи, поддержка и семейный доступ связаны между собой — без лабиринта настроек.")}</p><ul><li><Globe2 />{t("Live VLESS route status", "Живой статус VLESS-маршрута")}</li><li><MonitorSmartphone />{t("Device slots and setup links", "Слоты устройств и ссылки настройки")}</li><li><Crown />{t("Plan and access timeline", "Тариф и срок доступа")}</li></ul></div>
    </section>

    <section className="public-section public-family" id="family">
      <div className="public-family__copy"><span className="public-kicker"><UsersRound />{t("FAMILY ORBIT", "СЕМЕЙНАЯ ОРБИТА")}</span><h2>{t("Close people. Separate accounts. One protected space.", "Близкие люди. Разные аккаунты. Одно защищённое пространство.")}</h2><p>{t("Invite family members without sharing passwords. Everyone keeps their identity while you manage common limits and access.", "Приглашайте близких без передачи паролей. Каждый сохраняет свой аккаунт, а вы управляете общими лимитами и доступом.")}</p><button className="public-text-action" onClick={primaryAction}>{authenticated ? t("Manage your family", "Управлять семьёй") : t("Create your private orbit", "Создать приватную орбиту")}<ArrowRight /></button></div>
      <div className="public-family__orbit" aria-hidden="true"><i /><i /><span className="family-person family-person--owner">HZ<small>{t("You", "Вы")}</small></span><span className="family-person family-person--one">AK</span><span className="family-person family-person--two">MS</span><span className="family-person family-person--three">+1</span><b><ShieldCheck /></b></div>
    </section>

    <section className="public-section public-pricing" id="pricing">
      <header className="public-section__head"><div><span>{t("CLEAR PRICING", "ПОНЯТНЫЕ ТАРИФЫ")}</span><h2>{t("Pay only for the access you choose.", "Платите только за выбранный доступ.")}</h2></div><p>{t("Prices, period and limits are shown before payment. Top up through Platega by SBP, Russian card or crypto, then pay from your Hazbit balance.", "Цена, срок и лимиты показаны до оплаты. Пополните баланс через Platega по СБП, картой РФ или криптовалютой, затем оплатите тариф с баланса Hazbit.")}</p></header>
      <div className="public-price-grid">{plans.length ? plans.map((plan, index) => { const price = plan.prices[0]; return <article className={index === 1 ? "featured" : ""} key={plan.id}>{index === 1 && <span className="price-choice">{t("POPULAR", "ПОПУЛЯРНЫЙ")}</span>}<small>0{index + 1}</small><h3>{plan.name}</h3><p>{plan.description ?? t("Private VLESS access", "Приватный VLESS-доступ")}</p><strong>{formatPrice(price?.amount_minor ?? 0, price?.currency ?? "RUB")}<em>/ {price?.term_months ?? 1} {t("mo.", "мес.")}</em></strong><ul><li><Check />{plan.device_limit} {t("devices", "устройств")}</li><li><Check />{plan.family_member_limit ? `${plan.family_member_limit} ${t("family members", "участников семьи")}` : t("Personal access", "Личный доступ")}</li><li><Check />{t("Unlimited traffic", "Безлимитный трафик")}</li></ul><button onClick={primaryAction}>{authenticated ? t("Open client panel", "Открыть панель клиента") : t("Choose tariff", "Выбрать тариф")}<ArrowRight /></button></article>; }) : <div className="public-pricing-loading">{t("Loading current tariffs…", "Загружаем актуальные тарифы…")}</div>}</div>
    </section>

    <section className="public-cta"><div><span>{t("YOUR PRIVATE ROUTE IS READY", "ВАШ ПРИВАТНЫЙ МАРШРУТ ГОТОВ")}</span><h2>{t("Bring your internet into Hazbit orbit.", "Переведите свой интернет на орбиту Hazbit.")}</h2></div><button className="public-primary" onClick={primaryAction}>{authenticated ? t("Open client panel", "Открыть панель клиента") : t("Connect now", "Подключить сейчас")}<ArrowRight /></button></section>
    <footer className="public-footer"><div className="public-brand"><span><i /><i /><i /></span><b>HAZBIT<small>PRIVATE INTERNET</small></b></div><p>VLESS · {t("Private access for your devices and family", "Приватный доступ для ваших устройств и семьи")}</p><nav><a href="#privacy">{t("Privacy", "Конфиденциальность")}</a><a href="#terms">{t("Agreement", "Соглашение")}</a><a href="#contacts">{t("Support", "Поддержка")}</a></nav><span>© 2026 Hazbit</span></footer>
  </main>;
}

const formatPrice = (amountMinor: number, currency: string) => new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 0 }).format(amountMinor / 100);
