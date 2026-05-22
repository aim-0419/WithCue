// src/components/TopBar.jsx
// 탑바 (로고, 날짜/시간, 설정 바로가기)
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Settings } from "lucide-react";

export default function TopBar() {
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());

  // 시간 업데이트 
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);


  const formatted = now.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <header className="h-16 bg-slate-950 flex items-center justify-between px-6 text-white z-40 relative">
      {/* Left: Brand */}
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => navigate("/main")}
      >
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center -rotate-6">
          <span className="font-bold text-lg italic">W</span>
        </div>
        <span className="text-xl font-bold tracking-tight italic">
          WITHCUE
        </span>
      </div>

      {/* Right: Date/Time + Settings */}
      <div className="flex items-center gap-4">
        <div className="text-sm text-slate-300 tabular-nums">
          {formatted}
        </div>

        <button
          className="p-2 text-slate-400 hover:text-white transition-colors"
          aria-label="Settings"
          onClick={() => navigate("/settings")}
        >
          <Settings size={20} />
        </button>
      </div>
    </header>
  );
}
