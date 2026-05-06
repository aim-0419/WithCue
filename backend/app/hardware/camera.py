import pyrealsense2 as rs
import numpy as np
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class CameraManager:
    def __init__(self):
        self.pipeline = None
        self.config = None
        self.active = False
        self.intrinsics = None

    def start(self):
        """
        카메라 스트리밍 시작
        (이미 켜져 있으면 기존 파이프라인을 재사용합니다.)
        """
        if self.active and self.pipeline is not None:
            logger.info("[Camera] 이미 활성 상태입니다. 기존 파이프라인을 재사용합니다.")
            return True

        self.pipeline = None
        self.config = None
        self.intrinsics = None

        try:
            ctx = rs.context()
            devices = ctx.query_devices()
            if len(devices) == 0:
                raise RuntimeError("RealSense 장치를 찾지 못했습니다.")

            logger.info("[Camera] RealSense를 초기화하는 중입니다...")
            self.pipeline = rs.pipeline()
            self.config = rs.config()

            self.config.enable_stream(rs.stream.color, 848, 480, rs.format.bgr8, 30)
            self.config.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30)

            profile = self.pipeline.start(self.config)
            stream = profile.get_stream(rs.stream.depth)
            if stream:
                self.intrinsics = stream.as_video_stream_profile().get_intrinsics()
            if self.intrinsics is None:
                raise RuntimeError("RealSense depth intrinsics를 읽지 못했습니다.")

            self.active = True
            logger.info("[Camera] RealSense가 정상적으로 시작되었습니다.")
            return True

        except Exception as e:
            message = str(e)
            logger.exception("[Camera] 시작에 실패했습니다: %s", message)
            self.active = False
            self.intrinsics = None
            if self.pipeline is not None:
                try:
                    self.pipeline.stop()
                except Exception:
                    pass
            self.pipeline = None
            self.config = None

            if "Device or resource busy" in message:
                raise RuntimeError("RealSense 장치가 다른 프로세스에서 사용 중입니다.") from e
            raise RuntimeError(f"RealSense 초기화 실패: {message}") from e

    def stop(self):
        """
        카메라 스트리밍 종료
        (에러가 나도 강제로 상태를 '꺼짐'으로 만듦)
        """
        # 이미 꺼져 있으면 패스
        if not self.active:
            return

        logger.info("[Camera] RealSense를 종료하는 중입니다...")
        try:
            if self.pipeline:
                self.pipeline.stop()
        except Exception as e:
            logger.warning("[Camera] 종료 중 오류가 발생했지만 계속 진행합니다: %s", e)
        finally:
            self.pipeline = None
            self.config = None
            self.intrinsics = None
            self.active = False
            logger.info("[Camera] RealSense가 종료되었습니다.")

    def get_frame(self):
        """
        프레임 가져오기 (비동기 친화적)
        """
        if not self.active or self.pipeline is None:
            return None, None, None

        try:
            # 타임아웃 2초 (프레임 안 들어오면 에러 발생)
            frames = self.pipeline.wait_for_frames(timeout_ms=2000)
            
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()

            if not color_frame or not depth_frame:
                return None, None, None

            # numpy 배열로 변환
            color_image = np.asanyarray(color_frame.get_data())
            
            # Depth 데이터가 필요하면 여기서 변환 (현재는 원본 전달)
            # depth_image = np.asanyarray(depth_frame.get_data())
            
            # 필요한 경우 여기서 Align(정렬) 처리를 할 수도 있음
            
            return color_image, depth_frame, self.intrinsics

        except Exception as e:
            # 일시적인 프레임 드랍은 로그 남기지 않음 (로그 폭탄 방지)
            # print(f"[Camera] Frame Error: {e}")
            return None, None, None

    def get_3d_point(self, u, v, depth_frame, intrinsics):
        """ 2D 픽셀 좌표(u, v) -> 3D 좌표(x, y, z) 변환 """
        if not depth_frame or not intrinsics:
            return None
    
        # 1. 대상 픽셀의 깊이 값을 먼저 확인
        dist = depth_frame.get_distance(int(u), int(v))
        
        # 2. 만약 깊이 값이 0(유실)이라면, 주변 5x5 영역 탐색
        if dist <= 0:
            found = False
            # 중심에서 가까운 곳부터 외곽으로 확장하며 탁색
            for radius in range(1, 3):
                for i in range(-radius, radius + 1):
                    for j in range(-radius, radius + 1):
                        # 프레임 경계 밖으로 나가지 않도록 체크
                        check_u, check_v = int(u) + i, int(v) + j
                        if 0 <= check_u < 640 and 0 <= check_v < 480:
                            temp_dist = depth_frame.get_distance(check_u, check_v)
                            if temp_dist > 0:
                                dist = temp_dist
                                found = True
                                break
                    if  found: break
                if found: break
        
        # 3. 여전히 값을 못 찾았다면 None 반환
        if dist <= 0:
            return None
        
        # # 4. RealSense SDK를 이용한 3D 좌표 생성
        point_3d = rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], dist)
        return point_3d # [x, y, z]
    
    def update_keypoints_3d(self, keypoints: Dict, depth_frame, intrinsics):
        """
        YOLO keypoints(pixel)를 입력받아 미터 단위 3D 좌표(x_m, y_m, z)를 추가함.
        """
        if not keypoints or depth_frame is None or intrinsics is None:
            return keypoints
        
        for idx, kp in keypoints.items():
            # 1. 픽셀 -> 뎁스 맵 해상도 매핑 (이미 구현하신 비례식 적용)
            raw_u = max(0, min(int(kp['x'] * (848 / 1280)), 847))
            raw_v = max(0, min(int(kp['y'] * (480 / 720)), 479))
            
            # 2. 개별 점 3D 변환 호출
            p3d = self.get_3d_point(raw_u, raw_v, depth_frame, intrinsics)
            
            if p3d:
                kp['x_m'], kp ['y_m'], kp['z'] = p3d[0], p3d[1], p3d[2]
            else:
                kp['x_m'], kp ['y_m'], kp['z'] = None, None, None
                
        return keypoints

# 싱글톤 인스턴스 생성
camera_manager = CameraManager()
