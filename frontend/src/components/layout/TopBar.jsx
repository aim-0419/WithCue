// src/components/TopBar.jsx
// 탑바 (로고, 날짜/시간, 설정 바로가기)
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Settings } from "lucide-react";
import { getApiBase } from "../../services/runtimeConfig";

export default function TopBar() {
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [serverAlive, setServerAlive] = useState(false);

  // [조현석] TopBar 서버 상태 체크도 현재 접속 호스트 기준 백엔드 주소를 자동 계산해서 사용합니다.
  const HEALTH_URL = `${getApiBase()}/api/v1/system/health`;

  // 시간 업데이트 
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // 서버 상태 체크 (5초 주기)
  useEffect(()=>{
    let mounted = true;

    const checkServer = async () => {
      try {
        const res = await fetch(HEALTH_URL, { cache: "no-store" });
        if (!mounted) return;
        setServerAlive(res.ok);
      }catch (err) {
        if (!mounted) return;
        setServerAlive(false);
      }
    };

    //최초 1회 즉시 체크
    checkServer();

    const interval = setInterval(checkServer, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [HEALTH_URL]);


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

      {/* Right: Server Status + Date/Time + Settings */}
      <div className="flex items-center gap-4">
        {/* 🟢 서버 상태 표시 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-medium">server</span>
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              serverAlive ? "bg-green-500" : "bg-red-500"
            }`}
            title={serverAlive ? "서버 연결됨" : "서버 연결 끊김"}
          />
        </div>

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
