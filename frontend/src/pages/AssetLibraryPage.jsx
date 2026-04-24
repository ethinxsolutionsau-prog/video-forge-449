import React, { useEffect, useState } from "react";
import AppShell from "../components/AppShell";
import TopBar from "../components/TopBar";
import { api } from "../lib/api";
import { Link } from "react-router-dom";
import { Boxes } from "lucide-react";

export default function AssetLibraryPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [details, setDetails] = useState({});

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/projects");
        setProjects(data);
        const results = await Promise.all(
          data.map((p) => api.get(`/projects/${p.id}`).then((r) => [p.id, r.data]).catch(() => [p.id, null]))
        );
        const map = {};
        results.forEach(([id, v]) => { if (v) map[id] = v; });
        setDetails(map);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <AppShell>
        <TopBar title="Asset Library" />
        <div className="p-8 text-sm text-zinc-500 font-mono">Loading…</div>
      </AppShell>
    );
  }

  const allAssets = [];
  Object.entries(details).forEach(([pid, v]) => {
    (v.assets || []).forEach((a) => allAssets.push({ ...a, projectName: v.project.name, projectId: pid }));
  });

  return (
    <AppShell>
      <TopBar title="Asset Library" subtitle={`${allAssets.length} items`} />
      <div className="p-8 space-y-6">
        {allAssets.length === 0 ? (
          <div className="border border-zinc-800 border-dashed p-10 text-center rounded-sm">
            <Boxes size={24} strokeWidth={1.2} className="mx-auto mb-3 text-zinc-500" />
            <p className="text-sm text-zinc-400">No assets yet. Generate thumbnail concepts inside a project.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {allAssets.map((a) => (
              <Link key={a.id} to={`/app/projects/${a.projectId}`} className="border border-zinc-800 bg-[#121212] p-5 rounded-sm ff-card-hover">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-[#7B61FF]">{a.asset_type.replace(/_/g, " ")}</span>
                  <span className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">{a.status}</span>
                </div>
                <h4 className="text-sm font-semibold mb-2">{a.name}</h4>
                <div className="text-xs text-zinc-500">{a.projectName}</div>
                {a.brief?.thumbnail_title_text && (
                  <div className="mt-3 pt-3 border-t border-zinc-800 text-xs text-zinc-300">
                    "{a.brief.thumbnail_title_text}"
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
