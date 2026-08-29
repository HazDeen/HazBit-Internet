import { useEffect, useRef } from "react";
import { Send } from "lucide-react";
import { loginWithGoogle, loginWithTelegramWidget, type TelegramWidgetUser } from "../../api";
import { useI18n } from "../../i18n";

declare global {
  interface Window {
    google?: { accounts: { id: { initialize: (options: { client_id: string; callback: (value: { credential: string }) => void }) => void; renderButton: (element: HTMLElement, options: Record<string, unknown>) => void } } };
    onHazbitTelegramAuth?: (user: TelegramWidgetUser) => void;
  }
}

interface Props { onAuthenticated: () => void; onError: (message: string) => void; onTelegramId: () => void }
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? "";
const telegramBotUsername = (import.meta.env.VITE_TELEGRAM_BOT_USERNAME?.trim() ?? "").replace(/^@/, "");

export function ProviderButtons({ onAuthenticated, onError, onTelegramId }: Props) {
  const { t } = useI18n(); const googleRoot = useRef<HTMLDivElement>(null); const telegramRoot = useRef<HTMLDivElement>(null); const authenticatedRef = useRef(onAuthenticated); const errorRef = useRef(onError); authenticatedRef.current = onAuthenticated; errorRef.current = onError;
  useEffect(() => {
    if (!googleClientId || !googleRoot.current) return;
    const render = () => { if (!window.google || !googleRoot.current) return; window.google.accounts.id.initialize({ client_id: googleClientId, callback: ({ credential }) => { void loginWithGoogle(credential).then(() => authenticatedRef.current()).catch((value: unknown) => errorRef.current(value instanceof Error ? value.message : "Google authentication failed")); } }); googleRoot.current.replaceChildren(); window.google.accounts.id.renderButton(googleRoot.current, { type: "standard", theme: "filled_black", size: "large", shape: "pill", width: 320, text: "continue_with" }); };
    if (window.google) { render(); return; }
    const script = document.createElement("script"); script.src = "https://accounts.google.com/gsi/client"; script.async = true; script.onload = render; document.head.appendChild(script); return () => { script.onload = null; };
  }, []);
  useEffect(() => {
    if (!telegramBotUsername || !telegramRoot.current) return;
    window.onHazbitTelegramAuth = (user) => { void loginWithTelegramWidget(user).then(() => authenticatedRef.current()).catch((value: unknown) => errorRef.current(value instanceof Error ? value.message : "Telegram authentication failed")); };
    const root = telegramRoot.current; root.replaceChildren(); const script = document.createElement("script"); script.src = "https://telegram.org/js/telegram-widget.js?22"; script.async = true; script.dataset.telegramLogin = telegramBotUsername; script.dataset.size = "large"; script.dataset.userpic = "false"; script.dataset.radius = "14"; script.dataset.requestAccess = "write"; script.dataset.onauth = "onHazbitTelegramAuth(user)"; root.appendChild(script);
    return () => { delete window.onHazbitTelegramAuth; root.replaceChildren(); };
  }, []);
  return <div className="auth-providers">{googleClientId && <div className="auth-provider-render" ref={googleRoot} />}{telegramBotUsername && <div className="auth-provider-render telegram" ref={telegramRoot} />}<button type="button" className="auth-provider-id" onClick={onTelegramId}><Send size={17} />{t("Sign in by Telegram ID", "Войти по Telegram ID")}</button></div>;
}
