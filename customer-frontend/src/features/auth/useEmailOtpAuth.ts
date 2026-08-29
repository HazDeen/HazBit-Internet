import { useState, type FormEvent } from "react";
import { startEmailLogin, verifyEmailLogin } from "../../api";

export type EmailOtpStep = "email" | "code";
export type AuthFieldError = "email_required" | "email_invalid" | "code_invalid";

interface EmailOtpAuthOptions {
  onAuthenticated: () => void;
  onCodeSent?: (email: string) => void;
  onError?: (message: string) => void;
  onValidationError?: (error: AuthFieldError) => void;
}

export function useEmailOtpAuth({ onAuthenticated, onCodeSent, onError, onValidationError }: EmailOtpAuthOptions) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<EmailOtpStep>("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<AuthFieldError | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (step === "email" && !normalizedEmail) { setFieldError("email_required"); onValidationError?.("email_required"); return; }
    if (step === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(normalizedEmail)) { setFieldError("email_invalid"); onValidationError?.("email_invalid"); return; }
    if (step === "code" && !/^\d{6,8}$/.test(code.trim())) { setFieldError("code_invalid"); onValidationError?.("code_invalid"); return; }
    setBusy(true);
    setError(null);
    setFieldError(null);
    try {
      if (step === "email") {
        setEmail(normalizedEmail);
        await startEmailLogin(normalizedEmail);
        setStep("code");
        onCodeSent?.(normalizedEmail);
        return;
      }
      await verifyEmailLogin(normalizedEmail, code.trim());
      onAuthenticated();
    } catch (value) {
      const message = value instanceof Error ? value.message : "Unable to sign in";
      setError(message);
      onError?.(message);
    } finally {
      setBusy(false);
    }
  };

  const updateEmail = (value: string) => { setEmail(value); setFieldError(null); setError(null); };
  const updateCode = (value: string) => { setCode(value.replace(/\D/g, "").slice(0, 8)); setFieldError(null); setError(null); };
  const resetEmail = () => { setStep("email"); setCode(""); setError(null); setFieldError(null); };
  return { email, setEmail: updateEmail, code, setCode: updateCode, step, busy, error, fieldError, submit, resetEmail };
}
