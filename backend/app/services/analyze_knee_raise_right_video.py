# analyze_knee_raise_right_video.py
# 오른다리 Straight Leg Raise(SLR) DTW 테스트용
# - reference JSON 로드
# - 영상에서 feature sequence 추출
# - 1회 동작(start / peak / end) 자동 추출
# - DTW 점수 + 보상 패널티 계산
# - left 영상도 필요하면 flip_mediapipe_left_right() 후 right 기준으로 분석 가능

import os
import json
import cv2
import numpy as np
import mediapipe as mp
import logging

from app.services.dtw_feature_extractor import (
    get_knee_raise_right_features_mp,
    flip_mediapipe_left_right,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class KneeRaiseRightDTW:
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
        5개 feature
        [
            trunk,
            pelvic,
            right_hip_flexion,
            right_knee_angle,
            right_ankle_rel_y,
        ]
        """
        weights = np.array([
            2.7,   # trunk
            1.8,   # pelvic
            1.5,   # hip_flexion
            1.7,   # knee_angle (핵심)
            1.7,   # ankle_rel_y (핵심)
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
        - 무릎 굽힘
        - 몸통 기울기
        - 골반 흔들림
        """
        arr = np.array(user_seq, dtype=np.float32)

        trunk_mean = float(np.mean(arr[:, 0]))
        pelvic_std = float(np.std(arr[:, 1]))
        knee_min = float(np.min(arr[:, 3]))

        penalty = 0

        # knee bending penalty (핵심)
        if knee_min < 165:
            penalty += 15
        elif knee_min < 170:
            penalty += 8

        # trunk penalty
        if trunk_mean > 12:
            penalty += 10
        elif trunk_mean > 8:
            penalty += 5

        # pelvic instability penalty
        if pelvic_std > 8:
            penalty += 10
        elif pelvic_std > 5:
            penalty += 5

        penalty = min(penalty, 25)

        return {
            "penalty": penalty,
            "trunk_mean": trunk_mean,
            "pelvic_std": pelvic_std,
            "knee_min": knee_min,
        }

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)

        ref = self._normalize(self.ref_seq)
        user = self._normalize(user_seq)

        _, cost = self._dtw(ref, user)

        alpha = 6.0
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
            "pelvic_std": penalty_result["pelvic_std"],
            "knee_min": penalty_result["knee_min"],
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

        alpha_live = 6.0
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


def extract_one_rep_knee_raise_right(sequence, margin=3):
    """
    1회 동작 자동 추출
    - right_ankle_rel_y(index=4) 기준
    - baseline 가정 없이 valley -> peak -> valley로 자름
    """
    if not sequence:
        return [], None

    seq_arr = np.array(sequence, dtype=np.float32)   # (N, 5)
    lift_values = seq_arr[:, 4]                      # (N,)
    smooth_lift = np.array(moving_average(lift_values.tolist(), window=7), dtype=np.float32)

    n = len(smooth_lift)
    if n < 10:
        return [], {
            "start_idx": None,
            "peak_idx": None,
            "end_idx": None,
            "baseline": None,
            "peak_val": None,
            "start_threshold": None,
            "end_threshold": None,
        }

    # 앞뒤 10프레임 제외한 구간에서 peak 찾기
    search_start = 10
    search_end = n - 10 if n > 20 else n

    peak_idx = None
    for i in range(search_start, max(search_start, search_end - 1)):
        prev_v = float(smooth_lift[i - 1])
        curr_v = float(smooth_lift[i])
        next_v = float(smooth_lift[i + 1])

        if curr_v >= prev_v and curr_v >= next_v:
            if peak_idx is None or curr_v > float(smooth_lift[peak_idx]):
                peak_idx = i

    if peak_idx is None:
        peak_idx = int(np.argmax(smooth_lift))

    peak_val = float(smooth_lift[peak_idx])

    if peak_idx <= 2:
        start_idx = 0
    else:
        start_idx = int(np.argmin(smooth_lift[:peak_idx]))

    if peak_idx >= n - 3:
        end_idx = n - 1
    else:
        end_idx = peak_idx + int(np.argmin(smooth_lift[peak_idx:]))

    if end_idx <= start_idx:
        return [], {
            "start_idx": start_idx,
            "peak_idx": peak_idx,
            "end_idx": end_idx,
            "baseline": None,
            "peak_val": peak_val,
            "start_threshold": None,
            "end_threshold": None,
        }

    start_idx = max(0, start_idx - margin)
    end_idx = min(n - 1, end_idx + margin)

    rep_sequence = sequence[start_idx:end_idx + 1]

    debug_info = {
        "start_idx": start_idx,
        "peak_idx": peak_idx,
        "end_idx": end_idx,
        "baseline": None,
        "peak_val": peak_val,
        "start_threshold": None,
        "end_threshold": None,
    }

    return rep_sequence, debug_info


def preview_knee_raise_right_live_similarity(
    video_path: str,
    reference_path: str,
    model_path: str,
    sample_every_n: int = 2,
    visibility_th: float = 0.3,
    use_left_flip: bool = True,
    save_path: str = "./app/assets/knee_raise_right_live_similarity.mp4",
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

    dtw_engine = KneeRaiseRightDTW(reference_path)

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

                    if use_left_flip:
                        pts = flip_mediapipe_left_right(pts)

                    features = get_knee_raise_right_features_mp(pts)
                    if features is not None:
                        print("[RAW FEATURE]", features)
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

            cv2.rectangle(draw_frame, (20, 20), (450, 140), (0, 0, 0), -1)

            txt1 = "Knee Raise Right"
            txt2 = f"Input Side: {'LEFT->FLIP->RIGHT' if use_left_flip else 'RIGHT'}"
            txt3 = (
                "Similarity: analyzing..."
                if live_similarity is None
                else f"Similarity: {live_similarity:.2f}"
            )
            txt4 = (
                "Cost: -"
                if live_cost is None
                else f"Cost: {live_cost:.4f}"
            )

            cv2.putText(draw_frame, txt1, (35, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(draw_frame, txt2, (35, 72),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)
            cv2.putText(draw_frame, txt3, (35, 102),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(draw_frame, txt4, (35, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)

            out.write(draw_frame)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()
    out.release()

    print(f"[완료] 저장 경로: {save_path}")


def extract_knee_raise_right_sequence_from_video(
    video_path: str,
    model_path: str,
    sample_every_n: int = 3,
    visibility_th: float = 0.5,
    use_left_flip: bool = False,
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

                if use_left_flip:
                    pts = flip_mediapipe_left_right(pts)

                features = get_knee_raise_right_features_mp(pts)
                if features is not None:
                    trunk, pelvic, hip_flexion, knee_angle, ankle_rel_y = features

                    # # SLR reference 기준의 아주 느슨한 sanity filter
                    # if not (60 <= trunk <= 100):
                    #     frame_idx += 1
                    #     timestamp_ms += int(1000 / fps)
                    #     continue

                    # if not (80 <= pelvic <= 110):
                    #     frame_idx += 1
                    #     timestamp_ms += int(1000 / fps)
                    #     continue

                    # if not (120 <= hip_flexion <= 185):
                    #     frame_idx += 1
                    #     timestamp_ms += int(1000 / fps)
                    #     continue

                    # if not (140 <= knee_angle <= 185):
                    #     frame_idx += 1
                    #     timestamp_ms += int(1000 / fps)
                    #     continue

                    # if not (-80 <= ankle_rel_y <= 260):
                    #     frame_idx += 1
                    #     timestamp_ms += int(1000 / fps)
                    #     continue
                    
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


def analyze_knee_raise_right_video(
    video_path: str,
    reference_path: str,
    model_path: str,
    use_left_flip: bool = False,
):
    extracted = extract_knee_raise_right_sequence_from_video(
        video_path=video_path,
        model_path=model_path,
        sample_every_n=1,
        visibility_th=0.3,
        use_left_flip=use_left_flip,
    )

    full_sequence = extracted["sequence"]
    arr = np.array(full_sequence, dtype=np.float32)
    print("[DEBUG] sequence len:", len(arr))
    print("[DEBUG] ankle_rel_y min/max:", float(arr[:, 4].min()), float(arr[:, 4].max()))
    print("[DEBUG] first 20 ankle_rel_y:", arr[:20, 4].tolist())
    print("[DEBUG] last 20 ankle_rel_y:", arr[-20:, 4].tolist())
    if len(full_sequence) == 0:
        raise RuntimeError("유효한 feature sequence를 추출하지 못했습니다.")

    rep_sequence, debug_info = extract_one_rep_knee_raise_right(
        full_sequence,
        margin=3,
    )

    logger.info(
        "[REP DETECT] start=%s peak=%s end=%s baseline=%s peak_val=%s",
        debug_info.get("start_idx"),
        debug_info.get("peak_idx"),
        debug_info.get("end_idx"),
        debug_info.get("baseline"),
        debug_info.get("peak_val"),
    )

    if len(rep_sequence) == 0:
        raise RuntimeError(
            f"1회 수행 구간을 찾지 못했습니다. "
            f"(start_idx={debug_info['start_idx']}, peak_idx={debug_info['peak_idx']}, end_idx={debug_info['end_idx']})"
        )

    dtw_engine = KneeRaiseRightDTW(reference_path)
    compare_result = dtw_engine.compare(rep_sequence)

    logger.info(
        "[DTW RESULT] score=%s dtw_score=%s penalty=%s cost=%.4f trunk_mean=%.3f pelvic_std=%.3f knee_min=%.3f",
        compare_result["score"],
        compare_result["dtw_score"],
        compare_result["penalty"],
        compare_result["cost"],
        compare_result["trunk_mean"],
        compare_result["pelvic_std"],
        compare_result["knee_min"],
    )

    result = {
        "video": os.path.basename(video_path),
        "fps": extracted["fps"],
        "input_side_mode": "LEFT->FLIP->RIGHT" if use_left_flip else "RIGHT",
        "frames_total": len(full_sequence),
        "frames_used": len(rep_sequence),
        "start_idx": debug_info["start_idx"],
        "peak_idx": debug_info["peak_idx"],
        "end_idx": debug_info["end_idx"],
        "baseline": debug_info["baseline"],
        "peak_val": debug_info["peak_val"],
        "start_threshold": debug_info["start_threshold"],
        "end_threshold": debug_info["end_threshold"],
        "score": compare_result["score"],
        "dtw_score": compare_result["dtw_score"],
        "penalty": compare_result["penalty"],
        "cost": compare_result["cost"],
        "trunk_mean": compare_result["trunk_mean"],
        "pelvic_std": compare_result["pelvic_std"],
        "knee_min": compare_result["knee_min"],
    }

    print(f"input_side_mode    : {result['input_side_mode']}")
    print(f"start_idx          : {result['start_idx']}")
    print(f"peak_idx           : {result['peak_idx']}")
    print(f"end_idx            : {result['end_idx']}")
    print(f"baseline           : {result['baseline']}")
    print(f"peak_val           : {result['peak_val']}")
    print(f"start_threshold    : {result['start_threshold']}")
    print(f"end_threshold      : {result['end_threshold']}")
    print(f"dtw_score          : {result['dtw_score']}")
    print(f"penalty            : {result['penalty']}")
    print(f"score              : {result['score']}")
    print(f"cost               : {result['cost']}")
    print(f"trunk_mean         : {result['trunk_mean']}")
    print(f"pelvic_std         : {result['pelvic_std']}")
    print(f"knee_min           : {result['knee_min']}")

    return result


def main():
    video_path = "./app/assets/knee_raise_left_err4.mp4"
    reference_path = "./app/assets/reference/knee_raise_left_reference_mp.json"
    model_path = "./app/assets/models/pose_landmarker_full.task"
    

    # 오른다리 테스트 영상이면 False
    # 왼다리 테스트 영상을 right 기준으로 비교하려면 True
    use_left_flip = True

    preview_knee_raise_right_live_similarity(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        use_left_flip=use_left_flip,
        save_path="./app/assets/knee_raise_left_live_similarity.mp4",
    )

    result = analyze_knee_raise_right_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        use_left_flip=use_left_flip,
    )
    print("[DEBUG] video_path:", video_path)
    print("[DEBUG] use_left_flip:", use_left_flip)
    print("\n========== 분석 결과 ==========\n")
    print(f"[영상 정보]")
    print(f"- 파일명          : {result['video']}")
    print(f"- 입력 기준       : {result['input_side_mode']}")
    print(f"- FPS             : {result['fps']}")
    print(f"- 전체 프레임     : {result['frames_total']}")
    print(f"- 사용 프레임     : {result['frames_used']}")
    print(f"- 시작 인덱스     : {result['start_idx']}")
    print(f"- 피크 인덱스     : {result['peak_idx']}")
    print(f"- 종료 인덱스     : {result['end_idx']}")
    print(f"- baseline        : {result['baseline']}")
    print(f"- peak_val        : {result['peak_val']}")
    print(f"- start_threshold : {result['start_threshold']}")
    print(f"- end_threshold   : {result['end_threshold'] }\n")

    print(f"[점수]")
    print(f"- DTW 점수        : {result['dtw_score']}")
    print(f"- 최종 점수       : {result['score']}")
    print(f"- 보상 감점       : {result['penalty']}")
    print(f"- DTW cost        : {result['cost']:.4f}\n")

    print(f"[보상 분석]")
    print(f"- 몸통 평균       : {result['trunk_mean']:.3f}")
    print(f"- 골반 표준편차   : {result['pelvic_std']:.3f}")
    print(f"- 최소 무릎 각도  : {result['knee_min']:.3f}")
    print("\n===========================================\n")


if __name__ == "__main__":
    main()