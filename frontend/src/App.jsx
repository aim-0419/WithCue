import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainPage from "./features/main/pages/MainPage";
import AnalysisPage from "./features/analysis/pages/AnalysisPage";
import RecordPage from "./features/record/pages/RecordPage";
import ChooseExercisePage from "./features/exercise/pages/ChooseExercisePage";
import ExercisePage from "./features/exercise/pages/ExercisePage";
import CheckSelectPage from "./features/check/pages/CheckSelectPage";
import CheckPage from "./features/check/pages/CheckPage";
import CheckHistoryPage from "./features/check/pages/CheckHistoryPage";
import MyPage from "./features/my/pages/MyPage";
import SettingsPage from "./features/my/pages/SettingsPage";
import LoginPage from "./features/auth/pages/LoginPage";
import RegisterPage from "./features/auth/pages/RegisterPage";



export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/main" element={<MainPage />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/record" element={<RecordPage />} />

        {/* 인증 */}
        <Route path="/join" element={<RegisterPage />} />
        <Route path="/login" element={<LoginPage />} />

        <Route path="/check/select" element={<CheckSelectPage />} />
        <Route path="/check" element={<CheckPage />} />
        <Route path="/check/history" element={<CheckHistoryPage />} />
        <Route path="/choose-exercise" element={<ChooseExercisePage />} />
        <Route path="/exercise/:exerciseId" element={<ExercisePage />} />
        <Route path="/mypage" element={<MyPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
