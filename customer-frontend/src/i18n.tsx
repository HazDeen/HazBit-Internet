import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Locale } from "./types";

interface I18nValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (en: string, ru: string) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => localStorage.getItem("hazbit-customer-locale") === "en" ? "en" : "ru");
  const setLocale = (value: Locale) => { localStorage.setItem("hazbit-customer-locale", value); setLocaleState(value); };
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const value = useMemo(() => ({ locale, setLocale, t: (en: string, ru: string) => locale === "ru" ? ru : en }), [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("I18nProvider is missing");
  return value;
}
