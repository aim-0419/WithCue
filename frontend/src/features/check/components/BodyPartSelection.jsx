// 가동범위검사 전 부위 선택

import React, { useState } from "react";
import { 
  Dumbbell,
  Activity,
  ArrowRight,
  X,
  User,
  ScanLine,
  ChevronLeft,  
} from "lucide-react";

/**
 * props
 * - onSelect(partId: string)
 * - onSelectAll(): void
 * - onClose()
 */
export function BodyPartSelection({ onSelect, onClose, onSelectAll }) {
  const [subSelection, setSubSelection] = useState(null);

  const sideSelectionConfig = {
    shoulder: {
      title: "어느 쪽 어깨를 검사할까요?",
      left: {
        id: "shoulder_left",
        alt: "Left Shoulder",
        label: "왼쪽 어깨",
        desc: "왼쪽 어깨와 상체 가동범위 집중 검사",
        image:
          "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?q=80&w=2000&auto=format&fit=crop",
      },
      right: {
        id: "shoulder_right",
        alt: "Right Shoulder",
        label: "오른쪽 어깨",
        desc: "오른쪽 어깨와 상체 가동범위 집중 검사",
        image:
          "https://images.unsplash.com/photo-1574680096145-d05b474e2155?q=80&w=2000&auto=format&fit=crop",
      },
    },
    knee: {
      title: "어느 쪽 무릎을 검사할까요?",
      left: {
        id: "knee_left",
        alt: "Left Knee",
        label: "왼쪽 무릎",
        desc: "왼쪽 무릎 관절 집중 검사",
        image:
          "https://images.unsplash.com/photo-1599058945522-28d584b6f0ff?q=80&w=2000&auto=format&fit=crop",
      },
      right: {
        id: "knee_right",
        alt: "Right Knee",
        label: "오른쪽 무릎",
        desc: "오른쪽 무릎 관절 집중 검사",
        image:
          "https://images.unsplash.com/photo-1552196563-55cd4e45efb3?q=80&w=2000&auto=format&fit=crop",
      },
    },
  };
  
  const bodyParts = [
     {
        id: "all",
        name: "전체 정밀 검사",
        badge: "ANALYSIS",
        desc: "AI 스캔을 통해 전신의 불균형과 자세를 종합 진단합니다.",
        icon: ScanLine,
        color: "from-pink-500 to-rose-500",
    },
    {
      id: "shoulder",
      name: "어깨 / 상체",
      desc: "거북목 교정과 어깨 안정성을 위한 스트레칭 및 가동범위 측정",
      icon: User,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: "hip",
      name: "허리 / 코어",
      desc: "하체 정렬과 균형을 확인하기 위한 가동범위 측정",
      icon: Activity,
      color: "from-indigo-500 to-purple-500",
    },
    {
      id: "knee",
      name: "무릎 / 하체",
      desc: "무릎 굽힘 가동범위와 하체 안정성 측정",
      icon: Dumbbell,
      color: "from-emerald-500 to-teal-500",
    },
  ];

  const handleCardClick = (id) => {
    if (id === "all") {
      onSelectAll();
      return;
    }

    if (sideSelectionConfig[id]) {
      setSubSelection(id);
      return;
    }

    onSelect(id);
  };

  const activeSideSelection = subSelection
    ? sideSelectionConfig[subSelection]
    : null;

  return (
    <div className="w-full h-full bg-slate-950 text-white flex flex-col relative p-8 overflow-hidden">
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[100px] pointer-events-none -mr-20 -mt-20" />

      {/* HEADER */}
      <header className="flex justify-between items-center mb-12 z-10">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-6 bg-blue-500 rounded-full" />
            <span className="text-blue-500 font-bold tracking-widest text-xs uppercase">
              {activeSideSelection ? "Detailed Selection" : "Posture Check"}
            </span>
          </div>
          <h1 className="text-4xl font-bold">
            {activeSideSelection
              ? activeSideSelection.title
              : "검사할 부위를 선택하세요"}
          </h1>
        </div>

        <button
          onClick={onClose}
          className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X size={24} />
        </button>
      </header>

      {/* ===================== */}
      {/* MAIN SELECTION */}
      {/* ===================== */}
      {subSelection === null && (
        <div className="grid grid-cols-4 gap-6 flex-1 z-10">
          {bodyParts.map((part) => (
            <button
              key={part.id}
              onClick={() => handleCardClick(part.id)}
              className="group relative flex flex-col text-left p-8 rounded-3xl bg-slate-900/60 border border-slate-800 hover:border-blue-500/50 hover:bg-slate-800/80 transition-all overflow-hidden"
            >
              <div
                className={`absolute inset-0 bg-gradient-to-br ${part.color} opacity-0 group-hover:opacity-10 transition-opacity duration-500`}
              />

              <div
                className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${part.color} flex items-center justify-center mb-6 shadow-lg`}
              >
                <part.icon size={28} className="text-white" />
              </div>

              {part.badge && (
                <span className="mb-2 w-fit px-2 py-1 text-[10px] font-bold rounded bg-pink-500/20 text-pink-400 tracking-wider border border-pink-500/20">
                  {part.badge}
                </span>
              )}

              <h3 className="text-2xl font-bold mb-3 group-hover:text-blue-400 transition-colors">
                {part.name}
              </h3>

              <p className="text-slate-400 text-sm leading-relaxed mb-8 pr-4">
                {part.desc}
              </p>

              <div className="mt-auto flex items-center gap-2 text-slate-500 text-sm font-bold group-hover:text-white transition-colors">
                검사 시작하기
                <ArrowRight
                  size={16}
                  className="group-hover:translate-x-1 transition-transform"
                />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ===================== */}
      {/* KNEE SUB SELECTION */}
      {/* ===================== */}
      {activeSideSelection && (
        <div className="flex-1 flex flex-col z-10">
          <div className="flex gap-6 h-full max-h-[420px]">
            {/* LEFT */}
            <button
              onClick={() => onSelect(activeSideSelection.left.id)}
              className="flex-1 group relative rounded-3xl overflow-hidden border border-slate-800 hover:border-blue-500 transition-all bg-slate-900/50"
            >
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-slate-950/90 z-10" />
              <img
                src={activeSideSelection.left.image}
                alt={activeSideSelection.left.alt}
                className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-80 group-hover:scale-105 transition-all duration-500"
              />
              <div className="absolute bottom-0 left-0 p-8 z-20 text-left">
                <span className="text-blue-400 font-bold text-sm block mb-2 uppercase">
                  Left Side
                </span>
                <h3 className="text-4xl font-bold mb-2">
                  {activeSideSelection.left.label}
                </h3>
                <p className="text-slate-300 text-sm">
                  {activeSideSelection.left.desc}
                </p>
              </div>
            </button>

            {/* RIGHT */}
            <button
              onClick={() => onSelect(activeSideSelection.right.id)}
              className="flex-1 group relative rounded-3xl overflow-hidden border border-slate-800 hover:border-blue-500 transition-all bg-slate-900/50"
            >
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-slate-950/90 z-10" />
              <img
                src={activeSideSelection.right.image}
                alt={activeSideSelection.right.alt}
                className="absolute inset-0 w-full h-full object-cover opacity-60 group-hover:opacity-80 group-hover:scale-105 transition-all duration-500"
              />
              <div className="absolute bottom-0 left-0 p-8 z-20 text-left">
                <span className="text-blue-400 font-bold text-sm block mb-2 uppercase">
                  Right Side
                </span>
                <h3 className="text-4xl font-bold mb-2">
                  {activeSideSelection.right.label}
                </h3>
                <p className="text-slate-300 text-sm">
                  {activeSideSelection.right.desc}
                </p>
              </div>
            </button>
          </div>

          <div className="mt-8">
            <button
              onClick={() => setSubSelection(null)}
              className="flex items-center gap-2 text-slate-400 hover:text-white px-4 py-2 rounded-lg hover:bg-slate-900 transition-colors"
            >
              <ChevronLeft size={20} />
              이전 단계로 돌아가기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
