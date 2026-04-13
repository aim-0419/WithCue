import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { setAuthSession } from "../../../utils/authStorage";

const API_BASE = "http://192.168.0.25:8018/api/v1/auth";

export default function LoginPage() {
    const navigate = useNavigate();
    
    const [form, setForm] = useState({
        login_id: "",
        password: "",
    });

    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setForm((prev) => ({
            ...prev,
            [name]: value,
        }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError("");

        const payload = {
            login_id: form.login_id.trim(),
            password: form.password,
        };

        try{
            setLoading(true);

            const res = await fetch(`${API_BASE}/login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });

            const data = await res.json();

            if (!res.ok) {
                throw new Error(
                    typeof data.detail === "string"
                    ? data.detail
                    : JSON.stringify(data.detail)
                );
            }

            //토큰 저장
            setAuthSession({
              accessToken: data.access_token,
              tokenType: data.token_type || "bearer",
              userName: data.user_name,
              userId: data.user_id,
            });

            navigate("/main");
    } catch (err) {
      setError(err.message || "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
  <div style={{
    minHeight: "100vh",
    background: "#020617", // slate-950
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  }}>
    <form
      onSubmit={handleSubmit}
      style={{
        width: 360,
        background: "#0f172a", // slate-900
        padding: 32,
        borderRadius: 16,
        boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <h2 style={{ marginBottom: 8, color: "#fff" }}>
        다시 오셨네요 👋
      </h2>

      <p style={{ color: "#94a3b8", fontSize: 14 }}>
        오늘도 바른 자세로 시작해볼까요?
      </p>

      <input
        name="login_id"
        placeholder="아이디를 입력해주세요"
        value={form.login_id}
        onChange={handleChange}
        style={inputStyle}
      />

      <input
        type="password"
        name="password"
        placeholder="비밀번호를 입력해주세요"
        value={form.password}
        onChange={handleChange}
        style={inputStyle}
      />

      {error && (
        <div style={{ color: "#f87171", fontSize: 14 }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        style={{
          height: 44,
          background: "#6366f1",
          color: "#fff",
          border: "none",
          borderRadius: 8,
          cursor: "pointer",
        }}
      >
        {loading ? "로그인 중..." : "시작하기"}
      </button>

      <div
        onClick={() => navigate("/join")}
        style={{
          fontSize: 14,
          textAlign: "center",
          cursor: "pointer",
          color: "#94a3b8",
        }}
      >
        계정이 없으신가요?{" "}
        <span style={{ color: "#818cf8" }}>
          회원가입
        </span>
      </div>
    </form>
  </div>
);
}

const inputStyle = {
  height: 44,
  padding: "0 12px",
  borderRadius: 8,
  border: "1px solid #334155", // slate-700
  background: "#1e293b", // slate-800
  color: "#fff",
};
