import React, { useState } from "react";
import { toast } from "sonner";
import { Sparkles, Loader2 } from "lucide-react";
import { api, formatApiError } from "../lib/api";

export default function ThumbnailPanel({ projectId, assets, canEdit, onChange }) {
  const [generating, setGenerating] = useState(false);
  const concepts = (assets || []).filter((a) => a.asset_type === "thumbnail_concept" && a.brief);

  const generate = async () => {
    setGenerating(true);
    toast.loading("Generating thumbnail concepts…", { id: "gen-thumb" });
    try {
      const { data } = await api.post(`/projects/${projectId}/generate-thumbnails`);
      onChange(data);
      toast.success("Thumbnail concepts ready", { id: "gen-thumb" });
    } catch (err) {
      toast.error("Generation failed", { id: "gen-thumb", description: formatApiError(err.response?.data?.detail) || err.message });
    } finally {
      setGenerating(false);
    }
  };

  const Row = ({ label, value }) => (
    <div className="grid grid-cols-[120px_1fr] gap-3 text-sm">
      <span className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 pt-0.5">{label}</span>
      <span className="text-zinc-200 leading-relaxed">{value}</span>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[11px] text-zinc-500">
          {concepts.length} thumbnail concepts
        </div>
        {canEdit && (
          <button
            data-testid="generate-thumbnails-btn"
            onClick={generate}
            disabled={generating}
            className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-zinc-400 hover:text-[#00E5FF] border border-zinc-800 hover:border-[#00E5FF] px-2 py-1 rounded-sm transition-colors disabled:opacity-50"
          >
            {generating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} strokeWidth={1.5} />}
            {concepts.length ? "Regenerate" : "Generate"}
          </button>
        )}
      </div>

      {concepts.length === 0 ? (
        <div className="border border-zinc-800 border-dashed p-10 text-center rounded-sm">
          <p className="text-sm text-zinc-400">No thumbnail concepts yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {concepts.map((a, i) => {
            const b = a.brief;
            return (
              <div key={a.id} className="border border-zinc-800 bg-[#121212] rounded-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-zinc-800 bg-[#0A0A0A]">
                  <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Concept · {String(i + 1).padStart(2, "0")}
                  </div>
                  <div className="text-2xl font-bold tracking-tight text-white">{b.thumbnail_title_text}</div>
                </div>
                <div className="p-5 space-y-3">
                  <Row label="Composition" value={b.visual_composition} />
                  <Row label="Emotion" value={b.emotion_angle} />
                  <Row label="Background" value={b.background_idea} />
                  <Row label="Focal point" value={b.subject_focal_point} />
                  <Row label="Colour" value={b.colour_direction} />
                  <Row label="Click trigger" value={b.click_trigger} />
                  <div className="pt-3 border-t border-zinc-800">
                    <div className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mb-1">Image prompt</div>
                    <div className="font-mono text-xs text-[#7B61FF] leading-relaxed">{b.image_prompt}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
