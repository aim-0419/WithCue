// src/pages/Exercise/ExercisePage.jsx
// 맞춤형 운동 코칭

import { useEffect, useMemo, useRef, useState } from "react";
import SideBySideStage from "../../../components/layout/SideBySideStage";
import WsCamera from "../../../components/camera/WsCamera";
import { useNavigate, useParams } from "react-router-dom";
import { getWsBase } from "../../../services/runtimeConfig";
import { saveAccuracyHistory } from "../../../utils/accuracyHistory";
import { saveAccuracyToServer } from "../../../services/accuracyApi";
import {
  ExerciseResultView,
  formatExerciseDuration,
} from "../results/ExerciseResultPage";

const EXERCISE_RESULT_META = {
  bird_dog: {
    title: "버드독 결과 리포트",
    scoreLabel: "운동 수행 점수",
    summary: "코어와 팔다리 협응을 중심으로 세션 결과를 정리했습니다.",
    positiveTitle: "좌우 협응 흐름 양호",
    positiveBody: "팔과 다리의 교차 움직임이 비교적 안정적으로 이어졌습니다.",
    cautionTitle: "몸통 흔들림 주의",
    cautionBody: "팔과 다리를 올릴 때 골반과 몸통이 같이 흔들리지 않게 신경 써보세요.",
    repTarget: 3,
  },
  shoulder_front_raise_left: {
    title: "왼쪽 어깨 전방 거상 결과",
    scoreLabel: "운동 수행 점수",
    summary: "왼쪽 어깨의 거상 패턴과 상체 안정성을 기준으로 정리했습니다.",
    positiveTitle: "왼쪽 어깨 움직임 양호",
    positiveBody: "팔을 들어 올리는 흐름이 비교적 자연스럽게 유지되었습니다.",
    cautionTitle: "어깨 힘 과사용 주의",
    cautionBody: "승모근에 힘이 과하게 들어가지 않도록 어깨를 편하게 내린 채 진행해보세요.",
    repTarget: 3,
  },
  shoulder_front_raise_right: {
    title: "오른쪽 어깨 전방 거상 결과",
    scoreLabel: "운동 수행 점수",
    summary: "오른쪽 어깨의 거상 패턴과 상체 안정성을 기준으로 정리했습니다.",
    positiveTitle: "오른쪽 어깨 움직임 양호",
    positiveBody: "팔을 들어 올리는 흐름이 비교적 자연스럽게 유지되었습니다.",
    cautionTitle: "어깨 힘 과사용 주의",
    cautionBody: "승모근에 힘이 과하게 들어가지 않도록 어깨를 편하게 내린 채 진행해보세요.",
    repTarget: 3,
  },
  knee_raise_left: {
    title: "왼쪽 무릎 들어올리기 결과",
    scoreLabel: "운동 수행 점수",
    summary: "왼쪽 다리의 균형과 들어올리는 패턴을 기준으로 정리했습니다.",
    positiveTitle: "하체 중심 유지 양호",
    positiveBody: "서 있는 동안 중심이 비교적 안정적으로 유지되었습니다.",
    cautionTitle: "무릎 높이와 균형 보완",
    cautionBody: "다리를 올릴 때 상체가 같이 기울지 않도록 천천히 반복해보세요.",
    repTarget: 3,
  },
  knee_raise_right: {
    title: "오른쪽 무릎 들어올리기 결과",
    scoreLabel: "운동 수행 점수",
    summary: "오른쪽 다리의 균형과 들어올리는 패턴을 기준으로 정리했습니다.",
    positiveTitle: "하체 중심 유지 양호",
    positiveBody: "서 있는 동안 중심이 비교적 안정적으로 유지되었습니다.",
    cautionTitle: "무릎 높이와 균형 보완",
    cautionBody: "다리를 올릴 때 상체가 같이 기울지 않도록 천천히 반복해보세요.",
    repTarget: 3,
  },
  neck_rotation: {
    title: "목 좌우 돌리기 결과",
    scoreLabel: "운동 수행 점수",
    summary: "목 회전 범위와 상체 고정 정도를 기준으로 세션을 정리했습니다.",
    positiveTitle: "회전 흐름 양호",
    positiveBody: "목을 좌우로 돌리는 흐름이 전반적으로 부드럽게 유지되었습니다.",
    cautionTitle: "상체 동반 회전 주의",
    cautionBody: "고개를 돌릴 때 몸통까지 함께 돌아가지 않도록 시선을 천천히 이동해보세요.",
    repTarget: 3,
  },
};

export default function ExercisePage() {
  const navigate = useNavigate();
  // [조현석] 운동 코칭 페이지도 Check 페이지와 동일하게 현재 접속 호스트 기준 WS 주소를 사용합니다.
  const WS_BASE = getWsBase();
  const { exerciseId } = useParams();

  const DTW_EXERCISES = new Set([
    "bird_dog", 
    "shoulder_front_raise_left", 
    "shoulder_front_raise_right",
    "knee_raise_left",
    "knee_raise_right",
    "neck_rotation",
  ]);

  const wsUrl = useMemo(() => {
    if (DTW_EXERCISES.has(exerciseId)) {
      return `${WS_BASE}/api/v1/ws/dtw/${exerciseId}`;
    }
    return `${WS_BASE}/api/v1/ws/coach/${exerciseId}?limit=80`;
  }, [WS_BASE, exerciseId]);

  const [liveDtwScore, setLiveDtwScore] = useState(null);
  const [finalAccuracy, setFinalAccuracy] = useState(null);
  const [finished, setFinished] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);
  const [repCount, setRepCount] = useState(0);
  const [sessionDurationSec, setSessionDurationSec] = useState(0);
  const [completedAt, setCompletedAt] = useState(null);
  const [wsEnabled, setWsEnabled] = useState(true);
  const sessionStartedAtRef = useRef(Date.now());
  const hasSavedRef = useRef(false);
  const autoFinishAudioRef = useRef(null);
  const autoFinishArmedRef = useRef(false);

  const isDtwExercise = DTW_EXERCISES.has(exerciseId);
  const isBirdDogExercise = exerciseId === "bird_dog";

  const exerciseMeta = EXERCISE_RESULT_META[exerciseId] ?? {
    title: "운동 수행 결과 리포트",
    scoreLabel: "운동 수행 점수",
    summary: "이번 세션 결과를 기준으로 운동 수행 내용을 정리했습니다.",
    positiveTitle: "세션 흐름 안정적",
    positiveBody: "운동을 꾸준히 이어가며 전체 흐름을 유지했습니다.",
    cautionTitle: "자세 정확도 보완",
    cautionBody: "속도보다 정확한 자세를 우선해 다음 세션도 이어가보세요.",
    repTarget: null,
  };

  async function persistAccuracy() {
    if (typeof finalAccuracy !== "number") {
      return;
    }

    // [조현석] 서버 저장 실패 시 주간 점수가 완전히 유실되지 않도록 로컬 기록을 보조 저장소로 남겨둡니다.
    saveAccuracyHistory(finalAccuracy, "exercise");
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

  function resetExerciseState({ bumpSessionKey = false } = {}) {
    if (autoFinishAudioRef.current) {
      autoFinishAudioRef.current.pause();
      autoFinishAudioRef.current.currentTime = 0;
    }
    autoFinishArmedRef.current = false;
    setFinished(false);
    setLiveDtwScore(null);
    setFinalAccuracy(null);
    setRepCount(0);
    setSessionDurationSec(0);
    setCompletedAt(null);
    setWsEnabled(true);
    if (bumpSessionKey) {
      setSessionKey((prev) => prev + 1);
    }
    sessionStartedAtRef.current = Date.now();
    hasSavedRef.current = false;
  }

  useEffect(() => {
    if (!finished || hasSavedRef.current) {
      return;
    }

    hasSavedRef.current = true;
    persistAccuracy();
  }, [finished, finalAccuracy]);

  useEffect(() => {
    resetExerciseState({ bumpSessionKey: true });
  }, [exerciseId]);

  useEffect(() => {
    autoFinishAudioRef.current = new Audio(
      "/audio/exercise_auto_finish.mp3"
    );
    return () => {
      if (autoFinishAudioRef.current) {
        autoFinishAudioRef.current.pause();
        autoFinishAudioRef.current.currentTime = 0;
      }
    };
  }, []);

  function playAutoFinishAudio() {
    if (!autoFinishAudioRef.current) {
      return;
    }
    autoFinishAudioRef.current.currentTime = 0;
    autoFinishAudioRef.current.play().catch(() => {});
  }

  useEffect(() => {
    if (finished) {
      return;
    }

    if (!autoFinishArmedRef.current) {
      return;
    }

    if (
      typeof exerciseMeta.repTarget === "number" &&
      exerciseMeta.repTarget > 0 &&
      typeof repCount === "number" &&
      repCount >= exerciseMeta.repTarget
    ) {
      playAutoFinishAudio();
      const computedFinalAccuracy = finalizeExerciseAccuracy();
      setSessionDurationSec(
        Math.round((Date.now() - sessionStartedAtRef.current) / 1000)
      );
      setFinalAccuracy(computedFinalAccuracy);
      setCompletedAt(new Date().toISOString());
      setFinished(true);
    }
  }, [exerciseMeta.repTarget, finished, repCount]);

  function finalizeExerciseAccuracy() {
    if (typeof finalAccuracy === "number") {
      return finalAccuracy;
    }

    if (typeof liveDtwScore === "number") {
      return liveDtwScore;
    }

    return null;
  }

  const exerciseResult = useMemo(() => {
    const repLabel =
      typeof repCount === "number" && repCount > 0 ? `${repCount}회` : "기록 없음";
    const repSubValue =
      exerciseMeta.repTarget && repCount > 0 ? `/ ${exerciseMeta.repTarget}회` : null;

    return {
      ...exerciseMeta,
      primaryMetricLabel: "운동 시간",
      primaryMetricValue: formatExerciseDuration(sessionDurationSec),
      secondaryMetricLabel: "반복 횟수",
      secondaryMetricValue: repLabel,
      secondaryMetricSubValue: repSubValue,
      summary:
        typeof finalAccuracy === "number"
          ? `${exerciseMeta.summary} 최종 점수는 ${Math.round(finalAccuracy)}점입니다.`
          : exerciseMeta.summary,
    };
  }, [exerciseMeta, finalAccuracy, repCount, sessionDurationSec]);

  if (finished) {
    return (
      <ExerciseResultView
        scoreValue={finalAccuracy}
        timestamp={completedAt}
        exerciseResult={exerciseResult}
        onClose={() => {
          navigate("/main", { state: { finalAccuracy } });
        }}
        onChooseExercise={() => {
          navigate("/choose-exercise");
        }}
        onRetry={() => {
          resetExerciseState({ bumpSessionKey: true });
        }}
      />
    );
  }

  return (
    <SideBySideStage
      single
      bottomRightSlot={
        <button
          className="exit-btn"
          onClick={() => {
            const computedFinalAccuracy = finalizeExerciseAccuracy();
            setWsEnabled(false);
            setSessionDurationSec(
              Math.round((Date.now() - sessionStartedAtRef.current) / 1000)
            );
            setFinalAccuracy(computedFinalAccuracy);
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
      <div style={{ position: "relative", width: "100%", height: "100%" }}>
        
        {/* 유사도(=DTW) 표시 */}
        <div
          style={{
            position: "absolute",
            top: 20,
            left: 20,
            zIndex: 20,
            background: "rgba(0,0,0,0.6)",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 10,
            fontSize: 20,
            fontWeight: 700,
          }}
        >
          <div>정확도: {liveDtwScore ?? "-"}</div>
          <div>횟수: {repCount ?? 0}</div>
        </div>

        <WsCamera
          key={sessionKey}
          wsUrl={wsUrl}
          enabled={wsEnabled && !finished}
          onState={(data) => {
            if (data.status && data.status !== "waiting") {
              autoFinishArmedRef.current = true;
            }
            if (data.status === "waiting") {
              setLiveDtwScore(null);
              setFinalAccuracy(null);
              setRepCount(0);
              autoFinishArmedRef.current = false;
            }
            if (typeof data.similarity === "number") {
              setLiveDtwScore(data.similarity);
            }

            if (typeof data.avg_similarity === "number") {
              setFinalAccuracy(data.avg_similarity);
            }

            if (typeof data.accuracy_pct === "number") {
              if (!isDtwExercise && !isBirdDogExercise) {
                setFinalAccuracy(data.accuracy_pct);
              }
            }

            if (typeof data.rep_count === "number") {
              setRepCount(data.rep_count);
            }
          }}
          onResult={(data) => {
            if (typeof data.rep_count === "number") {
              setRepCount(data.rep_count);
            }
          }}
        />
      </div>
    }
    />
  );
}
