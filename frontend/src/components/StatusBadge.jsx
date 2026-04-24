import React from "react";
import { STATUS_META } from "../lib/format";

export default function StatusBadge({ status, className = "" }) {
  const meta = STATUS_META[status] || STATUS_META.DRAFT;
  return (
    <span
      data-testid={`status-badge-${status?.toLowerCase() || "draft"}`}
      className={`font-mono text-[10px] px-2 py-1 rounded-sm border inline-flex items-center gap-1.5 uppercase tracking-[0.12em] ${className}`}
      style={{
        color: meta.color,
        backgroundColor: meta.bg,
        borderColor: meta.color + "33",
      }}
    >
      <span className="ff-dot" />
      {meta.label}
    </span>
  );
}
