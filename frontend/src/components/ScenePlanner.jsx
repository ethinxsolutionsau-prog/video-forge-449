import React, { useState } from "react";
import { toast } from "sonner";
import { Sparkles, Loader2, Download } from "lucide-react";
import { api, formatApiError, API } from "../lib/api";
import { formatDuration } from "../lib/format";

export default function ScenePlanner({ projectId, scenes, canEdit, onChange, hasScript }) {
  const [generating, setGenerating] = useState(false);

  const generate = async () => {
    setGenerating(true);
    toast.loading("Generating scene plan…", { id: "gen-scenes" });
    try {
      const { data } = await api.post(`/projects/${projectId}/generate-scenes`);
      onChange(data);
      toast.success("Scenes generated", { id: "gen-scenes" });
    } catch (err) {
      toast.error("Generation failed", { id: "gen-scenes", description: formatApiError(err.response?.data?.detail) || err.message });
    } finally {
      setGenerating(false);
    }
  };

  const exportCsv = () => {
    window.open(`${API}/projects/${projectId}/export/scenes.csv`, "_blank");
  };

  if (!scenes || scenes.length === 0) {
    return (
      <div className="border border-zinc-800 border-dashed p-10 text-center rounded-sm">
        <p className="text-sm text-zinc-400 mb-4">
          {hasScript ? "No scene plan yet. Generate one from the script." : "Generate a script first, then break it into scenes."}
        </p>
        {canEdit && hasScript && (
          <button
            data-testid="generate-scenes-btn"
            onClick={generate}
            disabled={generating}
            className="inline-flex items-center gap-2 bg-[#00E5FF] text-black font-semibold text-sm px-4 py-2 rounded-sm hover:bg-[#33EFFF] disabled:opacity-60 transition-colors"
          >
            {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} strokeWidth={2} />}
            {generating ? "Generating…" : "Generate Scenes"}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[11px] text-zinc-500">
          {scenes.length} scenes · total {formatDuration(scenes[scenes.length - 1]?.end_time || 0)}
        </div>
        <div className="flex items-center gap-2">
          <button
            data-testid="export-scenes-csv"
            onClick={exportCsv}
            className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-zinc-400 hover:text-[#00E5FF] border border-zinc-800 hover:border-[#00E5FF] px-2 py-1 rounded-sm transition-colors"
          >
            <Download size={12} strokeWidth={1.5} /> CSV
          </button>
          {canEdit && (
            <button
              data-testid="regenerate-scenes-btn"
              onClick={generate}
              disabled={generating}
              className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-zinc-400 hover:text-[#00E5FF] border border-zinc-800 hover:border-[#00E5FF] px-2 py-1 rounded-sm transition-colors disabled:opacity-50"
            >
              {generating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} strokeWidth={1.5} />}
              Regenerate
            </button>
          )}
        </div>
      </div>

      <div className="border border-zinc-800 bg-[#121212] rounded-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-800 bg-[#0A0A0A]">
            <tr className="font-mono text-[10px] text-zinc-500 uppercase tracking-widest">
              <th className="text-left px-4 py-3 w-12">#</th>
              <th className="text-left px-4 py-3 w-28">Time</th>
              <th className="text-left px-4 py-3">Narration</th>
              <th className="text-left px-4 py-3 w-64">Visual · asset</th>
              <th className="text-left px-4 py-3 w-56">Caption</th>
            </tr>
          </thead>
          <tbody>
            {scenes.map((s) => (
              <tr key={s.id} className="border-b border-zinc-800 hover:bg-[#1A1A1A] transition-colors align-top">
                <td className="px-4 py-3 font-mono text-[#00E5FF] text-xs">{String(s.scene_number).padStart(2, "0")}</td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-400">
                  {formatDuration(s.start_time)} → {formatDuration(s.end_time)}
                </td>
                <td className="px-4 py-3 text-zinc-200 leading-relaxed">{s.narration_text}</td>
                <td className="px-4 py-3">
                  <div className="text-zinc-300 mb-1">{s.visual_direction}</div>
                  <div className="font-mono text-[10px] uppercase tracking-widest text-[#7B61FF]">
                    {s.asset_type.replace(/_/g, " ")}
                  </div>
                  {s.search_terms?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {s.search_terms.map((t, i) => (
                        <span key={i} className="font-mono text-[10px] px-1.5 py-0.5 border border-zinc-800 text-zinc-400 rounded-sm">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-zinc-300 italic">"{s.caption_text}"</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
