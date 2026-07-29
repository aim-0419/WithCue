export const REGION_META = {
  neck: {
    label: "목",
    joints: ["경추", "어깨선"],
    description:
      "목을 좌우로 돌리는 과정에서 경추 회전 범위와 몸통 고정 여부를 함께 확인합니다.",
  },
  right_arm: {
    label: "오른팔",
    joints: ["어깨", "팔꿈치", "손목"],
    description:
      "팔을 들어 올리는 과정에서 어깨 굴곡, 팔꿈치 각도, 손목 안정성을 확인합니다.",
  },
  left_arm: {
    label: "왼팔",
    joints: ["어깨", "팔꿈치", "손목"],
    description:
      "팔을 들어 올리는 과정에서 어깨 굴곡, 팔꿈치 각도, 손목 안정성을 확인합니다.",
  },
  torso: {
    label: "몸통",
    joints: ["척추", "골반", "어깨선"],
    description:
      "상체 중심선과 몸통 기울기를 바탕으로 운동 중 체간 안정성을 확인합니다.",
  },
  pelvis: {
    label: "골반",
    joints: ["고관절", "골반선"],
    description:
      "골반의 좌우 균형과 흔들림 정도를 확인해 하체 움직임의 기준 축을 분석합니다.",
  },
  right_leg: {
    label: "오른쪽 다리",
    joints: ["고관절", "무릎", "발목"],
    description:
      "다리를 들어 올리는 동안 고관절 가동 범위와 무릎, 발목 정렬 안정성을 확인합니다.",
  },
  left_leg: {
    label: "왼쪽 다리",
    joints: ["고관절", "무릎", "발목"],
    description:
      "다리를 들어 올리는 동안 고관절 가동 범위와 무릎, 발목 정렬 안정성을 확인합니다.",
  },
  right_thigh: {
    label: "오른쪽 허벅지",
    joints: ["고관절", "무릎"],
    description:
      "허벅지 구간에서 고관절과 무릎의 움직임 연결성을 중심으로 분석합니다.",
  },
  left_thigh: {
    label: "왼쪽 허벅지",
    joints: ["고관절", "무릎"],
    description:
      "허벅지 구간에서 고관절과 무릎의 움직임 연결성을 중심으로 분석합니다.",
  },
  right_calf: {
    label: "오른쪽 종아리",
    joints: ["무릎", "발목"],
    description:
      "종아리 구간에서 무릎 정렬과 발목 흔들림을 중심으로 하체 안정성을 확인합니다.",
  },
  left_calf: {
    label: "왼쪽 종아리",
    joints: ["무릎", "발목"],
    description:
      "종아리 구간에서 무릎 정렬과 발목 흔들림을 중심으로 하체 안정성을 확인합니다.",
  },
};

export default REGION_META;
