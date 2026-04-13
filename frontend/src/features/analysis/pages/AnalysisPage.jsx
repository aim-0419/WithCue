import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import { fetchAccuracyHistory } from "../../../services/accuracyApi";
import { readLatestAccuracy, toWeeklyChartData } from "../../../utils/accuracyHistory";

const EXERCISE_OPTIONS = [
  { id: "all", label: "전체" },
  { id: "bird_dog", label: "버드독" },
  { id: "shoulder_front_raise_left", label: "어깨 전방 거상(왼쪽)" },
  { id: "shoulder_front_raise_right", label: "어깨 전방 거상(오른쪽)" },
  { id: "knee_raise_left", label: "무릎 들어올리기(왼쪽)" },
  { id: "knee_raise_right", label: "무릎 들어올리기(오른쪽)" },
  { id: "neck_rotation", label: "목 좌우 돌리기" },
];

function getAverageScore(items) {
  if (!Array.isArray(items) || items.length === 0) return 0;
  const valid = items.filter(
    (item) => typeof item?.score === "number" && item.score > 0
  );
  if (valid.length === 0) return 0;
  const total = valid.reduce((sum, item) => sum + item.score, 0);
  return Math.round(total / valid.length);
}

function getBestDay(items) {
  const valid = Array.isArray(items)
    ? items.filter((item) => typeof item?.score === "number")
    : [];
  if (valid.length === 0) return { name: "-", score: 0 };
  const maxScore = Math.max(...valid.map((item) => item.score ?? 0));
  if (maxScore <= 0) return { name: "-", score: 0 };
  return valid.reduce((best, current) =>
    current.score > best.score ? current : best
  );
}

function getMonday(date = new Date()) {
  const current = new Date(date);
  const day = current.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  current.setHours(0, 0, 0, 0);
  current.setDate(current.getDate() + diff);
  return current;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toLocalDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toWeeklyAverageChartData(items, baseDate = new Date()) {
  const monday = getMonday(baseDate);
  const buckets = new Map();

  (items || []).forEach((entry) => {
    const measuredOn = entry?.measured_on;
    const score = entry?.accuracy_pct;
    if (!measuredOn || typeof score !== "number") return;
    const dateKey = String(measuredOn);
    if (!buckets.has(dateKey)) {
      buckets.set(dateKey, []);
    }
    buckets.get(dateKey).push(score);
  });

  const labels = ["월", "화", "수", "목", "금", "토", "일"];
  return labels.map((label, index) => {
    const date = addDays(monday, index);
    const dateKey = toLocalDateKey(date);
    const dayScores = buckets.get(dateKey) || [];
    const avg =
      dayScores.length > 0
        ? Math.round(dayScores.reduce((sum, val) => sum + val, 0) / dayScores.length)
        : 0;
    return { name: label, score: avg };
  });
}

export default function AnalysisPage() {
  const [weeklyAccuracyData, setWeeklyAccuracyData] = useState(() =>
    toWeeklyChartData(new Date(), "exercise")
  );
  const [serverLatestAccuracy, setServerLatestAccuracy] = useState(null);
  const [latestExerciseLabel, setLatestExerciseLabel] = useState(null);
  const [selectedExerciseId, setSelectedExerciseId] = useState("all");
  const [selectedLatestAccuracy, setSelectedLatestAccuracy] = useState(null);
  const [selectedExerciseLabel, setSelectedExerciseLabel] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function loadWeeklyAccuracy() {
      try {
        const items = await fetchAccuracyHistory({
          sourceType: "exercise",
          limit: 200,
        });
        if (!mounted) return;
        setWeeklyAccuracyData(
          Array.isArray(items) && items.length > 0
            ? toWeeklyAverageChartData(items, new Date())
            : toWeeklyAverageChartData([], new Date())
        );
        const latest = Array.isArray(items) && items.length > 0 ? items[0] : null;
        setServerLatestAccuracy(
          typeof latest?.accuracy_pct === "number" ? latest.accuracy_pct : null
        );
      } catch (error) {
        if (!mounted) return;
        console.error("[Accuracy] failed to fetch weekly data", error);
      }
    }

    async function loadLatestExercise() {
      try {
        const items = await fetchAccuracyHistory({
          sourceType: "exercise",
          limit: 1,
        });
        if (!mounted || !Array.isArray(items) || items.length === 0) return;
        const latest = items[0];
        const sourceKey = latest?.source_key;
        const labelMap = {
          bird_dog: "버드독",
          shoulder_front_raise_left: "어깨 전방 거상(왼쪽)",
          shoulder_front_raise_right: "어깨 전방 거상(오른쪽)",
          knee_raise_left: "무릎 들어올리기(왼쪽)",
          knee_raise_right: "무릎 들어올리기(오른쪽)",
          neck_rotation: "목 좌우 돌리기",
        };
        setLatestExerciseLabel(labelMap[sourceKey] ?? "운동");
      } catch (error) {
        if (!mounted) return;
        console.error("[Accuracy] failed to fetch latest exercise", error);
      }
    }

    loadWeeklyAccuracy();
    loadLatestExercise();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadExerciseTrend() {
      try {
        const items = await fetchAccuracyHistory({
          sourceType: "exercise",
          sourceKey: selectedExerciseId === "all" ? null : selectedExerciseId,
          limit: 200,
        });
        if (!mounted) return;
        setWeeklyAccuracyData(
          Array.isArray(items) && items.length > 0
            ? toWeeklyAverageChartData(items, new Date())
            : toWeeklyAverageChartData([], new Date())
        );
      } catch (error) {
        if (!mounted) return;
        console.error("[Accuracy] failed to fetch exercise trend", error);
      }
    }

    async function loadSelectedLatestAccuracy() {
      if (selectedExerciseId === "all") {
        setSelectedLatestAccuracy(null);
        setSelectedExerciseLabel(null);
        return;
      }
      try {
        const items = await fetchAccuracyHistory({
          sourceType: "exercise",
          sourceKey: selectedExerciseId,
          limit: 1,
        });
        if (!mounted || !Array.isArray(items) || items.length === 0) {
          setSelectedLatestAccuracy(null);
          setSelectedExerciseLabel(null);
          return;
        }
        const latest = items[0];
        setSelectedLatestAccuracy(
          typeof latest.accuracy_pct === "number" ? latest.accuracy_pct : null
        );
        const option = EXERCISE_OPTIONS.find(
          (entry) => entry.id === selectedExerciseId
        );
        setSelectedExerciseLabel(option?.label ?? null);
      } catch (error) {
        if (!mounted) return;
        console.error("[Accuracy] failed to fetch selected latest", error);
      }
    }

    loadExerciseTrend();
    loadSelectedLatestAccuracy();
    return () => {
      mounted = false;
    };
  }, [selectedExerciseId]);

  const latestAccuracy =
    serverLatestAccuracy ?? readLatestAccuracy("exercise") ?? 0;
  const displayLatestAccuracy =
    selectedExerciseId === "all"
      ? latestAccuracy
      : selectedLatestAccuracy;
  const averageScore = useMemo(
    () => getAverageScore(weeklyAccuracyData),
    [weeklyAccuracyData]
  );
  const bestDay = useMemo(
    () => getBestDay(weeklyAccuracyData),
    [weeklyAccuracyData]
  );
  const needsAttention =
    typeof displayLatestAccuracy === "number" ? displayLatestAccuracy < 70 : false;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <TopBar />
      <div className="px-6 pb-28 pt-6">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <div className="text-xs font-bold tracking-[0.3em] text-blue-400 uppercase mb-3">
              Analysis
            </div>
            <h1 className="text-3xl font-black tracking-tight mb-2">
              운동 자세 분석 대시보드
            </h1>
            <p className="text-slate-400">
              요일별 평균 점수 추이를 한눈에 확인해보세요.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_0.9fr] gap-6">
            <section className="rounded-[32px] border border-slate-800 bg-slate-900/60 p-6">
              <div className="flex items-center gap-3 mb-5">
                <BarChart3 className="text-blue-400" size={20} />
                <h2 className="text-xl font-bold">
                  {selectedExerciseId === "all"
                    ? "주간 평균 점수 추이"
                    : "운동별 평균 추이"}
                </h2>
              </div>
              <div className="mb-4">
                <label className="text-xs text-slate-400 font-semibold block mb-2">
                  운동 선택
                </label>
                <select
                  value={selectedExerciseId}
                  onChange={(event) => setSelectedExerciseId(event.target.value)}
                  className="w-full md:w-72 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {EXERCISE_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={weeklyAccuracyData}>
                    <defs>
                      <linearGradient id="analysisScoreFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                        <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.03} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey="name"
                      tickLine={false}
                      axisLine={false}
                      stroke="#64748b"
                      interval={0}
                      tickMargin={8}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0f172a",
                        border: "1px solid rgba(148, 163, 184, 0.2)",
                        borderRadius: "14px",
                        color: "#fff",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke="#38bdf8"
                      strokeWidth={3}
                      fill="url(#analysisScoreFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="rounded-[32px] border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-6">
              <h2 className="text-xl font-bold mb-5">이번 주 요약</h2>

              <div className="space-y-4">
                <div className="rounded-2xl bg-slate-800/60 border border-slate-700 p-4">
                  <div className="text-slate-400 text-xs mb-1">가장 좋은 날</div>
                  <div className="text-2xl font-bold">{bestDay.name}</div>
                  <div className="text-sm text-blue-400 mt-1">
                    {Math.round(bestDay.score ?? 0)}점
                  </div>
                </div>

                <div className="rounded-2xl bg-slate-800/60 border border-slate-700 p-4">
                  <div className="text-slate-400 text-xs mb-1">추천 포인트</div>
                  <div className="text-sm leading-relaxed text-slate-200">
                    {latestAccuracy >= 85
                      ? "현재 점수가 좋아 유지 운동과 가벼운 가동성 루틴을 이어가는 것이 좋습니다."
                      : latestAccuracy >= 70
                        ? "측정 전후 스트레칭을 함께 진행하면 점수 안정화에 도움이 됩니다."
                        : "측정과 운동 전 기본 자세를 먼저 확인하고, 강도는 낮춰서 천천히 진행해보세요."}
                  </div>
                </div>

                <div className="rounded-2xl bg-slate-800/60 border border-slate-700 p-4">
                  <div className="text-slate-400 text-xs mb-1">관리 가이드</div>
                  <ul className="space-y-2 text-sm text-slate-300">
                    <li>주 3회 이상 측정하면 변화 추이를 더 정확히 볼 수 있습니다.</li>
                    <li>운동 직후와 휴식일 점수를 비교하면 컨디션 차이를 파악하기 좋습니다.</li>
                    <li>점수가 낮은 날은 강도보다 자세 정확도를 우선해보세요.</li>
                  </ul>
                </div>
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-slate-400 text-sm">최근 정확도</span>
                <Activity className="text-blue-400" size={18} />
              </div>
              <div className="text-5xl font-black mb-2">
                {typeof displayLatestAccuracy === "number" ? (
                  <>
                    {Math.round(displayLatestAccuracy)}
                    <span className="text-lg text-slate-500 ml-1">%</span>
                  </>
                ) : (
                  <span className="text-slate-500 text-3xl">-</span>
                )}
              </div>
              <p className="text-slate-400 text-sm">
                {selectedExerciseId !== "all"
                  ? selectedExerciseLabel
                    ? `${selectedExerciseLabel} 기준 점수입니다.`
                    : "선택한 운동 기준 점수입니다."
                  : latestExerciseLabel
                    ? `${latestExerciseLabel} 기준 점수입니다.`
                    : "가장 최근 운동 세션 기준 점수입니다."}
              </p>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-slate-400 text-sm">주간 평균</span>
                <TrendingUp className="text-emerald-400" size={18} />
              </div>
              <div className="text-5xl font-black mb-2">
                {averageScore}
                <span className="text-lg text-slate-500 ml-1">점</span>
              </div>
              <p className="text-slate-400 text-sm">
                {selectedExerciseId !== "all"
                  ? selectedExerciseLabel
                    ? `${selectedExerciseLabel} 주간 평균 점수입니다.`
                    : "선택한 운동 기준 주간 평균입니다."
                  : "이번 주 누적 기록을 기반으로 계산한 평균 점수입니다."}
              </p>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-slate-400 text-sm">집중 관리</span>
                {needsAttention ? (
                  <AlertTriangle className="text-amber-400" size={18} />
                ) : (
                  <CheckCircle2 className="text-green-400" size={18} />
                )}
              </div>
              <div className="text-2xl font-bold mb-2">
                {needsAttention ? "자세 교정 우선" : "안정적인 흐름"}
              </div>
              <p className="text-slate-400 text-sm">
                {needsAttention
                  ? "최근 점수가 낮아 스트레칭과 기본 자세 점검이 우선입니다."
                  : "현재 점수가 안정적입니다. 꾸준히 유지해보세요."}
              </p>
            </div>
          </div>
        </div>
      </div>
      <BottomNav activeTab="analysis" />
    </div>
  );
}
