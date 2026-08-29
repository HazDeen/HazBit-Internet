import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";
import type { ToastTone } from "./useToastQueue";

const icons = { success: CheckCircle2, error: ShieldAlert, warning: AlertTriangle, info: Info };

export function InlineFeedback({ tone, title, description, id }: { tone: ToastTone; title: string; description?: string; id?: string }) {
  const Icon = icons[tone];
  return <div className={`inline-feedback inline-feedback--${tone}`} role={tone === "error" ? "alert" : "status"} id={id}><Icon /><div><b>{title}</b>{description && <span>{description}</span>}</div></div>;
}
