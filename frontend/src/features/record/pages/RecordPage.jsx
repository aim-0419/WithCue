// 재활 운동과 자세 분석 기록을 달력 형태로 보여주고,
// 날짜 클릭 시 모달로 세션 상세(rep별 정확도) 및 ROM 각도를 표시하는 기록 페이지.
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, X } from "lucide-react";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import {
  fetchSessions,
  fetchSessionDetail,
  fetchRomDates,
  fetchRomSnapshot,
} from "../../../services/sessionApi";

const WEEKDAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

const EXERCISE_LABELS = {
  bird_dog: "버드독",
  shoulder_front_raise_left: "어깨 전방 거상 (왼쪽)",
  shoulder_front_raise_right: "어깨 전방 거상 (오른쪽)",
  straight_leg_raise_left: "무릎 들어올리기 (왼쪽)",
  straight_leg_raise_right: "무릎 들어올리기 (오른쪽)",
  neck_rotation: "목 좌우 돌리기",
};

const ROM_KEY_LABELS = {
  shoulder_left_flexion_max: "어깨 굽힘 (왼쪽)",
  shoulder_right_flexion_max: "어깨 굽힘 (오른쪽)",
  shoulder_left_abduction_max: "어깨 외전 (왼쪽)",
  shoulder_right_abduction_max: "어깨 외전 (오른쪽)",
  neck_rotation_left_max: "목 회전 (왼쪽)",
  neck_rotation_right_max: "목 회전 (오른쪽)",
  knee_left_flexion_max: "무릎 굽힘 (왼쪽)",
  knee_right_flexion_max: "무릎 굽힘 (오른쪽)",
  hip_left_flexion_max: "고관절 굽힘 (왼쪽)",
  hip_right_flexion_max: "고관절 굽힘 (오른쪽)",
  trunk_rotation_max_avg: "몸통 회전",
};

const REP_LABEL_KO = {
  good: "양호",
  warning: "주의",
  error: "오류",
};

function toLocalDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date, n) {
  return new Date(date.getFullYear(), date.getMonth() + n, 1);
}

function formatMonthLabel(date) {
  return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long" }).format(date);
}

function formatDateLabel(dateKey) {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date(y, m - 1, d));
}

function formatTime(iso) {
  return new Date(iso).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function buildCalendarDays(currentMonth, calendarMeta) {
  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const cells = [];

  for (let i = 0; i < firstDay.getDay(); i++) {
    cells.push({ type: "blank", key: `blank-${i}` });
  }
  for (let day = 1; day <= lastDay.getDate(); day++) {
    const dateKey = toLocalDateKey(new Date(year, month, day));
    const meta = calendarMeta.get(dateKey) ?? { hasExercise: false, hasCheck: false };
    cells.push({ type: "day", key: dateKey, dateKey, day, meta });
  }
  return cells;
}

// ─── 모달 컴포넌트 ───────────────────────────────────────────────────────────

function RecordModal({ dateKey, exerciseSessions, hasCheck, onClose }) {
  const hasExercise = exerciseSessions.length > 0;
  const hasBoth = hasExercise && hasCheck;

  // 둘 다 있으면 선택 화면부터, 하나만 있으면 바로 해당 뷰
  const initialView = hasBoth ? "select" : hasExercise ? "exercise" : "check";
  const [view, setView] = useState(initialView);

  const [sessionDetails, setSessionDetails] = useState({});
  const [romSnapshot, setRomSnapshot] = useState(null);
  const [loading, setLoading] = useState(false);

  // view가 exercise/check로 바뀔 때 필요한 데이터만 로드
  useEffect(() => {
    if (view === "select") return;

    let mounted = true;
    setLoading(true);

    const promises = [];
    if (view === "exercise") {
      exerciseSessions.forEach((s) => {
        promises.push(
          fetchSessionDetail(s.sessionId).then((detail) => ({ type: "session", detail }))
        );
      });
    }
    if (view === "check") {
      promises.push(fetchRomSnapshot(dateKey).then((data) => ({ type: "rom", data })));
    }

    Promise.allSettled(promises).then((results) => {
      if (!mounted) return;
      const details = {};
      let rom = null;
      results.forEach((r) => {
        if (r.status !== "fulfilled") return;
        if (r.value.type === "session") details[r.value.detail.session_id] = r.value.detail;
        if (r.value.type === "rom") rom = r.value.data;
      });
      if (view === "exercise") setSessionDetails(details);
      if (view === "check") setRomSnapshot(rom);
      setLoading(false);
    });

    return () => { mounted = false; };
  }, [view, dateKey, exerciseSessions]);

  const sortedSessions = useMemo(
    () => [...exerciseSessions].sort((a, b) => new Date(a.recordedAt) - new Date(b.recordedAt)),
    [exerciseSessions]
  );

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto rounded-[32px] border border-slate-700 bg-slate-900 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-center gap-3">
            {/* 선택 화면이 아닌 경우, 둘 다 있으면 뒤로 가기 버튼 */}
            {hasBoth && view !== "select" && (
              <button
                type="button"
                onClick={() => setView("select")}
                className="w-9 h-9 rounded-xl border border-slate-700 bg-slate-800 flex items-center justify-center text-slate-400 hover:text-white transition-colors flex-shrink-0"
              >
                <ChevronLeft size={16} />
              </button>
            )}
            <div>
              <div className="text-xs font-bold tracking-widest text-cyan-400 uppercase mb-1">
                상세 기록
              </div>
              <div className="text-xl font-black">{formatDateLabel(dateKey)}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 rounded-xl border border-slate-700 bg-slate-800 flex items-center justify-center text-slate-400 hover:text-white transition-colors flex-shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* 선택 화면 */}
        {view === "select" && (
          <div className="space-y-4">
            <p className="text-sm text-slate-400 mb-2">확인할 기록을 선택하세요.</p>
            <button
              type="button"
              onClick={() => setView("exercise")}
              className="w-full rounded-2xl border border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 transition-colors p-5 text-left"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="w-3 h-3 rounded-full bg-blue-500" />
                <span className="text-base font-bold text-blue-300">재활 운동</span>
              </div>
              <div className="text-sm text-slate-400">
                {exerciseSessions.length}개 세션 · rep별 점수 확인
              </div>
            </button>
            <button
              type="button"
              onClick={() => setView("check")}
              className="w-full rounded-2xl border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 transition-colors p-5 text-left"
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500" />
                <span className="text-base font-bold text-emerald-300">자세 분석</span>
              </div>
              <div className="text-sm text-slate-400">부위별 가동 범위 각도 확인</div>
            </button>
          </div>
        )}

        {/* 재활 운동 상세 */}
        {view === "exercise" && (
          loading ? (
            <div className="py-12 text-center text-slate-400">불러오는 중...</div>
          ) : (
            <div className="space-y-4">
              {sortedSessions.map((s) => {
                const detail = sessionDetails[s.sessionId];
                return (
                  <div
                    key={s.sessionId}
                    className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-4"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="text-sm font-bold text-white">
                          {EXERCISE_LABELS[s.exerciseCode] ?? s.exerciseCode}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {formatTime(s.recordedAt)}
                          {detail?.ended_at ? ` ~ ${formatTime(detail.ended_at)}` : ""}
                        </div>
                      </div>
                      <div className="text-right">
                        {s.accuracy != null && (
                          <div className="text-lg font-black text-blue-300">{s.accuracy}점</div>
                        )}
                        {s.totalReps > 0 && (
                          <div className="text-xs text-slate-500">총 {s.totalReps}회</div>
                        )}
                      </div>
                    </div>

                    {detail?.reps?.length > 0 ? (
                      <div className="space-y-1.5">
                        <div className="grid grid-cols-[auto_1fr_auto] gap-2 text-[11px] text-slate-500 font-semibold px-1 mb-1">
                          <span>횟수</span>
                          <span>평가</span>
                          <span className="text-right">점수</span>
                        </div>
                        {detail.reps.map((rep) => {
                          const score = Math.round(rep.rep_accuracy_pct);
                          const labelText = REP_LABEL_KO[rep.label] ?? rep.label ?? "";
                          const scoreColor =
                            score >= 80 ? "text-emerald-400"
                            : score >= 60 ? "text-yellow-400"
                            : "text-red-400";
                          return (
                            <div
                              key={rep.rep_no}
                              className="grid grid-cols-[auto_1fr_auto] gap-2 items-center rounded-xl bg-slate-900/80 px-3 py-2"
                            >
                              <span className="text-xs text-slate-400 w-6 text-center">
                                {rep.rep_no}
                              </span>
                              <span className="text-xs text-slate-300">{labelText || "—"}</span>
                              <span className={`text-sm font-bold ${scoreColor}`}>{score}점</span>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500">rep 데이터가 없습니다.</div>
                    )}

                    {/* 신체 부위별 수행 분석 */}
                    {detail?.rom && Object.keys(detail.rom).length > 0 && (
                      <div className="mt-4 pt-4 border-t border-slate-700/50">
                        <div className="text-[11px] text-slate-500 font-semibold mb-2">신체 부위별 수행 분석</div>
                        <div className="space-y-1.5">
                          {Object.entries(detail.rom).map(([key, val]) => (
                            <div
                              key={key}
                              className="flex items-center justify-between rounded-xl bg-slate-900/80 px-3 py-2"
                            >
                              <span className="text-xs text-slate-300">{ROM_KEY_LABELS[key] ?? key}</span>
                              <span className="text-xs font-bold text-blue-300">{Math.round(val)}°</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )
        )}

        {/* 자세 분석 상세 */}
        {view === "check" && (
          loading ? (
            <div className="py-12 text-center text-slate-400">불러오는 중...</div>
          ) : (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
              {romSnapshot?.rom && Object.keys(romSnapshot.rom).length > 0 ? (
                <div className="space-y-1.5">
                  {Object.entries(romSnapshot.rom).map(([key, angle]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between rounded-xl bg-slate-900/80 px-3 py-2"
                    >
                      <span className="text-sm text-slate-300">{ROM_KEY_LABELS[key] ?? key}</span>
                      <span className="text-sm font-bold text-emerald-300">{Math.round(angle)}°</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-slate-500">측정 데이터가 없습니다.</div>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
}

// ─── 메인 페이지 ─────────────────────────────────────────────────────────────

export default function RecordPage() {
  const [exerciseSessions, setExerciseSessions] = useState([]);
  const [checkDates, setCheckDates] = useState(new Set());
  const [currentMonth, setCurrentMonth] = useState(() => startOfMonth(new Date()));
  const [modalDateKey, setModalDateKey] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const [sessionsPayload, datesPayload] = await Promise.all([
          fetchSessions({ limit: 500 }),
          fetchRomDates(),
        ]);
        if (!mounted) return;

        const items = Array.isArray(sessionsPayload?.items) ? sessionsPayload.items : [];
        setExerciseSessions(
          items.map((s) => ({
            dateKey: toLocalDateKey(new Date(s.started_at)),
            accuracy: typeof s.overall_accuracy_pct === "number" ? Math.round(s.overall_accuracy_pct) : null,
            recordedAt: s.started_at,
            exerciseCode: s.exercise_code,
            totalReps: s.total_reps ?? 0,
            sessionId: s.session_id,
          }))
        );

        const dates = Array.isArray(datesPayload?.dates) ? datesPayload.dates : [];
        setCheckDates(new Set(dates));
      } catch (err) {
        console.error("[Record] 기록 불러오기 실패", err);
      }
    }
    load();
    return () => { mounted = false; };
  }, []);

  const exerciseDateSet = useMemo(
    () => new Set(exerciseSessions.map((s) => s.dateKey)),
    [exerciseSessions]
  );

  const calendarMeta = useMemo(() => {
    const map = new Map();
    exerciseDateSet.forEach((d) => {
      if (!map.has(d)) map.set(d, { hasExercise: false, hasCheck: false });
      map.get(d).hasExercise = true;
    });
    checkDates.forEach((d) => {
      if (!map.has(d)) map.set(d, { hasExercise: false, hasCheck: false });
      map.get(d).hasCheck = true;
    });
    return map;
  }, [exerciseDateSet, checkDates]);

  const calendarDays = useMemo(
    () => buildCalendarDays(currentMonth, calendarMeta),
    [currentMonth, calendarMeta]
  );

  const modalExerciseSessions = useMemo(
    () => modalDateKey ? exerciseSessions.filter((s) => s.dateKey === modalDateKey) : [],
    [exerciseSessions, modalDateKey]
  );

  const modalHasCheck = modalDateKey ? checkDates.has(modalDateKey) : false;

  function handleDayClick(cell) {
    if (!cell.meta.hasExercise && !cell.meta.hasCheck) return;
    setModalDateKey(cell.dateKey);
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="px-6 pb-28 pt-6">
        <div className="max-w-3xl mx-auto">
          <div className="mb-6">
            <div className="text-xs font-bold tracking-[0.3em] text-cyan-400 uppercase mb-3">Record</div>
            <h1 className="text-3xl font-black tracking-tight mb-2">운동 · 측정 기록</h1>
            <p className="text-slate-400">기록이 있는 날짜를 눌러 상세 내용을 확인하세요.</p>
          </div>

          <div className="flex items-center gap-5 mb-6">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
              <span className="text-sm text-slate-400">재활 운동</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span className="text-sm text-slate-400">자세 분석</span>
            </div>
          </div>

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
                <div key={label} className="text-center text-xs font-bold text-slate-500 py-2">
                  {label}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-2">
              {calendarDays.map((cell) => {
                if (cell.type === "blank") {
                  return <div key={cell.key} className="aspect-square" />;
                }

                const { hasExercise: hE, hasCheck: hC } = cell.meta;
                const hasAny = hE || hC;

                return (
                  <button
                    key={cell.key}
                    type="button"
                    onClick={() => handleDayClick(cell)}
                    className={[
                      "aspect-square rounded-2xl border transition-all p-2 flex flex-col justify-between",
                      hasAny
                        ? "border-slate-700 bg-slate-900 hover:bg-slate-800 cursor-pointer"
                        : "border-slate-800 bg-slate-950/60 cursor-default",
                    ].join(" ")}
                  >
                    <span className={`text-sm font-bold ${hasAny ? "text-white" : "text-slate-600"}`}>
                      {cell.day}
                    </span>
                    <div className="flex gap-1 justify-end">
                      {hE && <span className="w-2 h-2 rounded-full bg-blue-500" />}
                      {hC && <span className="w-2 h-2 rounded-full bg-emerald-500" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>

      {modalDateKey && (
        <RecordModal
          dateKey={modalDateKey}
          exerciseSessions={modalExerciseSessions}
          hasCheck={modalHasCheck}
          onClose={() => setModalDateKey(null)}
        />
      )}

      <BottomNav activeTab="record" />
    </div>
  );
}
