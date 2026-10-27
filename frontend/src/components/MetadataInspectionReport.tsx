import type { InspectionCheck } from "../api/inspection";
import { Icon } from "./Icon";
import "../styles/metadata-inspection.css";

export function MetadataInspectionReport({ message, checks }: { message: string; checks: InspectionCheck[] }) {
  return <div className="metadata-inspection-report" role="status">
    <strong>{message}</strong>
    <div>{checks.map((check) => <div className={check.ok ? "inspection-item" : "inspection-item inspection-item--warning"} key={check.label}>
      <Icon name={check.ok ? "check" : "alert"} size={14} />
      <span>{check.label}<strong>{check.detail}</strong></span>
    </div>)}</div>
  </div>;
}
