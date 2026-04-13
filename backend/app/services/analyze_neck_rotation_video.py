# analyze_neck_rotation_video.py
# 목 좌우 회전 DTW 테스트용
# - reference JSON 로드
# - 영상에서 feature sequence 추출
# - 왕복 1세트(start ~ end) 자동 추출
# - DTW 점수 + rule 기반 피드백 확인
# - penalty는 아직 사용하지 않음

import os
import json
import cv2
import numpy as np
import mediapipe as mp
import logging

from app.services.dtw_feature_extractor import get_neck_rotation_features_mp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class NeckRotationDTW:
    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)

    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        """
        4개 feature
        [
            trunk_rotation,
            neck_turn_angle,
            head_tilt,
            shoulder_line_angle,
        ]
        """
        weights = np.array([
            2.6,   # trunk_rotation
            2.2,   # neck_turn_angle (핵심)
            2.8,   # head_tilt
            1.2,   # shoulder_line_angle
        ], dtype=np.float32)

        return np.linalg.norm((a - b) * weights)

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(
                    dp[i - 1, j],
                    dp[i, j - 1],
                    dp[i - 1, j - 1],
                )

        i, j = n, m
        path_len = 0
        while i > 0 and j > 0:
            path_len += 1
            candidates = [
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
                (dp[i - 1, j - 1], i - 1, j - 1),
            ]
            _, i, j = min(candidates, key=lambda x: x[0])

        path_len = max(path_len, 1)
        total_cost = float(dp[n, m])
        norm_cost = total_cost / path_len
        return total_cost, norm_cost

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)

        ref = self._normalize(self.ref_seq)
        user = self._normalize(user_seq)

        _, norm_cost = self._dtw(ref, user)

        alpha = 10.0
        dtw_score = max(0, min(100, round(100 - alpha * norm_cost, 2)))

        return {
            "score": dtw_score,
            "dtw_score": dtw_score,
            "cost": float(norm_cost),
        }

    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 12,
        live_window: int = 60,
    ):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
            }

        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq
        user = self._normalize(live_seq)

        ref_len = len(self.ref_seq)
        user_len = len(live_seq)
        use_len = min(ref_len, user_len)

        ref_partial_raw = self.ref_seq[:use_len]
        ref_partial = self._normalize(ref_partial_raw)
        user_partial = user[-use_len:]

        _, norm_cost = self._dtw(ref_partial, user_partial)

        alpha_live = 10.0
        live_similarity = max(0, min(100, round(100 - alpha_live * norm_cost, 2)))

        return {
            "live_similarity": live_similarity,
            "cost": float(norm_cost),
        }


def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)

    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()

def build_neck_rotation_live_feedback(mp_features):
    """
    실시간 1문장 피드백
    feature:
    [
        trunk_rotation,
        neck_turn_angle,
        head_tilt,
        shoulder_line_angle,
    ]
    """
    if mp_features is None:
        return "analyzing..."

    trunk_rotation = float(mp_features[0])
    head_tilt = float(mp_features[2])
    shoulder_line_angle = float(mp_features[3])

    # 우선순위: 몸통 > 고개 숙임 > 어깨 기울기 > 정상
    if trunk_rotation > 8:
        return "Keep your torso still. Do not rotate your body."
    elif head_tilt > 20:
        return "Do not tilt your head down. Keep your head level.."
    elif shoulder_line_angle > 8:
        return "Keep your shoulders level. Do not tilt them.."
    else:
        return "Good job. Rotate your head smoothly from side to side.."


def preview_neck_rotation_video(
    video_path: str,
    reference_path: str,
    model_path: str,
    save_path: str,
    sample_every_n: int = 2,
    visibility_th: float = 0.3,
):
    """
    테스트 영상용 preview
    - 프레임마다 neck feature 추출
    - 실시간 DTW similarity 계산
    - 실시간 피드백 1문장 계산
    - 화면에 점수/피드백 그려서 mp4 저장
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps < 10 or fps > 120:
        fps = 30
    fps = int(round(fps))

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(save_path, fourcc, fps, (width, height))

    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    PoseLandmarker = mp.tasks.vision.PoseLandmarker

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.3,
        min_pose_presence_confidence=0.3,
        min_tracking_confidence=0.3,
        output_segmentation_masks=False,
    )

    dtw_engine = NeckRotationDTW(reference_path)

    sequence = []
    frame_idx = 0
    timestamp_ms = 0

    live_similarity = None
    live_cost = None
   

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break

            draw_frame = frame_bgr.copy()

            if frame_idx % sample_every_n == 0:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                result = landmarker.detect_for_video(mp_image, timestamp_ms)

                mp_features = None

                if result.pose_landmarks:
                    lms = result.pose_landmarks[0]
                    pts = {}

                    for i, lm in enumerate(lms):
                        vis = getattr(lm, "visibility", 1.0)
                        if vis < visibility_th:
                            continue

                        x = lm.x * width
                        y = lm.y * height
                        pts[i] = (x, y)

                    mp_features = get_neck_rotation_features_mp(pts)

                    if mp_features is not None:
                        current = tuple(round(v, 3) for v in mp_features)
                        prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                        if current != prev:
                            sequence.append(mp_features)

                        live_result = dtw_engine.get_live_similarity(
                            sequence,
                            min_frames=12,
                            live_window=60,
                        )

                        if live_result["live_similarity"] is not None:
                            live_similarity = live_result["live_similarity"]
                            live_cost = live_result["cost"]

            

            # 오버레이 배경
            cv2.rectangle(draw_frame, (20, 20), (320, 95), (0, 0, 0), -1)

            txt1 = "Neck Rotation Test"
            txt2 = (
                "DTW: analyzing..."
                if live_similarity is None
                else f"DTW: {live_similarity:.2f}"
            )
            txt3 = (
                "Cost: -"
                if live_cost is None
                else f"Cost: {live_cost:.4f}"
            )
         

            cv2.putText(
                draw_frame, txt1, (35, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA
            )
            cv2.putText(
                draw_frame, txt2, (35, 82),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA
            )
            cv2.putText(
                draw_frame, txt3, (35, 112),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2, cv2.LINE_AA
            )
     

            out.write(draw_frame)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()
    out.release()

    print(f"[완료] preview 저장 경로: {save_path}")


def extract_neck_rotation_sequence_from_video(
    video_path: str,
    model_path: str,
    sample_every_n: int = 2,
    visibility_th: float = 0.3,
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps < 10 or fps > 120:
        fps = 30
    fps = int(round(fps))

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    PoseLandmarker = mp.tasks.vision.PoseLandmarker

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.3,
        min_pose_presence_confidence=0.3,
        min_tracking_confidence=0.3,
        output_segmentation_masks=False,
    )

    sequence = []
    source_frame_indices = []

    frame_idx = 0
    timestamp_ms = 0

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break

            if frame_idx % sample_every_n != 0:
                frame_idx += 1
                timestamp_ms += int(1000 / fps)
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks:
                lms = result.pose_landmarks[0]
                pts = {}

                for i, lm in enumerate(lms):
                    vis = getattr(lm, "visibility", 1.0)
                    if vis < visibility_th:
                        continue

                    x = lm.x * width
                    y = lm.y * height
                    pts[i] = (x, y)

                features = get_neck_rotation_features_mp(pts)
                if features is not None:
                    current = tuple(round(v, 3) for v in features)
                    prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                    if current != prev:
                        sequence.append(features)
                        source_frame_indices.append(frame_idx)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()

    return {
        "video_path": video_path,
        "fps": fps,
        "sequence": sequence,
        "source_frame_indices": source_frame_indices,
    }


def extract_one_rep_neck_rotation(sequence, source_frame_indices=None):
    """
    왕복 1세트:
    시작(정면) -> 한쪽 -> 중간(정면) -> 반대쪽 -> 마지막 정면
    """
    if not sequence:
        return [], None

    seq_arr = np.array(sequence, dtype=np.float32)
    turn_values = np.abs(seq_arr[:, 1])  # abs(neck_turn_angle)
    smooth_turn = np.array(moving_average(turn_values.tolist(), window=7), dtype=np.float32)

    n = len(smooth_turn)
    if n < 20:
        return [], {
            "start_idx": None,
            "peak_idx": None,
            "end_idx": None,
            "neutral_baseline": None,
            "peak_val": None,
        }

    head_n = min(20, max(5, n // 10))
    tail_n = min(20, max(5, n // 10))
    neutral_candidates = np.concatenate([
        smooth_turn[:head_n],
        smooth_turn[-tail_n:]
    ])
    neutral_baseline = float(np.median(neutral_candidates))

    peak_val = float(np.max(smooth_turn))
    peak_idx = int(np.argmax(smooth_turn))

    if peak_val < neutral_baseline + 8:
        return [], {
            "start_idx": None,
            "peak_idx": peak_idx,
            "end_idx": None,
            "neutral_baseline": neutral_baseline,
            "peak_val": peak_val,
        }

    active_threshold = max(neutral_baseline + 12.0, peak_val * 0.35)

    start_idx = None
    sustain = 6
    for i in range(0, n - sustain + 1):
        if np.all(smooth_turn[i:i + sustain] >= active_threshold):
            start_idx = i
            break

    if start_idx is None:
        return [], {
            "start_idx": None,
            "peak_idx": peak_idx,
            "end_idx": None,
            "neutral_baseline": neutral_baseline,
            "peak_val": peak_val,
        }

    return_threshold = neutral_baseline + 4.0
    return_sustain = 8
    neutral_runs = []

    i = peak_idx + 1
    while i <= n - return_sustain:
        if np.all(smooth_turn[i:i + return_sustain] <= return_threshold):
            run_start = i
            j = i + return_sustain

            while j < n and smooth_turn[j] <= return_threshold:
                j += 1

            run_end = j - 1
            neutral_runs.append((run_start, run_end))
            i = j
        else:
            i += 1

    if len(neutral_runs) >= 2:
        end_idx = neutral_runs[1][1]
    elif len(neutral_runs) == 1:
        end_idx = neutral_runs[0][1]
    else:
        end_idx = n - 1

    if end_idx <= start_idx:
        return [], {
            "start_idx": start_idx,
            "peak_idx": peak_idx,
            "end_idx": end_idx,
            "neutral_baseline": neutral_baseline,
            "peak_val": peak_val,
        }

    start_margin = 5
    end_margin = 5
    start_idx = max(0, start_idx - start_margin)
    end_idx = min(n - 1, end_idx + end_margin)

    rep_sequence = sequence[start_idx:end_idx + 1]

    debug_info = {
        "start_idx": start_idx,
        "peak_idx": peak_idx,
        "end_idx": end_idx,
        "neutral_baseline": neutral_baseline,
        "peak_val": peak_val,
        "start_source_frame": (
            int(source_frame_indices[start_idx])
            if source_frame_indices and start_idx < len(source_frame_indices)
            else None
        ),
        "end_source_frame": (
            int(source_frame_indices[end_idx])
            if source_frame_indices and end_idx < len(source_frame_indices)
            else None
        ),
    }

    return rep_sequence, debug_info


def build_neck_rotation_feedback(rep_sequence):
    arr = np.array(rep_sequence, dtype=np.float32)

    trunk_mean = float(np.mean(arr[:, 0]))
    trunk_max = float(np.max(arr[:, 0]))
    head_tilt_mean = float(np.mean(arr[:, 2]))
    head_tilt_max = float(np.max(arr[:, 2]))
    shoulder_line_mean = float(np.mean(arr[:, 3]))

    feedbacks = []

    if trunk_max > 8:
        feedbacks.append("몸통이 같이 돌아가지 않게 해주세요.")
    if head_tilt_max > 20:
        feedbacks.append("고개를 숙이지 말고 정면 높이를 유지해주세요.")
    if shoulder_line_mean > 8:
        feedbacks.append("어깨를 기울이지 말고 편하게 유지해주세요.")

    if not feedbacks:
        feedbacks.append("좋아요. 목만 자연스럽게 좌우로 회전했습니다.")

    return {
        "feedbacks": feedbacks,
        "trunk_mean": round(trunk_mean, 3),
        "trunk_max": round(trunk_max, 3),
        "head_tilt_mean": round(head_tilt_mean, 3),
        "head_tilt_max": round(head_tilt_max, 3),
        "shoulder_line_mean": round(shoulder_line_mean, 3),
    }


def analyze_neck_rotation_video(
    video_path: str,
    reference_path: str,
    model_path: str,
):
    extracted = extract_neck_rotation_sequence_from_video(
        video_path=video_path,
        model_path=model_path,
        sample_every_n=2,
        visibility_th=0.3,
    )

    full_sequence = extracted["sequence"]
    source_frame_indices = extracted["source_frame_indices"]

    if len(full_sequence) == 0:
        raise RuntimeError("유효한 feature sequence를 추출하지 못했습니다.")

    rep_sequence, debug_info = extract_one_rep_neck_rotation(
        full_sequence,
        source_frame_indices=source_frame_indices,
    )

    if len(rep_sequence) == 0:
        raise RuntimeError(
            f"왕복 1세트 구간을 찾지 못했습니다. "
            f"(start_idx={debug_info['start_idx']}, peak_idx={debug_info['peak_idx']}, end_idx={debug_info['end_idx']})"
        )

    dtw_engine = NeckRotationDTW(reference_path)
    compare_result = dtw_engine.compare(rep_sequence)
    feedback_result = build_neck_rotation_feedback(rep_sequence)

    logger.info(
        "[NECK DTW RESULT] score=%s cost=%.4f trunk_max=%.3f head_tilt_max=%.3f shoulder_line_mean=%.3f",
        compare_result["score"],
        compare_result["cost"],
        feedback_result["trunk_max"],
        feedback_result["head_tilt_max"],
        feedback_result["shoulder_line_mean"],
    )

    result = {
        "video": os.path.basename(video_path),
        "fps": extracted["fps"],
        "frames_total": len(full_sequence),
        "frames_used": len(rep_sequence),
        "start_idx": debug_info["start_idx"],
        "peak_idx": debug_info["peak_idx"],
        "end_idx": debug_info["end_idx"],
        "start_source_frame": debug_info["start_source_frame"],
        "end_source_frame": debug_info["end_source_frame"],
        "neutral_baseline": debug_info["neutral_baseline"],
        "peak_val": debug_info["peak_val"],
        "score": compare_result["score"],
        "dtw_score": compare_result["dtw_score"],
        "cost": compare_result["cost"],
        "feedbacks": feedback_result["feedbacks"],
        "trunk_mean": feedback_result["trunk_mean"],
        "trunk_max": feedback_result["trunk_max"],
        "head_tilt_mean": feedback_result["head_tilt_mean"],
        "head_tilt_max": feedback_result["head_tilt_max"],
        "shoulder_line_mean": feedback_result["shoulder_line_mean"],
    }

    return result


def main():
    video_path = "./app/assets/neck_rotation_err5.mp4"
    reference_path = "./app/assets/reference/neck_rotation_reference_mp.json"
    model_path = "./app/assets/models/pose_landmarker_full.task"

    save_path = "./app/assets/neck_rotation_similarity.mp4"

    # 1) 최종 분석 결과
    result = analyze_neck_rotation_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
    )

    # 2) 테스트 영상 preview 저장
    preview_neck_rotation_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        save_path=save_path,
        sample_every_n=2,
        visibility_th=0.3,
    )

    print("\n========== 목 좌우 회전 분석 결과 ==========\n")
    print(f"[저장 완료] → {save_path}\n")

    print(f"[영상 정보]")
    print(f"- 파일명             : {result['video']}")
    print(f"- FPS                : {result['fps']}")
    print(f"- 전체 프레임        : {result['frames_total']}")
    print(f"- 사용 프레임        : {result['frames_used']}")
    print(f"- 시작 인덱스        : {result['start_idx']}")
    print(f"- 피크 인덱스        : {result['peak_idx']}")
    print(f"- 종료 인덱스        : {result['end_idx']}")
    print(f"- 시작 원본 프레임   : {result['start_source_frame']}")
    print(f"- 종료 원본 프레임   : {result['end_source_frame']}")
    print(f"- neutral baseline   : {result['neutral_baseline']:.3f}")
    print(f"- peak val           : {result['peak_val']:.3f}\n")

    print(f"[점수]")
    print(f"- DTW 점수           : {result['dtw_score']}")
    print(f"- DTW cost           : {result['cost']:.4f}\n")

    print(f"[자세 요약]")
    print(f"- 몸통 평균          : {result['trunk_mean']}")
    print(f"- 몸통 최대          : {result['trunk_max']}")
    print(f"- 고개 숙임 평균     : {result['head_tilt_mean']}")
    print(f"- 고개 숙임 최대     : {result['head_tilt_max']}")
    print(f"- 어깨선 평균        : {result['shoulder_line_mean']}\n")

    print(f"[피드백]")
    for fb in result["feedbacks"]:
        print(f"- {fb}")

    print("\n===========================================\n")


if __name__ == "__main__":
    main()