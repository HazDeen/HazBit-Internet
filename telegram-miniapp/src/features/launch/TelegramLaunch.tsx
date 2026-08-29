import { ArrowRight, LoaderCircle, LockKeyhole, MessageCircle, ShieldCheck } from "lucide-react";
import { CompactRouteSphere } from "../../components/CompactRouteSphere";
import { MiniBrand } from "../../components/MiniBrand";

type Tr = (en: string, ru: string) => string;

export function TelegramLaunch({ error, retry, tr }: { error: string | null; retry?: () => void; tr: Tr }) {
  return <main className="telegram-launch">
    <header><MiniBrand /><span><LockKeyhole />{tr("TELEGRAM SECURE ENTRY", "ЗАЩИЩЁННЫЙ ВХОД TELEGRAM")}</span></header>
    <section className="telegram-launch__visual"><CompactRouteSphere connected={!error} label={tr("Hazbit private route", "Приватный маршрут Hazbit")} /><span className="telegram-launch__badge"><i />{error ? tr("Telegram context required", "Нужен контекст Telegram") : tr("Signed session", "Подписанная сессия")}</span></section>
    <section className="telegram-launch__copy">
      <p>{tr("YOUR INTERNET IN ONE ORBIT", "ВАШ ИНТЕРНЕТ НА ОДНОЙ ОРБИТЕ")}</p>
      <h1>{error ? tr("Open Hazbit inside Telegram.", "Откройте Hazbit внутри Telegram.") : tr("Opening your private space.", "Открываем приватное пространство.")}</h1>
      <span>{error ? tr("Telegram securely passes your identity to Hazbit. No email or password is required here.", "Telegram безопасно передаёт вашу личность в Hazbit. Почта и пароль здесь не нужны.") : tr("Checking the signed session and synchronizing VLESS access, devices and family.", "Проверяем подписанную сессию и синхронизируем VLESS-доступ, устройства и семью.")}</span>
      {error ? <button onClick={retry}><MessageCircle />{tr("Continue in Telegram", "Продолжить в Telegram")}<ArrowRight /></button> : <div className="telegram-launch__loading"><LoaderCircle className="spin" />{tr("Connecting securely…", "Безопасно подключаем…")}</div>}
      {error && <small><ShieldCheck />{error}</small>}
    </section>
  </main>;
}
