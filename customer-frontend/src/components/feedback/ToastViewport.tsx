import { useEffect, type CSSProperties } from "react";
import { AlertTriangle, Check, Info, ShieldAlert, X } from "lucide-react";
import type { ToastMessage, ToastTone } from "./useToastQueue";
import "./feedback.css";

interface ToastViewportProps {
  messages: ToastMessage[];
  onDismiss: (id: string) => void;
}

const icons: Record<ToastTone, typeof Check> = {
  success: Check,
  error: ShieldAlert,
  warning: AlertTriangle,
  info: Info,
};

export function ToastViewport({ messages, onDismiss }: ToastViewportProps) {
  return <aside className="toast-viewport" aria-label="Notifications" aria-live="polite">{messages.map((message) => <ToastItem key={message.id} message={message} onDismiss={onDismiss} />)}</aside>;
}

function ToastItem({ message, onDismiss }: { message: ToastMessage; onDismiss: (id: string) => void }) {
  const Icon = icons[message.tone];
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(message.id), message.duration);
    return () => window.clearTimeout(timer);
  }, [message.duration, message.id, onDismiss]);

  return <article className={`feedback-toast feedback-toast--${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>
    <span className="feedback-toast__icon"><Icon /></span>
    <div><strong>{message.title}</strong>{message.description && <p>{message.description}</p>}</div>
    <button onClick={() => onDismiss(message.id)} aria-label="Закрыть уведомление / Dismiss notification"><X /></button>
    <i className="feedback-toast__progress" style={{ "--toast-duration": `${message.duration}ms` } as CSSProperties} />
  </article>;
}
