# 서비스 전반에서 공유하는 열거형(Enum) 타입을 정의하는 모듈.
# 운동 스테이지(어떤 동작을 수행 중인지)를 문자열 상수로 관리해 오타를 방지한다.

from enum import Enum

# 코칭 가능한 재활 운동 종류를 열거한 클래스.
# SHOULDER_ABDUCTION(어깨 벌리기), SIDE_LEG_RAISE(옆으로 다리 들기), KNEE_FLEXION(무릎 굽히기)을 지원한다.
class Stage(Enum):
    SHOULDER_ABDUCTION = "SHOULDER_ABDUCTION"
    SIDE_LEG_RAISE = "SIDE_LEG_RAISE"
    KNEE_FLEXION = "KNEE_FLEXION"
