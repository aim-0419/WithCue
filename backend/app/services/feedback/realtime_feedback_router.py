from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.exercises.bird_dog.feedback import extract_birddog_issues
from app.exercises.knee_raise.feedback import extract_knee_raise_right_issues
from app.exercises.neck_rotation.feedback import extract_neck_rotation_issues
from app.exercises.shoulder_front_raise.feedback import extract_shoulder_front_raise_issues


Extractor = {
    "bird_dog": extract_birddog_issues,
    "knee_raise_right": extract_knee_raise_right_issues,
    "neck_rotation": extract_neck_rotation_issues,
    "shoulder_front_raise": extract_shoulder_front_raise_issues,
}


class RealTimeFeedbackRouter:
    def __init__(self, cooldown_sec: float = 2.5, emit_threshold: float = 0.35):
        self.cooldown_sec = float(cooldown_sec)
        self.emit_threshold = float(emit_threshold)
        self._last_emit_at: Dict[str, float] = {}

    def _cooldown_ok(self, key: str, now_sec: float) -> bool:
        last = self._last_emit_at.get(key, -1e9)
        return (now_sec - last) >= self.cooldown_sec

    def _pick_issue_for_emit(
        self, exercise_type: str, issues: List[Dict[str, Any]], timestamp_sec: float
    ) -> Optional[Dict[str, Any]]:
        if not issues:
            return None
        ordered = sorted(issues, key=lambda x: float(x.get("severity", 0.0)), reverse=True)
        for issue in ordered:
            sev = float(issue.get("severity", 0.0))
            if sev < self.emit_threshold:
                continue
            key = f"{exercise_type}:{issue.get('error_type', 'unknown')}"
            if not self._cooldown_ok(key, timestamp_sec):
                continue
            self._last_emit_at[key] = timestamp_sec
            return issue
        return None

    def process(
        self, exercise_type: str, compare_result: Dict[str, Any], timestamp_sec: float
    ) -> Dict[str, Any]:
        if exercise_type not in Extractor:
            return {"exercise_type": exercise_type, "feedback": None, "issue": None, "all_issues": []}

        issues = Extractor[exercise_type](compare_result)
        emit_issue = self._pick_issue_for_emit(exercise_type, issues, float(timestamp_sec))
        feedback = emit_issue["instant_feedback"] if emit_issue else None
        return {
            "exercise_type": exercise_type,
            "feedback": feedback,
            "issue": emit_issue,
            "all_issues": issues,
        }

