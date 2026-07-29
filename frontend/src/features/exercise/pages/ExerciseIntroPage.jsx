// 운동 시작 전 수행 방법을 안내하는 인트로 화면.
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, CheckCircle2, AlertCircle } from "lucide-react";
import "./ExerciseIntroPage.css";

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
      "동작을 반복합니다.",
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
      "동작을 반복합니다.",
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
      "좌우 교대로 반복합니다.",
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
      "동작을 반복합니다.",
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
      "동작을 반복합니다.",
    ],
    tips: [
      "상체가 앞뒤로 기울지 않도록 허리를 곧게 세웁니다.",
      "무릎을 올릴 때 발끝이 바닥을 향하도록 합니다.",
      "통증이 느껴지면 즉시 멈추세요.",
    ],
  },
  bird_dog: {
    name: "버드독",
    category: "허리 / 코어",
    level: "Easy",
    minutes: 8,
    cover: "/images/exercises/birddog.webp",
    goal: "코어 안정성과 좌우 팔다리 협응 능력을 기릅니다.",
    steps: [
      "손과 무릎이 바닥에 닿는 네 발 기기 자세로 시작합니다.",
      "손은 어깨 아래, 무릎은 골반 아래에 위치시킵니다.",
      "코어에 힘을 주고 허리를 수평으로 유지합니다.",
      "오른팔과 왼다리를 동시에 앞뒤로 뻗어 2~3초 유지합니다.",
      "천천히 제자리로 내리고 반대편(왼팔, 오른다리)으로 반복합니다.",
    ],
    tips: [
      "허리가 아치형으로 꺾이지 않도록 복부에 힘을 줍니다.",
      "골반이 한쪽으로 기울지 않게 수평을 유지하세요.",
      "팔과 다리를 바닥과 평행하게 뻗는 것이 목표입니다.",
    ],
  },
};

const LEVEL_COLOR = {
  Easy: "#22c55e",
  Medium: "#f59e0b",
  Hard: "#ef4444",
};

export default function ExerciseIntroPage() {
  const navigate = useNavigate();
  const { exerciseId } = useParams();

  const intro = EXERCISE_INTRO[exerciseId] ?? {
    name: "운동 안내",
    category: "재활",
    level: "Easy",
    minutes: 10,
    cover: null,
    goal: "올바른 자세로 운동을 수행합니다.",
    steps: ["카메라 앞에 자리를 잡고 운동을 시작합니다."],
    tips: ["통증이 있으면 즉시 멈추세요."],
  };

  return (
    <div className="ei-root">
      <header className="ei-header">
        <button className="ei-back" onClick={() => navigate("/choose-exercise")}>
          <ArrowLeft size={18} />
          운동 선택
        </button>
      </header>

      <main className="ei-main">
        <section className="ei-hero">
          <div className="ei-cover">
            {intro.cover ? (
              <img src={intro.cover} alt="" className="ei-coverImg" />
            ) : (
              <div className="ei-coverFallback" />
            )}
            <div className="ei-coverShade" />
          </div>

          <div className="ei-heroInfo">
            <div className="ei-eyebrow">PRE-EXERCISE GUIDE</div>
            <h1 className="ei-name">{intro.name}</h1>
            <div className="ei-badges">
              <span className="ei-badge">{intro.category}</span>
              <span
                className="ei-badge"
                style={{ color: LEVEL_COLOR[intro.level] ?? "#94a3b8", borderColor: LEVEL_COLOR[intro.level] ?? "#94a3b8" }}
              >
                {intro.level}
              </span>
              <span className="ei-badge">⏱ {intro.minutes} min</span>
            </div>
            <p className="ei-goal">{intro.goal}</p>
          </div>
        </section>

        <section className="ei-content">
          <div className="ei-panel">
            <div className="ei-panelTitle">
              <CheckCircle2 size={18} style={{ color: "#60a5fa" }} />
              수행 방법
            </div>
            <ol className="ei-steps">
              {intro.steps.map((step, i) => (
                <li key={i} className="ei-step">
                  <span className="ei-stepNum">{i + 1}</span>
                  <span className="ei-stepText">{step}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="ei-panel">
            <div className="ei-panelTitle">
              <AlertCircle size={18} style={{ color: "#f59e0b" }} />
              주의사항
            </div>
            <ul className="ei-tips">
              {intro.tips.map((tip, i) => (
                <li key={i} className="ei-tip">
                  <span className="ei-tipDot" />
                  {tip}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div className="ei-footer">
          <button
            className="ei-startBtn"
            onClick={() => navigate(`/exercise/${exerciseId}`)}
          >
            <Play size={20} fill="currentColor" />
            운동 시작하기
          </button>
        </div>
      </main>
    </div>
  );
}
