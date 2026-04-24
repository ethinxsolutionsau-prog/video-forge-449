import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Sparkles, Zap, Download, Layers } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white">
      <div className="ff-grid min-h-screen">
        <header className="flex items-center justify-between px-8 py-5 border-b border-zinc-800 bg-[#0A0A0A]/80 backdrop-blur">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 flex items-center justify-center bg-[#00E5FF] text-black font-black font-mono text-lg"
              style={{ clipPath: "polygon(0 0, 100% 0, 100% 70%, 85% 100%, 0 100%)" }}
            >
              F
            </div>
            <span className="font-semibold tracking-tight">FacelessForge</span>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" data-testid="landing-login" className="text-sm text-zinc-400 hover:text-white">Sign in</Link>
            <Link to="/register" data-testid="landing-register" className="bg-[#00E5FF] text-black font-semibold text-sm px-4 py-2 rounded-sm hover:bg-[#33EFFF] transition-colors flex items-center gap-2">
              Get started <ArrowRight size={14} strokeWidth={2} />
            </Link>
          </div>
        </header>

        <section className="max-w-5xl mx-auto px-8 py-24 md:py-32">
          <div className="font-mono text-[11px] tracking-[0.2em] text-[#00E5FF] uppercase mb-6 ff-rise">
            ▌ Creator Operations · v1
          </div>
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.05] max-w-4xl ff-rise ff-rise-1">
            Turn any idea into a
            <span className="block text-[#00E5FF]">YouTube-ready content package.</span>
          </h1>
          <p className="mt-8 max-w-2xl text-zinc-400 text-base md:text-lg leading-relaxed ff-rise ff-rise-2">
            FacelessForge is the control room for faceless YouTube creators.
            One prompt becomes your hook, script, scene plan, metadata, and thumbnail concepts — scored, tracked,
            and exportable in seconds.
          </p>
          <div className="mt-10 flex items-center gap-3 ff-rise ff-rise-3">
            <Link to="/register" data-testid="hero-register" className="bg-[#00E5FF] text-black font-semibold text-sm px-5 py-3 rounded-sm hover:bg-[#33EFFF] transition-colors flex items-center gap-2">
              Start forging <ArrowRight size={14} strokeWidth={2} />
            </Link>
            <Link to="/login" data-testid="hero-demo" className="border border-zinc-800 text-white text-sm px-5 py-3 rounded-sm hover:border-[#00E5FF] hover:text-[#00E5FF] transition-colors">
              Try demo creator
            </Link>
          </div>

          <div className="mt-20 grid grid-cols-1 md:grid-cols-4 gap-4">
            {[
              { icon: Sparkles, title: "Generate", body: "GPT-5.2 writes hooks, scripts, scenes, and metadata tuned to your niche." },
              { icon: Layers, title: "Orchestrate", body: "Every project moves through a visible 8-step production pipeline." },
              { icon: Zap, title: "Score", body: "0–100 quality score shows exactly what's missing before publish." },
              { icon: Download, title: "Export", body: "Download TXT, CSV, JSON, or a full ZIP package. Your content stays yours." },
            ].map((f, i) => (
              <div
                key={f.title}
                className="border border-zinc-800 bg-[#121212] p-5 rounded-sm ff-rise"
                style={{ animationDelay: `${200 + i * 60}ms` }}
              >
                <f.icon size={18} strokeWidth={1.5} color="#00E5FF" />
                <div className="mt-4 font-semibold text-sm">{f.title}</div>
                <div className="mt-2 text-xs text-zinc-400 leading-relaxed">{f.body}</div>
              </div>
            ))}
          </div>
        </section>

        <footer className="border-t border-zinc-800 px-8 py-6 font-mono text-[11px] text-zinc-600 uppercase tracking-widest">
          FacelessForge · creator operations · dark mode first
        </footer>
      </div>
    </div>
  );
}
