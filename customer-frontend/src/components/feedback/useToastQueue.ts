import { useCallback, useState } from "react";

export type ToastTone = "success" | "error" | "warning" | "info";

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
  duration: number;
}

interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
  duration?: number;
}

export function useToastQueue() {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const dismiss = useCallback((id: string) => {
    setMessages((current) => current.filter((message) => message.id !== id));
  }, []);

  const push = useCallback((input: ToastInput) => {
    const message: ToastMessage = {
      id: crypto.randomUUID(),
      title: input.title,
      description: input.description,
      tone: input.tone ?? "success",
      duration: input.duration ?? (input.tone === "error" ? 5200 : 3800),
    };
    setMessages((current) => [...current.slice(-3), message]);
    return message.id;
  }, []);

  return { messages, push, dismiss };
}
