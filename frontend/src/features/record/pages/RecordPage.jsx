import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  History,
  Target,
} from "lucide-react";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import { readAccuracyHistoryEntries } from "../../../utils/accuracyHistory";
import { fetchAccuracyHistory } from "../../../services/accuracyApi";

const WEEKDAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

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

function formatMonthLabel(date) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
  }).format(date);
}

function toLocalDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

function buildCalendarDays(currentMonth, recordsByDate) {
  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const daysInMonth = lastDay.getDate();
  const leadingBlanks = firstDay.getDay();
  const cells = [];

  for (let index = 0; index < leadingBlanks; index += 1) {
    cells.push({ type: "blank", key: `blank-${index}` });
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(year, month, day);
    const dateKey = toLocalDateKey(date);
    const record = recordsByDate.get(dateKey) ?? null;

    cells.push({
      type: "day",
      key: dateKey,
      date,
      dateKey,
      day,
      record,
    });
  }

  return cells;
}

export default function RecordPage() {
  const [records, setRecords] = useState([]);
  const [selectedDateKey, setSelectedDateKey] = useState(() =>
    toLocalDateKey(new Date())
  );
  const [currentMonth, setCurrentMonth] = useState(() => startOfMonth(new Date()));

  useEffect(() => {
    let mounted = true;

    const fallbackRecords = readAccuracyHistoryEntries("exercise");
    setRecords(fallbackRecords);

    async function loadHistory() {
      try {
        const payload = await fetchAccuracyHistory({ sourceType: "exercise" });
        if (!mounted || !Array.isArray(payload)) return;
        const mapped = payload.map((item) => ({
          dateKey: String(item.measured_on),
          accuracy: typeof item.accuracy_pct === "number" ? item.accuracy_pct : 0,
          recordedAt: item.recorded_at,
          sourceType: item.source_type ?? "exercise",
          sourceKey: item.source_key ?? null,
        }));
        setRecords(mapped);
      } catch (error) {
        console.error("[Record] failed to fetch", error);
      }
    }

    loadHistory();
    return () => {
      mounted = false;
    };
  }, []);

  const stats = useMemo(() => {
    if (records.length === 0) {
      return { count: 0, average: 0, best: 0 };
    }

    const total = records.reduce((sum, item) => sum + item.accuracy, 0);
    const best = records.reduce(
      (max, item) => (item.accuracy > max ? item.accuracy : max),
      0
    );

    return {
      count: records.length,
      average: Math.round(total / records.length),
      best,
    };
  }, [records]);

  const recordsByDate = useMemo(() => {
    const map = new Map();
    records.forEach((record) => {
      const existing = map.get(record.dateKey);
      if (!existing) {
        map.set(record.dateKey, record);
        return;
      }
      if (
        new Date(record.recordedAt).getTime() >
        new Date(existing.recordedAt).getTime()
      ) {
        map.set(record.dateKey, record);
      }
    });
    return map;
  }, [records]);

  const calendarDays = useMemo(
    () => buildCalendarDays(currentMonth, recordsByDate),
    [currentMonth, recordsByDate]
  );

  const selectedRecord = useMemo(() => {
    if (!selectedDateKey) return null;
    return recordsByDate.get(selectedDateKey) ?? null;
  }, [recordsByDate, selectedDateKey]);

  const dayRecords = useMemo(() => {
    if (!selectedDateKey) return [];
    return records.filter((record) => record.dateKey === selectedDateKey);
  }, [records, selectedDateKey]);

  const dayAverage = useMemo(() => {
    if (dayRecords.length === 0) return 0;
    const total = dayRecords.reduce((sum, record) => sum + record.accuracy, 0);
    return Math.round(total / dayRecords.length);
  }, [dayRecords]);

  const exerciseSummary = useMemo(() => {
    const labelMap = {
      bird_dog: "버드독",
      shoulder_front_raise_left: "어깨 전방 거상(왼쪽)",
      shoulder_front_raise_right: "어깨 전방 거상(오른쪽)",
      knee_raise_left: "무릎 들어올리기(왼쪽)",
      knee_raise_right: "무릎 들어올리기(오른쪽)",
      neck_rotation: "목 좌우 돌리기",
    };

    const map = new Map();
    dayRecords.forEach((record) => {
      const key = record.sourceKey ?? "unknown";
      if (!map.has(key)) {
        map.set(key, { key, label: labelMap[key] ?? "운동", scores: [] });
      }
      map.get(key).scores.push(record.accuracy);
    });

    return Array.from(map.values()).map((entry) => {
      const avg =
        entry.scores.length > 0
          ? Math.round(
              entry.scores.reduce((sum, score) => sum + score, 0) /
                entry.scores.length
            )
          : 0;
      return { ...entry, average: avg };
    });
  }, [dayRecords]);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="px-6 pb-28 pt-6">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <div className="text-xs font-bold tracking-[0.3em] text-cyan-400 uppercase mb-3">
              Record
            </div>
            <h1 className="text-3xl font-black tracking-tight mb-2">
              운동 · 측정 기록
            </h1>
            <p className="text-slate-400">
              날짜를 눌러 해당 날짜의 자세 측정 및 운동 기록 상세를 확인해보세요.
            </p>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.85fr] gap-6">
            <section className="rounded-[32px] border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between gap-3 mb-5">
                <div className="flex items-center gap-3">
                  <CalendarDays className="text-cyan-400" size={20} />
                  <h2 className="text-xl font-bold">기록 달력</h2>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setCurrentMonth((prev) => addMonths(prev, -1))}
                    className="w-10 h-10 rounded-xl border border-slate-800 bg-slate-950/70 flex items-center justify-center hover:border-slate-700 transition-colors"
                  >
                    <ChevronLeft size={18} />
                  </button>
                  <div className="min-w-[140px] text-center text-sm font-semibold text-slate-200">
                    {formatMonthLabel(currentMonth)}
                  </div>
                  <button
                    type="button"
                    onClick={() => setCurrentMonth((prev) => addMonths(prev, 1))}
                    className="w-10 h-10 rounded-xl border border-slate-800 bg-slate-950/70 flex items-center justify-center hover:border-slate-700 transition-colors"
                  >
                    <ChevronRight size={18} />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-7 gap-2 mb-3">
                {WEEKDAY_LABELS.map((label) => (
                  <div
                    key={label}
                    className="text-center text-xs font-bold text-slate-500 py-2"
                  >
                    {label}
                  </div>
                ))}
              </div>

              {records.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-700 p-10 text-center text-slate-400">
                  아직 저장된 기록이 없습니다. 측정 또는 운동을 완료하면 달력에 표시됩니다.
                </div>
              ) : (
                <div className="grid grid-cols-7 gap-2">
                  {calendarDays.map((cell) => {
                    if (cell.type === "blank") {
                      return <div key={cell.key} className="aspect-square" />;
                    }

                    const isSelected = selectedDateKey === cell.dateKey;
                    const hasRecord = Boolean(cell.record);

                    return (
                      <button
                        key={cell.key}
                        type="button"
                        onClick={() => setSelectedDateKey(cell.dateKey)}
                        className={[
                          "aspect-square rounded-2xl border transition-all text-left p-3 flex flex-col justify-between",
                          hasRecord
                            ? "border-cyan-500/30 bg-cyan-500/10 hover:bg-cyan-500/15"
                            : "border-slate-800 bg-slate-950/60 hover:bg-slate-900",
                          isSelected ? "ring-2 ring-cyan-400 border-cyan-400" : "",
                        ].join(" ")}
                      >
                        <span className="text-sm font-bold text-white">
                          {cell.day}
                        </span>
                        {hasRecord ? (
                          <div>
                            <div className="text-[11px] text-cyan-300 font-semibold">
                              기록 있음
                            </div>
                          </div>
                        ) : (
                          <span className="text-[11px] text-slate-600">-</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="rounded-[32px] border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-5">
              <div className="flex items-center gap-3 mb-5">
                <Clock3 className="text-cyan-400" size={20} />
                <h2 className="text-xl font-bold">기록 상세</h2>
              </div>

              {!selectedRecord ? (
                <div className="rounded-2xl border border-dashed border-slate-700 p-10 text-center text-slate-400">
                  달력에서 기록이 있는 날짜를 선택해 상세 내용을 확인하세요.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
                    <div className="text-slate-400 text-sm mb-1">기록 날짜</div>
                    <div className="text-2xl font-black">
                      {formatDateLabel(selectedRecord.recordedAt)}
                    </div>
                    <div className="text-sm text-slate-500 mt-2">
                      저장 시각 {formatTimeLabel(selectedRecord.recordedAt)}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
                    <div className="text-slate-400 text-sm mb-3">
                      진행한 운동
                    </div>
                    {exerciseSummary.length === 0 ? (
                      <div className="text-sm text-slate-500">
                        해당 날짜에 기록된 운동이 없습니다.
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {exerciseSummary.map((entry) => (
                          <div
                            key={entry.key}
                            className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3"
                          >
                            <div className="text-sm font-semibold text-slate-200">
                              {entry.label}
                            </div>
                            <div className="text-sm text-cyan-300 font-bold">
                              평균 {entry.average}점
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
                    <div className="text-slate-400 text-sm mb-3">
                      운동별 가장 많이 나온 피드백
                    </div>
                    {exerciseSummary.length === 0 ? (
                      <div className="text-sm text-slate-500">
                        해당 날짜에 기록된 운동이 없습니다.
                      </div>
                    ) : (
                      <div className="space-y-3 max-h-24 overflow-y-auto pr-1 hide-scrollbar">
                        {exerciseSummary.map((entry) => (
                          <div
                            key={`${entry.key}-feedback`}
                            className="rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3"
                          >
                            <div className="text-sm font-semibold text-slate-200 mb-1">
                              {entry.label}
                            </div>
                            <div className="text-xs text-slate-500">
                              피드백 기록이 아직 저장되지 않아 표시할 수 없습니다.
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
                    <div className="text-slate-400 text-sm mb-2">세션 정보</div>
                    <div className="space-y-2 text-sm text-slate-300">
                      <div>유형: 운동 기록</div>
                      <div>상태: 자동 저장 완료</div>
                      <div>기준: 해당 날짜의 진행한 운동의 평균 점수</div>
                    </div>
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
      <BottomNav activeTab="record" />
    </div>
  );
}
