// src/pages/Exercise/ExercisePage.jsx
// 맞춤형 운동 코칭

import { useEffect, useMemo, useRef, useState } from "react";
import SideBySideStage from "../../../components/layout/SideBySideStage";
import WsCamera from "../../../components/camera/WsCamera";
import { useNavigate, useParams } from "react-router-dom";
import { getApiBase, getWsBase } from "../../../services/runtimeConfig";
import { saveAccuracyHistory } from "../../../utils/accuracyHistory";
import { saveAccuracyToServer } from "../../../services/accuracyApi";
import {
  ExerciseResultView,
  formatExerciseDuration,
} from "../results/ExerciseResultPage";

const DEFAULT_ANALYZING_FEEDBACK = "동작 분석 중입니다.";
const DEFAULT_WAITING_FEEDBACK = "자세를 인식 중입니다.";
const FEEDBACK_COOLDOWN_MS = 2500;
const FEEDBACK_FALLBACK_DISPLAY_MS = 1800;

const FEEDBACK_AUDIO_MAP = {
  "팔과 다리의 가동범위를 기준보다 조금 더 확보해 주세요.":
    "팔과_다리의_가동범위를_기준보다_조금_더_확보해_주세요.mp3",
  "좌우 균형이 흔들립니다. 몸통 중심을 고정해 주세요.":
    "좌우_균형이_흔들립니다_몸통_중심을_고정해_주세요.mp3",
  "관절 정렬이 무너집니다. 허리/어깨 라인을 유지해 주세요.":
    "관절_정렬이_무너집니다_허리어깨_라인을_유지해_주세요.mp3",
  "팔을 들 때 어깨가 같이 올라갑니다. 승모근 힘을 줄이고 들어 주세요.":
    "팔을_들_때_어깨가_같이_올라갑니다_승모근_힘을_줄이고_들어_주세요.mp3",
  "몸통이 함께 움직입니다. 상체를 세운 상태를 유지해 주세요.":
    "몸통이_함께_움직입니다_상체를_세운_상태를_유지해_주세요.mp3",
  "팔꿈치가 과하게 굽혀집니다. 팔을 조금 더 편 상태로 올려 주세요.":
    "팔꿈치가_과하게_굽혀집니다_팔을_조금_더_편_상태로_올려_주세요.mp3",
  "다리를 들 때 몸통이 같이 흔들립니다. 상체를 고정해 주세요.":
    "다리를_들_때_몸통이_같이_흔들립니다_상체를_고정해주세요.mp3",
  "골반 흔들림이 큽니다. 골반을 수평으로 유지해 주세요.":
    "골반_흔들림이_큽니다_골반을_수평으로_유지해_주세요.mp3",
  "무릎이 굽혀집니다. 다리를 더 곧게 유지해 주세요.":
    "무릎이_굽혀집니다_다리를_더_곧게_유지해_주세요.mp3",
  "좌우 회전 범위 차이가 큽니다. 양쪽을 같은 크기로 회전해 주세요.":
    "좌우_회전_범위_차이가_큽니다_양쪽을_같은_크기로_회전해_주세요.mp3",
  "회전 범위가 작습니다. 통증 없는 범위에서 조금 더 돌려 주세요.":
    "회전_범위가_작습니다_통증_없는_범위에서_조금_더_돌려_주세요.mp3",
  "목 회전 시 어깨나 몸통이 같이 따라갑니다. 목만 분리해서 움직여 주세요.":
    "목_회전_시_어깨나_몸통이_같이_따라갑니다_목만_분리해서_움직여_주세요.mp3",
};

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
  const API_BASE = getApiBase();
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

  const feedbackAudioBase = useMemo(() => `${API_BASE}/assets/tts`, [API_BASE]);

  const [liveDtwScore, setLiveDtwScore] = useState(null);
  const [finalAccuracy, setFinalAccuracy] = useState(null);
  const [finished, setFinished] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);
  const [repCount, setRepCount] = useState(0);
  const [liveFeedback, setLiveFeedback] = useState(DEFAULT_ANALYZING_FEEDBACK);
  const [sessionDurationSec, setSessionDurationSec] = useState(0);
  const [completedAt, setCompletedAt] = useState(null);
  const [wsEnabled, setWsEnabled] = useState(true);
  const sessionStartedAtRef = useRef(Date.now());
  const hasSavedRef = useRef(false);
  const autoFinishAudioRef = useRef(null);
  const autoFinishArmedRef = useRef(false);
  const activeFeedbackAudioRef = useRef(null);
  const defaultFeedbackRef = useRef(DEFAULT_ANALYZING_FEEDBACK);
  const activeFeedbackMessageRef = useRef("");
  const feedbackCooldownTimerRef = useRef(null);
  const feedbackFallbackTimerRef = useRef(null);
  const feedbackGateStateRef = useRef("open");

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
    clearFeedbackPlayback({ nextFeedback: DEFAULT_ANALYZING_FEEDBACK });
    autoFinishArmedRef.current = false;
    setFinished(false);
    setLiveDtwScore(null);
    setFinalAccuracy(null);
    setRepCount(0);
    setLiveFeedback(DEFAULT_ANALYZING_FEEDBACK);
    defaultFeedbackRef.current = DEFAULT_ANALYZING_FEEDBACK;
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

  function clearFeedbackAudio() {
    if (activeFeedbackAudioRef.current) {
      activeFeedbackAudioRef.current.pause();
      activeFeedbackAudioRef.current.currentTime = 0;
      activeFeedbackAudioRef.current = null;
    }
  }

  function clearFeedbackTimers() {
    if (feedbackCooldownTimerRef.current) {
      clearTimeout(feedbackCooldownTimerRef.current);
      feedbackCooldownTimerRef.current = null;
    }
    if (feedbackFallbackTimerRef.current) {
      clearTimeout(feedbackFallbackTimerRef.current);
      feedbackFallbackTimerRef.current = null;
    }
  }

  function clearFeedbackPlayback({
    nextFeedback = defaultFeedbackRef.current,
  } = {}) {
    clearFeedbackTimers();
    clearFeedbackAudio();
    feedbackGateStateRef.current = "open";
    activeFeedbackMessageRef.current = "";
    setLiveFeedback(nextFeedback);
  }

  function startFeedbackPlayback(message) {
    if (!message) {
      return;
    }

    const filename = FEEDBACK_AUDIO_MAP[message];
    activeFeedbackMessageRef.current = message;
    feedbackGateStateRef.current = "playing";
    setLiveFeedback(message);

    const enterCooldown = () => {
      clearFeedbackAudio();
      feedbackGateStateRef.current = "cooldown";
      feedbackCooldownTimerRef.current = setTimeout(() => {
        feedbackCooldownTimerRef.current = null;
        feedbackGateStateRef.current = "open";
        activeFeedbackMessageRef.current = "";
        setLiveFeedback(defaultFeedbackRef.current);
      }, FEEDBACK_COOLDOWN_MS);
    };

    if (!filename) {
      feedbackFallbackTimerRef.current = setTimeout(() => {
        feedbackFallbackTimerRef.current = null;
        enterCooldown();
      }, FEEDBACK_FALLBACK_DISPLAY_MS);
      return;
    }

    const audio = new Audio(`${feedbackAudioBase}/${filename}`);
    activeFeedbackAudioRef.current = audio;
    audio.onended = () => {
      enterCooldown();
    };
    audio.onerror = () => {
      enterCooldown();
    };
    audio.play().catch(() => {
      enterCooldown();
    });
  }

  function finishSession() {
    if (finished) {
      return;
    }

    const computedFinalAccuracy = finalizeExerciseAccuracy();
    setWsEnabled(false);
    setSessionDurationSec(
      Math.round((Date.now() - sessionStartedAtRef.current) / 1000)
    );
    setFinalAccuracy(computedFinalAccuracy);
    setCompletedAt(new Date().toISOString());
    setFinished(true);
  }

  function updateLiveFeedback(nextFeedback, { force = false } = {}) {
    if (typeof nextFeedback !== "string") {
      return;
    }

    const trimmed = nextFeedback.trim();
    if (!trimmed) {
      return;
    }

    const isDefaultFeedback =
      trimmed === DEFAULT_ANALYZING_FEEDBACK || trimmed === DEFAULT_WAITING_FEEDBACK;

    if (isDefaultFeedback) {
      defaultFeedbackRef.current = trimmed;
      if (
        !force &&
        feedbackGateStateRef.current !== "open"
      ) {
        return;
      }
      if (force) {
        clearFeedbackPlayback({ nextFeedback: trimmed });
      }
      setLiveFeedback(trimmed);
      return;
    }

    if (force) {
      clearFeedbackPlayback({ nextFeedback: defaultFeedbackRef.current });
    }

    // 재생 시작부터 cooldown 종료까지는 게이트를 닫고,
    // 그 사이 들어온 피드백은 큐에 쌓지 않고 그대로 버립니다.
    if (feedbackGateStateRef.current !== "open") {
      return;
    }

    if (activeFeedbackMessageRef.current === trimmed) {
      return;
    }

    startFeedbackPlayback(trimmed);
  }

  useEffect(() => {
    return () => {
      clearFeedbackPlayback({ nextFeedback: defaultFeedbackRef.current });
    };
  }, []);

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
      finishSession();
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
            finishSession();
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

        <div
          style={{
            position: "absolute",
            left: 20,
            right: 20,
            bottom: 20,
            zIndex: 20,
            background: "rgba(0,0,0,0.72)",
            color: "#fff",
            padding: "14px 18px",
            borderRadius: 14,
            fontSize: 18,
            fontWeight: 600,
            lineHeight: 1.45,
            boxShadow: "0 8px 24px rgba(0,0,0,0.28)",
          }}
        >
          {liveFeedback || DEFAULT_ANALYZING_FEEDBACK}
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
              updateLiveFeedback(DEFAULT_WAITING_FEEDBACK, { force: true });
              autoFinishArmedRef.current = false;
            }
            if (data.status === "session_finished" || data.session_finished) {
              finishSession();
              return;
            }
            if (typeof data.feedback === "string" && data.feedback.trim()) {
              updateLiveFeedback(data.feedback);
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
            if (data.status === "session_finished" || data.session_finished) {
              finishSession();
              return;
            }
            if (typeof data.feedback === "string" && data.feedback.trim()) {
              updateLiveFeedback(data.feedback, { force: true });
            }
          }}
        />
      </div>
    }
    />
  );
}
