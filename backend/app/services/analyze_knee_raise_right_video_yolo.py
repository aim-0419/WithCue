import os
import json
import cv2
import numpy as np
import logging

from ultralytics import YOLO

from app.services.dtw_feature_extractor import (
    get_knee_raise_right_features_yolo,
    flip_yolo_left_right,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class KneeRaiseRightYoloDTW:
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
        weights = np.array([
            1.8,  # hip_flexion
            2.0,  # knee_angle
            2.2,  # ankle_height
        ], dtype=np.float32)
        return float(np.linalg.norm((a - b) * weights))

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])

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
        arr = np.array(user_seq, dtype=np.float32)

        hip_mean = float(np.mean(arr[:, 0]))
        knee_min = float(np.min(arr[:, 1]))
        ankle_peak = float(np.max(arr[:, 2]))

        penalty = 0

        if knee_min < 150:
            penalty += 15
        elif knee_min < 165:
            penalty += 8

        if ankle_peak < 50:
            penalty += 10

        penalty = min(penalty, 25)

        return {
            "penalty": penalty,
            "hip_mean": hip_mean,
            "knee_min": knee_min,
            "ankle_peak": ankle_peak,
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
            "hip_mean": penalty_result["hip_mean"],
            "knee_min": penalty_result["knee_min"],
            "ankle_peak": penalty_result["ankle_peak"],
        }

    def get_live_similarity(self, partial_user_seq, min_frames: int = 10, live_window: int = 30):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {"live_similarity": None, "cost": None}

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

        return {"live_similarity": live_similarity, "cost": float(cost)}


def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)

    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()


def yolo_pts_from_frame(model, frame_bgr, visibility_th=0.3, imgsz=640):
    results = model(frame_bgr, verbose=False, device="cpu", imgsz=imgsz)

    if not results or results[0].keypoints is None:
        return None, None

    kpts = results[0].keypoints

    if kpts.xy is None or len(kpts.xy) == 0:
        return None, results[0]

    xy = kpts.xy[0].cpu().numpy()
    conf = kpts.conf[0].cpu().numpy() if kpts.conf is not None else None

    pts = {}
    for i, p in enumerate(xy):
        if conf is not None and conf[i] < visibility_th:
            continue

        x, y = float(p[0]), float(p[1])
        if x <= 0 and y <= 0:
            continue

        pts[i] = (x, y)

    return pts, results[0]


def extract_one_rep_knee_raise_right(sequence, margin=3):
    if not sequence:
        return [], None

    seq_arr = np.array(sequence, dtype=np.float32)
    lift_values = seq_arr[:, 2]
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

    start_idx = 0 if peak_idx <= 2 else int(np.argmin(smooth_lift[:peak_idx]))
    end_idx = n - 1 if peak_idx >= n - 3 else peak_idx + int(np.argmin(smooth_lift[peak_idx:]))

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
    save_path: str = "./app/assets/knee_raise_left_live_similarity_yolo.mp4",
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

    model = YOLO(model_path)
    dtw_engine = KneeRaiseRightYoloDTW(reference_path)

    sequence = []
    frame_idx = 0
    live_similarity = None
    live_cost = None

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        draw_frame = frame_bgr.copy()

        if frame_idx % sample_every_n == 0:
            pts, result0 = yolo_pts_from_frame(
                model,
                frame_bgr,
                visibility_th=visibility_th,
                imgsz=640,
            )

            if result0 is not None:
                draw_frame = result0.plot()

            if pts is not None:
                if use_left_flip:
                    pts = flip_yolo_left_right(pts)

                features = get_knee_raise_right_features_yolo(pts)

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

        cv2.rectangle(draw_frame, (20, 20), (520, 150), (0, 0, 0), -1)

        txt1 = "Knee Raise YOLO"
        txt2 = f"Input Side: {'LEFT->FLIP->RIGHT' if use_left_flip else 'RIGHT'}"
        txt3 = "Similarity: analyzing..." if live_similarity is None else f"Similarity: {live_similarity:.2f}"
        txt4 = "Cost: -" if live_cost is None else f"Cost: {live_cost:.4f}"

        cv2.putText(draw_frame, txt1, (35, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(draw_frame, txt2, (35, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)
        cv2.putText(draw_frame, txt3, (35, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(draw_frame, txt4, (35, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)

        out.write(draw_frame)
        frame_idx += 1

    cap.release()
    out.release()

    print(f"[완료] 저장 경로: {save_path}")


def extract_knee_raise_right_sequence_from_video(
    video_path: str,
    model_path: str,
    sample_every_n: int = 3,
    visibility_th: float = 0.3,
    use_left_flip: bool = False,
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 0 else 30

    model = YOLO(model_path)

    sequence = []
    frame_idx = 0

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        if frame_idx % sample_every_n != 0:
            frame_idx += 1
            continue

        pts, _ = yolo_pts_from_frame(
            model,
            frame_bgr,
            visibility_th=visibility_th,
            imgsz=640,
        )

        if pts is not None:
            if use_left_flip:
                pts = flip_yolo_left_right(pts)

            features = get_knee_raise_right_features_yolo(pts)

            if features is not None:
                current = tuple(round(v, 3) for v in features)
                prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                if current != prev:
                    sequence.append(features)

        frame_idx += 1

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

    if len(full_sequence) == 0:
        raise RuntimeError("유효한 feature sequence를 추출하지 못했습니다.")

    arr = np.array(full_sequence, dtype=np.float32)

    print("[DEBUG] sequence len:", len(arr))
    print("[DEBUG] ankle_height min/max:", float(arr[:, 2].min()), float(arr[:, 2].max()))
    print("[DEBUG] first 20 ankle_height:", arr[:20, 2].tolist())
    print("[DEBUG] last 20 ankle_height:", arr[-20:, 2].tolist())

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

    dtw_engine = KneeRaiseRightYoloDTW(reference_path)
    compare_result = dtw_engine.compare(rep_sequence)

    logger.info(
        "[DTW RESULT] score=%s dtw_score=%s penalty=%s cost=%.4f hip_mean=%.3f knee_min=%.3f ankle_peak=%.3f",
        compare_result["score"],
        compare_result["dtw_score"],
        compare_result["penalty"],
        compare_result["cost"],
        compare_result["hip_mean"],
        compare_result["knee_min"],
        compare_result["ankle_peak"],
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
        "hip_mean": compare_result["hip_mean"],
        "knee_min": compare_result["knee_min"],
        "ankle_peak": compare_result["ankle_peak"],
    }

    return result


def main():
    video_path = "./app/assets/knee_raise_left_err4.mp4"
    reference_path = "./app/assets/reference/knee_raise_left_reference_yolo.json"
    model_path = "./app/assets/models/yolov8n-pose.pt"

    use_left_flip = True

    preview_knee_raise_right_live_similarity(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        use_left_flip=use_left_flip,
        save_path="./app/assets/knee_raise_left_live_similarity_yolo.mp4",
    )

    result = analyze_knee_raise_right_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        use_left_flip=use_left_flip,
    )

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
    print(f"- peak_val        : {result['peak_val']}\n")

    print(f"[점수]")
    print(f"- DTW 점수        : {result['dtw_score']}")
    print(f"- 최종 점수       : {result['score']}")
    print(f"- 보상 감점       : {result['penalty']}")
    print(f"- DTW cost        : {result['cost']:.4f}\n")

    print(f"[YOLO Feature 분석]")
    print(f"- 고관절 평균     : {result['hip_mean']:.3f}")
    print(f"- 최소 무릎 각도  : {result['knee_min']:.3f}")
    print(f"- 발목 최고 높이  : {result['ankle_peak']:.3f}")
    print("\n===========================================\n")


if __name__ == "__main__":
    main()