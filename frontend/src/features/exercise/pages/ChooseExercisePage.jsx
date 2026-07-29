// src/pages/Exercise/ChooseExercisePage.jsx
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, LayoutGrid, User, Activity, Accessibility, X, Play, CheckCircle2, AlertCircle, ArrowLeft } from "lucide-react";
import { getRomData } from "../../../utils/romStorage";
import "./ChooseExercisePage.css";

const ROM_REQUIRED = {
  shoulder_front_raise_left:  ["shoulder_left_flexion_max"],
  shoulder_front_raise_right: ["shoulder_right_flexion_max"],
  straight_leg_raise_left:    ["seated_knee_extension_left_max"],
  straight_leg_raise_right:   ["seated_knee_extension_right_max"],
  neck_rotation:              ["neck_rotation_left_max", "neck_rotation_right_max"],
};

const CATEGORIES = [
  { key: "전체", label: "전체 보기", sub: "맞춤형 진단과 인기 운동 프로그램을 확인하세요.", Icon: LayoutGrid },
  { key: "어깨", label: "어깨 / 목", sub: "상체 가동성·안정화", Icon: User },
  { key: "허리", label: "허리 / 코어", sub: "코어 안정화·통증 완화", Icon: Activity },
  { key: "무릎", label: "하체 / 무릎", sub: "균형·지지·무릎 안정화", Icon: Accessibility },
];

const EXERCISES = [
  {
    id: "shoulder_front_raise",
    category: "어깨",
    name: "어깨 전방 거상",
    desc: "팔을 앞쪽으로 들어 올리는 동작을 통해 어깨 전면 근육을 강화하고 안정적인 자세를 유지하는 연습입니다.",
    minutes: 15,
    level: "Medium",
    cover: "/images/exercises/arm_front_raise.webp",
    sideOptions: [
      { label: "왼쪽", id: "shoulder_front_raise_left" },
      { label: "오른쪽", id: "shoulder_front_raise_right" },
    ],
  },
  {
    id: "neck_rotation",
    category: "어깨",
    name: "목 좌우 돌리기",
    desc: "목의 긴장을 풀고 경추 정렬을 돕습니다.",
    minutes: 10,
    level: "Easy",
    cover: "/images/exercises/neck_rotation.webp",
  },
  {
    id: "straight_leg_raise",
    category: "무릎",
    name: "무릎 들어올리기",
    desc: "균형·지지 강화로 무릎 부담을 줄입니다.",
    minutes: 10,
    level: "Easy",
    cover: "/images/exercises/knee_raise.webp",
    sideOptions: [
      { label: "왼쪽", id: "straight_leg_raise_left" },
      { label: "오른쪽", id: "straight_leg_raise_right" },
    ],
  },
];

const EXERCISE_INTRO = {
  shoulder_front_raise_left: {
    name: "어깨 전방 거상 (왼쪽)",
    category: "어깨 / 목",
    level: "Medium",
    minutes: 15,
    cover: "/images/exercises/arm_front_raise.webp",
    goal: "어깨 전면 근육을 강화하고 어깨 관절 가동 범위를 늘립니다.",
    steps: [
      "발을 어깨 너비로 벌리고 바르게 서서 시작합니다.",
      "왼팔을 편안하게 내린 상태에서 준비합니다.",
      "숨을 내쉬면서 왼팔을 앞으로 천천히 들어올립니다.",
      "어깨 높이(90°)까지 올린 후 1~2초 유지합니다.",
      "숨을 들이쉬면서 천천히 제자리로 내립니다.",
    ],
    tips: [
      "어깨가 귀 쪽으로 올라가지 않도록 내린 채 진행하세요.",
      "팔꿈치를 과하게 구부리지 말고 편하게 핍니다.",
      "몸통이 앞뒤로 흔들리지 않게 상체를 세웁니다.",
    ],
  },
  shoulder_front_raise_right: {
    name: "어깨 전방 거상 (오른쪽)",
    category: "어깨 / 목",
    level: "Medium",
    minutes: 15,
    cover: "/images/exercises/arm_front_raise.webp",
    goal: "어깨 전면 근육을 강화하고 어깨 관절 가동 범위를 늘립니다.",
    steps: [
      "발을 어깨 너비로 벌리고 바르게 서서 시작합니다.",
      "오른팔을 편안하게 내린 상태에서 준비합니다.",
      "숨을 내쉬면서 오른팔을 앞으로 천천히 들어올립니다.",
      "어깨 높이(90°)까지 올린 후 1~2초 유지합니다.",
      "숨을 들이쉬면서 천천히 제자리로 내립니다.",
    ],
    tips: [
      "어깨가 귀 쪽으로 올라가지 않도록 내린 채 진행하세요.",
      "팔꿈치를 과하게 구부리지 말고 편하게 핍니다.",
      "몸통이 앞뒤로 흔들리지 않게 상체를 세웁니다.",
    ],
  },
  neck_rotation: {
    name: "목 좌우 돌리기",
    category: "어깨 / 목",
    level: "Easy",
    minutes: 10,
    cover: "/images/exercises/neck_rotation.webp",
    goal: "경추 가동성을 높이고 목 주변 근육의 긴장을 풀어줍니다.",
    steps: [
      "바른 자세로 앉거나 서서 정면을 바라봅니다.",
      "천천히 고개를 오른쪽으로 돌려 2~3초 유지합니다.",
      "통증 없이 최대한 돌릴 수 있는 범위까지만 움직입니다.",
      "중립 위치(정면)로 돌아옵니다.",
      "같은 방법으로 왼쪽으로 돌려 2~3초 유지합니다.",
    ],
    tips: [
      "몸통은 고정하고 목만 움직이세요.",
      "통증이 느껴지면 즉시 멈추고 범위를 줄이세요.",
      "빠르게 돌리지 말고 천천히 제어하며 움직입니다.",
    ],
  },
  straight_leg_raise_left: {
    name: "무릎 들어올리기 (왼쪽)",
    category: "하체 / 무릎",
    level: "Easy",
    minutes: 10,
    cover: "/images/exercises/knee_raise.webp",
    goal: "왼쪽 다리 근력을 강화하고 무릎 관절의 안정성을 높입니다.",
    steps: [
      "바른 자세로 서서 양발을 어깨 너비로 벌립니다.",
      "균형을 잡기 위해 필요하면 벽이나 의자를 가볍게 짚습니다.",
      "왼쪽 무릎을 천천히 최대한 높이 들어올립니다.",
      "1~2초 유지한 후 천천히 내려놓습니다.",
    ],
    tips: [
      "상체가 앞뒤로 기울지 않도록 허리를 곧게 세웁니다.",
      "무릎을 올릴 때 발끝이 바닥을 향하도록 합니다.",
      "통증이 느껴지면 즉시 멈추세요.",
    ],
  },
  straight_leg_raise_right: {
    name: "무릎 들어올리기 (오른쪽)",
    category: "하체 / 무릎",
    level: "Easy",
    minutes: 10,
    cover: "/images/exercises/knee_raise.webp",
    goal: "오른쪽 다리 근력을 강화하고 무릎 관절의 안정성을 높입니다.",
    steps: [
      "바른 자세로 서서 양발을 어깨 너비로 벌립니다.",
      "균형을 잡기 위해 필요하면 벽이나 의자를 가볍게 짚습니다.",
      "오른쪽 무릎을 천천히 최대한 높이 들어올립니다.",
      "1~2초 유지한 후 천천히 내려놓습니다.",
    ],
    tips: [
      "상체가 앞뒤로 기울지 않도록 허리를 곧게 세웁니다.",
      "무릎을 올릴 때 발끝이 바닥을 향하도록 합니다.",
      "통증이 느껴지면 즉시 멈추세요.",
    ],
  },
};

const LEVEL_COLOR = { Easy: "#22c55e", Medium: "#f59e0b", Hard: "#ef4444" };

export default function ChooseExercisePage() {
  const navigate = useNavigate();
  const [cat, setCat] = useState("전체");
  const [sidePrompt, setSidePrompt] = useState(null);
  const [introId, setIntroId] = useState(null);

  function goExercise(exerciseId) {
    setSidePrompt(null);
    setIntroId(exerciseId);
  }

  const activeCat = useMemo(
    () => CATEGORIES.find((c) => c.key === cat) || CATEGORIES[0],
    [cat]
  );

  const list = useMemo(() => {
    if (cat === "전체") return EXERCISES;
    return EXERCISES.filter((e) => e.category === cat);
  }, [cat]);

  const intro = introId ? (EXERCISE_INTRO[introId] ?? null) : null;

  return (
    <div className="cw-root">
      <aside className="cw-side">
        <div className="cw-sideTop">
          <div className="cw-sideEyebrow">SELECT WORKOUT</div>
          <div className="cw-sideTitle">운동 선택</div>
        </div>

        <nav className="cw-menu">
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              className={cat === c.key ? "cw-item active" : "cw-item"}
              onClick={() => setCat(c.key)}
            >
              <span className="cw-iconBox"><c.Icon size={18} /></span>
              <span className="cw-itemText">{c.label}</span>
              <span className="cw-itemRight" />
            </button>
          ))}
        </nav>

        <div className="cw-sideBottom">
          <button className="cw-back" onClick={() => navigate("/main")}>
            ← 돌아가기
          </button>
        </div>
      </aside>

      <main className="cw-main">
        <header className="cw-mainHeader">
          <div className="cw-mainTitle">{activeCat.label}</div>
          <div className="cw-mainSub">{activeCat.sub}</div>
        </header>

        <section className="cw-grid">
          {list.map((e) => (
            <button
              key={e.id}
              className="cw-card"
              onClick={() => {
                if (e.sideOptions && e.sideOptions.length > 0) {
                  setSidePrompt(e);
                } else {
                  goExercise(e.id);
                }
              }}
            >
              <div className="cw-cover">
                {e.cover ? (
                  <img src={e.cover} alt="" className="cw-coverImg" />
                ) : (
                  <div className="cw-coverFallback" />
                )}
                <div className="cw-coverShade" />
              </div>
              <div className="cw-cardBody">
                <div className="cw-cardName">{e.name}</div>
                <div className="cw-cardDesc">{e.desc}</div>
                <div className="cw-metaRow">
                  <div className="cw-metaLeft">
                    <span className="cw-meta">⏱ {e.minutes} min</span>
                    {e.level && <span className="cw-meta">• {e.level}</span>}
                  </div>
                  <div className="cw-play"><ChevronRight size={18} /></div>
                </div>
              </div>
            </button>
          ))}
        </section>
      </main>

      {/* 좌우 선택 모달 */}
      <div
        className="cw-modal"
        aria-hidden={!sidePrompt}
        style={{ opacity: sidePrompt ? 1 : 0, pointerEvents: sidePrompt ? "auto" : "none" }}
      >
        <div className="cw-modalCard">
          {sidePrompt && (
            <>
              <div className="cw-modalTop">
                <div>
                  <div className="cw-modalTitle">{sidePrompt.name}</div>
                  <div className="cw-modalSub">운동할 방향을 선택해주세요.</div>
                </div>
                <button className="cw-modalClose" onClick={() => setSidePrompt(null)} aria-label="닫기">
                  <X size={18} />
                </button>
              </div>
              <div className="cw-modalOptions">
                {sidePrompt.sideOptions.map((opt) => (
                  <button key={opt.id} className="cw-modalOption" onClick={() => goExercise(opt.id)}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 운동 안내 모달 */}
      {introId && intro && (
        <div className="cw-modal" style={{ alignItems: "center", overflowY: "auto" }}>
          <div className="cw-introCard">
            {/* 헤더 */}
            <div className="cw-introHeader">
              <button className="cw-introBack" onClick={() => setIntroId(null)}>
                <ArrowLeft size={16} />
                운동 선택
              </button>
              <button className="cw-modalClose" onClick={() => setIntroId(null)}>
                <X size={18} />
              </button>
            </div>

            {/* 히어로 */}
            <div className="cw-introHero">
              <div className="cw-introCover">
                {intro.cover && <img src={intro.cover} alt="" className="cw-introCoverImg" />}
                <div className="cw-introCoverShade" />
              </div>
              <div className="cw-introInfo">
                <div className="cw-introEyebrow">PRE-EXERCISE GUIDE</div>
                <h2 className="cw-introName">{intro.name}</h2>
                <div className="cw-introBadges">
                  <span className="cw-introBadge">{intro.category}</span>
                  <span className="cw-introBadge" style={{ color: LEVEL_COLOR[intro.level] ?? "#94a3b8", borderColor: LEVEL_COLOR[intro.level] ?? "#94a3b8" }}>
                    {intro.level}
                  </span>
                  <span className="cw-introBadge">⏱ {intro.minutes} min</span>
                </div>
                <p className="cw-introGoal">{intro.goal}</p>
              </div>
            </div>

            {/* 수행 방법 + 주의사항 */}
            <div className="cw-introContent">
              <div className="cw-introPanel">
                <div className="cw-introPanelTitle">
                  <CheckCircle2 size={16} style={{ color: "#60a5fa" }} />
                  수행 방법
                </div>
                <ol className="cw-introSteps">
                  {intro.steps.map((step, i) => (
                    <li key={i} className="cw-introStep">
                      <span className="cw-introStepNum">{i + 1}</span>
                      <span className="cw-introStepText">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="cw-introPanel">
                <div className="cw-introPanelTitle">
                  <AlertCircle size={16} style={{ color: "#f59e0b" }} />
                  주의사항
                </div>
                <ul className="cw-introTips">
                  {intro.tips.map((tip, i) => (
                    <li key={i} className="cw-introTip">
                      <span className="cw-introTipDot" />
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* 시작 버튼 */}
            <div className="cw-introFooter">
              <button className="cw-introStartBtn" onClick={() => navigate(`/exercise/${introId}`)}>
                <Play size={18} fill="currentColor" />
                운동 시작하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
