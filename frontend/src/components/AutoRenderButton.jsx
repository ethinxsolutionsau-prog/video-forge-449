import React, { useState } from "react";
import { toast } from "sonner";
import { Film, Loader2, CheckCircle2, AlertCircle, Download, ChevronDown, ChevronRight } from "lucide-react";
import { api, formatApiError } from "../lib/api";

/**
 * Single-click render orchestrator wired to the backend /render/auto endpoint.
 *
 * The endpoint runs the full ETHINX-style automation loop server-side
 * (auto-attach assets → auto-voiceover → preflight gate → queue render).
 * This component renders the action, the decision trace it returns, and
 * polls the resulting render job until completion or failure.
 */
export default function AutoRenderButton({ projectId, project, renderJob, canEdit, onChange }) {
  const [running, setRunning] = useState(false);
  const [decisions, setDecisions] = useState([]);
  const [jobId, setJobId] = useState(null);
  const [jobState, setJobState] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(true);

  const pollJob = async (id) => {
    let last = null;
    for (let i = 0; i < 90; i++) {
      try {
        const { data } = await api.get(`/projects/${projectId}/render/jobs/${id}`);
        last = data;
        setJobState(data);
        if (["completed", "failed", "cancelled", "expired_artifact"].includes(data.status)) {
          break;
        }
      } catch {/* keep polling on transient errors */}
      await new Promise((r) => setTimeout(r, 2500));
    }
    onChange?.();
    return last;
  };

  const run = async () => {
    setRunning(true);
    setDecisions([]);
    setJobId(null);
    setJobState(null);
    setError(null);
    setExpanded(true);
    toast.loading("Starting one-click render…", { id: "auto-render" });
    try {
      const { data } = await api.post(`/projects/${projectId}/render/auto`);
      setDecisions(data.decisions || []);
      setJobId(data.job?.id || null);
      setJobState(data.job || null);
      toast.success("Render queued — preparing artefacts", { id: "auto-render" });
      if (data.job?.id) {
        const final = await pollJob(data.job.id);
        if (final?.status === "completed") {
          toast.success("Render complete · MP4 ready", { id: "auto-render" });
        } else if (final?.status === "failed") {
          toast.error(`Render failed: ${final.error_message || "see logs"}`, { id: "auto-render" });
        }
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      // Backend may return either a string or a structured {message, blockers, decisions}
      if (detail && typeof detail === "object") {
        setError(detail);
        setDecisions(detail.decisions || []);
      }
      toast.error("Auto-render aborted", {
        id: "auto-render",
        description: typeof detail === "string" ? detail : detail?.message || err.message,
      });
    } finally {
      setRunning(false);
    }
  };

  const completed = jobState?.status === "completed" && jobState?.output_url;
  const failed = jobState?.status === "failed" || error;
  const inProgress = running || ["queued", "validating", "preparing_assets", "rendering"].includes(jobState?.status);

  const hasExistingRender = renderJob?.status === "completed" && renderJob?.output_url;

  return (
    <div
      data-testid="auto-render-card"
      className="border border-zinc-800 bg-[#121212] rounded-sm overflow-hidden"
    >
      <div className="p-5 flex items-center justify-between gap-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <Film size={16} className="text-[#00E5FF]" strokeWidth={1.8} />
          <div>
            <div className="text-sm font-semibold text-white">One-click render</div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mt-0.5">
              Auto-attach · auto-voiceover · preflight · queue
            </div>
          </div>
        </div>
        {canEdit && (
          <button
            data-testid="auto-render-btn"
            disabled={running || inProgress}
            onClick={run}
            className="flex items-center gap-2 bg-[#00E5FF] text-black font-semibold text-sm px-4 py-2.5 rounded-sm hover:bg-[#33EFFF] disabled:opacity-60 transition-colors"
          >
            {inProgress ? <Loader2 size={14} className="animate-spin" /> : <span className="text-base leading-none">🎬</span>}
            {inProgress ? (jobState?.current_step?.replace(/_/g, " ") || "Working…") : (hasExistingRender ? "Render again" : "Render now")}
          </button>
        )}
      </div>

      {/* Trace */}
      {decisions.length > 0 && (
        <div className="border-b border-zinc-800">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="w-full px-5 py-2.5 flex items-center justify-between text-left hover:bg-[#161616] transition-colors"
            data-testid="auto-render-trace-toggle"
          >
            <span className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">
              Decision trace · {decisions.length} step{decisions.length === 1 ? "" : "s"}
            </span>
            {expanded ? <ChevronDown size={12} className="text-zinc-500" /> : <ChevronRight size={12} className="text-zinc-500" />}
          </button>
          {expanded && (
            <div className="px-5 pb-4 space-y-2" data-testid="auto-render-trace">
              {decisions.map((d) => (
                <div key={`iter-${d.iteration}`} className="flex items-start gap-3 text-xs">
                  <span
                    className="font-mono text-[10px] uppercase tracking-widest mt-0.5"
                    style={{ color: d.preflight_ok ? "#00FF66" : "#FFB020" }}
                  >
                    {d.preflight_ok ? "OK" : `#${d.iteration}`}
                  </span>
                  <div className="flex-1">
                    {d.preflight_ok ? (
                      <span className="text-[#00FF66]">Preflight green — render queued</span>
                    ) : d.remediation ? (
                      <span className="text-zinc-300">
                        <span className="text-[#FFB020]">{d.issues?.join(" · ") || "issues"}</span>
                        <span className="text-zinc-500"> → </span>
                        <span className="text-[#00E5FF]">{d.remediation.type}</span>
                        <span className="text-zinc-500"> ({formatSummary(d.remediation.summary)})</span>
                      </span>
                    ) : (
                      <span className="text-[#FF3366]">Blocked: {d.issues?.join(" · ")}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Live job progress */}
      {(inProgress || jobState) && !completed && !failed && (
        <div className="px-5 py-4 space-y-2" data-testid="auto-render-progress">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-widest">
            <span className="text-zinc-500">{jobState?.current_step?.replace(/_/g, " ") || "queued"}</span>
            <span className="text-[#00E5FF]">{jobState?.progress ?? 0}%</span>
          </div>
          <div className="h-1.5 bg-[#0A0A0A] border border-zinc-800 overflow-hidden rounded-sm">
            <div
              className="h-full bg-[#00E5FF] transition-all"
              style={{ width: `${jobState?.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Final result */}
      {completed && (
        <div className="px-5 py-4 space-y-3" data-testid="auto-render-result-ok">
          <div className="flex items-center gap-2 text-[#00FF66]">
            <CheckCircle2 size={14} strokeWidth={2} />
            <span className="font-mono text-[10px] uppercase tracking-widest">
              MP4 ready · {Math.round(jobState.duration || 0)}s
            </span>
          </div>
          <video
            controls
            src={jobState.output_url}
            preload="metadata"
            className="w-full rounded-sm border border-zinc-800 bg-black aspect-video"
          />
          <a
            href={jobState.output_url}
            download
            data-testid="auto-render-download"
            className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-zinc-300 hover:text-[#00E5FF] border border-zinc-800 hover:border-[#00E5FF] px-2 py-1.5 rounded-sm transition-colors"
          >
            <Download size={12} /> Download MP4
          </a>
        </div>
      )}

      {failed && (
        <div className="px-5 py-4" data-testid="auto-render-result-error">
          <div className="flex items-start gap-2 text-[#FF3366]">
            <AlertCircle size={14} className="mt-0.5" />
            <div className="text-xs">
              <div className="font-mono uppercase tracking-widest text-[10px]">Render failed</div>
              <div className="text-zinc-300 mt-1">
                {jobState?.error_message ||
                  (error && (typeof error === "object" ? error.message : error)) ||
                  "Unknown error"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatSummary(s) {
  if (!s) return "";
  if (s.attached !== undefined) {
    return `${s.attached}/${s.total} attached${s.mock ? " · mock" : ""}`;
  }
  if (s.asset_id) {
    return `${s.duration ?? "?"}s · ${s.provider}${s.mock ? " · mock" : ""}`;
  }
  try {
    return JSON.stringify(s);
  } catch {
    return "";
  }
}
