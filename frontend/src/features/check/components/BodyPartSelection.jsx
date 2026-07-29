// 가동범위검사 전 부위 선택
import { Dumbbell, Activity, ArrowRight, X, User, ScanLine } from "lucide-react";

export function BodyPartSelection({ onSelect, onClose, onSelectAll }) {
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
      name: "어깨",
      desc: "좌우 어깨 전방 거상 가동범위를 측정합니다.",
      icon: User,
      color: "from-blue-500 to-cyan-500",
    },
    {
      id: "neck",
      name: "목",
      desc: "목 좌우 회전 가동범위를 측정합니다.",
      icon: Activity,
      color: "from-indigo-500 to-purple-500",
    },
    {
      id: "knee",
      name: "무릎",
      desc: "좌우 무릎 신전 가동범위와 기립 능력을 측정합니다.",
      icon: Dumbbell,
      color: "from-emerald-500 to-teal-500",
    },
  ];

  const handleCardClick = (id) => {
    if (id === "all") {
      onSelectAll();
      return;
    }
    onSelect(id);
  };

  return (
    <div className="w-full h-dvh bg-slate-950 text-white flex flex-col relative p-8 overflow-hidden">
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[100px] pointer-events-none -mr-20 -mt-20" />

      <header className="flex justify-between items-center mb-12 z-10">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1.5 h-6 bg-blue-500 rounded-full" />
            <span className="text-blue-500 font-bold tracking-widest text-xs uppercase">
              Posture Check
            </span>
          </div>
          <h1 className="text-4xl font-bold">검사할 부위를 선택하세요</h1>
        </div>

        <button
          onClick={onClose}
          className="p-3 rounded-full bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <X size={24} />
        </button>
      </header>

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
              <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
