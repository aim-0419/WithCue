import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ClipboardList } from "lucide-react";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import { readAccuracyHistoryEntries } from "../../../utils/accuracyHistory";
import { fetchAccuracyHistory } from "../../../services/accuracyApi";

export default function CheckHistoryPage() {
  const [entries, setEntries] = useState(() =>
    readAccuracyHistoryEntries("check")
  );

  useEffect(() => {
    let mounted = true;

    async function loadHistory() {
      try {
        const payload = await fetchAccuracyHistory({ sourceType: "check" });
        if (!mounted || !Array.isArray(payload)) return;
        const mapped = payload.map((item) => ({
          dateKey: String(item.measured_on),
          accuracy: typeof item.accuracy_pct === "number" ? item.accuracy_pct : 0,
          recordedAt: item.recorded_at,
          sourceType: item.source_type ?? "check",
        }));
        setEntries(mapped);
      } catch (error) {
        console.error("[CheckHistory] failed to fetch", error);
      }
    }

    loadHistory();
    return () => {
      mounted = false;
    };
  }, []);

  const items = useMemo(
    () =>
      entries.map((entry) => ({
        ...entry,
        formattedDate: new Intl.DateTimeFormat("ko-KR", {
          month: "2-digit",
          day: "2-digit",
          weekday: "short",
        }).format(new Date(entry.recordedAt)),
        formattedTime: new Intl.DateTimeFormat("ko-KR", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        }).format(new Date(entry.recordedAt)),
      })),
    [entries]
  );

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="px-6 pb-28 pt-6">
        <div className="max-w-3xl mx-auto">
          <div className="mb-6">
            <div className="text-xs font-bold tracking-[0.3em] text-cyan-400 uppercase mb-3">
              Check History
            </div>
            <h1 className="text-3xl font-black tracking-tight mb-2">부위별 검사 결과</h1>
            <p className="text-slate-400">
              부위별 검사 결과를 날짜별로 확인할 수 있습니다.
            </p>
          </div>

          {items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-700 p-10 text-center text-slate-400">
              아직 저장된 검사 결과가 없습니다.
            </div>
          ) : (
            <div className="space-y-4">
              {items.map((item) => (
                <div
                  key={`${item.dateKey}-${item.recordedAt}`}
                  className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 flex items-center justify-between"
                >
                  <div>
                    <div className="text-sm text-slate-400 flex items-center gap-2">
                      <CalendarDays size={16} />
                      {item.formattedDate} · {item.formattedTime}
                    </div>
                    <div className="mt-2 text-lg font-semibold flex items-center gap-2">
                      <ClipboardList size={18} />
                      검사 결과
                    </div>
                  </div>
                  <div className="text-3xl font-black text-cyan-300">
                    {item.accuracy}점
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <BottomNav activeTab="check-history" />
    </div>
  );
}
