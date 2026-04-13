import {
  Activity,
  CalendarDays,
  ChevronRight,
  LogOut,
  Mic2,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import { readAccuracyHistoryEntries } from "../../../utils/accuracyHistory";
import { fetchAccuracyHistory } from "../../../services/accuracyApi";
import { clearAuthSession } from "../../../utils/authStorage";

function formatDateLabel(value) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  }).format(new Date(value));
}

function formatTimeLabel(value) {
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export default function MyPage() {
  const navigate = useNavigate();
  const [recentRecords, setRecentRecords] = useState([]);

  const userName =
    typeof window !== "undefined" ? localStorage.getItem("user_name") : "";

  useEffect(() => {
    let mounted = true;
    setRecentRecords(readAccuracyHistoryEntries("exercise").slice(0, 3));

    async function loadRecentRecords() {
      try {
        const payload = await fetchAccuracyHistory({
          sourceType: "exercise",
          limit: 3,
        });
        if (!mounted || !Array.isArray(payload)) return;
        const mapped = payload.map((item) => ({
          dateKey: String(item.measured_on),
          accuracy: typeof item.accuracy_pct === "number" ? item.accuracy_pct : 0,
          recordedAt: item.recorded_at,
          sourceType: item.source_type ?? "exercise",
        }));
        setRecentRecords(mapped.slice(0, 3));
      } catch (error) {
        console.error("[MyPage] failed to fetch", error);
      }
    }

    loadRecentRecords();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <TopBar />
      <BottomNav activeTab="profile" />

      <div className="px-6 pt-6 pb-28">
        <div className="max-w-4xl mx-auto">
          <section className="relative overflow-hidden rounded-[32px] border border-slate-800 bg-gradient-to-br from-blue-700 via-blue-600 to-cyan-500 p-6 shadow-2xl shadow-blue-950/20">
            <div className="absolute right-0 top-0 h-48 w-48 translate-x-12 -translate-y-10 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute left-0 bottom-0 h-40 w-40 -translate-x-8 translate-y-10 rounded-full bg-slate-950/20 blur-3xl" />

            <div className="relative z-10">
              <div className="mb-3 text-xs font-bold tracking-[0.3em] text-blue-100 uppercase">
                My Profile
              </div>
              <h1 className="text-3xl font-black tracking-tight mb-2">
                {userName ? `${userName}님 안녕하세요` : "내 정보"}
              </h1>
              <p className="text-blue-50/85 mb-6">
                이번 주 운동 흐름과 최근 기록을 한 번에 확인해보세요.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-4 backdrop-blur-sm">
                  <div className="text-xs text-blue-100/80 mb-1">오늘 진행</div>
                  <div className="text-2xl font-black">1회</div>
                </div>
                <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-4 backdrop-blur-sm">
                  <div className="text-xs text-blue-100/80 mb-1">이번 주 루틴</div>
                  <div className="text-2xl font-black">3 / 5회</div>
                </div>
                <div className="rounded-2xl border border-white/15 bg-white/10 px-4 py-4 backdrop-blur-sm">
                  <div className="text-xs text-blue-100/80 mb-1">컨디션</div>
                  <div className="text-2xl font-black">안정적</div>
                </div>
              </div>
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_0.9fr] gap-6 mt-6">
            <section className="rounded-[28px] border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between mb-5">
                <h2 className="flex items-center gap-2 text-xl font-bold">
                  <Activity className="text-emerald-400" size={20} />
                  최근 운동 기록
                </h2>
                <button
                  type="button"
                  onClick={() => navigate("/record")}
                  className="text-sm text-slate-400 hover:text-white transition-colors flex items-center gap-1"
                >
                  전체 보기
                  <ChevronRight size={16} />
                </button>
              </div>

              <div className="space-y-3">
                {recentRecords.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-700 p-8 text-center text-slate-400">
                    아직 저장된 기록이 없습니다.
                  </div>
                ) : (
                  recentRecords.map((record) => (
                    <div
                      key={record.recordedAt}
                      className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 flex items-center justify-between gap-4"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 text-slate-400 text-sm mb-1">
                          <CalendarDays size={14} />
                          <span>{formatDateLabel(record.recordedAt)}</span>
                        </div>
                        <div className="font-bold text-lg truncate">
                          자세/운동 기록
                        </div>
                        <div className="text-sm text-slate-500 mt-1">
                          저장 시각 {formatTimeLabel(record.recordedAt)}
                        </div>
                      </div>

                      <div className="shrink-0 text-right">
                        <div className="text-2xl font-black text-blue-400">
                          {record.accuracy}
                        </div>
                        <div className="text-xs text-slate-500">정확도 점수</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-[28px] border border-slate-800 bg-slate-900/60 p-5">
              <h2 className="flex items-center gap-2 text-xl font-bold mb-5">
                <ShieldCheck className="text-blue-400" size={20} />
                계정 설정
              </h2>

              <div className="space-y-3">
                <button
                  type="button"
                  onClick={() => navigate("/settings")}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 flex items-center justify-between hover:border-slate-700 hover:bg-slate-900 transition-colors"
                >
                  <span className="flex items-center gap-3 font-semibold">
                    <Mic2 size={18} className="text-cyan-400" />
                    음성 설정
                  </span>
                  <ChevronRight size={18} className="text-slate-500" />
                </button>

                <button
                  type="button"
                  onClick={() => console.log("my info")}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-4 flex items-center justify-between hover:border-slate-700 hover:bg-slate-900 transition-colors"
                >
                  <span className="flex items-center gap-3 font-semibold">
                    <UserRound size={18} className="text-blue-400" />
                    내 정보
                  </span>
                  <ChevronRight size={18} className="text-slate-500" />
                </button>

                <button
                  type="button"
                  onClick={() => {
                    clearAuthSession();
                    navigate("/login");
                  }}
                  className="w-full rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-4 flex items-center justify-between text-red-400 hover:bg-red-500/15 transition-colors"
                >
                  <span className="flex items-center gap-3 font-semibold">
                    <LogOut size={18} />
                    로그아웃
                  </span>
                  <ChevronRight size={18} className="text-red-300/70" />
                </button>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
