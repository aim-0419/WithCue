import TopBar from "../../components/TopBar";
import BottomNav from "../../components/BottomNav";
import { clearAuthSession } from "../../utils/authStorage"; // 로그아웃
import { setAuthSession } from "../../utils/authStorage";
import { useNavigate } from "react-router-dom";

export default function MyPage() {
  const navigate = useNavigate();

  const recent = [
    { date: "01.21", name: "어깨 가동성 운동", duration: "15분" },
    { date: "01.20", name: "무릎 안정화 운동", duration: "10분" },
    { date: "01.19", name: "스트레칭", duration: "12분" },
  ];

  const userName =
    typeof window !== "undefined" ? localStorage.getItem("user_name") : "";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #ffffff, #f6f9ff)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <TopBar />
      <BottomNav activeTab="profile" />

      <div
        style={{
          width: "100%",
          maxWidth: 520,
          margin: "0 auto",
          padding: "18px 16px 24px",
          boxSizing: "border-box",
        }}
      >
        <section
          style={{
            background:
              "radial-gradient(120% 120% at 0% 0%, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0.00) 55%), linear-gradient(135deg, #2563eb 0%, #4f8cff 60%, #7aa8ff 100%)",
            borderRadius: 18,
            border: 0,
            boxShadow: "0 10px 30px rgba(2, 6, 23, 0.05)",
            padding: 18,
            color: "#fff",
          }}
        >
          <h1
            style={{
              fontWeight: 800,
              fontSize: 16,
              margin: "0 0 18px 0",
              opacity: 0.95,
            }}
          >
            {userName ? `${userName}님 안녕하세요 👋` : "안녕하세요 👋"}
          </h1>

          <div
            style={{
              fontSize: 26,
              fontWeight: 900,
              letterSpacing: "-0.02em",
              marginBottom: 14,
              textAlign: "center",
            }}
          >
            <span>오늘 1회</span>
            <span style={{ opacity: 0.8 }}> · </span>
            <span>이번주 3 / 5 회</span>
          </div>

          <div
            style={{
              textAlign: "center",
              fontSize: 14,
              opacity: 0.92,
            }}
          >
            오늘 운동을 잘 진행 중이에요
          </div>
        </section>

        <section style={{ marginTop: 16 }}>
          <div
            style={{
              fontWeight: 900,
              fontSize: 16,
              color: "#0f172a",
              margin: "10px 2px 10px",
            }}
          >
            최근 운동 기록
          </div>

          <div
            style={{
              background: "#fff",
              borderRadius: 18,
              border: "1px solid rgba(15, 23, 42, 0.10)",
              boxShadow: "0 10px 30px rgba(2, 6, 23, 0.05)",
              padding: "8px 0 10px",
            }}
          >
            {recent.map((r, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 16px",
                  borderTop: idx === 0 ? "none" : "1px solid rgba(15, 23, 42, 0.08)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    minWidth: 0,
                  }}
                >
                  <span style={{ opacity: 0.8 }}>📅</span>
                  <span
                    style={{
                      fontWeight: 800,
                      color: "#0f172a",
                    }}
                  >
                    {r.date}
                  </span>
                  <span
                    style={{
                      color: "#334155",
                      fontWeight: 700,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      maxWidth: 240,
                    }}
                  >
                    {r.name}
                  </span>
                </div>

                <div
                  style={{
                    color: "#0f172a",
                    fontWeight: 900,
                    flex: "0 0 auto",
                  }}
                >
                  {r.duration}
                </div>
              </div>
            ))}

            <button
              type="button"
              onClick={() => console.log("all records")}
              style={{
                width: "100%",
                border: "none",
                background: "transparent",
                cursor: "pointer",
                color: "#2563eb",
                fontWeight: 900,
                padding: "14px 16px 8px",
              }}
            >
              전체 기록 보기 &gt;
            </button>
          </div>
        </section>

        <section style={{ marginTop: 16 }}>
          <div
            style={{
              background: "#fff",
              borderRadius: 18,
              border: "1px solid rgba(15, 23, 42, 0.10)",
              boxShadow: "0 10px 30px rgba(2, 6, 23, 0.05)",
              overflow: "hidden",
            }}
          >
            <button
              type="button"
              onClick={() => console.log("voice settings")}
              style={{
                width: "100%",
                border: "none",
                background: "transparent",
                padding: "16px 16px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
                fontSize: 15,
                fontWeight: 900,
                color: "#0f172a",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span style={{ opacity: 0.85 }}>🔊</span>
                <span>음성 설정</span>
              </span>
              <span style={{ color: "#94a3b8", fontSize: 20 }}>›</span>
            </button>

            <div
              style={{
                height: 1,
                background: "rgba(15, 23, 42, 0.08)",
                margin: "0 16px",
              }}
            />

            <button
              type="button"
              onClick={() => console.log("my info")}
              style={{
                width: "100%",
                border: "none",
                background: "transparent",
                padding: "16px 16px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
                fontSize: 15,
                fontWeight: 900,
                color: "#0f172a",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span style={{ opacity: 0.85 }}>👤</span>
                <span>내 정보</span>
              </span>
              <span style={{ color: "#94a3b8", fontSize: 20 }}>›</span>
            </button>

            <div
              style={{
                height: 1,
                background: "rgba(15, 23, 42, 0.08)",
                margin: "0 16px",
              }}
            />

            <button
              type="button"
              onClick={() => {
                clearAuthSession();
                navigate("/login");
              }}
              style={{
                width: "100%",
                border: "none",
                background: "transparent",
                padding: "16px 16px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
                fontSize: 15,
                fontWeight: 900,
                color: "#ef4444",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span style={{ opacity: 0.85 }}>⏻</span>
                <span>로그아웃</span>
              </span>
              <span style={{ color: "#94a3b8", fontSize: 20 }}>›</span>
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}