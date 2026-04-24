import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import AppShell from "../components/AppShell";
import TopBar from "../components/TopBar";
import { api, formatApiError } from "../lib/api";

const ROLES = ["admin", "creator", "editor", "viewer"];

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchUsers = async () => {
    try {
      const { data } = await api.get("/admin/users");
      setUsers(data);
    } catch (err) {
      toast.error("Could not load", { description: formatApiError(err.response?.data?.detail) || err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const changeRole = async (id, role) => {
    try {
      await api.patch(`/admin/users/${id}/role`, { role });
      toast.success(`Role updated to ${role}`);
      fetchUsers();
    } catch (err) {
      toast.error("Update failed", { description: formatApiError(err.response?.data?.detail) || err.message });
    }
  };

  return (
    <AppShell>
      <TopBar title="Users" subtitle="Admin console" />
      <div className="p-8 space-y-6">
        {loading ? (
          <div className="text-sm text-zinc-500 font-mono">Loading…</div>
        ) : (
          <div className="border border-zinc-800 bg-[#121212] rounded-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="border-b border-zinc-800 bg-[#0A0A0A]">
                <tr className="font-mono text-[10px] text-zinc-500 uppercase tracking-widest">
                  <th className="text-left px-5 py-3">Name</th>
                  <th className="text-left px-5 py-3">Email</th>
                  <th className="text-left px-5 py-3 w-40">Role</th>
                  <th className="text-left px-5 py-3 w-40">Created</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-zinc-800 hover:bg-[#1A1A1A]">
                    <td className="px-5 py-3">{u.name}</td>
                    <td className="px-5 py-3 font-mono text-xs text-zinc-400">{u.email}</td>
                    <td className="px-5 py-3">
                      <select
                        data-testid={`role-select-${u.id}`}
                        value={u.role}
                        onChange={(e) => changeRole(u.id, e.target.value)}
                        className="bg-[#0A0A0A] border border-zinc-800 px-2 py-1 text-xs font-mono uppercase rounded-sm"
                      >
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className="px-5 py-3 font-mono text-[11px] text-zinc-500">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
