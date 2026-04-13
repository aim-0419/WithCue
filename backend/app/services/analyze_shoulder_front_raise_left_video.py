import os
import json
import cv2
import numpy as np
import mediapipe as mp
import logging

from app.services.dtw_feature_extractor import (
    get_shoulder_front_raise_left_features_mp,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ShoulderFrontRaiseLeftDTW:
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
        6개 feature
        [
            trunk,
            shoulder_rise,
            left_arm_raise,
            left_elbow_angle,
            left_arm_h_err,
            support_dist,
        ]
        """
        weights = np.array([
            1.0,   # trunk
            1.2,   # shoulder_rise
            1.5,   # left_arm_raise
            1.0,   # left_elbow_angle
            1.2,   # left_arm_h_err
            2.0,   # support_dist
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

    def _calc_penalty(self, user_seq: np.ndarray):
        """
        간단한 보상 패널티
        - 몸통 흔들림
        - 어깨 보상
        - 팔꿈치 과도 굽힘
        """
        arr = np.array(user_seq, dtype=np.float32)

        trunk_mean = float(np.mean(arr[:, 0]))
        shoulder_rise_mean = float(np.mean(arr[:, 1]))
        elbow_min = float(np.min(arr[:, 3]))

        penalty = 0

        # trunk penalty
        if trunk_mean > 12:
            penalty += 12
        elif trunk_mean > 8:
            penalty += 6

        # shoulder compensation penalty
        if shoulder_rise_mean > 18:
            penalty += 12
        elif shoulder_rise_mean > 12:
            penalty += 6

        # elbow bending penalty
        if elbow_min < 120:
            penalty += 12
        elif elbow_min < 140:
            penalty += 6

        penalty = min(penalty, 25)

        return {
            "penalty": penalty,
            "trunk_mean": trunk_mean,
            "shoulder_rise_mean": shoulder_rise_mean,
            "elbow_min": elbow_min,
        }

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)

        ref = self._normalize(self.ref_seq)
        user = self._normalize(user_seq)

        _, cost = self._dtw(ref, user)

        alpha = 12.0
        dtw_score = max(0, min(100, round(100 - alpha * cost, 2)))

        penalty_result = self._calc_penalty(user_seq)
        penalty = penalty_result["penalty"]

        final_score = max(0, min(100, round(dtw_score - penalty, 2)))

        return {
            "score": final_score,
            "dtw_score": dtw_score,
            "cost": float(cost),
            "penalty": penalty,
            "trunk_mean": penalty_result["trunk_mean"],
            "shoulder_rise_mean": penalty_result["shoulder_rise_mean"],
            "elbow_min": penalty_result["elbow_min"],
        }

    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 10,
        live_window: int = 30,
    ):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
            }

        if len(user_seq) > live_window:
            user_seq = user_seq[-live_window:]

        user = self._normalize(user_seq)

        ref_len = len(self.ref_seq)
        user_len = len(user_seq)
        use_len = min(ref_len, user_len)

        ref_partial_raw = self.ref_seq[:use_len]
        ref_partial = self._normalize(ref_partial_raw)
        user_partial = user[-use_len:]

        _, cost = self._dtw(ref_partial, user_partial)

        alpha_live = 12.0
        live_similarity = max(0, min(100, round(100 - alpha_live * cost, 2)))

        return {
            "live_similarity": live_similarity,
            "cost": float(cost),
        }


def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)

    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()


def extract_one_rep_shoulder_front_raise_left(sequence, margin=3):
    """
    1회 동작 자동 추출
    - left_arm_raise(index=2) 기준
    - 첫 번째 상승 / peak / 하강 구간만 자름
    """
    if not sequence:
        return [], None

    arr = np.array(sequence, dtype=np.float32)
    raise_values = arr[:, 2]
    smooth_raise = np.array(moving_average(raise_values.tolist(), window=5), dtype=np.float32)

    # 시작점: 처음 의미 있게 올라가는 지점
    start_threshold = 35.0
    start_idx = None
    for i in range(len(smooth_raise)):
        if smooth_raise[i] >= start_threshold:
            start_idx = i
            break

    if start_idx is None:
        return [], {
            "start_idx": None,
            "peak_idx": None,
            "end_idx": None,
        }

    # 첫 번째 local peak
    peak_idx = None
    peak_search_threshold = 80.0
    for i in range(start_idx + 2, len(smooth_raise) - 2):
        prev_v = smooth_raise[i - 1]
        curr_v = smooth_raise[i]
        next_v = smooth_raise[i + 1]

        if curr_v >= peak_search_threshold and curr_v >= prev_v and curr_v >= next_v:
            peak_idx = i
            break

    if peak_idx is None:
        search_end = min(len(smooth_raise), start_idx + 60)
        rel_idx = int(np.argmax(smooth_raise[start_idx:search_end]))
        peak_idx = start_idx + rel_idx

    peak_val = float(smooth_raise[peak_idx])

    # 종료점: peak 이후 충분히 내려간 구간
    end_threshold = peak_val * 0.3
    hold_n = 5
    end_idx = len(sequence) - 1

    for i in range(peak_idx + 1, len(sequence) - hold_n + 1):
        window_vals = smooth_raise[i:i + hold_n]
        if all(v <= end_threshold for v in window_vals):
            end_idx = i
            break

    if end_idx <= peak_idx:
        end_idx = min(len(sequence) - 1, peak_idx + 20)

    start_idx = max(0, start_idx - margin)
    end_idx = min(len(sequence) - 1, end_idx + margin)

    rep_sequence = sequence[start_idx:end_idx + 1]

    debug_info = {
        "start_idx": start_idx,
        "peak_idx": peak_idx,
        "end_idx": end_idx,
        "peak_val": peak_val,
        "start_threshold": start_threshold,
        "end_threshold": end_threshold,
    }

    return rep_sequence, debug_info


def preview_shoulder_front_raise_left_live_similarity(
    video_path: str,
    reference_path: str,
    model_path: str,
    sample_every_n: int = 3,
    visibility_th: float = 0.3,
    save_path: str = "./app/assets/shoulder_front_raise_left_live_similarity.mp4",
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 0 else 30

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

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

    dtw_engine = ShoulderFrontRaiseLeftDTW(reference_path)

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

                    features = get_shoulder_front_raise_left_features_mp(pts)
                    if features is not None:
                        current = tuple(round(v, 3) for v in features)
                        prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                        if current != prev:
                            sequence.append(features)

                        live_result = dtw_engine.get_live_similarity(
                            sequence,
                            min_frames=10,
                            live_window=30,
                        )

                        live_similarity = live_result["live_similarity"]
                        live_cost = live_result["cost"]

            cv2.rectangle(draw_frame, (20, 20), (420, 120), (0, 0, 0), -1)

            txt1 = "Shoulder Front Raise Left"
            txt2 = (
                "Similarity: analyzing..."
                if live_similarity is None
                else f"Similarity: {live_similarity:.2f}"
            )
            txt3 = (
                "Cost: -"
                if live_cost is None
                else f"Cost: {live_cost:.4f}"
            )

            cv2.putText(draw_frame, txt1, (35, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(draw_frame, txt2, (35, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(draw_frame, txt3, (35, 108),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)

            out.write(draw_frame)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()
    out.release()

    print(f"[완료] 저장 경로: {save_path}")


def extract_shoulder_front_raise_left_sequence_from_video(
    video_path: str,
    model_path: str,
    sample_every_n: int = 3,
    visibility_th: float = 0.3,
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 0 else 30

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

                features = get_shoulder_front_raise_left_features_mp(pts)
                if features is not None:
                    current = tuple(round(v, 3) for v in features)
                    prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                    if current != prev:
                        sequence.append(features)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()

    return {
        "video_path": video_path,
        "fps": fps,
        "sequence": sequence,
    }


def analyze_shoulder_front_raise_left_video(
    video_path: str,
    reference_path: str,
    model_path: str,
):
    extracted = extract_shoulder_front_raise_left_sequence_from_video(
        video_path=video_path,
        model_path=model_path,
        sample_every_n=3,
        visibility_th=0.3,
    )

    full_sequence = extracted["sequence"]
    if len(full_sequence) == 0:
        raise RuntimeError("유효한 feature sequence를 추출하지 못했습니다.")

    rep_sequence, debug_info = extract_one_rep_shoulder_front_raise_left(
        full_sequence,
        margin=3,
    )

    logger.info(
        "[REP DETECT] start=%s peak=%s end=%s",
        debug_info.get("start_idx"),
        debug_info.get("peak_idx"),
        debug_info.get("end_idx"),
    )

    if len(rep_sequence) == 0:
        raise RuntimeError(
            f"1회 수행 구간을 찾지 못했습니다. "
            f"(start_idx={debug_info['start_idx']}, peak_idx={debug_info['peak_idx']}, end_idx={debug_info['end_idx']})"
        )

    dtw_engine = ShoulderFrontRaiseLeftDTW(reference_path)
    compare_result = dtw_engine.compare(rep_sequence)

    logger.info(
        "[DTW RESULT] score=%s dtw_score=%s penalty=%s cost=%.4f trunk_mean=%.3f shoulder_rise_mean=%.3f elbow_min=%.3f",
        compare_result["score"],
        compare_result["dtw_score"],
        compare_result["penalty"],
        compare_result["cost"],
        compare_result["trunk_mean"],
        compare_result["shoulder_rise_mean"],
        compare_result["elbow_min"],
    )

    result = {
        "video": os.path.basename(video_path),
        "fps": extracted["fps"],
        "frames_total": len(full_sequence),
        "frames_used": len(rep_sequence),
        "start_idx": debug_info["start_idx"],
        "peak_idx": debug_info["peak_idx"],
        "end_idx": debug_info["end_idx"],
        "score": compare_result["score"],
        "dtw_score": compare_result["dtw_score"],
        "penalty": compare_result["penalty"],
        "cost": compare_result["cost"],
        "trunk_mean": compare_result["trunk_mean"],
        "shoulder_rise_mean": compare_result["shoulder_rise_mean"],
        "elbow_min": compare_result["elbow_min"],
    }

    print(f"start_idx          : {result['start_idx']}")
    print(f"peak_idx           : {result['peak_idx']}")
    print(f"end_idx            : {result['end_idx']}")
    print(f"dtw_score          : {result['dtw_score']}")
    print(f"penalty            : {result['penalty']}")
    print(f"score              : {result['score']}")
    print(f"cost               : {result['cost']:.4f}")
    print(f"trunk_mean         : {result['trunk_mean']:.3f}")
    print(f"shoulder_rise_mean : {result['shoulder_rise_mean']:.3f}")
    print(f"elbow_min          : {result['elbow_min']:.3f}")

    return result


def main():
    video_path = "./app/assets/shoulder_front_raise_left_test3.mp4"
    reference_path = "./app/assets/reference/shoulder_front_raise_left_reference_mp.json"
    model_path = "./app/assets/models/pose_landmarker_full.task"

    preview_shoulder_front_raise_left_live_similarity(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        save_path="./app/assets/shoulder_front_raise_left_live_similarity.mp4",
    )

    result = analyze_shoulder_front_raise_left_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
    )

    print("\n========== 왼팔 전방 거상 분석 결과 ==========\n")
    print(f"[영상 정보]")
    print(f"- 파일명        : {result['video']}")
    print(f"- FPS           : {result['fps']}")
    print(f"- 전체 프레임   : {result['frames_total']}")
    print(f"- 사용 프레임   : {result['frames_used']}")
    print(f"- 시작 인덱스   : {result['start_idx']}")
    print(f"- 피크 인덱스   : {result['peak_idx']}")
    print(f"- 종료 인덱스   : {result['end_idx']}\n")

    print(f"[점수]")
    print(f"- 최종 점수     : {result['score']}")
    print(f"- DTW 점수      : {result['dtw_score']}")
    print(f"- 보상 감점     : {result['penalty']}")
    print(f"- DTW cost      : {result['cost']:.4f}\n")

    print(f"[보상 분석]")
    print(f"- 몸통 평균     : {result['trunk_mean']:.3f}")
    print(f"- 어깨상승 평균 : {result['shoulder_rise_mean']:.3f}")
    print(f"- 최소 팔꿈치각 : {result['elbow_min']:.3f}")
    print("\n===========================================\n")


if __name__ == "__main__":
    main()