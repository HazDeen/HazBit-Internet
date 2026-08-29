import { useEffect } from "react";
import { ArrowRight, Check, Languages, LoaderCircle, LockKeyhole, Mail, X } from "lucide-react";
import { useI18n } from "../../i18n";
import { demoMode } from "../../api";
import { InlineFeedback } from "../../components/feedback/InlineFeedback";
import type { ToastTone } from "../../components/feedback/useToastQueue";
import { useEmailOtpAuth, type AuthFieldError } from "./useEmailOtpAuth";
import "./auth-dialog.css";

interface AuthDialogProps {
  open: boolean;
  onClose: () => void;
  onAuthenticated: () => void;
  notify: (input: { title: string; description?: string; tone?: ToastTone }) => void;
}

export function AuthDialog({ open, onClose, onAuthenticated, notify }: AuthDialogProps) {
  const { locale, setLocale, t } = useI18n();
  const validationText = (value: AuthFieldError) => ({
    email_required: t("Enter your email address", "Введите электронную почту"),
    email_invalid: t("Use an address like name@example.com", "Используйте адрес вида name@example.com"),
    code_invalid: t("Enter the 6–8 digit code from the email", "Введите код из письма: от 6 до 8 цифр"),
  })[value];
  const auth = useEmailOtpAuth({
    onAuthenticated: () => { notify({ title: t("Welcome to Hazbit", "Добро пожаловать в Hazbit"), description: t("Your secure session is ready", "Защищённая сессия готова"), tone: "success" }); onAuthenticated(); },
    onCodeSent: (email) => notify({ title: t("Code sent", "Код отправлен"), description: t(`Check ${email}`, `Проверьте почту ${email}`), tone: "info" }),
    onError: (message) => notify({ title: t("Unable to sign in", "Не удалось войти"), description: message, tone: "error" }),
    onValidationError: (value) => notify({ title: t("Check the highlighted field", "Проверьте выделенное поле"), description: validationText(value), tone: "warning" }),
  });

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", closeOnEscape); };
  }, [open, onClose]);

  if (!open) return null;
  return <div className="auth-layer" role="presentation">
    <button className="auth-layer__scrim" aria-label={t("Close sign in", "Закрыть вход")} onClick={onClose} />
    <section className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="auth-dialog__aside">
        <div className="auth-dialog__mark"><span><i /><i /><i /></span><b>HAZBIT</b></div>
        <div className="auth-dialog__promise">
          <p>{t("PRIVATE ACCESS", "ПРИВАТНЫЙ ДОСТУП")}</p>
          <h2>{t("One email. No password to remember.", "Одна почта. Никаких паролей для запоминания.")}</h2>
          <ul><li><Check />{t("One-time secure code", "Одноразовый защищённый код")}</li><li><Check />{t("Session and device controls", "Контроль сессий и устройств")}</li><li><Check />{t("Fast access from any screen", "Быстрый вход с любого экрана")}</li></ul>
        </div>
        <div className="auth-dialog__route"><i /><span>VLESS</span><i /><span>HAZBIT</span><i /></div>
      </div>
      <form className="auth-dialog__form" onSubmit={auth.submit} noValidate>
        <div className="auth-dialog__controls">
          <button type="button" className="auth-dialog__language" onClick={() => setLocale(locale === "ru" ? "en" : "ru")}><Languages size={14} />{locale.toUpperCase()}</button>
          <button type="button" className="auth-dialog__close" onClick={onClose} aria-label={t("Close", "Закрыть")}><X size={19} /></button>
        </div>
        <span className="auth-dialog__symbol">{auth.step === "email" ? <Mail /> : <LockKeyhole />}</span>
        <p className="auth-dialog__eyebrow">{auth.step === "email" ? t("SIGN IN OR CREATE ACCOUNT", "ВХОД ИЛИ СОЗДАНИЕ АККАУНТА") : t("EMAIL CONFIRMATION", "ПОДТВЕРЖДЕНИЕ ПОЧТЫ")}</p>
        <h1 id="auth-title">{auth.step === "email" ? t("Connect to Hazbit", "Подключиться к Hazbit") : t("Enter the code", "Введите код")}</h1>
        <p>{auth.step === "email" ? t("We will send a one-time code. If this email is new, the account will be created automatically.", "Отправим одноразовый код. Если почта новая — аккаунт создастся автоматически.") : t(`We sent a code to ${auth.email}.`, `Код отправлен на ${auth.email}.`)}</p>
        {demoMode && <div className="auth-dialog__demo"><span>DEMO</span>{auth.step === "email" ? t("Use any email to preview the flow", "Введите любую почту для просмотра") : t("Use code 000000", "Используйте код 000000")}</div>}
        {auth.step === "email" ? <label>{t("Email", "Электронная почта")}<input type="email" value={auth.email} onChange={(event) => auth.setEmail(event.target.value)} placeholder="you@example.com" aria-invalid={Boolean(auth.fieldError)} aria-describedby={auth.fieldError ? "auth-field-error" : undefined} autoFocus />{auth.fieldError && <span className="field-error" id="auth-field-error">{validationText(auth.fieldError)}</span>}</label> : <label>{t("One-time code", "Одноразовый код")}<input className="auth-dialog__otp" inputMode="numeric" autoComplete="one-time-code" value={auth.code} onChange={(event) => auth.setCode(event.target.value)} placeholder="000000" aria-invalid={Boolean(auth.fieldError)} aria-describedby={auth.fieldError ? "auth-field-error" : undefined} autoFocus />{auth.fieldError && <span className="field-error" id="auth-field-error">{validationText(auth.fieldError)}</span>}</label>}
        {auth.error && <InlineFeedback tone="error" title={t("Authentication failed", "Ошибка авторизации")} description={auth.error} />}
        <button className="auth-dialog__submit" disabled={auth.busy}>{auth.busy ? <LoaderCircle className="spin" /> : <ArrowRight />}<span>{auth.step === "email" ? t("Send secure code", "Отправить защищённый код") : t("Open personal account", "Открыть личный кабинет")}</span></button>
        {auth.step === "code" && <button className="auth-dialog__back" type="button" onClick={auth.resetEmail}>{t("Use another email", "Указать другую почту")}</button>}
        <small><LockKeyhole size={13} />{t("Protected by rotating sessions and rate limiting", "Защищено ротацией сессий и rate limiting")}</small>
      </form>
    </section>
  </div>;
}
