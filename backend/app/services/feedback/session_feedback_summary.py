# 운동 세션 전체에서 발생한 자세 문제를 누적하고 요약하는 모듈.
# 매 프레임마다 감지된 문제를 쌓아두었다가 세션 종료 시
# 가장 오래 지속되고 심각했던 문제 TOP 3를 계산해 반환합니다.
# 사용자에게 "이번 운동에서 가장 많이 틀린 자세"를 알려주는 데 사용됩니다.

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# 세션 동안 발생한 자세 문제를 종류별로 누적해 점수화하는 클래스.
# 지속 시간, 평균 심각도, 최대 심각도를 가중합산해 최종 순위를 결정합니다.
class SessionFeedbackSummary:
    # 누적 기준 최소 심각도와 최종 점수 계산에 쓸 가중치를 설정합니다.
    # 매개변수:
    #   min_track_severity - 이 값 미만의 문제는 집계에서 제외 (기본 0.2)
    #   w_duration - 지속 시간 가중치 (기본 0.5)
    #   w_mean_severity - 평균 심각도 가중치 (기본 0.35)
    #   w_max_severity - 최대 심각도 가중치 (기본 0.15)
    def __init__(
        self,
        min_track_severity: float = 0.2,
        w_duration: float = 0.5,
        w_mean_severity: float = 0.35,
        w_max_severity: float = 0.15,
    ):
        self.min_track_severity = float(min_track_severity)
        self.w_duration = float(w_duration)
        self.w_mean_severity = float(w_mean_severity)
        self.w_max_severity = float(w_max_severity)
        self._stats: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # 프레임 하나에서 감지된 자세 문제들을 내부 통계에 누적합니다.
    # 최소 심각도 미만인 문제는 무시합니다.
    # 매개변수: exercise_type - 운동 종류 / issues - 이 프레임의 문제 목록 / dt_sec - 이전 프레임과의 시간 간격(초)
    def observe(self, exercise_type: str, issues: List[Dict[str, Any]], dt_sec: float) -> None:
        dt = max(0.0, float(dt_sec))
        for issue in issues:
            sev = float(issue.get("severity", 0.0))
            if sev < self.min_track_severity:
                continue
            err = str(issue.get("error_type", "unknown"))
            body = str(issue.get("body_part", "unknown"))
            key = (exercise_type, err)
            row = self._stats.get(key)
            if row is None:
                row = {
                    "exercise_type": exercise_type,
                    "error_type": err,
                    "body_part": body,
                    "count": 0,
                    "duration_sec": 0.0,
                    "severity_sum": 0.0,
                    "severity_max": 0.0,
                    "last_feedback": str(issue.get("instant_feedback", "")),
                }
                self._stats[key] = row

            row["count"] += 1
            row["duration_sec"] += dt
            row["severity_sum"] += sev
            row["severity_max"] = max(float(row["severity_max"]), sev)
            if issue.get("instant_feedback"):
                row["last_feedback"] = str(issue["instant_feedback"])

    # 세션 종료 후 누적된 통계를 바탕으로 가장 심각한 자세 문제 목록을 반환합니다.
    # 지속 시간, 평균/최대 심각도를 가중합산해 순위를 매깁니다.
    # 매개변수: top_k - 반환할 상위 문제 수 (기본 3)
    # 반환값: {"top_issues": 상위 k개 목록, "all_issues": 전체 목록} 딕셔너리
    def finalize(self, top_k: int = 3) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for row in self._stats.values():
            count = max(1, int(row["count"]))
            mean_sev = float(row["severity_sum"]) / count
            score = (
                self.w_duration * float(row["duration_sec"])
                + self.w_mean_severity * mean_sev
                + self.w_max_severity * float(row["severity_max"])
            )
            items.append(
                {
                    "exercise_type": row["exercise_type"],
                    "error_type": row["error_type"],
                    "body_part": row["body_part"],
                    "count": int(row["count"]),
                    "duration_sec": float(row["duration_sec"]),
                    "mean_severity": mean_sev,
                    "max_severity": float(row["severity_max"]),
                    "aggregate_score": float(score),
                    "feedback": row["last_feedback"],
                }
            )

        items.sort(key=lambda x: x["aggregate_score"], reverse=True)
        return {"top_issues": items[: max(1, int(top_k))], "all_issues": items}


# 세션 요약 결과를 사람이 읽기 쉬운 텍스트 줄 목록으로 변환합니다.
# 매개변수: summary - finalize()가 반환한 요약 딕셔너리
# 반환값: 화면에 표시할 텍스트 줄 리스트
def format_top3_text(summary: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    top = list(summary.get("top_issues", []))
    if not top:
        return ["세션 요약: 큰 자세 오류가 감지되지 않았습니다."]
    lines.append("세션 요약 TOP3")
    for idx, item in enumerate(top, start=1):
        lines.append(
            f"{idx}. [{item['exercise_type']}] {item['body_part']} - "
            f"지속 {item['duration_sec']:.1f}s, 평균강도 {item['mean_severity']:.2f}"
        )
        lines.append(f"   피드백: {item['feedback']}")
    return lines
