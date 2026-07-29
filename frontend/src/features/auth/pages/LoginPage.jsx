import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { setAuthSession } from "../../../utils/authStorage";
import { getApiBase } from "../../../services/runtimeConfig";

const API_BASE = `${getApiBase()}/api/v1/auth`;

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
              userGender: data.gender,
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
    minHeight: "100%",
    background: "#020617",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "1.5rem",
  }}>
    <form
      onSubmit={handleSubmit}
      style={{
        width: "28rem",
        background: "#0f172a",
        padding: "2.5rem",
        borderRadius: "1rem",
        boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
        display: "flex",
        flexDirection: "column",
        gap: "1.25rem",
      }}
    >
      <h2 style={{ marginBottom: "0.5rem", color: "#fff", fontSize: "1.5rem" }}>
        다시 오셨네요 👋
      </h2>

      <p style={{ color: "#94a3b8", fontSize: "1rem" }}>
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
        <div style={{ color: "#f87171", fontSize: "0.875rem" }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        style={{
          height: "3.25rem",
          background: "#6366f1",
          color: "#fff",
          border: "none",
          borderRadius: "0.5rem",
          cursor: "pointer",
        }}
      >
        {loading ? "로그인 중..." : "시작하기"}
      </button>

      <div
        onClick={() => navigate("/join")}
        style={{
          fontSize: "0.875rem",
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
  height: "3.25rem",
  padding: "0 0.75rem",
  borderRadius: "0.5rem",
  border: "1px solid #334155",
  background: "#1e293b",
  color: "#fff",
};
