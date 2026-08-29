import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Bitcoin,
  CreditCard,
  Landmark,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import { api, idempotencyKey } from "../../api";
import { useI18n } from "../../i18n";
import type { Wallet, WalletTopUp } from "../../types";
import "./billing.css";

interface BillingPageProps {
  notify: (message: string) => void;
}

const methods = [
  { id: 2, icon: Landmark, en: "SBP", ru: "СБП", detailEn: "QR or bank link", detailRu: "QR или ссылка в банк" },
  { id: 10, icon: CreditCard, en: "Russian card", ru: "Карта РФ", detailEn: "MIR and Russian cards", detailRu: "МИР и карты российских банков" },
  { id: 13, icon: Bitcoin, en: "Crypto", ru: "Криптовалюта", detailEn: "Platega crypto checkout", detailRu: "Криптоформа Platega" },
] as const;

export function BillingPage({ notify }: BillingPageProps) {
  const { locale, t } = useI18n();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [amount, setAmount] = useState("1000");
  const [method, setMethod] = useState<2 | 10 | 13>(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setWallet(await api<Wallet>("/billing/wallet")); }
    catch (value) { setError(value instanceof Error ? value.message : t("Unable to load wallet", "Не удалось загрузить кошелёк")); }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const topUp = async (event: FormEvent) => {
    event.preventDefault();
    const rubles = Number(amount);
    if (!Number.isInteger(rubles) || rubles < 100) {
      setError(t("Enter a whole amount from 100 ₽", "Введите целую сумму от 100 ₽"));
      return;
    }
    setBusy(true); setError(null);
    try {
      const result = await api<WalletTopUp>("/billing/top-ups", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("wallet-top-up") },
        body: JSON.stringify({ amount_minor: rubles * 100, currency: "RUB", payment_method: method }),
      });
      if (result.checkout_url) {
        window.location.assign(result.checkout_url);
        return;
      }
      await load();
      notify(t("Balance topped up", "Баланс пополнен"));
    } catch (value) {
      setError(value instanceof Error ? value.message : t("Top-up failed", "Не удалось пополнить баланс"));
    } finally { setBusy(false); }
  };

  const toggleRenewal = async () => {
    if (!wallet) return;
    setBusy(true); setError(null);
    try {
      const updated = await api<Wallet>("/billing/auto-renew", {
        method: "PATCH",
        body: JSON.stringify({ enabled: !wallet.auto_renew_enabled }),
      });
      setWallet(updated);
      notify(updated.auto_renew_enabled ? t("Auto-renewal enabled", "Автопродление включено") : t("Auto-renewal disabled", "Автопродление выключено"));
    } catch (value) {
      setError(value instanceof Error ? value.message : t("Unable to update renewal", "Не удалось изменить автопродление"));
    } finally { setBusy(false); }
  };

  return <div className="page-stack billing-page">
    <section className="wallet-hero">
      <div className="wallet-hero__copy"><span><WalletCards />{t("HAZBIT BALANCE", "БАЛАНС HAZBIT")}</span><strong>{wallet ? money(wallet.balance_minor, wallet.currency, locale) : "—"}</strong><p>{t("Top up once and let Hazbit renew access from your balance. Every movement stays in the immutable ledger.", "Пополняйте баланс, а Hazbit продлит доступ автоматически. Каждое движение сохраняется в неизменяемом журнале.")}</p></div>
      <div className="wallet-orbit" aria-hidden="true"><i /><i /><span><ShieldCheck /></span><b>RUB</b></div>
      <button className="wallet-refresh" onClick={() => void load()} aria-label={t("Refresh balance", "Обновить баланс")}><RefreshCw /></button>
    </section>

    <div className="billing-layout">
      <form className="surface-card topup-panel" onSubmit={topUp}>
        <header><div><p className="eyebrow">PLATEGA CHECKOUT</p><h3>{t("Top up balance", "Пополнить баланс")}</h3></div><ShieldCheck /></header>
        <label>{t("Amount", "Сумма")}<span className="amount-input"><input inputMode="numeric" value={amount} onChange={(event) => setAmount(event.target.value.replace(/\D/g, "").slice(0, 7))} aria-describedby="topup-hint" required /><b>₽</b></span></label>
        <small id="topup-hint">{t("Minimum 100 ₽. Your balance receives the amount shown.", "Минимум 100 ₽. На баланс зачисляется указанная сумма.")}</small>
        <fieldset><legend>{t("Payment method", "Способ оплаты")}</legend><div className="payment-methods">{methods.map(({ id, icon: Icon, en, ru, detailEn, detailRu }) => <button type="button" key={id} className={method === id ? "active" : ""} aria-pressed={method === id} onClick={() => setMethod(id)}><Icon /><span><b>{t(en, ru)}</b><small>{t(detailEn, detailRu)}</small></span></button>)}</div></fieldset>
        {error && <div className="inline-error" role="alert">{error}</div>}
        <button className="primary-button wide" disabled={busy}>{busy ? <LoaderCircle className="spin" /> : <ArrowUpRight />} {t("Continue in Platega", "Перейти к оплате Platega")}</button>
        <p className="provider-note"><ShieldCheck />{t("Card and banking details are entered only on the protected Platega page and never reach Hazbit.", "Данные карты и банка вводятся только на защищённой странице Platega и не передаются Hazbit.")}</p>
      </form>

      <section className="surface-card renewal-panel">
        <header><div><p className="eyebrow">AUTO RENEW</p><h3>{t("Automatic renewal", "Автоматическое продление")}</h3></div><button className={`renew-switch ${wallet?.auto_renew_enabled ? "on" : ""}`} onClick={toggleRenewal} disabled={busy || !wallet?.auto_renew_plan_price_id} role="switch" aria-checked={wallet?.auto_renew_enabled ?? false}><i /></button></header>
        <div className="renewal-status"><span>{wallet?.auto_renew_enabled ? <RefreshCw /> : <ShieldCheck />}</span><div><b>{wallet?.auto_renew_enabled ? t("Enabled", "Включено") : t("Under your control", "Под вашим контролем")}</b><p>{wallet?.auto_renew_enabled ? t("The tariff will be charged only from the Hazbit balance.", "Тариф будет списан только с баланса Hazbit.") : t("Enable it after purchasing a paid tariff.", "Включите после покупки платного тарифа.")}</p></div></div>
        <dl><div><dt>{t("Next attempt", "Следующее списание")}</dt><dd>{wallet?.next_renewal_at ? date(wallet.next_renewal_at, locale) : "—"}</dd></div><div><dt>{t("Last issue", "Последняя проблема")}</dt><dd>{wallet?.last_renewal_failure ?? t("None", "Нет")}</dd></div></dl>
      </section>
    </div>

    <section className="surface-card wallet-ledger"><header><div><p className="eyebrow">LEDGER</p><h3>{t("Balance movements", "Движения по балансу")}</h3></div><span>{wallet?.transactions.length ?? 0}</span></header>{wallet?.transactions.length ? <div>{wallet.transactions.map((item) => <article key={item.id}><span className={item.amount_minor > 0 ? "credit" : "debit"}>{item.amount_minor > 0 ? <ArrowDownLeft /> : <ArrowUpRight />}</span><div><b>{label(item.transaction_type, t)}</b><small>{item.description ?? "Hazbit"} · {date(item.created_at, locale)}</small></div><strong className={item.amount_minor > 0 ? "positive" : ""}>{item.amount_minor > 0 ? "+" : ""}{money(item.amount_minor, item.currency, locale)}</strong></article>)}</div> : <p className="ledger-empty">{t("No balance movements yet", "Операций по балансу пока нет")}</p>}</section>
  </div>;
}

const money = (minor: number, currency: string, locale: string) => new Intl.NumberFormat(locale === "ru" ? "ru-RU" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(minor / 100);
const date = (value: string, locale: string) => new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-US", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
const label = (value: string, t: (en: string, ru: string) => string) => ({ payment_credit: t("Balance top-up", "Пополнение баланса"), subscription_debit: t("Tariff payment", "Оплата тарифа"), promo_credit: t("Promo bonus", "Бонус по промокоду"), referral_credit: t("Referral bonus", "Реферальный бонус"), reversal: t("Payment reversal", "Возврат платежа") }[value] ?? value);
