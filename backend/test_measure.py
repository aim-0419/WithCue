import sys
import os

# 프로젝트 경로 추가 (모듈을 불러오기 위함)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 필요한 함수들 임포트 (경로가 다를 경우 수정하세요)
from app.services.rules.posture import get_pose_angle
from app.core.geometry import calculate_angle

def run_test():
    print("🧪 [Test] 자세 분석 로직 독립 테스트 시작\n")

    # 1. 아까 로그에서 찍혔던 실제 데이터 샘플 (SHOULDER_ABDUCTION용)
    # {5: 어깨, 7: 팔꿈치, 11: 골반}
    sample_keypoints = {
        5: {'x': 269, 'y': 10}, 
        6: {'x': 341, 'y': 20}, 
        7: {'x': 252, 'y': 144}, 
        8: {'x': 360, 'y': 219}, 
        11: {'x': 282, 'y': 354}, 
        12: {'x': 327, 'y': 362}
    }

    # 2. get_pose_angle 직접 호출
    print(f"--- 1. get_pose_angle 테스트 ---")
    res = get_pose_angle("SHOULDER_ABDUCTION", sample_keypoints)
    print(f"결과 각도: {res}°\n")

    # 3. geometry.py의 calculate_angle 직접 테스트
    # (골반, 어깨, 팔꿈치 순서)
    print(f"--- 2. calculate_angle 직접 테스트 ---")
    p11 = [282.0, 354.0]
    p5 = [269.0, 10.0]
    p7 = [252.0, 144.0]
    
    try:
        angle = calculate_angle(p11, p5, p7)
        print(f"P11:{p11}, P5:{p5}, P7:{p7}")
        print(f"직접 계산된 각도: {angle}°")
    except Exception as e:
        print(f"❌ 계산 중 에러 발생: {e}")

if __name__ == "__main__":
    run_test()