// src/pages/Exercise/ChooseExercisePage.jsx
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, LayoutGrid, User, Activity, Accessibility, X  } from "lucide-react";

const CATEGORIES = [
  { key: "전체", label: "전체 보기", sub: "맞춤형 진단과 인기 운동 프로그램을 확인하세요.", Icon: LayoutGrid },
  { key: "어깨", label: "어깨 / 목", sub: "상체 가동성·안정화", Icon: User },
  { key: "허리", label: "허리 / 코어", sub: "코어 안정화·통증 완화", Icon: Activity },
  { key: "무릎", label: "하체 / 무릎", sub: "균형·지지·무릎 안정화", Icon: Accessibility },
];


// 이미지 없으면 그라데이션으로도 돌아가게 cover 선택값 지원
const EXERCISES = [
  {
    id: "sh-001",
    category: "어깨",
    type: "WORKOUT",
    badgeColor: "blue",
    name: "덤벨 숄더 프레스",
    desc: "어깨 전면과 측면 근육을 강화하는 필수 운동",
    minutes: 15,
    level: "Medium",
    cover:
      "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?auto=format&fit=crop&w=1400&q=80",
  },
  {
    id: "sh-002",
    category: "어깨",
    type: "WORKOUT",
    badgeColor: "blue",
    name: "거북목 교정 스트레칭",
    desc: "목의 긴장을 풀고 경추 정렬을 돕습니다.",
    minutes: 10,
    level: "Easy",
    cover:
      "https://images.unsplash.com/photo-1574680096145-d05b474e2155?auto=format&fit=crop&w=1400&q=80",
  },
  {
    id: "hip-001",
    category: "허리",
    type: "WORKOUT",
    badgeColor: "blue",
    name: "허리 스트레칭",
    desc: "허리 주변 근육 이완으로 통증 완화",
    minutes: 8,
    level: "Easy",
    cover:
      "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?auto=format&fit=crop&w=1400&q=80",
  },
  {
    id: "kn-001",
    category: "무릎",
    type: "WORKOUT",
    badgeColor: "blue",
    name: "무릎 안정화",
    desc: "균형·지지 강화로 무릎 부담을 줄입니다.",
    minutes: 10,
    level: "Easy",
    cover:
      "https://images.unsplash.com/photo-1556817411-31ae72fa3ea0?auto=format&fit=crop&w=1400&q=80",
  },
];

export default function ChooseExercisePage() {
  const navigate = useNavigate();
  const [cat, setCat] = useState("전체");

  const activeCat = useMemo(
    () => CATEGORIES.find((c) => c.key === cat) || CATEGORIES[0],
    [cat]
  );

  const list = useMemo(() => {
    if (cat === "전체") return EXERCISES;
    return EXERCISES.filter((e) => e.category === cat);
  }, [cat]);

  return (
    <div className="cw-root">
      {/* Sidebar */}
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
              <span className="cw-iconBox">
                <c.Icon size={18} />
              </span>
              <span className="cw-itemText">{c.label}</span>
              <span className="cw-itemRight" />
            </button>
          ))}
        </nav>

        <div className="cw-sideBottom">
          <button className="cw-back" onClick={() => navigate(-1)}>
            ← 돌아가기
          </button>
        </div>
      </aside>

      {/* Main */}
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
              onClick={() => navigate(`/exercise/${e.id}`)}
            >
              <div className="cw-cover">
                {e.cover ? (
                  <img src={e.cover} alt="" className="cw-coverImg" />
                ) : (
                  <div className="cw-coverFallback" />
                )}
                <div className="cw-coverShade" />

                <div
                  className={
                    e.badgeColor === "pink" ? "cw-badge pink" : "cw-badge blue"
                  }
                >
                  {e.type}
                </div>
              </div>

              <div className="cw-cardBody">
                <div className="cw-cardName">{e.name}</div>
                <div className="cw-cardDesc">{e.desc}</div>

                <div className="cw-metaRow">
                  <div className="cw-metaLeft">
                    <span className="cw-meta">
                      ⏱ {e.minutes} min
                    </span>
                    {e.level ? (
                      <span className="cw-meta">• {e.level}</span>
                    ) : (
                      <span className="cw-meta" style={{ opacity: 0.6 }}>
                        • Analysis
                      </span>
                    )}
                  </div>

                  <div className="cw-play">
                    <ChevronRight size={18} />
                  </div>
                </div>
              </div>
            </button>
          ))}
        </section>
      </main>

      <style>{`
        /* layout */
        .cw-root{
          width:100%;
          height:100vh;
          overflow:hidden;
          display:flex;
          background: radial-gradient(1200px 800px at 60% 10%, rgba(59,130,246,0.18), transparent 55%),
                      radial-gradient(900px 700px at 40% 40%, rgba(99,102,241,0.14), transparent 60%),
                      #020617;
          color:#fff;
          font-family: inherit;
        }

        .cw-side{
          width: 280px;
          background: rgba(2,6,23,0.65);
          border-right:1px solid rgba(148,163,184,0.12);
          display:flex;
          flex-direction:column;
          padding: 18px 16px;
          box-sizing:border-box;
        }
        .cw-sideTop{ padding: 6px 6px 14px; }
        .cw-sideEyebrow{
          font-size: 11px;
          letter-spacing: 0.14em;
          color: #60a5fa;
          font-weight: 900;
        }
        .cw-sideTitle{
          margin-top: 6px;
          font-size: 22px;
          font-weight: 900;
        }

        .cw-menu{
          display:flex;
          flex-direction:column;
          gap:10px;
          padding-top: 10px;
        }
        .cw-item{
          width:100%;
          display:flex;
          align-items:center;
          gap:12px;
          padding: 14px 14px;
          border-radius: 14px;
          background: transparent;
          border: 1px solid transparent;
          color: rgba(226,232,240,0.78);
          cursor:pointer;
          font-weight: 900;
          text-align:left;
          font-family: inherit;
        }
        .cw-item:hover{
          background: rgba(15,23,42,0.55);
          border-color: rgba(148,163,184,0.10);
        }
        .cw-item.active{
          background: rgba(37,99,235,0.95);
          color:#fff;
          border-color: rgba(37,99,235,0.9);
        }
        .cw-itemDot{
          width: 18px;
          height: 18px;
          border-radius: 6px;
          background: rgba(148,163,184,0.14);
          border: 1px solid rgba(148,163,184,0.12);
          flex: 0 0 auto;
        }
        .cw-item.active .cw-itemDot{
          background: rgba(255,255,255,0.16);
          border-color: rgba(255,255,255,0.18);
        }
        .cw-itemText{ flex:1; font-size:14px; }
        .cw-itemRight{
          width: 6px;
          height: 6px;
          border-radius:999px;
          background: rgba(148,163,184,0.25);
        }
        .cw-item.active .cw-itemRight{
          background: rgba(255,255,255,0.85);
        }

        .cw-sideBottom{
          margin-top:auto;
          padding: 14px 6px 4px;
          border-top: 1px solid rgba(148,163,184,0.10);
        }
        .cw-back{
          width:100%;
          padding: 12px 12px;
          border-radius: 12px;
          background: rgba(15,23,42,0.6);
          border: 1px solid rgba(148,163,184,0.12);
          color: rgba(226,232,240,0.85);
          font-weight: 900;
          cursor:pointer;
          text-align:left;
          font-family: inherit;
        }
        .cw-back:hover{ border-color: rgba(148,163,184,0.25); }

        /* main */
        .cw-main{
          flex:1;
          overflow:auto;
          padding: 22px 26px 28px;
          box-sizing:border-box;
        }
        .cw-mainHeader{
          margin-bottom: 18px;
        }
        .cw-mainTitle{
          font-size: 28px;
          font-weight: 900;
          letter-spacing: -0.02em;
        }
        .cw-mainSub{
          margin-top: 6px;
          color: rgba(226,232,240,0.68);
          font-weight: 800;
          font-size: 13px;
        }

        /* grid */
        .cw-grid{
          display:grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 18px;
        }
        @media (max-width: 1200px){
          .cw-grid{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        @media (max-width: 860px){
          .cw-root{ flex-direction:column; }
          .cw-side{ width:100%; }
          .cw-grid{ grid-template-columns: 1fr; }
        }

        /* card */
        .cw-card{
          background: rgba(2,6,23,0.55);
          border: 1px solid rgba(148,163,184,0.10);
          border-radius: 18px;
          overflow:hidden;
          cursor:pointer;
          text-align:left;
          color:#fff;
          padding:0;
          font-family: inherit;
        }
        .cw-card:hover{
          border-color: rgba(148,163,184,0.22);
          transform: translateY(-1px);
        }
        .cw-cover{
          position:relative;
          height: 210px;
          background: rgba(15,23,42,0.85);
        }
        .cw-coverImg{
          position:absolute;
          inset:0;
          width:100%;
          height:100%;
          object-fit:cover;
          opacity:0.95;
        }
        .cw-coverFallback{
          position:absolute; inset:0;
          background: radial-gradient(600px 240px at 40% 10%, rgba(59,130,246,0.35), transparent 60%),
                      linear-gradient(180deg, rgba(15,23,42,0.9), rgba(2,6,23,0.9));
        }
        .cw-coverShade{
          position:absolute;
          inset:0;
          background: linear-gradient(180deg, rgba(2,6,23,0.15), rgba(2,6,23,0.92));
        }
        .cw-badge{
          position:absolute;
          top: 12px;
          left: 12px;
          font-size: 11px;
          font-weight: 900;
          padding: 6px 10px;
          border-radius: 10px;
          letter-spacing: 0.02em;
        }
        .cw-badge.blue{
          background: rgba(37,99,235,0.95);
        }
        .cw-badge.pink{
          background: rgba(244,63,94,0.95);
        }

        .cw-cardBody{
          padding: 16px 16px 14px;
        }
        .cw-cardName{
          font-size: 17px;
          font-weight: 900;
          margin-bottom: 6px;
        }
        .cw-cardDesc{
          font-size: 13px;
          color: rgba(226,232,240,0.72);
          font-weight: 800;
          line-height: 1.4;
          min-height: 36px;
        }
        .cw-metaRow{
          margin-top: 14px;
          display:flex;
          align-items:center;
          justify-content:space-between;
          padding-top: 12px;
          border-top: 1px solid rgba(148,163,184,0.10);
        }
        .cw-metaLeft{
          display:flex;
          gap:10px;
          align-items:center;
        }
        .cw-meta{
          font-size: 12px;
          font-weight: 900;
          color: rgba(226,232,240,0.70);
        }
        .cw-play{
          width: 34px;
          height: 34px;
          border-radius: 999px;
          background: rgba(15,23,42,0.85);
          border: 1px solid rgba(148,163,184,0.14);
          display:flex;
          align-items:center;
          justify-content:center;
          color: rgba(226,232,240,0.88);
        }
      `}</style>
    </div>
  );
}
