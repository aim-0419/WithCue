# 목 회전 가동범위(ROM) 측정 프로세서.
# 오디오 스크립트가 phase를 주도하며, 백엔드는 매 프레임 좌우 최대값만 갱신한다.
# 세션 종료는 프론트의 signal_done() 호출로만 이루어진다.
import logging
from datetime import datetime

from app.exercises.shared.base import BaseProcessor
from app.exercises.neck_rotation.features import get_neck_rotation_features_yolo

logger = logging.getLogger(__name__)


class NeckROMMeasurementProcessor(BaseProcessor):

    def __init__(self, fps=30):
        self.fps = fps
        self.check_tag = "check_neck"
        self.left_max = 0.0
        self.right_max = 0.0
        self._finished = False

    def signal_done(self):
        self._finished = True

    def extract_mp_features(self, pts):
        return get_neck_rotation_features_yolo(pts)

    def reset(self):
        self.__init__(self.fps)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self._finished:
            return {
                "mode": "MEASURE",
                "stage": "NECK_ROM",
                "status": "finished",
                "message": "목 가동범위 검사가 완료되었습니다",
                "rom": {
                    "neck_rotation_left_max":  int(round(self.left_max)),
                    "neck_rotation_right_max": int(round(self.right_max)),
                },
                "measured_at": datetime.now().isoformat(timespec="seconds"),
            }

        if mp_features is None:
            return {"mode": "MEASURE", "stage": "NECK_ROM", "status": "waiting", "message": "자세를 인식 중입니다."}

        neck_angle = mp_features[1]

        # 좌우 최대값 갱신 (phase 무관, 매 프레임)
        if neck_angle < 0:
            self.left_max = max(self.left_max, abs(neck_angle))
        elif neck_angle > 0:
            self.right_max = max(self.right_max, abs(neck_angle))

        return {
            "mode": "MEASURE",
            "stage": "NECK_ROM",
            "status": "measuring",
            "message": "",
            "left_max": int(self.left_max),
            "right_max": int(self.right_max),
        }
