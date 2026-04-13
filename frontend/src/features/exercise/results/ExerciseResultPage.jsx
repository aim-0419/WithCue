import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Share2,
  RefreshCw,
  ChevronRight,
  Download,
} from "lucide-react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  PolarAngleAxis,
} from "recharts";

function clampScore(value, fallback = 0) {
  return Math.max(0, Math.min(100, Math.round(value ?? fallback)));
}

function formatDateTime(value) {
  const date = value ? new Date(value) : new Date();
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function formatExerciseDuration(seconds) {
  const safeSeconds = Math.max(0, Math.round(seconds ?? 0));
  const minutes = String(Math.floor(safeSeconds / 60)).padStart(2, "0");
  const secs = String(safeSeconds % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
}

export function ExerciseResultView({
  onClose,
  onRetry,
  onChooseExercise,
  scoreValue,
  timestamp,
  exerciseResult,
}) {
  const finalScore = clampScore(scoreValue);
  const scoreGrade =
    finalScore >= 90 ? "우수" : finalScore >= 75 ? "양호" : "연습 필요";
  const scoreData = [{ name: "점수", value: finalScore, fill: "#3b82f6" }];

  return (
    <div className="w-full h-full bg-slate-950 text-white flex flex-col relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-64 bg-gradient-to-b from-blue-900/20 to-transparent pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      <header className="flex items-center justify-between px-8 py-6 z-10">
        <div className="flex items-center gap-3">
          <div className="w-2 h-8 bg-blue-600 rounded-full" />
          <h1 className="text-2xl font-bold tracking-tight">
            {exerciseResult?.title ?? "운동 수행 결과 리포트"}
          </h1>
        </div>
        <div className="text-slate-400 text-sm font-medium">
          {formatDateTime(timestamp)}
        </div>
      </header>

      <main className="flex-1 grid grid-cols-12 gap-6 px-8 pb-8 z-10">
        <div className="col-span-4 flex flex-col gap-6">
          <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-3xl p-6 flex flex-col items-center justify-center">
            <h2 className="text-slate-400 font-bold mb-4 text-xs tracking-widest uppercase">
              {exerciseResult?.scoreLabel ?? "운동 수행 점수"}
            </h2>

            <div className="relative w-48 h-48 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart
                  innerRadius="80%"
                  outerRadius="100%"
                  barSize={10}
                  data={scoreData}
                  startAngle={90}
                  endAngle={-270}
                >
                  <PolarAngleAxis
                    type="number"
                    domain={[0, 100]}
                    angleAxisId={0}
                    tick={false}
                  />
                  <RadialBar background dataKey="value" cornerRadius={30} />
                </RadialBarChart>
              </ResponsiveContainer>

              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-6xl font-black">{finalScore}</span>
                <span className="font-bold text-lg text-blue-500">
                  {scoreGrade}
                </span>
              </div>
            </div>

            <p className="text-center text-slate-300 text-sm mt-4 px-4 leading-relaxed">
              {exerciseResult?.summary ??
                "이번 세션 기록이 자동 저장되었습니다. 꾸준히 반복하면 안정성이 더 좋아질 수 있습니다."}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 h-32">
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {exerciseResult?.primaryMetricLabel ?? "운동 시간"}
              </span>
              <span className="text-2xl font-bold">
                {exerciseResult?.primaryMetricValue ?? "00:00"}
              </span>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {exerciseResult?.secondaryMetricLabel ?? "반복 횟수"}
              </span>
              <span className="text-2xl font-bold flex items-center gap-1">
                {exerciseResult?.secondaryMetricValue ?? "0회"}
                {exerciseResult?.secondaryMetricSubValue ? (
                  <span className="text-sm text-slate-500 font-normal">
                    {exerciseResult.secondaryMetricSubValue}
                  </span>
                ) : null}
              </span>
            </div>
          </div>
        </div>

        <div className="col-span-5">
          <div className="h-full bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
            <h3 className="text-lg font-bold mb-6">운동 수행 피드백</h3>

            <div className="space-y-4">
              <div className="flex gap-4 p-4 bg-green-500/10 border border-green-500/20 rounded-2xl">
                <div className="bg-green-500/20 p-2 rounded-lg text-green-400">
                  <CheckCircle2 size={20} />
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">
                    {exerciseResult?.positiveTitle ?? "세션 흐름 안정적"}
                  </h4>
                  <p className="text-xs text-green-200/70 leading-relaxed">
                    {exerciseResult?.positiveBody ??
                      "운동을 꾸준히 이어가며 전체 흐름을 유지했습니다."}
                  </p>
                </div>
              </div>

              <div className="flex gap-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl">
                <div className="bg-amber-500/20 p-2 rounded-lg text-amber-400">
                  <AlertTriangle size={20} />
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">
                    {exerciseResult?.cautionTitle ?? "자세 정확도 보완"}
                  </h4>
                  <p className="text-xs text-amber-200/70 leading-relaxed">
                    {exerciseResult?.cautionBody ??
                      "속도보다 정확한 자세를 우선해 다음 세션도 이어가보세요."}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-3">
          <div className="h-full bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 p-6 rounded-3xl flex flex-col justify-between">
            <div>
              <h3 className="text-lg font-bold mb-4">세션 완료</h3>
              <p className="text-slate-400 text-sm leading-relaxed">
                운동 결과는 자동으로 저장되었습니다. 다음 운동을 이어가거나 메인으로 돌아갈 수 있습니다.
              </p>
            </div>

            <div className="flex flex-col gap-3">
              <button
                onClick={onClose}
                className="w-full py-4 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                나가기
                <ChevronRight size={18} />
              </button>

              <button
                onClick={onChooseExercise}
                className="w-full py-4 bg-slate-800 hover:bg-slate-700 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                다른 운동하기
                <ChevronRight size={18} />
              </button>

              <button
                onClick={onRetry}
                className="w-full py-4 bg-slate-800 hover:bg-slate-700 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                <RefreshCw size={18} />
                다시 운동
              </button>

              <div className="flex gap-3 mt-2">
                <button className="flex-1 py-3 bg-slate-900 border border-slate-700 rounded-xl flex items-center justify-center">
                  <Share2 size={18} />
                </button>
                <button className="flex-1 py-3 bg-slate-900 border border-slate-700 rounded-xl flex items-center justify-center">
                  <Download size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
