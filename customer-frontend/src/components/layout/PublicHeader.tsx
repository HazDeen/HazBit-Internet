import { Languages, LayoutDashboard, Moon, Sun } from "lucide-react";
import { useI18n } from "../../i18n";
import type { Theme } from "../../types";

interface PublicHeaderProps {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  authenticated: boolean;
  onAccountAction: () => void;
}

export function PublicHeader({ theme, onThemeChange, authenticated, onAccountAction }: PublicHeaderProps) {
  const { locale, setLocale, t } = useI18n();
  return <header className="public-header">
    <a className="public-brand" href="#top" aria-label="Hazbit — на главную"><span><i /><i /><i /></span><b>HAZBIT<small>PRIVATE INTERNET</small></b></a>
    <nav aria-label={t("Product navigation", "Навигация по продукту")}>
      <a href="#how">{t("How it works", "Как работает")}</a>
      <a href="#possibilities">{t("Possibilities", "Возможности")}</a>
      <a href="#pricing">{t("Pricing", "Тарифы")}</a>
      <a href="#family">{t("Family", "Для семьи")}</a>
    </nav>
    <div className="public-header__actions">
      <div className="public-language" aria-label={t("Interface language", "Язык интерфейса")}><Languages size={15} /><button className={locale === "ru" ? "active" : ""} onClick={() => setLocale("ru")}>RU</button><button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")}>EN</button></div>
      <button className="public-icon-button" aria-label={t("Change theme", "Сменить тему")} onClick={() => onThemeChange(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button>
      <button className={`public-connect-button ${authenticated ? "is-portal" : ""}`} onClick={onAccountAction}>{authenticated && <LayoutDashboard size={15} />}{authenticated ? t("Client panel", "Панель клиента") : t("Sign in", "Войти")}</button>
    </div>
  </header>;
}
