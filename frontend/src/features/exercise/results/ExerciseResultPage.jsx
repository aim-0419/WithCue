import React, { useMemo, useState } from "react";
import {
  Share2,
  RefreshCw,
  ChevronRight,
  Download,
  X,
} from "lucide-react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  PolarAngleAxis,
} from "recharts";
import BodyFigure from "./components/BodyFigure";
import RegionMetricPanel from "./components/RegionMetricPanel";
import REGION_META from "./config/regionMeta";

const EXERCISE_REGION_RULES = {
  shoulder_front_raise_right: {
    defaultRegion: "right_arm",
    enabledRegions: ["right_arm"],
  },
  shoulder_front_raise_left: {
    defaultRegion: "left_arm",
    enabledRegions: ["left_arm"],
  },
  neck_rotation: {
    defaultRegion: "neck",
    enabledRegions: ["neck", "torso"],
  },
  straight_leg_raise_right: {
    defaultRegion: "right_leg",
    enabledRegions: ["pelvis", "right_leg"],
  },
  straight_leg_raise_left: {
    defaultRegion: "left_leg",
    enabledRegions: ["pelvis", "left_leg"],
  },
};

function clampScore(value, fallback = 0) {
  return Math.max(0, Math.min(100, Math.round(value ?? fallback)));
}

function formatMetricValue(value, unit = "") {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return `${value}${unit}`;
  return String(value);
}

function getStatusByRatio(value, target, lowThreshold = 0.8, warningThreshold = 0.95) {
  if (value == null) return "정보 없음";
  const ratio = Math.max(0, Math.min(1, Number(value) / Number(target)));
  if (ratio >= warningThreshold) return "양호";
  if (ratio >= lowThreshold) return "주의";
  return "부족";
}

function buildBodyMetricsFromRom(rom) {
  if (!rom || typeof rom !== "object") return null;

  const createMetric = (label, value, target, unit = "") => ({
    label,
    value: formatMetricValue(value, unit),
    target: target ? `목표 ${target}${unit}` : "—",
    status: value == null ? "정보 없음" : getStatusByRatio(value, target),
  });

  return {
    neck: {
      label: "목",
      joints: ["경추", "어깨선"],
      metrics: [
        createMetric(
          "좌우 회전 평균",
          rom.neck_rotation_left_max != null && rom.neck_rotation_right_max != null
            ? Math.round((Number(rom.neck_rotation_left_max) + Number(rom.neck_rotation_right_max)) / 2)
            : null,
          70,
          "°"
        ),
        createMetric(
          "좌우 회전 차이",
          rom.neck_rotation_left_max != null && rom.neck_rotation_right_max != null
            ? Math.abs(Number(rom.neck_rotation_left_max) - Number(rom.neck_rotation_right_max))
            : null,
          10,
          "°"
        ),
      ],
    },
    right_arm: {
      label: "오른쪽 팔",
      joints: ["어깨", "팔꿈치", "손목"],
      metrics: [
        createMetric("어깨 굴곡 최대", rom.shoulder_right_flexion_max, 150, "°"),
      ],
    },
    left_arm: {
      label: "왼쪽 팔",
      joints: ["어깨", "팔꿈치", "손목"],
      metrics: [
        createMetric("어깨 굴곡 최대", rom.shoulder_left_flexion_max, 150, "°"),
      ],
    },
    torso: {
      label: "몸통",
      joints: ["척추", "골반", "어깨선"],
      metrics: [
        {
          label: "몸통 회전 최대 (rep 평균)",
          value: rom.trunk_rotation_max_avg != null ? `${rom.trunk_rotation_max_avg}°` : "—",
          target: "목표 20° 이하",
          status: rom.trunk_rotation_max_avg == null ? "정보 없음"
            : rom.trunk_rotation_max_avg < 10 ? "양호"
            : rom.trunk_rotation_max_avg < 15 ? "주의"
            : "부족",
        },
      ],
    },
    pelvis: {
      label: "골반",
      joints: ["고관절", "골반선"],
      metrics: [
        createMetric("STS 완료", rom.sts_completed ? "완료" : "미완료", 1),
      ],
    },
    right_leg: {
      label: "오른쪽 다리",
      joints: ["고관절", "무릎", "발목"],
      metrics: [
        createMetric("무릎 신전 최대", rom.seated_knee_extension_right_max, 150, "°"),
        createMetric("앉은 자세 굴곡", rom.knee_flexion_at_sit_right, 120, "°"),
      ],
    },
    left_leg: {
      label: "왼쪽 다리",
      joints: ["고관절", "무릎", "발목"],
      metrics: [
        createMetric("무릎 신전 최대", rom.seated_knee_extension_left_max, 150, "°"),
        createMetric("앉은 자세 굴곡", rom.knee_flexion_at_sit_left, 120, "°"),
      ],
    },
  };
}

function buildSummaryFromRom(rom) {
  if (!rom || typeof rom !== "object") return null;
  const parts = [];
  if (rom.shoulder_left_flexion_max != null || rom.shoulder_right_flexion_max != null) {
    parts.push("어깨 ROM 분석 완료");
  }
  if (rom.neck_rotation_left_max != null || rom.neck_rotation_right_max != null) {
    parts.push("목 회전 분석 완료");
  }
  if (rom.sts_completed != null) {
    parts.push("STS 수행 여부 확인 완료");
  }
  return parts.length ? parts.join(" · ") : null;
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
  const sourceKey = exerciseResult?.sourceKey;
  const regionRule = EXERCISE_REGION_RULES[sourceKey];
  const defaultRegion = regionRule?.defaultRegion ?? "right_arm";
  const [selectedRegion, setSelectedRegion] = useState(defaultRegion);
  const [isRegionModalOpen, setIsRegionModalOpen] = useState(false);
  const userGender = exerciseResult?.userGender ?? "male";
  const romData = useMemo(() => {
    return exerciseResult?.rom || exerciseResult?.romData || null;
  }, [exerciseResult]);
  const derivedBodyMetrics = useMemo(() => buildBodyMetricsFromRom(romData), [romData]);
  const selectedRegionMeta = REGION_META[selectedRegion];
  const selectedRegionData =
    exerciseResult?.bodyMetrics?.[selectedRegion] ||
    derivedBodyMetrics?.[selectedRegion] ||
    null;
  const derivedScore = useMemo(() => {
    if (typeof scoreValue === "number") return scoreValue;
    if (typeof exerciseResult?.score === "number") return exerciseResult.score;
    return null;
  }, [exerciseResult, scoreValue]);
  const finalScore = derivedScore != null ? clampScore(derivedScore) : null;
  const derivedSummary = exerciseResult?.summary || buildSummaryFromRom(romData) || "이번 세션 기록이 자동 저장되었습니다.";
  const primaryMetricLabel = exerciseResult?.primaryMetricLabel || "완료 반복";
  const primaryMetricValue = exerciseResult?.primaryMetricValue || "0회";
  const secondaryMetricLabel = exerciseResult?.secondaryMetricLabel || "평균 정확도";
  const secondaryMetricValue = exerciseResult?.secondaryMetricValue || "기록 없음";
  const scoreGrade =
    finalScore == null ? "—" : finalScore >= 90 ? "우수" : finalScore >= 75 ? "양호" : "연습 필요";
  const scoreData = [{ name: "점수", value: finalScore ?? 0, fill: "#3b82f6" }];
  const summaryText = derivedSummary;
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
              {exerciseResult?.scoreLabel ?? "종합 정확도"}
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
                <span className="text-6xl font-black">{finalScore ?? "—"}</span>
                <span className="font-bold text-lg text-blue-500">
                  {scoreGrade}
                </span>
              </div>
            </div>

            <p className="text-center text-slate-300 text-sm mt-4 px-4 leading-relaxed">
              {summaryText}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 h-32">
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {primaryMetricLabel}
              </span>
              <span className="text-2xl font-bold">
                {primaryMetricValue}
              </span>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-slate-500 text-xs font-bold mb-1">
                {secondaryMetricLabel}
              </span>
              <span className="text-2xl font-bold flex items-center gap-1">
                {secondaryMetricValue}
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
            <div className="mb-5">
              <h3 className="text-lg font-bold">신체 부위별 수행 분석</h3>
              <p className="text-xs text-slate-500 mt-1">
                선택한 부위의 운동 수행 정확도와 주요 오류를 확인하세요.
              </p>
            </div>

            <div className="h-[calc(100%-56px)]">
              <div className="bg-slate-950/40 border border-slate-800 rounded-2xl p-5 h-full">
                <BodyFigure
                  gender={userGender}
                  selectedRegion={selectedRegion}
                  enabledRegions={regionRule?.enabledRegions}
                  onSelectRegion={(region) => {
                    setSelectedRegion(region);
                    setIsRegionModalOpen(true);
                  }}
                />
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

      {isRegionModalOpen ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm px-6">
          <div className="w-full max-w-xl rounded-3xl border border-slate-800 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.24em] text-slate-500">
                  Region Analysis
                </p>
                <h3 className="mt-1 text-lg font-bold text-white">
                  {selectedRegionMeta?.label ?? selectedRegionData.label}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsRegionModalOpen(false)}
                className="rounded-full border border-slate-700 bg-slate-950/70 p-2 text-slate-300 hover:border-slate-600 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5">
              {selectedRegionData ? (
                <RegionMetricPanel
                  selectedRegionData={{
                    ...selectedRegionData,
                    label: selectedRegionMeta?.label ?? selectedRegionData.label,
                    joints:
                      selectedRegionMeta?.joints ?? selectedRegionData.joints,
                  }}
                  description={selectedRegionMeta?.description}
                  className="border-0 bg-transparent p-0"
                />
              ) : (
                <p className="text-slate-400 text-sm text-center py-6">
                  이번 세션에서 측정된 데이터가 없습니다.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );

}