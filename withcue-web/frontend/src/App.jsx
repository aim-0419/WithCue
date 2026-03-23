import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainPage from "./pages/Main/MainPage";
import ChooseExercisePage from "./pages/Exercise/ChooseExercisePage";
import ExercisePage from "./pages/Exercise/ExercisePage";
import CheckSelectPage from "./pages/Check/CheckSelectPage";
import CheckPage from "./pages/Check/CheckPage";
import MyPage from "./pages/My/MyPage";
import SettingsPage from "./pages/My/SettingsPage";
import LoginPage from "./pages/Login/LoginPage";
import RegisterPage from "./pages/Login/RegisterPage";



export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/main" element={<MainPage />} />

        {/* 인증 */}
        <Route path="/join" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />

        <Route path="/check/select" element={<CheckSelectPage />} />
        <Route path="/check" element={<CheckPage />} />
        <Route path="/choose-exercise" element={<ChooseExercisePage />} />
        <Route path="/exercise/:exerciseId" element={<ExercisePage />} />
        <Route path="/mypage" element={<MyPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
