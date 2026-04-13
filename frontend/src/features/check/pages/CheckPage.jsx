// src/pages/Check/CheckPage.jsx
// 현재 가동범위/상태 측정

import { useState } from "react";
import SideBySideStage from "../../../components/layout/SideBySideStage";
import WsCamera from "../../../components/camera/WsCamera";
import { useSearchParams, useLocation, useNavigate } from "react-router-dom";
import { CheckResultView } from "../results/CheckResultPage";
import { getWsBase } from "../../../services/runtimeConfig";
import { saveAccuracyHistory } from "../../../utils/accuracyHistory";
import { saveAccuracyToServer } from "../../../services/accuracyApi";

export default function CheckPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [sp] = useSearchParams();
  const selectedPart =
    sp.get("part") ?? location.state?.selectedPart;  // "knee" | "hip" | "shoulder" | null
  const [progress, setProgress] = useState("");
  const [stage, setStage] = useState("");
  const [finished, setFinished] = useState(false);
  const [finalAccuracy, setFinalAccuracy] = useState(100);
  const [completedAt, setCompletedAt] = useState(null);

  const WS_BASE = getWsBase();
  
  const wsUrl = selectedPart
    ? `${WS_BASE}/api/v1/ws/measure?parts=${encodeURIComponent(selectedPart)}`
    : `${WS_BASE}/api/v1/ws/measure`;

  console.log("🧪 CheckPage", { selectedPart, wsUrl });

  async function persistAccuracy() {
    // [조현석] 측정 화면도 운동 화면과 동일하게 서버 장애 시를 대비한 로컬 백업 기록을 유지합니다.
    saveAccuracyHistory(finalAccuracy, "check");
    try {
      // [조현석] 주간 차트에 측정 결과도 반영할 수 있게 체크 종료 시 마지막 정확도를 서버에 저장합니다.
      await saveAccuracyToServer({
        accuracyPct: finalAccuracy,
        sourceType: "check",
        sourceKey: selectedPart ?? "full_body",
      });
    } catch (error) {
      console.error("[Accuracy] failed to persist to server", error);
    }
  }
  
  // 측정완료 -> CheckResultView
  if (finished) {
    return (
      <CheckResultView
        selectedPart={selectedPart ?? "full_body"}
        scoreValue={finalAccuracy}
        timestamp={completedAt}
        onClose={async ()=>{
          // [조현석] 측정 종료 후 메인으로 돌아갈 때 서버/로컬에 최종 정확도를 함께 저장합니다.
          await persistAccuracy();
          navigate("/main", { state: { finalAccuracy } });
        }}
        onSelectOtherPart={async () => {
          await persistAccuracy();
          navigate("/check/select");
        }}
        onRetry={()=>{
          setFinished(false);
          setProgress("");
          setStage("");
          setFinalAccuracy(100);
          setCompletedAt(null);
        }}
        />
    );
  }

  //측정 화면
  return (
    <SideBySideStage
      single
      topSlot={
        !selectedPart && progress ? (
          <div className="progress-pill">{progress}</div>
        ) : null
      }
      bottomRightSlot={
        <button
          className="exit-btn"
          onClick={() => {
            setCompletedAt(new Date().toISOString());
            setFinished(true);
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
          enabled={!finished}
          onState={(data) => {
            if (data.progress) setProgress(data.progress);
            if (data.stage) setStage(data.stage);
            // [조현석] 측정 도중 들어오는 accuracy_pct 중 가장 마지막 값을 최종 정확도로 사용합니다.
            if (typeof data.accuracy_pct === "number") setFinalAccuracy(data.accuracy_pct);
            console.log("MEASURE:", data.status, data.stage, data.progress);
          }}
          onResult={(data) => {
            if (data.status === "finished") {
              setCompletedAt(new Date().toISOString());
              setFinished(true);
            }
          }}
        />
      }
    />
  );
}
