from __future__ import annotations

from typing import Any, Dict, List, Tuple


class SessionFeedbackSummary:
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

