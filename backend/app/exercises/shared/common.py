# 운동 코칭 피드백 생성에 공통으로 사용되는 작은 유틸리티 함수 모음.
# 유사도 수치 처리, 자세 오류 특징 추출, 피드백 이슈 객체 생성 등
# 여러 운동 모듈에서 반복적으로 필요한 계산을 한 곳에 모아 둔다.
from __future__ import annotations

from typing import Any, Dict, Iterable, List


# 임의의 실수 값을 0.0 이상 1.0 이하로 잘라 반환한다.
# 비율이나 확률 값이 범위를 벗어나지 않도록 보정할 때 사용한다.
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


# DTW 비교 결과에서 특정 특징(name)의 오류 크기를 꺼낸다.
# compare_result: DTW 비교 결과 딕셔너리.
# name: 꺼내고 싶은 특징 이름 (예: "elbow_angle").
# default: 해당 특징이 없을 때 반환할 기본값.
# 반환값: 해당 특징의 오류 수치 (0.0 이상의 실수).
def feature_error(compare_result: Dict[str, Any], name: str, default: float = 0.0) -> float:
    feature_errors = compare_result.get("feature_errors", {}) or {}
    return float(feature_errors.get(name, default))


# 현재 DTW 결과의 동작 단계(phase)가 지정한 단계 목록에 포함되는지 확인한다.
# compare_result: DTW 비교 결과 딕셔너리.
# phases: 확인할 단계 이름 목록 (예: ["up", "hold"]).
# 반환값: 현재 단계가 목록에 있으면 True, 아니면 False.
def phase_is(compare_result: Dict[str, Any], phases: Iterable[str]) -> bool:
    phase = str(compare_result.get("phase", "unknown"))
    return phase in set(phases)


# DTW 비교 결과에서 오류가 큰 특징 이름을 순서대로 최대 limit개 반환한다.
# compare_result: DTW 비교 결과 딕셔너리.
# limit: 반환할 최대 특징 수 (기본값 3).
# 반환값: 오류가 큰 순서로 정렬된 특징 이름 리스트.
def top_features(compare_result: Dict[str, Any], limit: int = 3) -> List[str]:
    feature_errors = compare_result.get("feature_errors", {}) or {}
    ordered = sorted(
        feature_errors.items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    return [name for name, _ in ordered[: max(1, int(limit))]]


# 유사도가 기준값(threshold)에 비해 얼마나 부족한지를 0 이상의 값으로 반환한다.
# similarity: 현재 유사도 값 (없으면 0 반환).
# threshold: 목표 기준 유사도.
# scale: 차이를 얼마나 크게 증폭할지 결정하는 배율.
# 반환값: 유사도 부족 정도를 나타내는 0 이상의 실수.
def similarity_gap(similarity: Any, threshold: float, scale: float = 30.0) -> float:
    if similarity is None:
        return 0.0
    return max(0.0, (float(threshold) - float(similarity)) / float(scale))


# 하나의 자세 오류 이슈 딕셔너리를 만들어 반환한다.
# error_type: 오류의 종류 이름 (예: "elbow_flare").
# body_part: 오류가 발생한 신체 부위 (예: "elbow").
# severity: 오류의 심각도 (0~1 범위로 자동 보정됨).
# instant_feedback: 사용자에게 즉시 보여줄 피드백 문자열.
# metric_name: 측정값의 이름 (예: "elbow_angle").
# metric_value: 실제 측정 수치.
# 반환값: 위 정보를 담은 딕셔너리.
def build_issue(
    *,
    error_type: str,
    body_part: str,
    severity: float,
    instant_feedback: str,
    metric_name: str,
    metric_value: float,
) -> Dict[str, Any]:
    return {
        "error_type": error_type,
        "body_part": body_part,
        "severity": clamp01(severity),
        "instant_feedback": instant_feedback,
        "metric_name": metric_name,
        "metric_value": float(metric_value),
    }

# kalman filtering 
# yolo좌표가 프레임마다 튀는걸 줄이기 위해, 각 관절 좌표별로 칼만 필터를 하나씩 만들어 부드럽게 만듦. 
import cv2
import numpy as np

# 3D Kalman Filter 지원 버전
# depth가 없는 경우에는 기존처럼 2D(x,y) 필터를 사용하고,
# depth가 있는 경우에는 3D(x,y,z) 필터를 사용한다. 
class KalmanKeypointSmoother: 
    def __init__(self, process_noise=1e-3, measurement_noise=1.0): 
        # 관절별 kalman filter 저장
        self.filters = {} 
        
        # 움직임 변화 허용 정도
        # 값이 크면 급격한 움직임을 더 잘 따라감
        self.process_noise = process_noise 
        
        # 측정값(YOLO)의 노이즈 정도
        # 값이 크면 측정값을 덜 믿고 더 부드럽게 보정
        self.measurement_noise = measurement_noise

    
    # -----------------------------
    # 2D Kalman Filter 생성
    # 상태: x, y, vx, vy
    # 측정: x, y
    # -----------------------------
    def _create_filter_2d(self, x, y):
        kf = cv2.KalmanFilter(4, 2)
        
        # 위치 + 속도 기반 예측 모델
        kf.transitionMatrix = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float32)
        
        # 실제 측정은 x,y만 사용
        kf.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float32)
        
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * self.process_noise
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * self.measurement_noise
        kf.errorCovPost = np.eye(4, dtype=np.float32)
        
        # 초기 위치 설정
        kf.statePost = np.array([[x], [y], [0], [0]], dtype=np.float32)
        
        return kf

    # -----------------------------
    # 3D Kalman Filter 생성
    # 상태: x, y, z, vx, vy, vz
    # 측정: x, y, z
    # -----------------------------
    def _create_filter_3d(self, x, y, z):
        kf = cv2.KalmanFilter(6, 3)
        
        # 위치 + 속도 기반 3차원 예측 모델
        kf.transitionMatrix = np.array([
            [1, 0, 0, 1, 0, 0],
            [0, 1, 0, 0, 1, 0],
            [0, 0, 1, 0, 0, 1],
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1],
        ], dtype=np.float32)

        # 실제 측정은 x,y,z만 사용
        kf.measurementMatrix = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
        ], dtype=np.float32)

        kf.processNoiseCov = np.eye(6, dtype=np.float32) * self.process_noise
        kf.measurementNoiseCov = np.eye(3, dtype=np.float32) * self.measurement_noise
        kf.errorCovPost = np.eye(6, dtype=np.float32)
        
        # 초기 위치 설정
        kf.statePost = np.array([[x], [y], [z], [0], [0], [0]], dtype=np.float32)
        
        return kf

    # -----------------------------
    # 모든 관절 좌표 보정
    # 입력:
    #   2D -> (x, y)
    #   3D -> (x, y, z)
    # 출력:
    #   보정된 좌표 딕셔너리
    # -----------------------------
    def smooth(self, pts: dict):
        smoothed = {}

        for idx, p in pts.items():
            
            # -------------------------
            # 3D 좌표 처리
            # -------------------------
            if len(p) >= 3:
                x, y, z = float(p[0]), float(p[1]), float(p[2])
                
                # 동일 관절이라도
                # 2D/3D 필터를 분리해서 관리
                key = (idx, "3d")

                if key not in self.filters:
                    self.filters[key] = self._create_filter_3d(x, y, z)

                kf = self.filters[key]
                
                # 다음 위치 예측
                kf.predict()

                # 실제 측정값 반영
                measurement = np.array([[x], [y], [z]], dtype=np.float32)
                corrected = kf.correct(measurement)

                smoothed[idx] = (
                    float(corrected[0][0]),
                    float(corrected[1][0]),
                    float(corrected[2][0]),
                )
                
            # -------------------------
            # 2D 좌표 처리
            # -------------------------
            else:
                x, y = float(p[0]), float(p[1])
                key = (idx, "2d")

                if key not in self.filters:
                    self.filters[key] = self._create_filter_2d(x, y)

                kf = self.filters[key]
                kf.predict()

                measurement = np.array([[x], [y]], dtype=np.float32)
                corrected = kf.correct(measurement)

                smoothed[idx] = (
                    float(corrected[0][0]),
                    float(corrected[1][0]),
                )
                
        # 보정된 좌표 반환
        return smoothed
    
     # 운동 종료 시 필터 초기화
    def reset(self):
        self.filters.clear()
            