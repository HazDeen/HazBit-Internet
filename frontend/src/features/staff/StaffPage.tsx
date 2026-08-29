import {
  Check,
  CheckCircle2,
  LoaderCircle,
  MailPlus,
  Pencil,
  Radio,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";

import { api } from "../../api";
import { useResource } from "../../hooks/useResource";
import { useI18n } from "../../i18n";
import type { StaffDirectory, StaffMember } from "../../types";

export function StaffPage({ notify }: { notify: (message: string) => void }) {
  const { locale, t } = useI18n();
  const resource = useResource<StaffDirectory>("/admin/staff");
  const [editing, setEditing] = useState<StaffMember | "new" | null>(null);

  if (!resource.data) {
    return (
      <div className={`resource-state ${resource.error ? "error" : ""}`}>
        <LoaderCircle className={resource.loading ? "spin" : ""} size={22} />
        <b>{t(resource.loading ? "Loading operational data" : "Data unavailable")}</b>
        <span>{resource.error ?? t("Reading the latest committed state…")}</span>
      </div>
    );
  }
  const data = resource.data;

  const revoke = async (id: string) => {
    await api(`/admin/staff/invitations/${id}`, { method: "DELETE" });
    notify(t("Invitation revoked"));
    resource.reload();
  };

  return (
    <div className="page-stack staff-page">
      <section className="staff-hero">
        <div>
          <p className="overline">{t("Access governance")}</p>
          <h2>{t("The right access for every operator.")}</h2>
          <span>{t("Role presets provide safe defaults; individual permissions cover exceptional responsibilities.")}</span>
        </div>
        <div className="staff-hero-metric"><strong>{data.members.length}</strong><span>{t("active operators")}</span></div>
        <button className="primary-button" onClick={() => setEditing("new")}><MailPlus size={16} /> {t("Invite operator")}</button>
      </section>

      <section className="staff-role-strip">
        {Object.entries(data.role_presets)
          .filter(([role]) => role !== "super_admin")
          .map(([role, permissions]) => (
            <article key={role}>
              <span className={`role-orb role-${role}`}><ShieldCheck size={17} /></span>
              <div><b>{t(title(role))}</b><small>{permissions.length} {t("permissions")}</small></div>
            </article>
          ))}
      </section>

      <section className="panel staff-directory">
        <header className="panel-header">
          <div><p>{t("Team directory")}</p><h3>{t("Operators & access")}</h3></div>
          <span className="security-note"><ShieldCheck size={15} /> {t("All changes are audited")}</span>
        </header>
        <div className="staff-list">
          {data.members.map((member) => {
            const effective = new Set(member.roles.flatMap((role) => data.role_presets[role] ?? []));
            member.permissions.forEach((permission) => effective.add(permission));
            const locked = member.roles.includes("super_admin");
            return (
              <article key={member.user_id}>
                <span className="staff-avatar">{initials(member.email)}</span>
                <div className="staff-identity"><b>{member.public_name ?? member.email.split("@")[0]}</b><small>{member.email}</small></div>
                <div className="staff-roles">{member.roles.map((role) => <span key={role}>{t(title(role))}</span>)}</div>
                <div className="staff-access"><b>{effective.size}</b><small>{t("effective permissions")}</small></div>
                <div className={`telegram-state ${member.telegram_linked ? "linked" : ""}`}><Radio size={14} /><span>{t(member.telegram_linked ? "Bot linked" : "Bot not linked")}</span></div>
                <button className="quiet-button" disabled={locked} onClick={() => setEditing(member)}><Pencil size={14} /> {t(locked ? "Owner protected" : "Edit access")}</button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="panel pending-invites">
        <header className="panel-header"><div><p>{t("Secure onboarding")}</p><h3>{t("Pending invitations")}</h3></div><span>{data.invitations.length}</span></header>
        {data.invitations.length ? (
          <div>{data.invitations.map((invitation) => (
            <article key={invitation.id}>
              <span className="invitation-icon"><MailPlus size={16} /></span>
              <div><b>{invitation.email}</b><small>{invitation.roles.map((role) => t(title(role))).join(" · ")} · {t("Valid until")} {localizedLongDate(invitation.expires_at, locale)}</small></div>
              <button className="icon-button family-remove" onClick={() => revoke(invitation.id)} aria-label={t("Revoke invitation")}><X size={15} /></button>
            </article>
          ))}</div>
        ) : <div className="family-empty"><CheckCircle2 size={20} /><span>{t("No pending invitations")}</span></div>}
      </section>

      {editing && (
        <StaffAccessEditor
          member={editing === "new" ? null : editing}
          directory={data}
          onClose={() => setEditing(null)}
          onSaved={() => {
            const created = editing === "new";
            setEditing(null);
            resource.reload();
            notify(t(created ? "Invitation sent" : "Access updated"));
          }}
        />
      )}
    </div>
  );
}

function StaffAccessEditor({ member, directory, onClose, onSaved }: { member: StaffMember | null; directory: StaffDirectory; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const roles = Object.keys(directory.role_presets).filter((role) => role !== "super_admin");
  const [email, setEmail] = useState(member?.email ?? "");
  const [role, setRole] = useState(member?.roles.find((value) => value !== "super_admin") ?? "support");
  const [permissions, setPermissions] = useState<string[]>(member?.permissions ?? []);
  const [reason, setReason] = useState("Обновление обязанностей оператора");
  const [advanced, setAdvanced] = useState(Boolean(member?.permissions.length));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preset = new Set(directory.role_presets[role] ?? []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { roles: [role], permissions, ...(member ? { reason } : { email }) };
      await api(member ? `/admin/staff/${member.user_id}` : "/admin/staff/invitations", {
        method: member ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("Unable to save access"));
    } finally {
      setBusy(false);
    }
  };

  const togglePermission = (permission: string) => {
    setPermissions((current) => current.includes(permission)
      ? current.filter((item) => item !== permission)
      : [...current, permission]);
  };

  return (
    <div className="modal-layer">
      <button className="modal-scrim" onClick={onClose} aria-label={t("Close")} />
      <form className="modal staff-editor" onSubmit={submit}>
        <header>
          <div><p className="overline">{t(member ? "Access policy" : "Secure invitation")}</p><h2>{t(member ? "Edit operator access" : "Invite a new operator")}</h2></div>
          <button type="button" className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button>
        </header>
        {!member && <label className="field-label">{t("Work email")}<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="operator@hazdeen.xyz" required /></label>}
        <fieldset className="role-picker">
          <legend>{t("Role preset")}</legend>
          {roles.map((value) => (
            <label className={role === value ? "active" : ""} key={value}>
              <input type="radio" name="staff-role" value={value} checked={role === value} onChange={() => setRole(value)} />
              <span className={`role-orb role-${value}`}><ShieldCheck size={16} /></span>
              <span><b>{t(title(value))}</b><small>{directory.role_presets[value]?.length ?? 0} {t("permissions")}</small></span><Check size={15} />
            </label>
          ))}
        </fieldset>
        <button className="advanced-toggle" type="button" onClick={() => setAdvanced((value) => !value)}><Settings size={15} /> {t("Individual permissions")}<span>{advanced ? "−" : "+"}</span></button>
        {advanced && (
          <div className="permission-grid">
            {directory.available_permissions.filter((permission) => permission !== "staff.manage").map((permission) => (
              <label className={preset.has(permission) ? "preset" : ""} key={permission}>
                <input type="checkbox" disabled={preset.has(permission)} checked={preset.has(permission) || permissions.includes(permission)} onChange={() => togglePermission(permission)} />
                <span><b>{t(title(permission.replace(".", " ")))}</b><small>{preset.has(permission) ? t("Included in role") : t("Additional grant")}</small></span>
              </label>
            ))}
          </div>
        )}
        {member && <label className="field-label">{t("Audit reason")}<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required /></label>}
        {error && <div className="inline-error">{error}</div>}
        <footer><button type="button" className="quiet-button" onClick={onClose}>{t("Cancel")}</button><button className="primary-button" disabled={busy}>{busy && <LoaderCircle className="spin" size={15} />}{t(member ? "Save access" : "Send invitation")}</button></footer>
      </form>
    </div>
  );
}

const title = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
const initials = (email: string) => email.split("@")[0].split(/[._-]/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
const localizedLongDate = (value: string, locale: "en" | "ru") => new Date(value).toLocaleDateString(locale === "ru" ? "ru-RU" : "en", { day: "2-digit", month: "short", year: "numeric" });
