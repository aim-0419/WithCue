import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  PolarAngleAxis,
} from "recharts";

function clampScore(value, fallback = 78) {
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

const CHECK_RESULT_META = {
  shoulder: {
    title: "어깨 자세 분석 결과",
    summary: "어깨 높이와 상체 정렬을 기준으로 현재 자세 상태를 분석했습니다.",
    positiveTitle: "상체 정렬 비교적 안정적",
    positiveBody: "상체 중심축이 크게 무너지지 않고 유지되었습니다.",
    cautionTitle: "어깨 전방 말림 경향",
    cautionBody: "어깨가 앞으로 말리지 않도록 흉곽 스트레칭과 견갑 안정화 운동이 도움됩니다.",
  },
  shoulder_left: {
    title: "왼쪽 어깨 자세 분석 결과",
    summary: "왼쪽 어깨 가동범위와 좌우 균형을 기준으로 분석했습니다.",
    positiveTitle: "왼쪽 어깨 가동 흐름 양호",
    positiveBody: "선택한 쪽 어깨 움직임이 비교적 안정적으로 관찰되었습니다.",
    cautionTitle: "왼쪽 어깨 보상 움직임 주의",
    cautionBody: "팔을 들 때 몸통이 같이 기울지 않도록 주의가 필요합니다.",
  },
  shoulder_right: {
    title: "오른쪽 어깨 자세 분석 결과",
    summary: "오른쪽 어깨 가동범위와 좌우 균형을 기준으로 분석했습니다.",
    positiveTitle: "오른쪽 어깨 가동 흐름 양호",
    positiveBody: "선택한 쪽 어깨 움직임이 비교적 안정적으로 관찰되었습니다.",
    cautionTitle: "오른쪽 어깨 보상 움직임 주의",
    cautionBody: "팔을 들 때 몸통이 같이 기울지 않도록 주의가 필요합니다.",
  },
  hip: {
    title: "허리 · 코어 분석 결과",
    summary: "골반 정렬과 코어 중심 유지 상태를 기준으로 분석했습니다.",
    positiveTitle: "골반 정렬 안정적",
    positiveBody: "좌우 골반 높이 차이가 크지 않고 중심 유지가 양호합니다.",
    cautionTitle: "코어 안정성 보완 필요",
    cautionBody: "다리 움직임 시 몸통이 함께 흔들리지 않도록 코어 안정화가 필요합니다.",
  },
  knee_left: {
    title: "왼쪽 무릎 분석 결과",
    summary: "왼쪽 무릎 굴곡과 하체 정렬 상태를 기준으로 분석했습니다.",
    positiveTitle: "하체 지지 흐름 양호",
    positiveBody: "선택한 하체의 지지와 움직임 흐름이 비교적 안정적입니다.",
    cautionTitle: "무릎 정렬 주의",
    cautionBody: "무릎이 안쪽으로 쏠리지 않도록 고관절과 엉덩이 근육 보강이 필요합니다.",
  },
  knee_right: {
    title: "오른쪽 무릎 분석 결과",
    summary: "오른쪽 무릎 굴곡과 하체 정렬 상태를 기준으로 분석했습니다.",
    positiveTitle: "하체 지지 흐름 양호",
    positiveBody: "선택한 하체의 지지와 움직임 흐름이 비교적 안정적입니다.",
    cautionTitle: "무릎 정렬 주의",
    cautionBody: "무릎이 안쪽으로 쏠리지 않도록 고관절과 엉덩이 근육 보강이 필요합니다.",
  },
  full_body: {
    title: "전신 자세 분석 결과",
    summary: "전신 정렬과 균형 상태를 바탕으로 현재 자세를 종합 분석했습니다.",
    positiveTitle: "전신 균형 비교적 양호",
    positiveBody: "전체적인 중심축과 정렬 흐름이 크게 무너지지 않았습니다.",
    cautionTitle: "세부 부위 교정 권장",
    cautionBody: "어깨, 골반, 무릎 정렬을 세부적으로 보완하면 더 안정적인 자세를 만들 수 있습니다.",
  },
};

export function CheckResultView({
  onClose,
  onRetry,
  onSelectOtherPart,
  scoreValue,
  timestamp,
  selectedPart,
}) {
  const finalScore = clampScore(scoreValue);
  const meta =
    CHECK_RESULT_META[selectedPart ?? "full_body"] ?? CHECK_RESULT_META.full_body;
  const scoreGrade =
    finalScore >= 85 ? "양호" : finalScore >= 70 ? "주의 필요" : "교정 권장";
  const scoreData = [{ name: "점수", value: finalScore, fill: "#eab308" }];

  return (
    <div className="w-full h-full bg-slate-950 text-white flex flex-col relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-64 bg-gradient-to-b from-amber-900/20 to-transparent pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-amber-600/10 rounded-full blur-3xl pointer-events-none" />

      <header className="flex items-center justify-between px-8 py-6 z-10">
        <div className="flex items-center gap-3">
          <div className="w-2 h-8 bg-amber-500 rounded-full" />
          <h1 className="text-2xl font-bold tracking-tight">{meta.title}</h1>
        </div>
        <div className="text-slate-400 text-sm font-medium">
          {formatDateTime(timestamp)}
        </div>
      </header>

      <main className="flex-1 grid grid-cols-12 gap-6 px-8 pb-8 z-10">
        <div className="col-span-4 flex flex-col gap-6">
          <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-3xl p-6 flex flex-col items-center justify-center">
            <h2 className="text-slate-400 font-bold mb-4 text-xs tracking-widest uppercase">
              신체 밸런스 점수
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
                <span className="font-bold text-lg text-amber-500">
                  {scoreGrade}
                </span>
              </div>
            </div>

            <p className="text-center text-slate-300 text-sm mt-4 px-4 leading-relaxed">
              {meta.summary}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 h-32">
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                분석 상태
              </span>
              <span className="text-2xl font-bold">
                {finalScore >= 85 ? "안정" : finalScore >= 70 ? "주의" : "교정"}
              </span>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                결과 등급
              </span>
              <span className="text-2xl font-bold flex items-center gap-1 text-amber-500">
                {scoreGrade}
                <AlertTriangle size={16} />
              </span>
            </div>
          </div>
        </div>

        <div className="col-span-5">
          <div className="h-full bg-slate-900/50 border border-slate-800 rounded-3xl p-6">
            <h3 className="text-lg font-bold mb-6">상세 진단 결과</h3>

            <div className="space-y-4">
              <div className="flex gap-4 p-4 bg-green-500/10 border border-green-500/20 rounded-2xl">
                <div className="bg-green-500/20 p-2 rounded-lg text-green-400">
                  <CheckCircle2 size={20} />
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">{meta.positiveTitle}</h4>
                  <p className="text-xs text-green-200/70 leading-relaxed">
                    {meta.positiveBody}
                  </p>
                </div>
              </div>

              <div className="flex gap-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl">
                <div className="bg-amber-500/20 p-2 rounded-lg text-amber-400">
                  <AlertOctagon size={20} />
                </div>
                <div>
                  <h4 className="font-bold text-sm mb-1">{meta.cautionTitle}</h4>
                  <p className="text-xs text-amber-200/70 leading-relaxed">
                    {meta.cautionBody}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-3">
          <div className="h-full bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 p-6 rounded-3xl flex flex-col justify-between">
            <div>
              <h3 className="text-lg font-bold mb-4">진단 완료</h3>
              <p className="text-slate-400 text-sm leading-relaxed">
                현재 자세 상태가 저장되었습니다. 권장 운동을 꾸준히 수행해 주세요.
              </p>
            </div>

            <div className="flex flex-col gap-3">
              <button
                onClick={onClose}
                className="w-full py-4 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                메인으로 이동
                <ChevronRight size={18} />
              </button>

              <button
                onClick={onSelectOtherPart}
                className="w-full py-4 bg-slate-700 hover:bg-slate-600 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                다른 부위 측정하기
              </button>

              <button
                onClick={onRetry}
                className="w-full py-4 bg-slate-800 hover:bg-slate-700 rounded-xl font-bold flex items-center justify-center gap-2"
              >
                <RefreshCw size={18} />
                재측정
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
