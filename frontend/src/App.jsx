import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import MainPage from "./features/main/pages/MainPage";
import AnalysisPage from "./features/analysis/pages/AnalysisPage";
import RecordPage from "./features/record/pages/RecordPage";
import ChooseExercisePage from "./features/exercise/pages/ChooseExercisePage";
import ExerciseIntroPage from "./features/exercise/pages/ExerciseIntroPage";
import ExercisePage from "./features/exercise/pages/ExercisePage";
import CheckSelectPage from "./features/check/pages/CheckSelectPage";
import CheckPage from "./features/check/pages/CheckPage";
import CheckHistoryPage from "./features/check/pages/CheckHistoryPage";
import MyPage from "./features/my/pages/MyPage";
import SettingsPage from "./features/my/pages/SettingsPage";
import LoginPage from "./features/auth/pages/LoginPage";
import RegisterPage from "./features/auth/pages/RegisterPage";
import { getAccessToken } from "./utils/authStorage";

function PrivateRoute({ children }) {
  return getAccessToken() ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />

        {/* 인증 */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/join" element={<RegisterPage />} />

        {/* 보호된 경로 */}
        <Route path="/main" element={<PrivateRoute><MainPage /></PrivateRoute>} />
        <Route path="/analysis" element={<PrivateRoute><AnalysisPage /></PrivateRoute>} />
        <Route path="/record" element={<PrivateRoute><RecordPage /></PrivateRoute>} />
        <Route path="/check/select" element={<PrivateRoute><CheckSelectPage /></PrivateRoute>} />
        <Route path="/check" element={<PrivateRoute><CheckPage /></PrivateRoute>} />
        <Route path="/check/history" element={<PrivateRoute><CheckHistoryPage /></PrivateRoute>} />
        <Route path="/choose-exercise" element={<PrivateRoute><ChooseExercisePage /></PrivateRoute>} />
        <Route path="/exercise/:exerciseId/intro" element={<PrivateRoute><ExerciseIntroPage /></PrivateRoute>} />
        <Route path="/exercise/:exerciseId" element={<PrivateRoute><ExercisePage /></PrivateRoute>} />
        <Route path="/mypage" element={<PrivateRoute><MyPage /></PrivateRoute>} />
        <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
      </Routes>
    </BrowserRouter>
  );
}
