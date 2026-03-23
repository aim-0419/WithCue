import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setAuthSession } from "../../utils/authStorage";

export default function RegisterPage() {
  const navigate = useNavigate();

  const API_BASE =
    import.meta.env.VITE_API_BASE || "http://192.168.0.188:8018/api/v1/auth";

  const [form, setForm] = useState({
    login_id: "",
    user_name: "",
    phone_number: "",
    password: "",
    passwordConfirm: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const formatPhone = (value) => {
    const numbers = value.replace(/\D/g, "").slice(0, 11);
    if (numbers.length < 4) return numbers;
    if (numbers.length < 8) return `${numbers.slice(0, 3)}-${numbers.slice(3)}`;
    return `${numbers.slice(0, 3)}-${numbers.slice(3, 7)}-${numbers.slice(7)}`;
  };

  const handleChange = (e) => {
    const { name, value } = e.target;

    if (name === "phone_number") {
      setForm((prev) => ({
        ...prev,
        phone_number: formatPhone(value),
      }));
      return;
    }

    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const validate = () => {
    if (!form.login_id.trim()) return "아이디를 입력해주세요.";
    if (form.login_id.trim().length < 4) return "아이디는 4자 이상 입력해주세요.";
    if (form.login_id.trim().length > 50) return "아이디는 50자 이하로 입력해주세요.";

    if (!form.user_name.trim()) return "이름을 입력해주세요.";
    if (form.user_name.trim().length > 100) return "이름은 100자 이하로 입력해주세요.";

    const phone = form.phone_number.replace(/\D/g, "");
    if (!phone) return "전화번호를 입력해주세요.";
    if (phone.length < 4) return "전화번호는 4자 이상 입력해주세요.";
    if (phone.length > 20) return "전화번호는 20자 이하로 입력해주세요.";

    if (!form.password) return "비밀번호를 입력해주세요.";
    if (form.password.length < 4) return "비밀번호는 4자 이상 입력해주세요.";
    if (form.password.length > 128) return "비밀번호는 128자 이하로 입력해주세요.";

    if (!form.passwordConfirm) return "비밀번호 확인을 입력해주세요.";
    if (form.password !== form.passwordConfirm) return "비밀번호가 일치하지 않습니다.";

    return "";
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    const err = validate();
    if (err) {
      setError(err);
      return;
    }

    const payload = {
      login_id: form.login_id.trim(),
      user_name: form.user_name.trim(),
      phone_number: form.phone_number.replace(/\D/g, ""),
      password: form.password,
    };

    try {
      setLoading(true);

      const res = await fetch(`${API_BASE}/register`, {
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

      setAuthSession({
              accessToken: data.access_token,
              tokenType: data.token_type || "bearer",
              userName: data.user_name,
              userId: data.user_id,
            });

      navigate("/login");
    } catch (err) {
      setError(err.message || "회원가입 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const loginIdValid =
    form.login_id.trim().length >= 4 && form.login_id.trim().length <= 50;
  const userNameValid =
    form.user_name.trim().length >= 1 && form.user_name.trim().length <= 100;
  const phoneDigits = form.phone_number.replace(/\D/g, "");
  const phoneValid = phoneDigits.length >= 4 && phoneDigits.length <= 20;
  const passwordValid =
    form.password.length >= 4 && form.password.length <= 128;
  const passwordConfirmValid =
    !!form.passwordConfirm && form.password === form.passwordConfirm;

  const labelClass = "block text-sm font-medium text-slate-200 mb-2";
  const inputClass =
    "w-full h-12 px-4 rounded-2xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:border-cyan-400 outline-none";
  const hintClass = "mt-2 text-xs";
  const getHintColor = (value, valid) => {
    if (!value) return "text-slate-400";
    return valid ? "text-emerald-400" : "text-slate-400";
  };

  return (
    <div className="min-h-dvh bg-slate-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-3xl p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-white text-center">회원가입</h1>
        <p className="text-slate-400 text-sm text-center mt-2 mb-6">
          계정을 생성하세요
        </p>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className={labelClass}>
              아이디 <span className="text-rose-400">*</span>
            </label>
            <input
              name="login_id"
              placeholder="아이디를 입력해주세요"
              value={form.login_id}
              onChange={handleChange}
              className={inputClass}
            />
            <p className={`${hintClass} ${getHintColor(form.login_id, loginIdValid)}`}>
              4자 이상 50자 이하
            </p>
          </div>

          <div>
            <label className={labelClass}>
              이름 <span className="text-rose-400">*</span>
            </label>
            <input
              name="user_name"
              placeholder="이름을 입력해주세요"
              value={form.user_name}
              onChange={handleChange}
              className={inputClass}
            />
            <p className={`${hintClass} ${getHintColor(form.user_name, userNameValid)}`}>
              1자 이상 100자 이하
            </p>
          </div>

          <div>
            <label className={labelClass}>
              전화번호 <span className="text-rose-400">*</span>
            </label>
            <input
              name="phone_number"
              placeholder="010-1234-5678"
              value={form.phone_number}
              onChange={handleChange}
              maxLength={13}
              inputMode="numeric"
              className={inputClass}
            />
            <p className={`${hintClass} ${getHintColor(phoneDigits, phoneValid)}`}>
              4자 이상 20자 이하 / 숫자 입력 시 자동 하이픈
            </p>
          </div>

          <div>
            <label className={labelClass}>
              비밀번호 <span className="text-rose-400">*</span>
            </label>
            <input
              type="password"
              name="password"
              placeholder="비밀번호를 입력해주세요"
              value={form.password}
              onChange={handleChange}
              className={inputClass}
            />
            <p className={`${hintClass} ${getHintColor(form.password, passwordValid)}`}>
              4자 이상 128자 이하
            </p>
          </div>

          <div>
            <label className={labelClass}>
              비밀번호 확인 <span className="text-rose-400">*</span>
            </label>
            <input
              type="password"
              name="passwordConfirm"
              placeholder="비밀번호를 다시 입력해주세요"
              value={form.passwordConfirm}
              onChange={handleChange}
              className={inputClass}
            />
            <p
              className={`${hintClass} ${
                !form.passwordConfirm
                  ? "text-slate-400"
                  : passwordConfirmValid
                  ? "text-emerald-400"
                  : "text-rose-400"
              }`}
            >
              {!form.passwordConfirm
                ? "비밀번호를 다시 입력해주세요"
                : passwordConfirmValid
                ? "비밀번호가 일치합니다"
                : "비밀번호가 일치하지 않습니다"}
            </p>
          </div>

          {error && <div className="text-rose-400 text-sm">{error}</div>}

          <button
            type="submit"
            disabled={loading}
            className="w-full h-12 rounded-2xl bg-cyan-400 text-slate-900 font-semibold hover:brightness-95 disabled:opacity-60"
          >
            {loading ? "가입 중..." : "회원가입"}
          </button>
        </form>

        <div className="text-center text-sm text-slate-400 mt-6">
          이미 계정이 있나요?{" "}
          <Link to="/login" className="text-cyan-400 hover:underline">
            로그인
          </Link>
        </div>
      </div>
    </div>
  );
}