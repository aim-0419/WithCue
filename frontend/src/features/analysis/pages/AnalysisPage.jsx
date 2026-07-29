// 재활 운동 수행 점수와 자세 분석 ROM 추이를 탭으로 전환해 보여주는 통계 페이지.
import { useEffect, useMemo, useState } from "react";
import bodyDefault from "../../../assets/body/body_default.png";
import { Activity, TrendingUp } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import { fetchSessions, fetchRomHistory } from "../../../services/sessionApi";

const DAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

function getThisWeekDays() {
  const now = new Date();
  const sunday = new Date(now);
  sunday.setDate(now.getDate() - now.getDay());
  sunday.setHours(0, 0, 0, 0);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(sunday);
    d.setDate(sunday.getDate() + i);
    return d.toISOString().slice(0, 10);
  });
}

const EXERCISE_OPTIONS = [
  { id: "all", label: "전체" },
  { id: "neck_rotation", label: "목 돌리기" },
  {
    id: "shoulder_front_raise",
    label: "어깨 전방 거상",
    sides: [
      { key: "shoulder_front_raise_left", label: "왼쪽", color: "#22c55e" },
      { key: "shoulder_front_raise_right", label: "오른쪽", color: "#f97316" },
    ],
  },
  {
    id: "straight_leg_raise",
    label: "무릎 들어올리기",
    sides: [
      { key: "straight_leg_raise_left", label: "왼쪽", color: "#22c55e" },
      { key: "straight_leg_raise_right", label: "오른쪽", color: "#f97316" },
    ],
  },
];

// 각 그룹은 좌/우(또는 여러 키)를 한 차트에 함께 표시한다.
const ROM_GROUPS = [
  {
    label: "목",
    lines: [
      { keys: ["neck_rotation_left_max"], label: "왼쪽", color: "#34d399" },
      { keys: ["neck_rotation_right_max"], label: "오른쪽", color: "#38bdf8" },
    ],
  },
  {
    label: "어깨",
    lines: [
      { keys: ["shoulder_left_flexion_max", "shoulder_left_abduction_max"], label: "왼쪽", color: "#34d399" },
      { keys: ["shoulder_right_flexion_max", "shoulder_right_abduction_max"], label: "오른쪽", color: "#38bdf8" },
    ],
  },
  {
    label: "무릎",
    lines: [
      { keys: ["knee_left_flexion_max"], label: "왼쪽", color: "#34d399" },
      { keys: ["knee_right_flexion_max"], label: "오른쪽", color: "#38bdf8" },
    ],
  },
  {
    label: "고관절",
    lines: [
      { keys: ["hip_left_flexion_max"], label: "왼쪽", color: "#34d399" },
      { keys: ["hip_right_flexion_max"], label: "오른쪽", color: "#38bdf8" },
    ],
  },
];

// 인체 이미지 위 각 ROM 부위 점 위치 (이미지 컨테이너 기준 %)
const ROM_MARKERS = [
  { groupIdx: 0, dots: [{ top: "14%", left: "50%" }] },                                    // 목
  { groupIdx: 1, dots: [{ top: "18%", left: "35%" }, { top: "18%", left: "64%" }] },       // 어깨
  { groupIdx: 3, dots: [{ top: "40%", left: "42%" }, { top: "40%", left: "58%" }] },       // 고관절
  { groupIdx: 2, dots: [{ top: "64%", left: "43%" }, { top: "64%", left: "57%" }] },       // 무릎
];

function getDotColor(diff) {
  if (diff == null) return "#475569";
  if (diff <= 5) return "#22c55e";
  if (diff <= 10) return "#eab308";
  return "#f97316";
}

function formatDateShort(iso) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const TOOLTIP_STYLE = {
  backgroundColor: "#0f172a",
  border: "1px solid rgba(148,163,184,0.2)",
  borderRadius: "12px",
  color: "#fff",
  fontSize: 13,
};

// ── 재활 운동 탭 ──────────────────────────────────────────────────────────────
function ExerciseTab({ sessions }) {
  const [selectedExercise, setSelectedExercise] = useState("all");

  const selectedOpt = EXERCISE_OPTIONS.find((o) => o.id === selectedExercise);
  const isSided = !!selectedOpt?.sides;

  const chartData = useMemo(() => {
    const weekDays = getThisWeekDays();
    const weekStart = new Date(weekDays[0]);
    const weekEnd = new Date(weekDays[6]);
    weekEnd.setHours(23, 59, 59, 999);

    const inWeek = (s) => { const d = new Date(s.recordedAt); return d >= weekStart && d <= weekEnd; };
    const toKey = (iso) => new Date(iso).toISOString().slice(0, 10);
    const dailyAvg = (scores) => {
      const v = scores.filter((x) => x != null && x > 0);
      return v.length > 0 ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : 0;
    };

    if (isSided) {
      const maps = Object.fromEntries(selectedOpt.sides.map((s) => [s.key, new Map()]));
      selectedOpt.sides.forEach((side) => {
        sessions.filter((s) => s.exerciseCode === side.key && inWeek(s)).forEach((s) => {
          const dk = toKey(s.recordedAt);
          if (!maps[side.key].has(dk)) maps[side.key].set(dk, []);
          maps[side.key].get(dk).push(s.accuracy);
        });
      });
      return weekDays.map((dk, i) => {
        const point = { name: DAY_LABELS[i] };
        selectedOpt.sides.forEach((side) => {
          point[side.key] = dailyAvg(maps[side.key].get(dk) ?? []);
        });
        return point;
      });
    }

    const filtered = (selectedExercise === "all"
      ? sessions
      : sessions.filter((s) => s.exerciseCode === selectedExercise)
    ).filter(inWeek);
    const byDate = new Map();
    filtered.forEach((s) => {
      const dk = toKey(s.recordedAt);
      if (!byDate.has(dk)) byDate.set(dk, []);
      byDate.get(dk).push(s.accuracy);
    });
    return weekDays.map((dk, i) => ({ name: DAY_LABELS[i], score: dailyAvg(byDate.get(dk) ?? []) }));
  }, [sessions, selectedExercise, isSided]);

  const avg = useMemo(() => {
    if (isSided) return null;
    const active = chartData.filter((d) => d.score > 0);
    return active.length > 0
      ? Math.round(active.reduce((s, d) => s + d.score, 0) / active.length)
      : null;
  }, [chartData, isSided]);

  const sideAvgs = useMemo(() => {
    if (!isSided) return null;
    return Object.fromEntries(
      selectedOpt.sides.map((side) => {
        const active = chartData.filter((d) => d[side.key] > 0);
        const val = active.length > 0
          ? Math.round(active.reduce((s, d) => s + d[side.key], 0) / active.length)
          : null;
        return [side.key, val];
      })
    );
  }, [chartData, isSided, selectedOpt]);

  const makeDot = (color) => (props) => {
    const { cx, cy, value, index } = props;
    if (value === 0) return <circle key={index} cx={cx} cy={cy} r={3} fill="rgba(148,163,184,0.25)" />;
    return <circle key={index} cx={cx} cy={cy} r={4} fill={color} />;
  };

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* 운동 선택 */}
      <div className="flex gap-2 flex-wrap">
        {EXERCISE_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setSelectedExercise(opt.id)}
            className={[
              "px-4 py-2 rounded-xl text-xs font-bold transition-colors",
              selectedExercise === opt.id
                ? "bg-blue-500 text-white"
                : "bg-slate-800 text-slate-400 hover:bg-slate-700",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* 좌/우 범례 */}
      {isSided && (
        <div className="flex gap-4">
          {selectedOpt.sides.map((side) => (
            <div key={side.key} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full inline-block" style={{ background: side.color }} />
              <span className="text-xs text-slate-400">{side.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* 차트 */}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="name" tickLine={false} axisLine={false} stroke="#64748b" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} tickLine={false} axisLine={false} stroke="#64748b" tick={{ fontSize: 11 }} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v, name) => {
                if (!v) return ["기록 없음", ""];
                const side = selectedOpt?.sides?.find((s) => s.key === name);
                return [`${v}점`, side?.label ?? "점수"];
              }}
            />
            {!isSided && avg && <ReferenceLine y={avg} stroke="#38bdf8" strokeDasharray="4 4" strokeOpacity={0.5} />}
            {isSided && sideAvgs && selectedOpt.sides.map((side) =>
              sideAvgs[side.key] != null && (
                <ReferenceLine key={side.key} y={sideAvgs[side.key]} stroke={side.color} strokeDasharray="4 4" strokeOpacity={0.6} />
              )
            )}
            {isSided
              ? selectedOpt.sides.map((side) => (
                <Line key={side.key} type="monotone" dataKey={side.key}
                  stroke={side.color} strokeWidth={2.5}
                  dot={makeDot(side.color)} activeDot={{ r: 6 }} connectNulls />
              ))
              : <Line type="monotone" dataKey="score" stroke="#38bdf8" strokeWidth={2.5}
                dot={makeDot("#38bdf8")} activeDot={{ r: 6 }} />
            }
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── 자세 분석 탭 ──────────────────────────────────────────────────────────────
function RomTab() {
  const [romData, setRomData] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState(null);

  useEffect(() => {
    let mounted = true;
    const allKeys = [...new Set(ROM_GROUPS.flatMap((g) => g.lines.flatMap((l) => l.keys)))];

    Promise.allSettled(
      allKeys.map((key) =>
        fetchRomHistory(key).then((payload) => {
          const items = Array.isArray(payload?.items) ? payload.items : [];
          const latest = items
            .filter((item) => item.angle_deg > 0)
            .reduce((best, item) =>
              !best || new Date(item.measured_at) > new Date(best.measured_at) ? item : best
              , null);
          return { key, data: latest };
        })
      )
    ).then((results) => {
      if (!mounted) return;
      const data = {};
      results.forEach((r) => {
        if (r.status === "fulfilled" && r.value.data) {
          data[r.value.key] = r.value.data;
        }
      });
      setRomData(data);
      setLoading(false);
    });

    return () => { mounted = false; };
  }, []);

  if (loading) {
    return <div className="h-full flex items-center justify-center text-slate-500 text-sm">불러오는 중...</div>;
  }

  const getLineVal = (line) => {
    const entries = line.keys
      .map((k) => romData[k])
      .filter(Boolean)
      .filter((d) => d.angle_deg > 0);
    if (entries.length === 0) return null;
    const latest = entries.reduce((best, d) =>
      new Date(d.measured_at) > new Date(best.measured_at) ? d : best
    );
    return Math.round(latest.angle_deg);
  };

  const getVals = (group) => {
    const [l, r] = group.lines;
    const lv = getLineVal(l);
    const rv = getLineVal(r);
    const diff = lv != null && rv != null ? Math.abs(lv - rv) : null;
    return { lv, rv, diff };
  };

  const activeGroup = selectedGroup != null ? ROM_GROUPS[selectedGroup] : null;

  return (
    <div className="relative flex justify-center h-full min-h-0">
      {/* 인체 이미지 */}
      <div className="relative" style={{ aspectRatio: "2/3", height: "100%", maxWidth: "100%" }}>
        <img src={bodyDefault} className="h-full w-full object-contain opacity-80" alt="body" />
        {ROM_MARKERS.map(({ groupIdx, dots }) => {
          const { diff } = getVals(ROM_GROUPS[groupIdx]);
          const color = getDotColor(diff);
          return dots.map((pos, i) => (
            <div
              key={`${groupIdx}-${i}`}
              onClick={() => setSelectedGroup(groupIdx)}
              style={{
                position: "absolute",
                top: pos.top,
                left: pos.left,
                transform: "translate(-50%, -50%)",
                width: 18,
                height: 18,
                borderRadius: "50%",
                background: color,
                boxShadow: `0 0 12px ${color}, 0 0 5px ${color}`,
                border: "2px solid rgba(255,255,255,0.35)",
                cursor: "pointer",
              }}
            />
          ));
        })}
      </div>

      {/* 모달 */}
      {activeGroup && (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.55)", zIndex: 10 }}
          onClick={() => setSelectedGroup(null)}
        >
          <div
            className="rounded-2xl border border-slate-700 bg-slate-900 p-6 w-64"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 헤더 */}
            <div className="flex items-center justify-between mb-4">
              <span className="text-base font-bold text-white">{activeGroup.label}</span>
              {(() => {
                const allKeys = activeGroup.lines.flatMap((l) => l.keys);
                const at = allKeys.map((k) => romData[k]?.measured_at).filter(Boolean)[0];
                return at
                  ? <span className="text-xs text-slate-500">{new Date(at).toLocaleDateString("ko-KR")}</span>
                  : null;
              })()}
            </div>

            {/* 좌/차이/우 */}
            <div className="flex items-center justify-between text-center">
              {(() => {
                const [leftLine, rightLine] = activeGroup.lines;
                const { lv, rv, diff } = getVals(activeGroup);
                return (
                  <>
                    <div>
                      <div className="text-xs mb-1" style={{ color: leftLine.color }}>왼쪽</div>
                      <div className="text-2xl font-black text-white">{lv != null ? `${lv}°` : "—"}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 mb-1">차이</div>
                      <div className={`text-2xl font-black ${diff != null && diff > 10 ? "text-amber-400" : "text-emerald-300"}`}>
                        {diff != null ? `${diff}°` : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs mb-1" style={{ color: rightLine.color }}>오른쪽</div>
                      <div className="text-2xl font-black text-white">{rv != null ? `${rv}°` : "—"}</div>
                    </div>
                  </>
                );
              })()}
            </div>

            <button
              className="mt-5 w-full py-2 rounded-xl bg-slate-800 text-slate-300 text-sm font-bold"
              onClick={() => setSelectedGroup(null)}
            >
              닫기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────
export default function AnalysisPage() {
  const [activeTab, setActiveTab] = useState("exercise");
  const [exerciseSessions, setExerciseSessions] = useState([]);

  useEffect(() => {
    let mounted = true;
    fetchSessions({ limit: 500 })
      .then((payload) => {
        if (!mounted) return;
        const items = Array.isArray(payload?.items) ? payload.items : [];
        setExerciseSessions(
          items.map((s) => ({
            exerciseCode: s.exercise_code,
            accuracy: typeof s.overall_accuracy_pct === "number" ? Math.round(s.overall_accuracy_pct) : null,
            recordedAt: s.started_at,
          }))
        );
      })
      .catch((err) => console.error("[Statistics] 세션 불러오기 실패", err));
    return () => { mounted = false; };
  }, []);

  return (
    <div className="h-screen bg-slate-950 text-white flex flex-col overflow-hidden">
      <TopBar />

      <div className="flex-1 flex flex-col min-h-0 px-5 pt-4 pb-24">
        {/* 탭 전환 */}
        <div className="flex gap-2 mb-5 flex-shrink-0">
          <button
            type="button"
            onClick={() => setActiveTab("exercise")}
            className={[
              "flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-colors",
              activeTab === "exercise"
                ? "bg-blue-500/20 border border-blue-500/50 text-blue-300"
                : "bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700",
            ].join(" ")}
          >
            <Activity size={16} />
            재활 운동
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("rom")}
            className={[
              "flex-1 flex items-center justify-center gap-2 py-3 rounded-2xl text-sm font-bold transition-colors",
              activeTab === "rom"
                ? "bg-emerald-500/20 border border-emerald-500/50 text-emerald-300"
                : "bg-slate-800 border border-slate-700 text-slate-400 hover:bg-slate-700",
            ].join(" ")}
          >
            <TrendingUp size={16} />
            자세 분석
          </button>
        </div>

        {/* 탭 콘텐츠 */}
        <div className="flex-1 min-h-0">
          {activeTab === "exercise"
            ? <ExerciseTab sessions={exerciseSessions} />
            : <RomTab />
          }
        </div>
      </div>

      <BottomNav activeTab="analysis" />
    </div>
  );
}
