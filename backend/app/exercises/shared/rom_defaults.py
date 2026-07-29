# 자세 분석 세션 전 사용할 일반인 기준 ROM 더미 데이터.
# 실제 서비스에서는 자세 분석 완료 후 localStorage에서 읽어온 값으로 대체된다.

DEFAULT_ROM: dict = {
    "shoulder_left_flexion_max":         160.0,
    "shoulder_right_flexion_max":        160.0,
    "neck_rotation_left_max":             70.0,
    "neck_rotation_right_max":            70.0,
    "knee_flexion_at_sit_left":           90.0,
    "knee_flexion_at_sit_right":          90.0,
    "sts_completed":                     False,
    "seated_knee_extension_left_max":    165.0,
    "seated_knee_extension_right_max":   165.0,
    "straight_leg_raise_left_max":        70.0,
    "straight_leg_raise_right_max":       70.0,
}
