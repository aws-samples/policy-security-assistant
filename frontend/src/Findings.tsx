import { useState } from "react";

export interface Finding {
  type: string;       // ERROR, SECURITY_WARNING, WARNING, SUGGESTION
  issueCode: string;
  details: string;
  learnMoreLink?: string;
  path?: string;
}

const TYPE_CONFIG: Record<string, { label: string; className: string }> = {
  ERROR: { label: "Error", className: "finding-error" },
  SECURITY_WARNING: { label: "Security Warning", className: "finding-security" },
  WARNING: { label: "Warning", className: "finding-warning" },
  SUGGESTION: { label: "Suggestion", className: "finding-suggestion" },
};

export default function Findings({ findings }: { findings: Finding[] }) {
  if (!findings || findings.length === 0) {
    return (
      <div className="findings-panel findings-clean">
        <span className="findings-badge finding-clean">✓ No issues</span>
        <span>IAM Access Analyzer found no issues with this policy.</span>
      </div>
    );
  }

  const counts = findings.reduce<Record<string, number>>((acc, f) => {
    acc[f.type] = (acc[f.type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="findings-panel">
      <div className="findings-header">
        <span className="findings-title">IAM Access Analyzer</span>
        <div className="findings-badges">
          {Object.entries(counts).map(([type, count]) => {
            const cfg = TYPE_CONFIG[type] || { label: type, className: "finding-suggestion" };
            return (
              <span key={type} className={`findings-badge ${cfg.className}`}>
                {count} {cfg.label}{count > 1 ? "s" : ""}
              </span>
            );
          })}
        </div>
      </div>
      <ul className="findings-list">
        {findings.map((f, i) => (
          <FindingItem key={i} finding={f} />
        ))}
      </ul>
    </div>
  );
}

function FindingItem({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  const cfg = TYPE_CONFIG[finding.type] || { label: finding.type, className: "finding-suggestion" };

  return (
    <li className="finding-item">
      <button className="finding-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`findings-badge ${cfg.className}`}>{cfg.label}</span>
        <span className="finding-summary">{finding.details}</span>
        <span className="finding-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="finding-details">
          {finding.path && (
            <div className="finding-path">
              <span className="finding-detail-label">Location:</span> <code>{finding.path}</code>
            </div>
          )}
          {finding.issueCode && (
            <div className="finding-code">
              <span className="finding-detail-label">Issue:</span> {finding.issueCode}
            </div>
          )}
          {finding.learnMoreLink && (
            <a href={finding.learnMoreLink} target="_blank" rel="noopener noreferrer"
              className="finding-link">
              Learn more →
            </a>
          )}
        </div>
      )}
    </li>
  );
}
