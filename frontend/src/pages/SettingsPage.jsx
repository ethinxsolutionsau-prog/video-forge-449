import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Save } from "lucide-react";
import AppShell from "../components/AppShell";
import TopBar from "../components/TopBar";
import { api, formatApiError } from "../lib/api";

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/settings");
        setSettings(data);
      } catch {/* ignore */}
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.patch("/settings", {
        default_tone: settings.default_tone,
        default_visual_style: settings.default_visual_style,
        cost_limit_monthly: Number(settings.cost_limit_monthly),
        preferred_provider: settings.preferred_provider,
      });
      setSettings(data);
      toast.success("Settings saved");
    } catch (err) {
      toast.error("Save failed", { description: formatApiError(err.response?.data?.detail) || err.message });
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <AppShell>
        <TopBar title="Settings" />
        <div className="p-8 text-sm text-zinc-500 font-mono">Loading…</div>
      </AppShell>
    );
  }

  const inp = "w-full bg-[#0A0A0A] border border-zinc-800 px-3 py-2.5 text-sm rounded-sm focus:border-[#00E5FF]";
  const L = ({ children }) => (
    <label className="font-mono text-[10px] uppercase tracking-widest text-zinc-500 mb-2 block">{children}</label>
  );

  return (
    <AppShell>
      <TopBar title="Settings" subtitle="Studio configuration" />
      <div className="p-8 max-w-3xl space-y-6">
        <div className="border border-zinc-800 bg-[#121212] p-6 rounded-sm space-y-5">
          <h3 className="text-sm font-semibold text-white mb-2">AI provider</h3>
          <div>
            <L>Preferred provider</L>
            <select
              data-testid="setting-provider"
              value={settings.preferred_provider}
              onChange={(e) => setSettings({ ...settings, preferred_provider: e.target.value })}
              className={inp + " font-mono uppercase text-xs"}
            >
              <option value="openai/gpt-5.2">openai / gpt-5.2</option>
              <option value="openai/gpt-5.1">openai / gpt-5.1</option>
              <option value="anthropic/claude-sonnet-4-5-20250929">anthropic / claude-sonnet-4.5</option>
              <option value="gemini/gemini-3-flash-preview">gemini / 3-flash-preview</option>
            </select>
            <p className="font-mono text-[10px] text-zinc-600 mt-2">
              Generation falls back to deterministic output if the provider is unavailable.
            </p>
          </div>
          <div>
            <L>Monthly cost limit (USD)</L>
            <input
              data-testid="setting-cost-limit"
              type="number"
              value={settings.cost_limit_monthly}
              onChange={(e) => setSettings({ ...settings, cost_limit_monthly: e.target.value })}
              className={inp + " font-mono"}
            />
          </div>
        </div>

        <div className="border border-zinc-800 bg-[#121212] p-6 rounded-sm space-y-5">
          <h3 className="text-sm font-semibold text-white mb-2">Defaults</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <L>Default tone</L>
              <input
                data-testid="setting-tone"
                value={settings.default_tone}
                onChange={(e) => setSettings({ ...settings, default_tone: e.target.value })}
                className={inp}
              />
            </div>
            <div>
              <L>Default visual style</L>
              <input
                data-testid="setting-visual"
                value={settings.default_visual_style}
                onChange={(e) => setSettings({ ...settings, default_visual_style: e.target.value })}
                className={inp}
              />
            </div>
          </div>
        </div>

        <button
          data-testid="save-settings-btn"
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 bg-[#00E5FF] text-black font-semibold text-sm px-5 py-2.5 rounded-sm hover:bg-[#33EFFF] disabled:opacity-60 transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} strokeWidth={2} />}
          Save settings
        </button>
      </div>
    </AppShell>
  );
}
