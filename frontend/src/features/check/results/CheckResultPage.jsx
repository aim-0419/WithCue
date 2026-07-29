// 자세 분석 완료 후 ROM 측정값 기반 결과를 표시하는 페이지
import React, { useState, useEffect } from "react";
import { CheckCircle2, AlertTriangle, AlertOctagon, RefreshCw, ChevronRight, X } from "lucide-react";
import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from "recharts";
import { getRomData } from "../../../utils/romStorage";
import { fetchRomLatest } from "../../../services/sessionApi";
import BodyFigure from "../../exercise/results/components/BodyFigure";

const ROM_NORMS = [
  { key: "shoulder", label: "어깨 전방 거상", leftKey: "shoulder_left_flexion_max",     rightKey: "shoulder_right_flexion_max",     ref: 150, asymThreshold: 15 },
  { key: "neck",     label: "목 회전",         leftKey: "neck_rotation_left_max",         rightKey: "neck_rotation_right_max",         ref: 70,  asymThreshold: 10 },
  { key: "knee",     label: "무릎 신전",        leftKey: "seated_knee_extension_left_max", rightKey: "seated_knee_extension_right_max", ref: 150, asymThreshold: 10,
    extras: [{ label: "무릎 올리기 (SLR)", leftKey: "straight_leg_raise_left_max", rightKey: "straight_leg_raise_right_max", ref: 80, asymThreshold: 10 }] },
];

// ROM 측정 키 → 바디 히트 영역 매핑
const NORM_TO_REGIONS = {
  shoulder: ["left_arm", "right_arm"],
  neck:     ["neck"],
  knee:     ["left_leg", "right_leg"],
};

const REGION_TO_NORM = {
  left_arm:  "shoulder",
  right_arm: "shoulder",
  neck:      "neck",
  left_leg:  "knee",
  right_leg: "knee",
};

// 같은 그룹 내 영역은 hover 시 동시에 빛남
const HOVER_GROUPS = {
  left_arm:  "shoulder",
  right_arm: "shoulder",
  left_leg:  "knee",
  right_leg: "knee",
  neck:      "neck",
};

function calcPartStats(lv, rv, ref, asymThreshold) {
  const leftPct  = lv != null ? Math.min(100, Math.round((lv / ref) * 100)) : null;
  const rightPct = rv != null ? Math.min(100, Math.round((rv / ref) * 100)) : null;
  const available = [lv, rv].filter(v => v != null);
  const avgAchieve = available.length
    ? available.reduce((s, v) => s + Math.min(100, (v / ref) * 100), 0) / available.length
    : 0;
  const diff = (lv != null && rv != null) ? Math.abs(lv - rv) : null;
  const symScore = diff !== null ? Math.max(0, 100 - (diff / asymThreshold) * 50) : 100;
  return { leftPct, rightPct, avgAchieve, diff, partScore: avgAchieve * 0.6 + symScore * 0.4 };
}

function calcRomScore(rom) {
  if (!rom) return null;
  let total = 0, count = 0;
  for (const n of ROM_NORMS) {
    const lv = rom[n.leftKey], rv = rom[n.rightKey];
    if (lv != null || rv != null) {
      total += calcPartStats(lv, rv, n.ref, n.asymThreshold).partScore;
      count++;
    }
    for (const extra of n.extras ?? []) {
      const elv = rom[extra.leftKey], erv = rom[extra.rightKey];
      if (elv != null || erv != null) {
        total += calcPartStats(elv, erv, extra.ref, extra.asymThreshold).partScore;
        count++;
      }
    }
  }
  return count === 0 ? null : Math.round(60 + (total / count) * 0.4);
}

function scoreGrade(score) {
  if (score >= 85) return { label: "양호",    color: "text-green-400" };
  if (score >= 70) return { label: "주의",    color: "text-amber-400" };
  return               { label: "교정 필요", color: "text-red-400" };
}

function scoreDesc(score) {
  if (score >= 85) return "가동범위가 기준치에 충분히 도달했고 좌우 균형도 양호합니다.";
  if (score >= 70) return "일부 부위의 가동범위가 제한되거나 좌우 불균형이 관찰됩니다.";
  return "가동범위가 기준치에 미치지 못하거나 좌우 비대칭이 뚜렷합니다.";
}

function achieveColor(pct) {
  if (pct >= 95) return "bg-green-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-red-500";
}

function asymLabel(diff, asymThreshold) {
  if (diff === null) return null;
  if (diff < asymThreshold * 0.5) return { text: `${diff}° 차이 · 균형`,   color: "text-green-400" };
  if (diff < asymThreshold)       return { text: `${diff}° 차이 · 주의`,   color: "text-amber-400" };
  return                                  { text: `${diff}° 차이 · 불균형`, color: "text-red-400"   };
}

function partComment(norm, lv, rv, stats) {
  const { avgAchieve, diff } = stats;
  const highAsym = diff !== null && diff >= norm.asymThreshold;
  const lowRom   = avgAchieve < 80;
  if (!lowRom && !highAsym) return { icon: CheckCircle2,  color: "green", text: `기준 ${norm.ref}° 이상 달성, 좌우 차이 ${norm.asymThreshold}° 미만으로 균형이 양호합니다.` };
  if (!lowRom && highAsym)  return { icon: AlertTriangle, color: "amber", text: `가동범위는 기준을 충족하지만 좌우 차이가 ${diff}°로 기준(${norm.asymThreshold}°)을 초과합니다.` };
  if (lowRom  && !highAsym) return { icon: AlertTriangle, color: "amber", text: `기준 ${norm.ref}° 대비 가동범위가 제한되어 있습니다. 꾸준한 스트레칭과 재활이 필요합니다.` };
  return                           { icon: AlertOctagon,  color: "red",   text: `가동범위가 기준 ${norm.ref}°에 미치지 못하고, 좌우 차이도 ${diff}°로 불균형합니다. 집중 재활을 권장합니다.` };
}

function formatDateTime(value) {
  const date = value ? new Date(value) : new Date();
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
}

// 부위 상세 모달
function PartModal({ normKey, rom, onClose }) {
  const norm = ROM_NORMS.find(n => n.key === normKey);
  if (!norm) return null;

  const lv = rom[norm.leftKey];
  const rv = rom[norm.rightKey];
  const stats = calcPartStats(lv, rv, norm.ref, norm.asymThreshold);
  const { leftPct, rightPct, diff } = stats;
  const asym = asymLabel(diff, norm.asymThreshold);
  const comment = partComment(norm, lv, rv, stats);
  const Icon = comment.icon;
  const cm = {
    green: { bg: "bg-green-500/10", border: "border-green-500/30", icon: "bg-green-500/20 text-green-400", text: "text-green-300" },
    amber: { bg: "bg-amber-500/10", border: "border-amber-500/30", icon: "bg-amber-500/20 text-amber-400", text: "text-amber-300" },
    red:   { bg: "bg-red-500/10",   border: "border-red-500/30",   icon: "bg-red-500/20 text-red-400",     text: "text-red-300"   },
  }[comment.color];

  return (
    <div className="fixed inset-x-0 top-0 portrait:top-[15dvh] portrait:h-[50dvh] landscape:inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50"
         onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-[360px] max-w-[90vw] shadow-2xl"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold">{norm.label}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          {[{ label: "왼쪽", val: lv, pct: leftPct }, { label: "오른쪽", val: rv, pct: rightPct }].map(({ label, val, pct }) => (
            <div key={label} className="bg-slate-800 rounded-xl p-3">
              <div className="flex items-baseline gap-1.5 mb-2">
                <span className="text-xs text-slate-500">{label}</span>
                <span className="text-2xl font-black">{val != null ? `${val}°` : "—"}</span>
              </div>
              {pct !== null && (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${achieveColor(pct)}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                  </div>
                  <span className="text-xs text-slate-400 w-8 text-right">{pct}%</span>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between text-xs mb-4 px-0.5">
          {asym ? <span className={`font-semibold ${asym.color}`}>{asym.text}</span> : <span />}
          <span className="text-slate-500">기준 {norm.ref}°</span>
        </div>

        {norm.extras?.map(extra => {
          const elv = rom[extra.leftKey];
          const erv = rom[extra.rightKey];
          if (elv == null && erv == null) return null;
          const es = calcPartStats(elv, erv, extra.ref, extra.asymThreshold);
          const easym = asymLabel(es.diff, extra.asymThreshold);
          return (
            <div key={extra.label} className="mb-4">
              <div className="text-xs text-slate-400 mb-2">{extra.label}</div>
              <div className="grid grid-cols-2 gap-3 mb-2">
                {[{ label: "왼쪽", val: elv, pct: es.leftPct }, { label: "오른쪽", val: erv, pct: es.rightPct }].map(({ label, val, pct }) => (
                  <div key={label} className="bg-slate-800 rounded-xl p-3">
                    <div className="flex items-baseline gap-1.5 mb-2">
                      <span className="text-xs text-slate-500">{label}</span>
                      <span className="text-2xl font-black">{val != null ? `${val}°` : "—"}</span>
                    </div>
                    {pct !== null && (
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${achieveColor(pct)}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                        </div>
                        <span className="text-xs text-slate-400 w-8 text-right">{pct}%</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between text-xs px-0.5">
                {easym ? <span className={`font-semibold ${easym.color}`}>{easym.text}</span> : <span />}
                <span className="text-slate-500">기준 {extra.ref}°</span>
              </div>
            </div>
          );
        })}

        <div className={`flex items-start gap-2.5 p-3 ${cm.bg} border ${cm.border} rounded-xl`}>
          <div className={`p-1.5 rounded-lg ${cm.icon} flex-shrink-0 mt-0.5`}>
            <Icon size={14} />
          </div>
          <p className={`text-xs leading-relaxed ${cm.text}`}>{comment.text}</p>
        </div>
      </div>
    </div>
  );
}

export function CheckResultView({ onClose, onRetry, onSelectOtherPart, timestamp }) {
  // 서버(최신 ROM)를 우선 사용하고, 미로그인/실패 시 localStorage 값으로 폴백한다.
  const [rom, setRom] = useState(() => getRomData());
  useEffect(() => {
    let alive = true;
    fetchRomLatest()
      .then((data) => {
        if (alive && data?.rom && Object.keys(data.rom).length) setRom(data.rom);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  const score = calcRomScore(rom) ?? 0;
  const { label: gradeLabel, color: gradeColor } = scoreGrade(score);
  const scoreData = [{ value: score, fill: score >= 85 ? "#22c55e" : score >= 70 ? "#eab308" : "#ef4444" }];

  const measuredKeys = new Set(
    ROM_NORMS.filter(n => rom[n.leftKey] || rom[n.rightKey]).map(n => n.key)
  );

  // 활성화할 바디 오버레이 영역 목록
  const enabledRegions = [...measuredKeys].flatMap(k => NORM_TO_REGIONS[k] ?? []);

  const [activeNorm, setActiveNorm] = useState(null);

  function handleRegionSelect(regionId) {
    const normKey = REGION_TO_NORM[regionId];
    if (normKey && measuredKeys.has(normKey)) {
      setActiveNorm(normKey);
    }
  }

  return (
    <div className="w-full h-full bg-slate-950 text-white flex flex-col relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-64 bg-gradient-to-b from-blue-900/20 to-transparent pointer-events-none" />

      <header className="flex items-center justify-between px-8 py-5 z-10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-2 h-7 bg-blue-500 rounded-full" />
          <h1 className="text-xl font-bold tracking-tight">가동범위 검사 결과</h1>
        </div>
        <div className="text-slate-400 text-sm">{formatDateTime(timestamp)}</div>
      </header>

      <main className="flex-1 grid grid-cols-12 gap-5 px-8 pb-8 z-10 min-h-0">

        {/* 왼쪽: 종합 점수 */}
        <div className="col-span-3 flex flex-col gap-4 min-h-0">
          <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-3xl p-5 flex flex-col items-center justify-center min-h-0">
            <p className="text-slate-400 font-bold mb-3 text-xs tracking-widest uppercase">ROM 종합 점수</p>
            <div className="relative w-40 h-40 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <RadialBarChart innerRadius="80%" outerRadius="100%" barSize={10} data={scoreData} startAngle={90} endAngle={-270}>
                  <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                  <RadialBar background dataKey="value" cornerRadius={30} />
                </RadialBarChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-5xl font-black">{score}</span>
                <span className={`font-bold text-sm ${gradeColor}`}>{gradeLabel}</span>
              </div>
            </div>
            <p className="text-center text-slate-300 text-xs mt-4 leading-relaxed">{scoreDesc(score)}</p>
          </div>

          <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 text-xs text-slate-400 leading-relaxed flex-shrink-0">
            <p className="font-bold text-slate-300 mb-2">점수 기준</p>
            <p>· ROM 달성도 60% + 균형 40%</p>
            <p className="mt-1.5 font-semibold text-slate-300">일반인 기준</p>
            <p>· 어깨 150° / 비대칭 15° 초과 시 감점</p>
            <p>· 목 70° / 비대칭 10° 초과 시 감점</p>
            <p>· 무릎 150° / 비대칭 10° 초과 시 감점</p>
          </div>
        </div>

        {/* 중간: 인체 도식 */}
        <div className="col-span-6 min-h-0">
          <div className="h-full bg-slate-900/30 border border-slate-800 rounded-3xl p-4 flex flex-col min-h-0">
            <BodyFigure
              gender="male"
              selectedRegion={null}
              enabledRegions={enabledRegions}
              onSelectRegion={handleRegionSelect}
              hoverGroups={HOVER_GROUPS}
            />
          </div>
        </div>

        {/* 오른쪽: 측정 부위 요약 + 액션 */}
        <div className="col-span-3 flex flex-col gap-4 min-h-0">
          <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-4 flex-shrink-0">
            <p className="text-xs font-bold text-slate-400 mb-3 tracking-wide uppercase">측정 완료 부위</p>
            <div className="flex flex-col gap-2">
              {ROM_NORMS.map(n => {
                const done = measuredKeys.has(n.key);
                return (
                  <button key={n.key}
                    onClick={done ? () => setActiveNorm(n.key) : undefined}
                    disabled={!done}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-semibold transition-colors
                      ${done
                        ? "bg-blue-600/20 border border-blue-500/40 text-blue-300 hover:bg-blue-600/30 cursor-pointer"
                        : "bg-slate-800/40 border border-slate-700/40 text-slate-600 cursor-default"
                      }`}>
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${done ? "bg-blue-400" : "bg-slate-600"}`} />
                    {n.label}
                    {done && <ChevronRight size={12} className="ml-auto" />}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex-1 bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 p-5 rounded-3xl flex flex-col justify-between min-h-0">
            <div>
              <h3 className="text-base font-bold mb-2">진단 완료</h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                측정 결과가 저장되었습니다. 권장 운동을 꾸준히 수행해 주세요.
              </p>
            </div>
            <div className="flex flex-col gap-2.5">
              <button onClick={onClose} className="w-full py-3.5 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-colors">
                메인으로 이동 <ChevronRight size={16} />
              </button>
              <button onClick={onSelectOtherPart} className="w-full py-3.5 bg-slate-700 hover:bg-slate-600 rounded-xl font-bold text-sm transition-colors">
                다른 부위 측정하기
              </button>
              <button onClick={onRetry} className="w-full py-3.5 bg-slate-800 hover:bg-slate-700 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-colors">
                <RefreshCw size={15} /> 재측정
              </button>
            </div>
          </div>
        </div>

      </main>

      {activeNorm && (
        <PartModal normKey={activeNorm} rom={rom} onClose={() => setActiveNorm(null)} />
      )}
    </div>
  );
}
