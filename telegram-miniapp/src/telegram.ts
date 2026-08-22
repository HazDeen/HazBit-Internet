export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  photo_url?: string;
  is_premium?: boolean;
}

interface TelegramThemeParams {
  bg_color?: string;
  secondary_bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  header_bg_color?: string;
  accent_text_color?: string;
}

interface TelegramButton {
  isVisible: boolean;
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

interface TelegramMainButton extends TelegramButton {
  setText(text: string): void;
  enable(): void;
  disable(): void;
  showProgress(leaveActive?: boolean): void;
  hideProgress(): void;
  color?: string;
  textColor?: string;
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe?: { user?: TelegramUser; start_param?: string };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: TelegramThemeParams;
  viewportHeight: number;
  viewportStableHeight: number;
  isExpanded: boolean;
  BackButton: TelegramButton;
  MainButton: TelegramMainButton;
  HapticFeedback?: {
    impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  ready(): void;
  expand(): void;
  close(): void;
  disableVerticalSwipes?(): void;
  enableClosingConfirmation?(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  onEvent(event: string, callback: () => void): void;
  offEvent(event: string, callback: () => void): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void): void;
  showPopup?(params: { title?: string; message: string; buttons?: Array<{ id?: string; type?: string; text?: string }> }, callback?: (buttonId: string) => void): void;
}

declare global {
  interface Window { Telegram?: { WebApp?: TelegramWebApp } }
}

const telegram = () => window.Telegram?.WebApp;

export const tg = {
  get available() { return Boolean(telegram()?.initData); },
  get initData() { return telegram()?.initData ?? ""; },
  get user() { return telegram()?.initDataUnsafe?.user ?? null; },
  get startParam() {
    const query = new URLSearchParams(window.location.search);
    return telegram()?.initDataUnsafe?.start_param ?? query.get("tgWebAppStartParam") ?? query.get("startapp");
  },
  get platform() { return telegram()?.platform ?? "web"; },
  boot() {
    const app = telegram();
    const updateViewport = () => document.documentElement.style.setProperty("--tg-viewport-height", `${app?.viewportStableHeight || window.innerHeight}px`);
    updateViewport();
    app?.onEvent("viewportChanged", updateViewport);
    app?.disableVerticalSwipes?.();
    app?.enableClosingConfirmation?.();
    app?.expand();
    app?.ready();
    return () => { app?.offEvent("viewportChanged", updateViewport); };
  },
  appearance(theme: "dark" | "light") {
    const app = telegram();
    const color = theme === "light" ? "#f2f4fa" : "#070a12";
    app?.setHeaderColor(color);
    app?.setBackgroundColor(color);
  },
  back(callback: (() => void) | null) {
    const button = telegram()?.BackButton;
    if (!button) return () => undefined;
    if (!callback) { button.hide(); return () => undefined; }
    button.onClick(callback); button.show();
    return () => { button.offClick(callback); button.hide(); };
  },
  main(text: string, callback: () => void, loading = false) {
    const button = telegram()?.MainButton;
    if (!button) return () => undefined;
    button.color = "#7f93f5";
    button.textColor = "#ffffff";
    button.setText(text); button.onClick(callback); button.show();
    if (loading) { button.disable(); button.showProgress(); } else { button.enable(); button.hideProgress(); }
    return () => { button.offClick(callback); button.hideProgress(); button.hide(); };
  },
  haptic(type: "tap" | "success" | "error" | "selection") {
    const feedback = telegram()?.HapticFeedback;
    if (type === "tap") feedback?.impactOccurred("light");
    else if (type === "selection") feedback?.selectionChanged();
    else feedback?.notificationOccurred(type);
  },
  openTelegram(url: string) { telegram()?.openTelegramLink(url) ?? window.open(url, "_blank", "noopener"); },
  openLink(url: string) { telegram()?.openLink(url) ?? window.open(url, "_blank", "noopener"); },
  openInvoice(url: string, callback: (status: string) => void) {
    const app = telegram();
    if (!app) { callback("pending"); return; }
    app.openInvoice(url, callback);
  },
};
