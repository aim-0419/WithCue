// src/pages/Check/CheckPage.jsx
// 현재 가동범위/상태 측정

import { useEffect, useRef, useState } from "react";
import WsCamera from "../../../components/camera/WsCamera";
import TopBar from "../../../components/layout/TopBar";
import { useSearchParams, useLocation, useNavigate } from "react-router-dom";
import { CheckResultView } from "../results/CheckResultPage";
import { getWsBase } from "../../../services/runtimeConfig";
import { saveAccuracyHistory } from "../../../utils/accuracyHistory";
import { saveAccuracyToServer } from "../../../services/accuracyApi";
import { saveRomData } from "../../../utils/romStorage";
import { getAccessToken } from "../../../utils/authStorage";
import { getScript, playScript } from "../../../utils/checkAudioScript";
import { isMirrorMode } from "../../../utils/mirrorMode";

export default function CheckPage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [sp] = useSearchParams();
  const selectedPart =
    sp.get("part") ?? location.state?.selectedPart;  // "knee" | "hip" | "shoulder" | null
  const isMirror = isMirrorMode();
  const [progress, setProgress] = useState("");
  const [stage, setStage] = useState("");
  const [status, setStatus] = useState("");
  const [audioLabel, setAudioLabel] = useState("");
  const [finished, setFinished] = useState(false);
  const [finalAccuracy, setFinalAccuracy] = useState(100);
  const [completedAt, setCompletedAt] = useState(null);
  const wsCameraRef = useRef(null);
  const audioAbortRef = useRef(null);
  const audioStartedRef = useRef(false);

  const WS_BASE = getWsBase();

  // 서버가 측정 결과를 사용자에 매핑할 수 있도록 access token을 쿼리로 전달한다.
  const _token = getAccessToken();
  const _tokenQ = _token ? `token=${encodeURIComponent(_token)}` : "";
  const wsUrl = selectedPart
    ? `${WS_BASE}/api/v1/ws/measure?parts=${encodeURIComponent(selectedPart)}${_tokenQ ? `&${_tokenQ}` : ""}`
    : `${WS_BASE}/api/v1/ws/measure${_tokenQ ? `?${_tokenQ}` : ""}`;

  // 컴포넌트 언마운트 시 오디오 중단
  useEffect(() => {
    return () => audioAbortRef.current?.abort();
  }, []);

  // 첫 프레임 수신 후 1초 뒤 오디오 시작
  function startAudioOnce() {
    if (audioStartedRef.current) return;
    audioStartedRef.current = true;
    const controller = new AbortController();
    audioAbortRef.current = controller;
    setTimeout(async () => {
      const script = getScript(selectedPart);
      await playScript(script, {
        onPhase: (phase) => wsCameraRef.current?.sendPhase(phase),
        onStep: (label) => setAudioLabel(label),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        wsCameraRef.current?.sendPhase("DONE");
      }
    }, 1000);
  }

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
          setStatus("");
          setFinalAccuracy(100);
          setCompletedAt(null);
        }}
        />
    );
  }

  //측정 화면
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", background: "#0b1220", overflow: "hidden" }}>
      <TopBar />

      {/* 좌상단: 현재 재생 중인 안내 문구 */}
      {audioLabel && (
        <div
          style={{
            position: "absolute",
            top: 72,
            left: 20,
            zIndex: 20,
            background: "rgba(0,0,0,0.7)",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 10,
            fontSize: 18,
            fontWeight: 800,
            letterSpacing: "0.03em",
            maxWidth: "60%",
            lineHeight: 1.4,
          }}
        >
          {audioLabel}
        </div>
      )}

      {/* 우상단: 진행 단계 */}
      {(stage || progress) && (
        <div
          style={{
            position: "absolute",
            top: 72,
            right: 20,
            zIndex: 20,
            background: "rgba(0,0,0,0.6)",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 10,
            fontSize: 16,
            fontWeight: 700,
            textAlign: "right",
          }}
        >
          {stage && <div>{stage}</div>}
          {progress && <div style={{ opacity: 0.7, fontSize: 13 }}>{progress}</div>}
        </div>
      )}

      {/* 우하단: 종료 버튼 */}
      <div style={{ position: "absolute", right: 20, bottom: 20, zIndex: 30 }}>
        <button
          className="exit-btn"
          onClick={() => {
            audioAbortRef.current?.abort();
            setCompletedAt(new Date().toISOString());
            setFinished(true);
          }}
        >
          종료
        </button>
      </div>

      {/* 미러 모드가 아닐 때는 카메라 피드 표시, 미러 모드일 때는 WebSocket 연결만 유지 */}
      <div style={isMirror ? { display: "none" } : { position: "absolute", inset: 0, zIndex: 0 }}>
        <WsCamera
          ref={wsCameraRef}
          wsUrl={wsUrl}
          showFrame={!isMirror}
          enabled={!finished}
          onState={(data) => {
            startAudioOnce();
            if (data.progress) setProgress(data.progress);
            if (data.stage) setStage(data.stage);
            if (data.status) setStatus(data.status);
            else setStatus("waiting");
            if (typeof data.accuracy_pct === "number") setFinalAccuracy(data.accuracy_pct);
          }}
          onResult={(data) => {
            if (data.status === "finished") {
              if (data.rom) saveRomData(data.rom);
              setCompletedAt(new Date().toISOString());
              setFinished(true);
            }
          }}
        />
      </div>
    </div>
  );
}
