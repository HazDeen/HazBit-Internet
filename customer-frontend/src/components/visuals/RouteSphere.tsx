import { ShieldCheck, WifiOff } from "lucide-react";
import "./route-sphere.css";

interface RouteSphereProps {
  connected?: boolean;
  compact?: boolean;
  label?: string;
}

export function RouteSphere({ connected = true, compact = false, label }: RouteSphereProps) {
  return <div className={`route-sphere ${connected ? "is-connected" : "is-paused"} ${compact ? "is-compact" : ""}`} role="img" aria-label={label ?? (connected ? "VLESS route active" : "VLESS route paused")}>
    <div className="route-sphere__glow" />
    <div className="route-sphere__shell">
      <i className="route-sphere__orbit route-sphere__orbit--one"><b /></i>
      <i className="route-sphere__orbit route-sphere__orbit--two"><b /></i>
      <i className="route-sphere__orbit route-sphere__orbit--three"><b /></i>
      <span className="route-sphere__core">{connected ? <ShieldCheck /> : <WifiOff />}</span>
      <span className="route-sphere__node route-sphere__node--north" />
      <span className="route-sphere__node route-sphere__node--east" />
      <span className="route-sphere__node route-sphere__node--south" />
    </div>
    <span className="route-sphere__shadow" />
  </div>;
}
