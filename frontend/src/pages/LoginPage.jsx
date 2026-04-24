import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Loader2, ArrowRight } from "lucide-react";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("creator@facelessforge.io");
  const [password, setPassword] = useState("creator123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await login(email, password);
    setLoading(false);
    if (res.ok) navigate("/app");
    else setError(res.error);
  };

  return (
    <div className="min-h-screen ff-grid bg-[#0A0A0A] text-white flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        <div className="mb-10 text-center">
          <div className="inline-flex items-center gap-3 mb-6">
            <div
              className="w-10 h-10 flex items-center justify-center bg-[#00E5FF] text-black font-black font-mono text-xl"
              style={{ clipPath: "polygon(0 0, 100% 0, 100% 70%, 85% 100%, 0 100%)" }}
            >
              F
            </div>
            <span className="text-xl font-semibold tracking-tight">FacelessForge</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
            Sign in to your studio
          </h1>
          <p className="text-sm text-zinc-400">
            Turn any idea into a YouTube-ready content package.
          </p>
        </div>

        <form onSubmit={submit} data-testid="login-form" className={`border border-zinc-800 bg-[#121212] p-7 rounded-sm space-y-5 ${error ? "ff-shake" : ""}`}>
          <div className="space-y-2">
            <label className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">Email</label>
            <input
              data-testid="login-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-[#0A0A0A] border border-zinc-800 px-3 py-2.5 text-sm rounded-sm focus:border-[#00E5FF]"
              autoComplete="email"
            />
          </div>
          <div className="space-y-2">
            <label className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">Password</label>
            <input
              data-testid="login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#0A0A0A] border border-zinc-800 px-3 py-2.5 text-sm rounded-sm focus:border-[#00E5FF]"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div data-testid="login-error" className="text-[#FF3366] text-sm font-mono">
              {error}
            </div>
          )}

          <button
            data-testid="login-submit"
            type="submit"
            disabled={loading}
            className="w-full bg-[#00E5FF] text-black font-semibold text-sm py-2.5 rounded-sm hover:bg-[#33EFFF] disabled:opacity-60 flex items-center justify-center gap-2 transition-colors"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} strokeWidth={2} />}
            {loading ? "Signing in" : "Sign in"}
          </button>

          <div className="pt-2 border-t border-zinc-800 text-center">
            <span className="text-xs text-zinc-500">New here? </span>
            <Link to="/register" className="text-xs text-[#00E5FF] hover:text-[#33EFFF]" data-testid="goto-register">
              Create an account
            </Link>
          </div>

          <div className="pt-3 text-[10px] font-mono text-zinc-600 text-center tracking-wider">
            DEMO · creator@facelessforge.io / creator123
          </div>
        </form>
      </div>
    </div>
  );
}
