import { ShieldCheck, WifiOff } from "lucide-react";

export function CompactRouteSphere({ connected = true, label }: { connected?: boolean; label: string }) {
  return <div className={`compact-sphere ${connected ? "connected" : "paused"}`} role="img" aria-label={label}>
    <div className="compact-sphere__glow" />
    <i className="compact-sphere__orbit compact-sphere__orbit--one"><b /></i>
    <i className="compact-sphere__orbit compact-sphere__orbit--two"><b /></i>
    <span className="compact-sphere__core">{connected ? <ShieldCheck /> : <WifiOff />}</span>
    <span className="compact-sphere__shadow" />
  </div>;
}
