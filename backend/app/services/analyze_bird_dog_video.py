import os
import json
import cv2
import numpy as np
import mediapipe as mp

from app.services.dtw_feature_extractor import get_bird_dog_features_mp
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BirdDogDTW:
    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_peaks = self._get_motion_peaks(self.ref_seq)

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
        14개 feature 가중치
        [
            trunk, pelvic,
            right_arm, left_leg, left_arm, right_leg,
            right_arm_h_err, left_leg_h_err, left_arm_h_err, right_leg_h_err,
            right_elbow_angle, left_elbow_angle, left_knee_angle, right_knee_angle
        ]
        """
        weights = np.array([
            0.7, 0.7,                 # trunk, pelvic
            1.2, 1.2, 1.2, 1.2,       # motion angle 4개
            1.0, 1.0, 1.0, 1.0,       # horizontal error 4개
            1.2, 1.2, 1.2, 1.2        # elbow/knee angle 4개
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

    def _flip_left_right(self, seq: np.ndarray):
        """
        14개 feature 기준 좌우 반전

        원본:
        [
            trunk, pelvic,
            right_arm, left_leg, left_arm, right_leg,
            right_arm_h_err, left_leg_h_err, left_arm_h_err, right_leg_h_err,
            right_elbow_angle, left_elbow_angle, left_knee_angle, right_knee_angle
        ]

        반전:
        [
            trunk, pelvic,
            left_arm, right_leg, right_arm, left_leg,
            left_arm_h_err, right_leg_h_err, right_arm_h_err, left_leg_h_err,
            left_elbow_angle, right_elbow_angle, right_knee_angle, left_knee_angle
        ]
        """
        flipped = seq.copy()

        # motion angle swap
        flipped[:, 2], flipped[:, 4] = seq[:, 4], seq[:, 2]   # right_arm <-> left_arm
        flipped[:, 3], flipped[:, 5] = seq[:, 5], seq[:, 3]   # left_leg <-> right_leg

        # horizontal error swap
        flipped[:, 6], flipped[:, 8] = seq[:, 8], seq[:, 6]   # right_arm_h_err <-> left_arm_h_err
        flipped[:, 7], flipped[:, 9] = seq[:, 9], seq[:, 7]   # left_leg_h_err <-> right_leg_h_err

        # elbow / knee angle swap
        flipped[:, 10], flipped[:, 11] = seq[:, 11], seq[:, 10]  # right_elbow_angle <-> left_elbow_angle
        flipped[:, 12], flipped[:, 13] = seq[:, 13], seq[:, 12]  # left_knee_angle <-> right_knee_angle

        return flipped

    def _get_motion_peaks(self, seq: np.ndarray):
        """
        motion peak 비교는 여전히 motion angle 4개만 사용
        [right_arm, left_leg, left_arm, right_leg] = seq[:, 2:6]
        """
        return seq[:, 2:6].max(axis=0)

    def _calc_rom_penalty(self, user_seq: np.ndarray):
        """
        peak_ratios 순서:
        [right_arm, left_leg, left_arm, right_leg]
        """
        user_peaks = self._get_motion_peaks(user_seq)
        peak_ratios = user_peaks / (self.ref_peaks + 1e-6)

        mean_peak_ratio = float(np.mean(peak_ratios))
        min_peak_ratio = float(np.min(peak_ratios))
        max_peak_ratio = float(np.max(peak_ratios))

        # 좌우 균형
        arm_balance_gap = float(abs(peak_ratios[0] - peak_ratios[2]))
        leg_balance_gap = float(abs(peak_ratios[1] - peak_ratios[3]))
        balance_gap = arm_balance_gap + leg_balance_gap

        rom_penalty = 0

        # 1) 평균 ROM 부족 감점
        if mean_peak_ratio >= 0.90:
            rom_penalty += 0
        elif mean_peak_ratio >= 0.80:
            rom_penalty += 8
        elif mean_peak_ratio >= 0.70:
            rom_penalty += 18
        elif mean_peak_ratio >= 0.60:
            rom_penalty += 28
        else:
            rom_penalty += 40

        # 2) 한쪽이라도 너무 낮은 경우 추가 감점
        if min_peak_ratio < 0.60:
            rom_penalty += 18
        elif min_peak_ratio < 0.70:
            rom_penalty += 12
        elif min_peak_ratio < 0.80:
            rom_penalty += 6

        # 3) 좌우 불균형 감점
        if balance_gap >= 0.50:
            rom_penalty += 15
        elif balance_gap >= 0.35:
            rom_penalty += 10
        elif balance_gap >= 0.20:
            rom_penalty += 5

        # 4) 과도 상승 감점
        if max_peak_ratio > 1.25:
            rom_penalty += 12
        elif max_peak_ratio > 1.10:
            rom_penalty += 6

        rom_penalty = min(rom_penalty, 50)

        return {
            "rom_penalty": rom_penalty,
            "mean_peak_ratio": mean_peak_ratio,
            "min_peak_ratio": min_peak_ratio,
            "max_peak_ratio": max_peak_ratio,
            "arm_balance_gap": arm_balance_gap,
            "leg_balance_gap": leg_balance_gap,
            "balance_gap": balance_gap,
            "peak_ratios": peak_ratios,
        }
    
    def _calc_joint_penalty(self, user_seq: np.ndarray):
        """
        피크 구간에서 팔꿈치/무릎 펴짐 정도를 보고 별도 감점
        feature index:
        10: right_elbow_angle
        11: left_elbow_angle
        12: left_knee_angle
        13: right_knee_angle
        """
        arr = np.array(user_seq, dtype=np.float32)

        # A측: right_arm + left_leg
        # B측: left_arm + right_leg
        sig_a = arr[:, 2] + arr[:, 3]
        sig_b = arr[:, 4] + arr[:, 5]

        a_peak_idx = int(np.argmax(sig_a))
        b_peak_idx = int(np.argmax(sig_b))

        def angle_penalty(angle: float):
            # 180도에 가까울수록 잘 펴진 상태
            if angle >= 165:
                return 0
            elif angle >= 150:
                return 3
            elif angle >= 135:
                return 7
            else:
                return 12

        # A측 피크에서 봐야 할 관절
        right_elbow_a = float(arr[a_peak_idx, 10])
        left_knee_a = float(arr[a_peak_idx, 12])

        # B측 피크에서 봐야 할 관절
        left_elbow_b = float(arr[b_peak_idx, 11])
        right_knee_b = float(arr[b_peak_idx, 13])

        penalties = {
            "right_elbow_a": angle_penalty(right_elbow_a),
            "left_knee_a": angle_penalty(left_knee_a),
            "left_elbow_b": angle_penalty(left_elbow_b),
            "right_knee_b": angle_penalty(right_knee_b),
        }

        joint_penalty = sum(penalties.values())
        joint_penalty = min(joint_penalty, 25)

        return {
            "joint_penalty": joint_penalty,
            "a_peak_idx": a_peak_idx,
            "b_peak_idx": b_peak_idx,
            "right_elbow_a": right_elbow_a,
            "left_knee_a": left_knee_a,
            "left_elbow_b": left_elbow_b,
            "right_knee_b": right_knee_b,
            "joint_penalty_detail": penalties,
        }
        
    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)

        # 1) 원본 비교
        ref = self._normalize(self.ref_seq)
        user = self._normalize(user_seq)
        _, cost_original = self._dtw(ref, user)

        # 2) 좌우 반전 비교
        ref_flipped_raw = self._flip_left_right(self.ref_seq)
        ref_flipped = self._normalize(ref_flipped_raw)
        _, cost_flipped = self._dtw(ref_flipped, user)

        # 3) 더 좋은 방향 선택
        if cost_original <= cost_flipped:
            best_cost = cost_original
            used = "original"
        else:
            best_cost = cost_flipped
            used = "flipped"

        # 4) DTW 점수
        alpha = 3.0
        dtw_score = max(0, min(100, round(100 - alpha * best_cost)))

        # 5) ROM 감점
        rom_result = self._calc_rom_penalty(user_seq)

        rom_penalty = rom_result["rom_penalty"]
        mean_peak_ratio = rom_result["mean_peak_ratio"]
        min_peak_ratio = rom_result["min_peak_ratio"]
        max_peak_ratio = rom_result["max_peak_ratio"]
        arm_balance_gap = rom_result["arm_balance_gap"]
        leg_balance_gap = rom_result["leg_balance_gap"]
        balance_gap = rom_result["balance_gap"]
        peak_ratios = rom_result["peak_ratios"]
        
        # 6) Joint 감점
        joint_result = self._calc_joint_penalty(user_seq)
        joint_penalty = joint_result["joint_penalty"]

        # 7) 최종 점수
        final_score = max(0, min(100, dtw_score - rom_penalty - joint_penalty))

        return {
            "score": final_score,
            "dtw_score": dtw_score,
            "rom_penalty": rom_penalty,
            "cost": float(best_cost),
            "mean_peak_ratio": mean_peak_ratio,
            "min_peak_ratio": min_peak_ratio,
            "max_peak_ratio": max_peak_ratio,
            "arm_balance_gap": arm_balance_gap,
            "leg_balance_gap": leg_balance_gap,
            "balance_gap": balance_gap,
            "peak_ratios": peak_ratios.tolist(),
            "direction_used": used,
            "joint_penalty": joint_penalty,
            "a_peak_idx": joint_result["a_peak_idx"],
            "b_peak_idx": joint_result["b_peak_idx"],
            "right_elbow_a": joint_result["right_elbow_a"],
            "left_knee_a": joint_result["left_knee_a"],
            "left_elbow_b": joint_result["left_elbow_b"],
            "right_knee_b": joint_result["right_knee_b"],
            "joint_penalty_detail": joint_result["joint_penalty_detail"],
        }
        
    def _calc_live_joint_penalty(self, live_seq: np.ndarray, joint_avg_window: int = 5):
        """
        최근 몇 프레임 평균으로 관절 감점 계산
        - 실시간용이라 피크 1프레임 대신 최근 joint_avg_window 평균 사용
        """
        arr = np.array(live_seq, dtype=np.float32)

        if len(arr) == 0:
            return {
                "live_joint_penalty": 0,
                "right_elbow_mean": 180.0,
                "left_elbow_mean": 180.0,
                "left_knee_mean": 180.0,
                "right_knee_mean": 180.0,
                "joint_penalty_detail": {},
            }

        recent = arr[-joint_avg_window:] if len(arr) >= joint_avg_window else arr

        right_elbow_mean = float(np.mean(recent[:, 10]))
        left_elbow_mean = float(np.mean(recent[:, 11]))
        left_knee_mean = float(np.mean(recent[:, 12]))
        right_knee_mean = float(np.mean(recent[:, 13]))

        def angle_penalty(angle: float):
            if angle >= 165:
                return 0
            elif angle >= 150:
                return 3
            elif angle >= 135:
                return 7
            else:
                return 12

        penalties = {
            "right_elbow": angle_penalty(right_elbow_mean),
            "left_elbow": angle_penalty(left_elbow_mean),
            "left_knee": angle_penalty(left_knee_mean),
            "right_knee": angle_penalty(right_knee_mean),
        }

        live_joint_penalty = sum(penalties.values())
        live_joint_penalty = min(live_joint_penalty, 20)

        return {
            "live_joint_penalty": live_joint_penalty,
            "right_elbow_mean": right_elbow_mean,
            "left_elbow_mean": left_elbow_mean,
            "left_knee_mean": left_knee_mean,
            "right_knee_mean": right_knee_mean,
            "joint_penalty_detail": penalties,
        }


    def get_live_score(
        self,
        partial_user_seq,
        min_frames: int = 12,
        live_window: int = 30,
        joint_avg_window: int = 5,
    ):
        """
        실시간 종합점수 계산
        = 실시간 DTW 점수 - 실시간 ROM 감점 - 실시간 관절 감점

        partial_user_seq: 지금까지 누적된 사용자 feature sequence
        min_frames: 최소 프레임 수
        live_window: 최근 몇 개 feature 기준으로 비교할지
        joint_avg_window: 최근 몇 프레임 평균으로 관절 감점을 볼지
        """
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_score": None,
                "live_dtw_score": None,
                "live_rom_penalty": None,
                "live_joint_penalty": None,
                "live_similarity": None,
                "cost": None,
                "direction_used": None,
                "live_peak_ratios": None,
                "right_elbow_mean": None,
                "left_elbow_mean": None,
                "left_knee_mean": None,
                "right_knee_mean": None,
                "joint_penalty_detail": None,
            }

        # 최근 window만 사용
        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq

        # -----------------------------
        # 1) 실시간 DTW 점수
        # -----------------------------
        user = self._normalize(live_seq)

        ref_len = len(self.ref_seq)
        user_len = len(live_seq)
        use_len = min(ref_len, user_len)

        ref_partial_raw = self.ref_seq[:use_len]
        ref_partial = self._normalize(ref_partial_raw)

        user_partial = user[-use_len:]

        _, cost_original = self._dtw(ref_partial, user_partial)

        ref_flipped_raw = self._flip_left_right(self.ref_seq)[:use_len]
        ref_flipped = self._normalize(ref_flipped_raw)
        _, cost_flipped = self._dtw(ref_flipped, user_partial)

        if cost_original <= cost_flipped:
            best_cost = cost_original
            used = "original"
        else:
            best_cost = cost_flipped
            used = "flipped"

        alpha_live = 3.0
        live_dtw_score = max(0, min(100, round(100 - alpha_live * best_cost)))

        # -----------------------------
        # 2) 실시간 ROM 감점
        # -----------------------------
        live_peaks = self._get_motion_peaks(live_seq)
        live_peak_ratios = live_peaks / (self.ref_peaks + 1e-6)

        mean_peak_ratio = float(np.mean(live_peak_ratios))
        min_peak_ratio = float(np.min(live_peak_ratios))
        max_peak_ratio = float(np.max(live_peak_ratios))

        arm_balance_gap = float(abs(live_peak_ratios[0] - live_peak_ratios[2]))
        leg_balance_gap = float(abs(live_peak_ratios[1] - live_peak_ratios[3]))
        balance_gap = arm_balance_gap + leg_balance_gap

        live_rom_penalty = 0

        # 실시간은 너무 일찍 과하게 깎이지 않도록 완화
        # 최근 window 내에서 어느 정도 올라온 뒤에만 ROM 감점 반영
        motion_progress = float(np.max(live_peak_ratios))

        if motion_progress >= 0.70:
            # 평균 ROM 부족
            if mean_peak_ratio >= 0.90:
                live_rom_penalty += 0
            elif mean_peak_ratio >= 0.80:
                live_rom_penalty += 4
            elif mean_peak_ratio >= 0.70:
                live_rom_penalty += 8
            elif mean_peak_ratio >= 0.60:
                live_rom_penalty += 14
            else:
                live_rom_penalty += 20

            # 한쪽 너무 낮음
            if min_peak_ratio < 0.60:
                live_rom_penalty += 8
            elif min_peak_ratio < 0.70:
                live_rom_penalty += 5
            elif min_peak_ratio < 0.80:
                live_rom_penalty += 3

            # 좌우 불균형
            if balance_gap >= 0.50:
                live_rom_penalty += 8
            elif balance_gap >= 0.35:
                live_rom_penalty += 5
            elif balance_gap >= 0.20:
                live_rom_penalty += 3

            # 과도 상승
            if max_peak_ratio > 1.25:
                live_rom_penalty += 10
            elif max_peak_ratio > 1.10:
                live_rom_penalty += 5

        live_rom_penalty = min(live_rom_penalty, 25)

        # -----------------------------
        # 3) 실시간 관절 감점
        # -----------------------------
        joint_result = self._calc_live_joint_penalty(live_seq, joint_avg_window=joint_avg_window)
        live_joint_penalty = joint_result["live_joint_penalty"]

        # -----------------------------
        # 4) 최종 실시간 종합점수
        # -----------------------------
        live_score = max(0, min(100, live_dtw_score - live_rom_penalty - live_joint_penalty))

        return {
            "live_score": live_score,
            "live_dtw_score": live_dtw_score,
            "live_rom_penalty": live_rom_penalty,
            "live_joint_penalty": live_joint_penalty,
            "live_similarity": live_dtw_score,
            "cost": float(best_cost),
            "direction_used": used,
            "live_peak_ratios": live_peak_ratios.tolist(),
            "mean_peak_ratio": mean_peak_ratio,
            "min_peak_ratio": min_peak_ratio,
            "max_peak_ratio": max_peak_ratio,
            "arm_balance_gap": arm_balance_gap,
            "leg_balance_gap": leg_balance_gap,
            "balance_gap": balance_gap,
            "right_elbow_mean": joint_result["right_elbow_mean"],
            "left_elbow_mean": joint_result["left_elbow_mean"],
            "left_knee_mean": joint_result["left_knee_mean"],
            "right_knee_mean": joint_result["right_knee_mean"],
            "joint_penalty_detail": joint_result["joint_penalty_detail"],
        }
    
    def get_live_similarity(self, partial_user_seq, min_frames: int = 12, live_window: int = 30):
        """
        현재까지 들어온 sequence로 실시간 유사도 계산
        - partial_user_seq: 현재까지 누적된 사용자 feature sequence
        - min_frames: 너무 짧을 때 점수 흔들림 방지용 최소 프레임 수
        - live_window: 최근 몇 개 feature를 기준으로 볼지
        """
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
                "direction_used": None,
            }

        # 최근 live_window개만 사용
        if len(user_seq) > live_window:
            user_seq = user_seq[-live_window:]

        user = self._normalize(user_seq)

        ref_len = len(self.ref_seq)
        user_len = len(user_seq)
        use_len = min(ref_len, user_len)

        # reference도 같은 길이만큼 잘라 비교
        ref_partial_raw = self.ref_seq[:use_len]
        ref_partial = self._normalize(ref_partial_raw)

        user_partial = user[-use_len:]

        _, cost_original = self._dtw(ref_partial, user_partial)

        ref_flipped_raw = self._flip_left_right(self.ref_seq)[:use_len]
        ref_flipped = self._normalize(ref_flipped_raw)
        _, cost_flipped = self._dtw(ref_flipped, user_partial)

        if cost_original <= cost_flipped:
            best_cost = cost_original
            used = "original"
        else:
            best_cost = cost_flipped
            used = "flipped"

        alpha_live = 3.0
        live_similarity = max(0, min(100, round(100 - alpha_live * best_cost)))

        return {
            "live_similarity": live_similarity,
            "cost": float(best_cost),
            "direction_used": used,
        }

def get_signal(feat):
    """
    feat = [trunk, pelvic, right_arm, left_leg, left_arm, right_leg]
    """
    right_arm = feat[2]
    left_leg = feat[3]
    left_arm = feat[4]
    right_leg = feat[5]
    return (right_arm + left_leg) + (left_arm + right_leg)


def smooth_signals(signals, window_size=5):
    if len(signals) < window_size:
        return signals[:]

    half = window_size // 2
    smoothed = []
    for i in range(len(signals)):
        s = max(0, i - half)
        e = min(len(signals), i + half + 1)
        smoothed.append(float(np.mean(signals[s:e])))
    return smoothed


def extract_one_rep_bird_dog(sequence, active_ratio=0.55, smooth_window=3, margin=3):
    """
    버드독 전용:
    - A측(right_arm + left_leg)
    - B측(left_arm + right_leg)
    를 따로 보고
    둘 다 활성화된 구간이 있으면 1회로 판단
    """
    if not sequence:
        return [], None

    arr = np.array(sequence, dtype=np.float32)

    sig_a_raw = arr[:, 2] + arr[:, 3]  # right_arm + left_leg
    sig_b_raw = arr[:, 4] + arr[:, 5]  # left_arm + right_leg

    sig_a = np.array(smooth_signals(sig_a_raw.tolist(), window_size=smooth_window))
    sig_b = np.array(smooth_signals(sig_b_raw.tolist(), window_size=smooth_window))

    # 각 신호별 최소/최대 기반 활성 threshold
    a_min, a_max = float(sig_a.min()), float(sig_a.max())
    b_min, b_max = float(sig_b.min()), float(sig_b.max())

    a_th = a_min + (a_max - a_min) * active_ratio
    b_th = b_min + (b_max - b_min) * active_ratio

    a_active_idx = np.where(sig_a >= a_th)[0]
    b_active_idx = np.where(sig_b >= b_th)[0]

    debug_info = {
        "a_min": a_min,
        "a_max": a_max,
        "b_min": b_min,
        "b_max": b_max,
        "a_th": a_th,
        "b_th": b_th,
        "a_active_count": int(len(a_active_idx)),
        "b_active_count": int(len(b_active_idx)),
        "a_start": None,
        "a_end": None,
        "b_start": None,
        "b_end": None,
        "start_idx": None,
        "end_idx": None,
    }

    if len(a_active_idx) == 0 or len(b_active_idx) == 0:
        return [], debug_info

    a_start, a_end = int(a_active_idx[0]), int(a_active_idx[-1])
    b_start, b_end = int(b_active_idx[0]), int(b_active_idx[-1])

    debug_info["a_start"] = a_start
    debug_info["a_end"] = a_end
    debug_info["b_start"] = b_start
    debug_info["b_end"] = b_end
    
    first_start = min(a_start, b_start)
    first_end = a_end if a_start < b_start else b_end
    second_start = b_start if a_start < b_start else a_start

    gap = second_start - first_end
    debug_info["gap"] = gap

    max_gap = 999
    if gap > max_gap:
        return [], debug_info

    start_idx = max(0, min(a_start, b_start) - margin)
    end_idx = min(len(sequence) - 1, max(a_end, b_end) + margin)

    debug_info["start_idx"] = start_idx
    debug_info["end_idx"] = end_idx

    rep_sequence = sequence[start_idx:end_idx + 1]
    return rep_sequence, debug_info

def preview_bird_dog_live_similarity(
    video_path: str,
    reference_path: str,
    model_path: str,
    sample_every_n: int = 3,
    visibility_th: float = 0.3,
    save_path: str = "./app/assets/bird_dog_live_similarity.mp4",
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

    dtw_engine = BirdDogDTW(reference_path)

    sequence = []
    frame_idx = 0
    timestamp_ms = 0

    live_similarity = None
    live_score = None
    live_rom_penalty = None
    live_joint_penalty = None
    direction_used = None

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

                    features = get_bird_dog_features_mp(pts)
                    if features is not None:
                        current = tuple(round(v, 3) for v in features)
                        prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                        sequence.append(features)

                        live_result = dtw_engine.get_live_score(
                            sequence,
                            min_frames=12,
                            live_window=30,
                            joint_avg_window=5,
                        )

                        live_similarity = live_result["live_similarity"]
                        live_score = live_result["live_score"]
                        live_rom_penalty = live_result["live_rom_penalty"]
                        live_joint_penalty = live_result["live_joint_penalty"]
                        direction_used = live_result["direction_used"]

            # 텍스트 표시
            cv2.rectangle(draw_frame, (20, 20), (320, 80), (0, 0, 0), -1)

            if live_similarity is None:
                txt1 = "Similarity: analyzing..."
            else:
                txt1 = f"Similarity: {live_similarity}"

            cv2.putText(draw_frame, txt1, (35, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)

            out.write(draw_frame)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()
    out.release()

    print(f"[완료] 저장 경로: {save_path}")

def extract_bird_dog_sequence_from_video(
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

    live_similarity = None
    live_score = None
    live_rom_penalty = None
    live_joint_penalty = None
    direction_used = None

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

                features = get_bird_dog_features_mp(pts)
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


def analyze_bird_dog_video(
    video_path: str,
    reference_path: str,
    model_path: str,
):
    extracted = extract_bird_dog_sequence_from_video(
        video_path=video_path,
        model_path=model_path,
        sample_every_n=3,
        visibility_th=0.3,
    )

    full_sequence = extracted["sequence"]
    if len(full_sequence) == 0:
        raise RuntimeError("유효한 feature sequence를 추출하지 못했습니다.")

    rep_sequence, debug_info = extract_one_rep_bird_dog(
        full_sequence,
        active_ratio=0.45,
        smooth_window=3,
        margin=3,
    )
    logger.info(
        "[REP DETECT] start=%s end=%s a=(%s~%s) b=(%s~%s) gap=%s",
        debug_info.get("start_idx"),
        debug_info.get("end_idx"),
        debug_info.get("a_start"),
        debug_info.get("a_end"),
        debug_info.get("b_start"),
        debug_info.get("b_end"),
        debug_info.get("gap"),
    )

    if len(rep_sequence) == 0:
        raise RuntimeError(
            f"1회 수행 구간을 찾지 못했습니다. "
            f"(start_idx={debug_info['start_idx']}, end_idx={debug_info['end_idx']}, )"
        )

    dtw_engine = BirdDogDTW(reference_path)
    compare_result = dtw_engine.compare(rep_sequence)
    
    logger.info(
        "[DTW RESULT] score=%s dtw_score=%s rom_penalty=%s joint_penalty=%s cost=%.4f "
        "mean_peak_ratio=%.3f min_peak_ratio=%.3f max_peak_ratio=%.3f "
        "arm_balance_gap=%.3f leg_balance_gap=%.3f balance_gap=%.3f "
        "direction=%s peak_ratios=%s "
        "a_peak_idx=%s b_peak_idx=%s "
        "right_elbow_a=%.3f left_knee_a=%.3f left_elbow_b=%.3f right_knee_b=%.3f "
        "joint_detail=%s",
        compare_result["score"],
        compare_result["dtw_score"],
        compare_result["rom_penalty"],
        compare_result["joint_penalty"],
        compare_result["cost"],
        compare_result["mean_peak_ratio"],
        compare_result["min_peak_ratio"],
        compare_result["max_peak_ratio"],
        compare_result["arm_balance_gap"],
        compare_result["leg_balance_gap"],
        compare_result["balance_gap"],
        compare_result["direction_used"],
        compare_result["peak_ratios"],
        compare_result["a_peak_idx"],
        compare_result["b_peak_idx"],
        compare_result["right_elbow_a"],
        compare_result["left_knee_a"],
        compare_result["left_elbow_b"],
        compare_result["right_knee_b"],
        compare_result["joint_penalty_detail"],
    )
    result = {
        "video": os.path.basename(video_path),
        "fps": extracted["fps"],
        "frames_total": len(full_sequence),
        "frames_used": len(rep_sequence),
        "start_idx": debug_info["start_idx"],
        "end_idx": debug_info["end_idx"],
        "a_start": debug_info["a_start"],
        "a_end": debug_info["a_end"],
        "b_start": debug_info["b_start"],
        "b_end": debug_info["b_end"],
        "score": compare_result["score"],
        "dtw_score": compare_result["dtw_score"],
        "rom_penalty": compare_result["rom_penalty"],
        "cost": compare_result["cost"],
        "mean_peak_ratio": compare_result["mean_peak_ratio"],
        "peak_ratios": compare_result["peak_ratios"],
        "gap": debug_info["gap"],
        "direction_used": compare_result["direction_used"],
        "min_peak_ratio": compare_result["min_peak_ratio"],
        "max_peak_ratio": compare_result["max_peak_ratio"],
        "arm_balance_gap": compare_result["arm_balance_gap"],
        "leg_balance_gap": compare_result["leg_balance_gap"],
        "balance_gap": compare_result["balance_gap"],
        "joint_penalty": compare_result["joint_penalty"],
        "a_peak_idx": compare_result["a_peak_idx"],
        "b_peak_idx": compare_result["b_peak_idx"],
        "right_elbow_a": compare_result["right_elbow_a"],
        "left_knee_a": compare_result["left_knee_a"],
        "left_elbow_b": compare_result["left_elbow_b"],
        "right_knee_b": compare_result["right_knee_b"],
        "joint_penalty_detail": compare_result["joint_penalty_detail"],
    }
    print(f"a_start      : {result['a_start']}") 
    print(f"a_end        : {result['a_end']}")
    print(f"b_start      : {result['b_start']}")
    print(f"b_end        : {result['b_end']}")
    print(f"gap          : {result['gap']}")
    print(f"direction_used : {result['direction_used']}") # 원본이랑 사용자랑 비교했을때 원본과 같은 손 시작이면 original
    print(f"dtw_score      : {result['dtw_score']}") # 동작 패턴 점수 (흐름, 타이밍, 좌우 교차)
    print(f"rom_penalty    : {result['rom_penalty']}") # ROM 감점 (적정선까지 올리지 못했을 경우 감점)
    print(f"mean_peak_ratio: {result['mean_peak_ratio']:.3f}") # 평균적으로 기준의 어느정도 올라갔는지
    print(f"min_peak_ratio : {result['min_peak_ratio']:.3f}") # 가장 낮은 부위가 어느정도 올라갔는지
    print(f"max_peak_ratio : {result['max_peak_ratio']:.3f}") # 가장 많이 올라간 부위
    print(f"arm_balance_gap: {result['arm_balance_gap']:.3f}") 
    print(f"leg_balance_gap: {result['leg_balance_gap']:.3f}")
    print(f"balance_gap    : {result['balance_gap']:.3f}")
    print(f"direction_used : {result['direction_used']}")
    print(f"peak_ratios    : {result['peak_ratios']}") # 부위별 [right_arm, left_leg, left_arm, right_leg]
    print(f"joint_penalty  : {result['joint_penalty']}")
    print(f"a_peak_idx     : {result['a_peak_idx']}")
    print(f"b_peak_idx     : {result['b_peak_idx']}")
    print(f"right_elbow_a  : {result['right_elbow_a']:.3f}")
    print(f"left_knee_a    : {result['left_knee_a']:.3f}")
    print(f"left_elbow_b   : {result['left_elbow_b']:.3f}")
    print(f"right_knee_b   : {result['right_knee_b']:.3f}")
    print(f"joint_detail   : {result['joint_penalty_detail']}")
    return result


def main():
    video_path = "./app/assets/bird_dog_err8.mp4"
    reference_path = "./app/assets/reference/bird_dog_reference_mp.json"
    model_path = "./app/assets/models/pose_landmarker_full.task"

    # 1️⃣ 실시간 유사도 영상 생성
    preview_bird_dog_live_similarity(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
        save_path="./app/assets/bird_dog_live_similarity.mp4",
    )

    # 2️⃣ 최종 분석도 같이 실행
    result = analyze_bird_dog_video(
        video_path=video_path,
        reference_path=reference_path,
        model_path=model_path,
    )

    # 3️⃣ 출력
    print("\n========== 🔍 버드독 분석 결과 ==========\n")
    
    print(f"[영상 정보]")
    print(f"- 파일명        : {result['video']}")
    print(f"- FPS           : {result['fps']}")
    print(f"- 전체 프레임   : {result['frames_total']}")
    print(f"- 사용 프레임   : {result['frames_used']}")
    print(f"- 시작 인덱스   : {result['start_idx']}")
    print(f"- 종료 인덱스   : {result['end_idx']}\n")

    print(f"[점수]")
    print(f"- 최종 점수     : {result['score']}")
    print(f"- DTW 점수      : {result['dtw_score']}")
    print(f"- ROM 감점      : {result['rom_penalty']}")
    print(f"- 관절 감점     : {result['joint_penalty']}")
    print(f"- DTW cost      : {result['cost']:.4f}\n")

    print(f"[ROM 분석]")
    print(f"- 평균 비율     : {result['mean_peak_ratio']:.3f}")
    print(f"- 최소 비율     : {result['min_peak_ratio']:.3f}")
    print(f"- 최대 비율     : {result['max_peak_ratio']:.3f}")
    print(f"- 좌우 균형     : {result['balance_gap']:.3f}")
    print(f"- 방향          : {result['direction_used']}")
    print(f"- 피크 비율     : {result['peak_ratios']}\n")

    print(f"[관절 상태 (펴짐 정도)]")
    print(f"- A측 팔꿈치    : {result['right_elbow_a']:.1f}°")
    print(f"- A측 무릎      : {result['left_knee_a']:.1f}°")
    print(f"- B측 팔꿈치    : {result['left_elbow_b']:.1f}°")
    print(f"- B측 무릎      : {result['right_knee_b']:.1f}°")

    print(f"- 관절 감점 상세: {result['joint_penalty_detail']}\n")

    print("=========================================\n")


if __name__ == "__main__":
    main()
