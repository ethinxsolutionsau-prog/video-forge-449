import React, { useState } from "react";
import { toast } from "sonner";
import { Play, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { api, formatApiError, API } from "../lib/api";

const STEPS = [
  { key: "draft", label: "Draft" },
  { key: "script", label: "Script" },
  { key: "scenes", label: "Scenes" },
  { key: "metadata", label: "Metadata" },
  { key: "assets", label: "Assets" },
  { key: "ready", label: "Ready to Render" },
  { key: "completed", label: "Completed" },
];

export default function RenderPanel({ projectId, project, script, scenes, metadata, assets, renderJob, canEdit, onChange }) {
  const [running, setRunning] = useState(false);

  const done = {
    draft: true,
    script: !!script,
    scenes: (scenes || []).length > 0,
    metadata: !!metadata,
    assets: (assets || []).length > 0,
    ready: (project.status === "READY_TO_RENDER" || project.status === "COMPLETED"),
    completed: project.status === "COMPLETED",
  };

  const prepare = async () => {
    setRunning(true);
    toast.loading("Preparing render pipeline…", { id: "render" });
    try {
      const { data } = await api.post(`/projects/${projectId}/render`);
      onChange(data);
      if (data.render_job?.status === "FAILED") {
        toast.error("Render validation failed", { id: "render", description: data.render_job.error_message });
      } else {
        toast.success(`Render ${data.render_job?.status}`, { id: "render" });
      }
    } catch (err) {
      toast.error("Failed", { id: "render", description: formatApiError(err.response?.data?.detail) || err.message });
    } finally {
      setRunning(false);
    }
  };

  const exportZip = () => {
    window.open(`${API}/projects/${projectId}/export/package.zip`, "_blank");
  };

  return (
    <div className="space-y-6">
      {/* Pipeline steps */}
      <div className="border border-zinc-800 bg-[#121212] p-6 rounded-sm">
        <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mb-5">Production pipeline</div>
        <div className="grid grid-cols-7 gap-2">
          {STEPS.map((s, i) => {
            const isDone = done[s.key];
            const isCurrent = !isDone && (i === 0 || done[STEPS[i - 1].key]);
            const color = isDone ? "#00FF66" : isCurrent ? "#00E5FF" : "#27272A";
            return (
              <div key={s.key} className="flex flex-col items-center gap-2">
                <div
                  className="w-full h-1"
                  style={{ background: color, boxShadow: isDone ? "0 0 10px " + color : "none" }}
                />
                <div className="text-[10px] font-mono uppercase tracking-widest text-center" style={{ color: isDone ? "#fff" : "#71717A" }}>
                  {s.label}
                </div>
                {isDone ? (
                  <CheckCircle2 size={14} strokeWidth={1.8} color="#00FF66" />
                ) : isCurrent ? (
                  <span className="ff-dot" style={{ color: "#00E5FF" }} />
                ) : (
                  <span className="w-3.5 h-3.5 border border-zinc-700 rounded-full" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Render job status */}
      {renderJob && (
        <div
          className="border p-5 rounded-sm"
          style={{
            borderColor: renderJob.status === "FAILED" ? "#FF336633" : "#00FF6633",
            background: renderJob.status === "FAILED" ? "rgba(255,51,102,0.05)" : "rgba(0,255,102,0.03)",
          }}
        >
          <div className="flex items-start gap-3">
            {renderJob.status === "FAILED" ? (
              <AlertCircle size={18} strokeWidth={1.5} color="#FF3366" className="mt-0.5" />
            ) : (
              <CheckCircle2 size={18} strokeWidth={1.5} color="#00FF66" className="mt-0.5" />
            )}
            <div className="flex-1">
              <div className="font-mono text-[11px] uppercase tracking-widest mb-1" style={{ color: renderJob.status === "FAILED" ? "#FF3366" : "#00FF66" }}>
                Render job · {renderJob.status}
              </div>
              {renderJob.error_message ? (
                <div className="text-sm text-zinc-300">{renderJob.error_message}</div>
              ) : (
                <div className="text-sm text-zinc-300">
                  Progress {renderJob.progress}% · step: <span className="font-mono text-[#00E5FF]">{renderJob.current_step}</span>
                </div>
              )}
              {renderJob.output_path && (
                <div className="mt-2 font-mono text-[11px] text-zinc-500">output: {renderJob.output_path}</div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {canEdit && (
          <button
            data-testid="prepare-render-btn"
            onClick={prepare}
            disabled={running}
            className="flex items-center gap-2 bg-[#00E5FF] text-black font-semibold text-sm px-5 py-2.5 rounded-sm hover:bg-[#33EFFF] disabled:opacity-60 transition-colors"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} strokeWidth={2} />}
            {running ? "Preparing…" : "Prepare Render"}
          </button>
        )}
        <button
          data-testid="export-package-zip"
          onClick={exportZip}
          className="flex items-center gap-2 border border-zinc-800 text-white text-sm px-5 py-2.5 rounded-sm hover:border-[#00E5FF] hover:text-[#00E5FF] transition-colors"
        >
          Export package (ZIP)
        </button>
      </div>
    </div>
  );
}
