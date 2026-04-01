// src/pages/Exercise/ExercisePage.jsx
// 맞춤형 운동 코칭

import { useState } from "react";
import SideBySideStage from "../../components/SideBySideStage";
import WsCamera from "../../components/WsCamera";
import { useNavigate, useParams } from "react-router-dom";
import { getWsBase } from "../../utils/runtimeConfig";
import { saveAccuracyHistory } from "../../utils/accuracyHistory";
import { saveAccuracyToServer } from "../../utils/accuracyApi";

export default function ExercisePage() {
  const navigate = useNavigate();
  // [조현석] 운동 코칭 페이지도 Check 페이지와 동일하게 현재 접속 호스트 기준 WS 주소를 사용합니다.
  const WS_BASE = getWsBase();
  const { exerciseId } = useParams();
  const wsUrl = `${WS_BASE}/api/v1/ws/coach/${exerciseId}?limit=80`;
  const [finalAccuracy, setFinalAccuracy] = useState(0);

  async function persistAccuracy() {
    // [조현석] 서버 저장 실패 시 주간 점수가 완전히 유실되지 않도록 로컬 기록을 보조 저장소로 남겨둡니다.
    saveAccuracyHistory(finalAccuracy);
    try {
      // [조현석] 메인 차트를 DB 기준으로 보여주기 위해 운동 종료 시 마지막 정확도를 서버에도 함께 기록합니다.
      await saveAccuracyToServer({
        accuracyPct: finalAccuracy,
        sourceType: "exercise",
        sourceKey: exerciseId,
      });
      console.log("서버 저장 성공");
    } catch (error) {
      console.error("[Accuracy] failed to persist to server", error);
    }
      console.log("persist 종료");
  }

  return (
    <SideBySideStage
      single
      bottomRightSlot={
        <button
          className="exit-btn"
          onClick={async () => {
            // [조현석] 운동 코칭 종료 시 DB를 우선 기록하고, 로컬 기록도 같이 유지합니다.
            await persistAccuracy();
            navigate("/main", { state: { finalAccuracy } });
          }}
        >
          종료
        </button>
      }
      rightTitle="내 화면"
      rightSub="실시간 카메라"
      rightContent={
      <WsCamera
        wsUrl={wsUrl}
          onState={(data) => {
              // data.feedback, data.angle, data.target_angle
              if (typeof data.accuracy_pct === "number") {
                setFinalAccuracy(data.accuracy_pct);
              }
              console.log("COACH:", data.angle, data.feedback);
          }}
        />
      }
    />
  );
}
