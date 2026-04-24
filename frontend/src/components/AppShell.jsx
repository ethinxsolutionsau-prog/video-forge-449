import React from "react";
import Sidebar from "./Sidebar";

export default function AppShell({ children }) {
  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white">
      <Sidebar />
      <div className="ml-60 min-h-screen flex flex-col">{children}</div>
    </div>
  );
}
