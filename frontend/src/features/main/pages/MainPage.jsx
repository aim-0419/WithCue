// src/pages/Main/MainPage.jsx
// Main.jsx의 redirect 관리

import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Main from "../components/Main";
import "./MainPage.css";

import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";
import {
  clearAccuracyHistory,
  readLatestAccuracy,
  toWeeklyChartData,
} from "../../../utils/accuracyHistory";
import { getAccessToken } from "../../../utils/authStorage";
import { fetchWeeklyAccuracyFromServer } from "../../../services/accuracyApi";

export default function MainPage() {
  const navigate = useNavigate();
  const { pathname, state } = useLocation();
  const [weeklyAccuracyData, setWeeklyAccuracyData] = useState(() =>
    toWeeklyChartData(new Date(), "exercise")
  );
  const [serverLatestAccuracy, setServerLatestAccuracy] = useState(null);

  useEffect(() => {
    let mounted = true;
    const resetFlag = "withcue_accuracy_history_reset";

    if (getAccessToken() && !localStorage.getItem(resetFlag)) {
      clearAccuracyHistory();
      localStorage.setItem(resetFlag, "1");
    }

    async function loadWeeklyAccuracy() {
      try {
        // [조현석] 주간 점수를 브라우저별 localStorage가 아니라 서버 기록 기준으로 통일하기 위해 메인 진입 시 DB 데이터를 우선 조회합니다.
        const payload = await fetchWeeklyAccuracyFromServer({
          sourceType: "exercise",
        });
        if (!mounted) return;
        setWeeklyAccuracyData(
          Array.isArray(payload.items)
            ? payload.items
            : toWeeklyChartData(new Date(), "exercise")
        );
        setServerLatestAccuracy(
          typeof payload.latest_accuracy === "number" ? payload.latest_accuracy : null,
        );
      } catch (error) {
        if (!mounted) return;
        // [조현석] 서버 조회 실패 시 메인 화면이 비지 않도록 기존 로컬 차트 데이터를 폴백으로 유지합니다.
        console.error("[Accuracy] failed to fetch weekly data", error);
      }
    }

    loadWeeklyAccuracy();
    return () => {
      mounted = false;
    };
  }, []);

  // [조현석] 방금 측정을 마치고 돌아온 경우에는 state.finalAccuracy를 우선 사용하고,
  // 없으면 서버 최신 점수, 마지막으로 로컬 저장값을 사용합니다.
  const finalAccuracy =
    state?.finalAccuracy ?? serverLatestAccuracy ?? readLatestAccuracy("exercise") ?? 0;

  const activeTab = 
    pathname === "/main" ? "home" :
    pathname.startsWith("/analysis") ? "analysis" :
    pathname.startsWith("/record") ? "record" :
    pathname.startsWith("/mypage") ? "profile" : "home";

  return (
    <>
    <TopBar/>
    <div className="h-full bg-slate-950">
      <Main
        onStartWorkout={() => navigate("/choose-exercise")}
        onStartCheck={() => navigate("/check/select")}
      />

      <BottomNav activeTab={activeTab} />
    </div>
    </>
  );
}
