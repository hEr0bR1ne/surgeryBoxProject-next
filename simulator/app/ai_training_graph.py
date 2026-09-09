"""
Training analysis agent graph.

This module gives the student and teacher apps one shared training-analysis
backend. It prefers LangGraph when installed, but falls back to the same node
order without LangGraph so the UI keeps working on machines without the extra
dependency.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, TypedDict

from app.agent_memory import AgentMemoryStore, compact_memory_for_prompt
from app.i18n import get_language, tr, tr_choice, tr_training_label


try:
    from langgraph.graph import END, StateGraph
except Exception:
    END = "__end__"
    StateGraph = None


class TrainingAnalysisState(TypedDict, total=False):
    username: str
    session: Dict[str, Any]
    recent_records: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    agent_memory: Dict[str, Any]
    updated_memory: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    difficulty_plan: Dict[str, Any]
    student_debrief: Dict[str, Any]
    teacher_advice: Dict[str, Any]
    decision_basis: List[str]
    final_student_report: str
    final_teacher_report: str
    agent_trace: List[Dict[str, Any]]
    errors: List[str]
    graph_backend: str


@dataclass
class TrainingAgentConfig:
    api_key: str = ""
    base_url: str = ""
    model: str = "qwen-plus"
    enable_llm: bool = True
    temperature: float = 0.2

    @classmethod
    def from_environment(cls, enable_llm: bool = True) -> "TrainingAgentConfig":
        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        base_url = os.getenv("DASHSCOPE_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
        model = os.getenv("DASHSCOPE_MODEL") or os.getenv("OPENAI_MODEL") or "qwen-plus"

        try:
            from app import ai_config_local as local_config
        except ImportError:
            from app import ai_config_example as local_config

        api_key = api_key or getattr(local_config, "API_KEY", "")
        base_url = base_url or getattr(local_config, "BASE_URL", "")
        model = (os.getenv("DASHSCOPE_MODEL") or os.getenv("OPENAI_MODEL")
                 or getattr(local_config, "MODEL", "qwen-plus"))

        return cls(api_key=api_key, base_url=base_url, model=model, enable_llm=enable_llm)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _training_profile(mode: Any) -> Dict[str, Any]:
    mode_text = str(mode or "").strip().lower()

    if mode_text == "change_dressing":
        return {
            "mode": "change_dressing",
            "label": "dressing change",
            "event_label": "procedural steps",
            "count_label": "Steps",
            "correct_label": "Steps Correct",
            "score_completion_label": "step completion",
            "uses_quiz": False,
            "uses_pull_metrics": False,
            "next_session_focus": [
                "Verify the catheter site and dressing field before starting.",
                "Remove the old dressing carefully without disturbing the catheter.",
                "Place the new sterile dressing squarely over the insertion site and hold steady.",
            ],
            "teacher_focus": [
                "Watch whether the student protects the catheter while removing the old dressing.",
                "Check hand control and sterile field awareness during the new dressing placement.",
                "Ask the student to verbalize what they are inspecting at the insertion site.",
            ],
        }

    if mode_text == "comprehensive":
        return {
            "mode": "comprehensive",
            "label": "comprehensive AR training",
            "event_label": "checkpoints",
            "count_label": "Checkpoints",
            "correct_label": "Quiz Correct",
            "score_completion_label": "checkpoint completion",
            "uses_quiz": True,
            "uses_pull_metrics": True,
            "next_session_focus": [
                "Confirm the starting position before each attempt.",
                "Keep the pull movement smooth and observable.",
                "Pause at each checkpoint long enough to answer confidently.",
            ],
            "teacher_focus": [
                "Ask the student to verbalize the next checkpoint before pulling.",
                "Watch for rushed motion and confirm the catheter position after each event.",
                "Use one targeted correction per attempt rather than overloading feedback.",
            ],
        }

    return {
        "mode": mode_text or "remove_needle_simulator",
        "label": "catheter removal training",
        "event_label": "checkpoints",
        "count_label": "Checkpoints",
        "correct_label": "Quiz Correct",
        "score_completion_label": "checkpoint completion",
        "uses_quiz": True,
        "uses_pull_metrics": True,
        "next_session_focus": [
            "Confirm the starting position before each attempt.",
            "Keep the pull movement smooth and observable.",
            "Pause at each checkpoint long enough to answer confidently.",
        ],
        "teacher_focus": [
            "Ask the student to verbalize the next checkpoint before pulling.",
            "Watch for rushed motion and confirm the catheter position after each event.",
            "Use one targeted correction per attempt rather than overloading feedback.",
        ],
    }


def _training_context_prompt(profile: Dict[str, Any]) -> str:
    rules = [
        f"Training type: {profile.get('label', 'training')}.",
        f"Use '{profile.get('event_label', 'checkpoints')}' as the event wording.",
    ]
    if not profile.get("uses_quiz", True):
        rules.append("Do not mention quiz, quiz mastery, quiz questions, or quiz correctness.")
    if not profile.get("uses_pull_metrics", True):
        rules.append("Do not mention pull distance, pull movement, pull speed, needle pull, or starting position.")
    return " ".join(rules)


def _mode_summary(metrics: Dict[str, Any]) -> str:
    profile = _training_profile(metrics.get("training_mode"))
    label = profile.get("label", "training")
    event_label = profile.get("event_label", "checkpoints")
    completed = int(_as_float(metrics.get("events_completed")))
    expected = int(_as_float(metrics.get("expected_events"), 4))
    accuracy = _format_percent(metrics.get("accuracy_pct"))
    if get_language() == "zh":
        return (
            f"{tr_training_label(profile.get('mode'))}表现较好：已完成 "
            f"{completed}/{expected} 个{'步骤' if not profile['uses_quiz'] else '检查点'}，"
            f"正确率为 {accuracy}。"
        )
    return (
        f"Strong performance in {label}: {completed}/{expected} {event_label} "
        f"completed with {accuracy} accuracy."
    )


def _compact_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize full storage records and already-flattened UI summaries."""
    if not isinstance(record, dict):
        return {}

    data = record.get("training_data")
    if not isinstance(data, dict):
        data = record

    compact = dict(data)
    if record.get("completed_at") and not compact.get("completed_at"):
        compact["completed_at"] = record.get("completed_at")
    if record.get("username") and not compact.get("username"):
        compact["username"] = record.get("username")
    if record.get("file_path") and not compact.get("file_path"):
        compact["file_path"] = record.get("file_path")
    return compact


def _count_triggered_events(value: Any) -> int:
    if isinstance(value, dict):
        return sum(1 for item in value.values() if item is not None)
    if isinstance(value, list):
        return len(value)
    return 0


def _event_completion(data: Dict[str, Any]) -> Dict[str, Any]:
    expected = int(_as_float(data.get("expected_events"), 4))
    expected = max(expected, 1)

    phase_count = data.get("phase4_events_completed")
    if phase_count is not None:
        completed = int(max(0, _as_float(phase_count)))
    else:
        completed = _count_triggered_events(data.get("events_triggered"))
        if completed <= 0:
            completed = _count_triggered_events(data.get("events_results"))
        if completed <= 0:
            completed = _count_triggered_events(data.get("quiz_results"))

    completed = min(completed, expected)
    return {
        "expected_events": expected,
        "events_completed": completed,
        "completion_rate": completed / expected if expected else 0.0,
    }


def _accuracy_from_data(data: Dict[str, Any], completion: Dict[str, Any]) -> float:
    result_items = _as_list(data.get("events_results"))
    if not result_items:
        for key in ("quiz_results", "question_results", "assessment_results"):
            value = data.get(key)
            if isinstance(value, dict):
                result_items.extend(value.values())
            else:
                result_items.extend(_as_list(value))

    if result_items:
        answered = 0
        correct = 0
        for item in result_items:
            if not isinstance(item, dict):
                continue
            result = item.get("correct")
            if result is None:
                result = item.get("is_correct")
            if isinstance(result, str):
                lowered = result.strip().lower()
                if lowered in {"true", "correct", "yes", "1"}:
                    result = True
                elif lowered in {"false", "incorrect", "wrong", "no", "0"}:
                    result = False
            if result is True:
                answered += 1
                correct += 1
            elif result is False:
                answered += 1
        if not answered:
            return max(0.0, min(100.0, completion.get("completion_rate", 0.0) * 100.0))
        expected = max(completion.get("expected_events", 4), 1)
        return max(0.0, min(100.0, correct * 100.0 / expected))

    accuracy = data.get("accuracy")
    if accuracy is not None:
        return max(0.0, min(100.0, _as_float(accuracy)))

    return max(0.0, min(100.0, completion.get("completion_rate", 0.0) * 100.0))


def _quiz_result_metrics(data: Dict[str, Any], expected_events: int, uses_quiz: bool = True) -> Dict[str, Any]:
    result_items = _as_list(data.get("events_results"))
    if not result_items:
        for key in ("quiz_results", "question_results", "assessment_results"):
            value = data.get(key)
            if isinstance(value, dict):
                result_items.extend(value.values())
            else:
                result_items.extend(_as_list(value))

    answered = 0
    correct = 0
    incorrect = 0

    def first_number(*keys: str) -> Optional[float]:
        for key in keys:
            if data.get(key) is not None:
                return _as_float(data.get(key))
        return None

    for item in result_items:
        if not isinstance(item, dict):
            continue
        result = item.get("correct")
        if result is None:
            result = item.get("is_correct")
        if isinstance(result, str):
            lowered = result.strip().lower()
            if lowered in {"true", "correct", "yes", "1"}:
                result = True
            elif lowered in {"false", "incorrect", "wrong", "no", "0"}:
                result = False
        if result is True:
            answered += 1
            correct += 1
        elif result is False:
            answered += 1
            incorrect += 1

    if not answered:
        direct_answered = first_number(
            "quiz_answered_count",
            "assessment_answered_count",
            "answered_count",
            "phase4_events_completed",
            "events_completed",
        )
        if direct_answered is None:
            triggered_count = _count_triggered_events(data.get("events_triggered"))
            direct_answered = triggered_count if triggered_count > 0 else None

        direct_correct = first_number(
            "quiz_correct_count",
            "assessment_correct_count",
            "correct_count",
            "correct_answers",
            "correct_events",
            "correct_steps",
        )
        direct_incorrect = first_number(
            "quiz_incorrect_count",
            "assessment_incorrect_count",
            "incorrect_count",
            "wrong_answers",
            "incorrect_events",
            "incorrect_steps",
        )

        if direct_correct is None and data.get("accuracy") is not None:
            direct_correct = round(_as_float(data.get("accuracy")) * max(expected_events, 1) / 100.0)

        if direct_correct is not None:
            correct = max(0, int(round(direct_correct)))
        if direct_incorrect is not None:
            incorrect = max(0, int(round(direct_incorrect)))
        if direct_answered is not None:
            answered = max(0, int(round(direct_answered)))
        else:
            answered = correct + incorrect
        answered = max(answered, correct + incorrect)

    if answered:
        quiz_accuracy = correct * 100.0 / max(expected_events, 1)
    else:
        quiz_accuracy = None

    metrics = {
        "assessment_answered_count": answered,
        "assessment_correct_count": correct,
        "assessment_incorrect_count": incorrect,
        "assessment_accuracy_pct": round(quiz_accuracy, 1) if quiz_accuracy is not None else None,
    }

    if uses_quiz:
        metrics.update({
            "quiz_answered_count": answered,
            "quiz_correct_count": correct,
            "quiz_incorrect_count": incorrect,
            "quiz_accuracy_pct": round(quiz_accuracy, 1) if quiz_accuracy is not None else None,
        })
    else:
        metrics.update({
            "quiz_answered_count": 0,
            "quiz_correct_count": 0,
            "quiz_incorrect_count": 0,
            "quiz_accuracy_pct": None,
        })
    return metrics


def _speed_metrics(data: Dict[str, Any], elapsed_time: float, pull_distance_cm: float) -> Dict[str, float]:
    speed_samples = []
    for key in ("speed_samples", "speeds", "speed_history"):
        for sample in _as_list(data.get(key)):
            if isinstance(sample, dict):
                speed_samples.append(abs(_as_float(sample.get("speed") or sample.get("speed_cm_s"))))
            else:
                speed_samples.append(abs(_as_float(sample)))

    avg_speed = _as_float(
        data.get("avg_speed_cm_s")
        or data.get("average_speed_cm_s")
        or data.get("avg_speed")
        or data.get("speed_cm_s")
    )
    max_speed = _as_float(data.get("max_speed_cm_s") or data.get("max_speed") or data.get("max_pull_speed"))

    if speed_samples:
        avg_speed = mean(speed_samples)
        max_speed = max(speed_samples)
    elif not avg_speed and elapsed_time > 0 and pull_distance_cm > 0:
        avg_speed = pull_distance_cm / elapsed_time

    return {
        "avg_speed_cm_s": round(abs(avg_speed), 2),
        "max_speed_cm_s": round(abs(max_speed), 2),
    }


def build_training_metrics(session: Dict[str, Any], recent_records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    data = _compact_record(session)
    recent = [_compact_record(item) for item in (recent_records or []) if isinstance(item, dict)]
    training_mode = data.get("training_mode") or data.get("training_type") or "unknown"
    record_id = (
        data.get("record_id")
        or data.get("file_path")
        or data.get("completed_at")
        or f"{training_mode}:{data.get('elapsed_time', '')}:{data.get('accuracy', '')}"
    )
    profile = _training_profile(training_mode)
    completion = _event_completion(data)
    accuracy = _accuracy_from_data(data, completion)
    quiz_metrics = _quiz_result_metrics(data, completion["expected_events"], uses_quiz=profile["uses_quiz"])

    elapsed_time = _as_float(data.get("elapsed_time"))
    pull_distance_cm = _as_float(
        data.get("max_pull_distance_cm")
        or data.get("max_pull_distance")
        or data.get("max_pulled_distance_cm")
        or data.get("pulled_distance_cm")
    )
    speed = _speed_metrics(data, elapsed_time, pull_distance_cm)

    recent_accuracies = [
        _accuracy_from_data(item, _event_completion(item))
        for item in recent
        if item
    ]
    recent_times = [_as_float(item.get("elapsed_time")) for item in recent if _as_float(item.get("elapsed_time")) > 0]
    recent_avg_accuracy = mean(recent_accuracies) if recent_accuracies else None
    recent_avg_time = mean(recent_times) if recent_times else None

    trend_accuracy_delta = None
    if recent_avg_accuracy is not None:
        trend_accuracy_delta = round(accuracy - recent_avg_accuracy, 1)

    return {
        "record_id": record_id,
        "file_path": data.get("file_path"),
        "training_mode": training_mode,
        "training_label": profile["label"],
        "event_label": profile["event_label"],
        "count_label": profile["count_label"],
        "correct_label": profile["correct_label"],
        "score_completion_label": profile["score_completion_label"],
        "uses_quiz": profile["uses_quiz"],
        "uses_pull_metrics": profile["uses_pull_metrics"],
        "completed_at": data.get("completed_at"),
        "elapsed_time_s": round(elapsed_time, 1),
        "accuracy_pct": round(accuracy, 1),
        "stored_accuracy_pct": round(_as_float(data.get("accuracy")), 1) if data.get("accuracy") is not None else None,
        "expected_events": completion["expected_events"],
        "events_completed": completion["events_completed"],
        "completion_rate_pct": round(completion["completion_rate"] * 100.0, 1),
        "quiz_answered_count": quiz_metrics["quiz_answered_count"],
        "quiz_correct_count": quiz_metrics["quiz_correct_count"],
        "quiz_incorrect_count": quiz_metrics["quiz_incorrect_count"],
        "quiz_accuracy_pct": quiz_metrics["quiz_accuracy_pct"],
        "assessment_answered_count": quiz_metrics["assessment_answered_count"],
        "assessment_correct_count": quiz_metrics["assessment_correct_count"],
        "assessment_incorrect_count": quiz_metrics["assessment_incorrect_count"],
        "assessment_accuracy_pct": quiz_metrics["assessment_accuracy_pct"],
        "max_pull_distance_cm": round(pull_distance_cm, 2),
        "avg_speed_cm_s": speed["avg_speed_cm_s"],
        "max_speed_cm_s": speed["max_speed_cm_s"],
        "recent_attempts_considered": len(recent),
        "recent_avg_accuracy_pct": round(recent_avg_accuracy, 1) if recent_avg_accuracy is not None else None,
        "recent_avg_time_s": round(recent_avg_time, 1) if recent_avg_time is not None else None,
        "trend_accuracy_delta_pct": trend_accuracy_delta,
        "manual_reset_required": True,
        "raw": data,
    }


def fallback_risk_assessment(metrics: Dict[str, Any]) -> Dict[str, Any]:
    profile = _training_profile(metrics.get("training_mode"))
    reasons: List[str] = []
    risk_score = 0

    accuracy = _as_float(metrics.get("accuracy_pct"))
    completion = _as_float(metrics.get("completion_rate_pct"))
    elapsed_time = _as_float(metrics.get("elapsed_time_s"))
    max_speed = _as_float(metrics.get("max_speed_cm_s"))

    if completion < 75:
        risk_score += 2
        reasons.append("The required event sequence was not fully completed.")
    elif completion < 100:
        risk_score += 1
        reasons.append("One or more training checkpoints still need confirmation.")

    if accuracy < 60:
        risk_score += 2
        if profile["uses_quiz"]:
            reasons.append("Quiz or event accuracy is below the safe-practice target.")
        else:
            reasons.append("Procedural step accuracy is below the safe-practice target.")
    elif accuracy < 80:
        risk_score += 1
        reasons.append("Accuracy is improving but not yet stable.")

    if elapsed_time and elapsed_time < 15:
        risk_score += 1
        reasons.append("The attempt may have been rushed.")

    if profile["uses_pull_metrics"] and max_speed > 8:
        risk_score += 1
        reasons.append("Peak pull speed is high; the teacher should watch for abrupt motion.")

    if risk_score >= 3:
        level = "high"
    elif risk_score >= 1:
        level = "medium"
    else:
        level = "low"
        reasons.append("No obvious safety or completion risk was detected from the saved metrics.")

    return {
        "level": level,
        "score": risk_score,
        "reasons": reasons,
    }


def fallback_difficulty_plan(metrics: Dict[str, Any], risk: Dict[str, Any]) -> Dict[str, Any]:
    profile = _training_profile(metrics.get("training_mode"))
    accuracy = _as_float(metrics.get("accuracy_pct"))
    completion = _as_float(metrics.get("completion_rate_pct"))
    trend = metrics.get("trend_accuracy_delta_pct")
    risk_level = risk.get("level", "medium")

    if risk_level == "low" and accuracy >= 85 and completion >= 100:
        action = "increase"
        level = "next"
        reason = "The latest attempt is complete and accurate enough for a harder scenario."
    elif risk_level == "high" or accuracy < 60 or completion < 75:
        action = "decrease"
        level = "foundation"
        reason = "The student should stabilize the basics before adding difficulty."
    else:
        action = "keep"
        level = "current"
        reason = "The student is close to the target, so repetition at the same level is useful."

    if isinstance(trend, (int, float)) and trend < -10:
        action = "keep" if action == "increase" else action
        reason += " Recent accuracy is trending down, so avoid a sudden jump."

    return {
        "action": action,
        "recommended_level": level,
        "reason": reason,
        "next_session_focus": profile["next_session_focus"],
    }


def fallback_student_debrief(metrics: Dict[str, Any], risk: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    profile = _training_profile(metrics.get("training_mode"))
    accuracy = _as_float(metrics.get("accuracy_pct"))
    completion = _as_float(metrics.get("completion_rate_pct"))
    elapsed = _as_float(metrics.get("elapsed_time_s"))
    trend = metrics.get("trend_accuracy_delta_pct")
    event_label = profile["event_label"]

    strengths = []
    improvements = []
    next_steps = []

    if completion >= 100:
        strengths.append(f"You completed all required {event_label} in this attempt.")
    else:
        improvements.append(f"Focus on completing every required {event_label} before ending the attempt.")

    if accuracy >= 80:
        if profile["uses_quiz"]:
            strengths.append("Your checkpoint answer accuracy is in a strong range.")
        else:
            strengths.append("Your procedural step accuracy is in a strong range.")
    else:
        if profile["uses_quiz"]:
            improvements.append("Review the checkpoint questions and link each answer to the procedure step.")
        else:
            improvements.append("Review the dressing-change sequence and keep each movement deliberate.")

    if elapsed > 0:
        strengths.append(f"You completed the attempt in {elapsed:.1f} seconds.")

    expected = int(_as_float(metrics.get("expected_events"), 4))
    correct_key = "quiz_correct_count" if profile["uses_quiz"] else "assessment_correct_count"
    answered_key = "quiz_answered_count" if profile["uses_quiz"] else "assessment_answered_count"
    correct = int(_as_float(metrics.get(correct_key), 0))
    answered = int(_as_float(metrics.get(answered_key), 0))
    if answered:
        if profile["uses_quiz"]:
            strengths.append(f"You answered {correct}/{expected} checkpoint questions correctly.")
        else:
            strengths.append(f"{correct}/{expected} dressing-change steps were completed correctly.")

    if isinstance(trend, (int, float)):
        if trend > 0:
            strengths.append(f"Your accuracy is up by {trend:.1f} percentage points compared with recent attempts.")
        elif trend < 0:
            improvements.append(f"Your accuracy is down by {abs(trend):.1f} percentage points compared with recent attempts.")

    if not strengths:
        strengths.append("You have a usable attempt recorded, which gives us a baseline for improvement.")

    next_steps.extend(plan.get("next_session_focus", [])[:3])

    return {
        "summary": _mode_summary(metrics),
        "score": f"{accuracy:.1f}% accuracy, {completion:.1f}% {profile['score_completion_label']}",
        "risk_level": risk.get("level", "medium"),
        "strengths": strengths,
        "areas_to_improve": improvements or ["None identified; performance meets the current standard."],
        "next_steps": next_steps,
    }


def _metrics_for_llm(metrics: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(metrics)
    compact.pop("raw", None)
    compact.pop("manual_reset_required", None)
    return compact


def fallback_teacher_advice(metrics: Dict[str, Any], risk: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    profile = _training_profile(metrics.get("training_mode"))
    accuracy = _as_float(metrics.get("accuracy_pct"))
    completion = _as_float(metrics.get("completion_rate_pct"))

    if accuracy >= 85 and completion >= 100 and risk.get("level") == "low":
        level = "ready for increased difficulty"
    elif accuracy >= 65 and completion >= 75:
        level = "developing"
    else:
        level = "foundation"

    return {
        "student_level": level,
        "difficulty_recommendation": plan.get("action", "keep"),
        "rationale": plan.get("reason", ""),
        "teaching_focus": profile["teacher_focus"],
        "safety_notes": risk.get("reasons", []),
    }


def _strip_json_fence(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = _strip_json_fence(text)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _bullets(items: Iterable[Any]) -> str:
    lines = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines) if lines else "- Not available"


def _trace_lines(trace: Iterable[Dict[str, Any]], include_agents: Optional[Iterable[str]] = None) -> str:
    allowed = set(include_agents or [])
    lines = []
    for item in trace:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", "")).strip()
        if allowed and agent not in allowed:
            continue
        summary = str(item.get("summary", "")).strip()
        if agent and summary:
            lines.append(f"- {_agent_display_name(agent)}: {summary}")
    return "\n".join(lines) if lines else f"- {tr('report.sequential_completed')}"


def _format_percent(value: Any) -> str:
    return f"{_as_float(value):.1f}%"


def _localized_risk(value: Any) -> str:
    text = str(value or "medium").strip().lower()
    localized = tr_choice("risk", text)
    return localized if not localized.startswith("risk.") else text


def _localized_plan(value: Any) -> str:
    text = str(value or "keep").strip().lower()
    localized = tr_choice("plan", text)
    return localized if not localized.startswith("plan.") else text


def _localized_student_level(value: Any) -> str:
    text = str(value or "developing").strip()
    if get_language() != "zh":
        return text
    lower = text.lower()
    if "ready" in lower or "increase" in lower or "advanced" in lower:
        return "可提高难度"
    if "foundation" in lower or "basic" in lower:
        return "基础巩固阶段"
    if "developing" in lower or "intermediate" in lower:
        return "发展中"
    return text


def _localized_profile_label(profile: Dict[str, Any], key: str) -> str:
    value = str(profile.get(key, "")).strip()
    if get_language() != "zh":
        return value
    mapping = {
        "Steps": "步骤",
        "Steps Correct": "正确步骤",
        "Checkpoints": "检查点",
        "Quiz Correct": "答题正确",
    }
    return mapping.get(value, value)


def _localized_workflow_label(backend: str) -> str:
    backend_text = str(backend or "sequential").strip()
    if get_language() != "zh":
        return f"{backend_text} multi-agent graph"
    if backend_text.lower() == "langgraph":
        return "LangGraph 多智能体工作流"
    return "顺序多智能体工作流"


def _localized_score_text(metrics: Dict[str, Any], profile: Dict[str, Any]) -> str:
    if get_language() == "zh":
        return (
            f"{_format_percent(metrics.get('accuracy_pct'))} 正确率，"
            f"{_format_percent(metrics.get('completion_rate_pct'))} 完成率"
        )
    return (
        f"{_format_percent(metrics.get('accuracy_pct'))} accuracy, "
        f"{_format_percent(metrics.get('completion_rate_pct'))} {profile['score_completion_label']}"
    )


def _localize_report_item(item: Any) -> str:
    text = str(item).strip()
    if get_language() != "zh" or not text:
        return text

    exact = {
        "The required event sequence was not fully completed.": "本次未完整完成要求的事件流程。",
        "One or more training checkpoints still need confirmation.": "仍有一个或多个训练检查点需要确认。",
        "Quiz or event accuracy is below the safe-practice target.": "检查点答题或事件正确率低于安全练习目标。",
        "Procedural step accuracy is below the safe-practice target.": "流程步骤正确率低于安全练习目标。",
        "Accuracy is improving but not yet stable.": "正确率正在提升，但还不够稳定。",
        "The attempt may have been rushed.": "本次训练可能偏快，需要放慢确认节奏。",
        "Peak pull speed is high; the teacher should watch for abrupt motion.": "最大拔出速度偏高，教师应关注是否存在突然用力。",
        "No obvious safety or completion risk was detected from the saved metrics.": "保存指标未发现明显的安全或完成风险。",
        "No obvious safety risk was detected from the saved metrics.": "保存指标未发现明显安全风险。",
        "None identified; performance meets the current standard.": "暂未发现明显问题；当前表现已达到训练标准。",
        "Repeat the dressing placement while keeping the sterile field organized.": "继续练习新敷贴放置，同时保持无菌区域有序。",
        "Maintain the same smooth pull control in the next attempt.": "下一次继续保持平稳、可观察的拔出控制。",
        "Verify the catheter site and dressing field before starting.": "开始前确认导管位置和敷贴区域。",
        "Remove the old dressing carefully without disturbing the catheter.": "移除旧敷贴时避免牵拉或扰动导管。",
        "Place the new sterile dressing squarely over the insertion site and hold steady.": "将新无菌敷贴平整覆盖穿刺点并稳定按压。",
        "Confirm the starting position before each attempt.": "每次训练前确认起始位置。",
        "Keep the pull movement smooth and observable.": "保持拔出动作平稳、可观察。",
        "Pause at each checkpoint long enough to answer confidently.": "到达每个检查点时充分停顿并确认答案。",
        "Ask the student to verbalize the next checkpoint before pulling.": "让学生在操作前口述下一个检查点。",
        "Watch for rushed motion and confirm the catheter position after each event.": "观察是否动作过快，并在每个事件后确认导管位置。",
        "Use one targeted correction per attempt rather than overloading feedback.": "每次训练只给一个重点纠正，避免反馈过载。",
        "Watch whether the student protects the catheter while removing the old dressing.": "观察学生移除旧敷贴时是否保护导管。",
        "Check hand control and sterile field awareness during the new dressing placement.": "检查新敷贴放置时的手部控制和无菌意识。",
        "Ask the student to verbalize what they are inspecting at the insertion site.": "让学生口述正在观察穿刺点的哪些内容。",
    }
    if text in exact:
        return exact[text]
    if f"{text}." in exact:
        return exact[f"{text}."]

    match = re.match(r"Checkpoint quiz result:\s*(\d+/\d+)\s*correct\.?", text, flags=re.IGNORECASE)
    if match:
        return f"检查点答题结果：{match.group(1)} 正确。"

    match = re.match(r"Dressing-change step result:\s*(\d+/\d+)\s*correct\.?", text, flags=re.IGNORECASE)
    if match:
        return f"换敷贴步骤结果：{match.group(1)} 正确。"

    match = re.match(
        r"Maintain consistency across sessions; recent average accuracy is\s*([0-9.]+%)\.?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return f"保持多次训练稳定性；近期平均正确率为 {match.group(1)}。"

    match = re.match(r"You completed the attempt in\s*([0-9.]+)\s*seconds\.?", text, flags=re.IGNORECASE)
    if match:
        return f"本次训练用时 {match.group(1)} 秒。"

    return text


def _localized_bullets(items: Iterable[Any]) -> str:
    return _bullets(_localize_report_item(item) for item in items)


def _agent_display_name(agent: str) -> str:
    if get_language() != "zh":
        return agent
    names = {
        "Memory Agent": "记忆智能体",
        "Metrics Analyst": "指标分析智能体",
        "Risk Agent": "风险评估智能体",
        "Difficulty Planner": "难度规划智能体",
        "Student Debrief Agent": "学生复盘智能体",
        "Teacher Coaching Agent": "教师指导智能体",
        "Report Writer": "报告生成智能体",
    }
    return names.get(agent, agent)


def _llm_language_instruction() -> str:
    if get_language() == "zh":
        return "Return all student- or teacher-facing text in Simplified Chinese. "
    return "Return all student- or teacher-facing text in English. "


def _markdown_table(rows: Iterable[Iterable[Any]]) -> str:
    lines = [f"| {tr('report.metric')} | {tr('report.result')} |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    return "\n".join(lines)


def _display_training_label(profile: Dict[str, Any]) -> str:
    mode = profile.get("mode")
    if mode:
        label = tr_training_label(mode)
        if not label.startswith("training."):
            return label
    label = str(profile.get("label", "training")).strip()
    known = {
        "catheter removal training": "Catheter Removal Training",
        "comprehensive AR training": "Comprehensive AR Training",
        "dressing change": "Dressing Change",
    }
    return known.get(label, label.title())


def build_decision_basis(
    metrics: Dict[str, Any],
    risk: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Create deterministic, teacher-readable rules behind the AI recommendation."""
    metrics = metrics or {}
    risk = risk or {}
    plan = plan or {}
    profile = _training_profile(metrics.get("training_mode"))

    expected = int(_as_float(metrics.get("expected_events"), 4))
    completed = int(_as_float(metrics.get("events_completed")))
    accuracy = _as_float(metrics.get("accuracy_pct"))
    completion = _as_float(metrics.get("completion_rate_pct"))
    event_label = str(profile.get("event_label", "checkpoints"))
    event_label_title = event_label.capitalize()
    recommendation = str(plan.get("action") or "keep").strip().lower()
    risk_level = str(risk.get("level") or "medium").strip().lower()

    if get_language() == "zh":
        event_zh = "步骤" if not profile["uses_quiz"] else "检查点"
        basis = [
            f"{event_zh}规则：已完成 {completed}/{expected} 个{event_zh}（完成率 {_format_percent(completion)}）。"
        ]
        if profile["uses_quiz"]:
            correct = int(_as_float(metrics.get("quiz_correct_count"), 0))
            basis.append(f"正确率规则：检查点答题正确 {correct}/{expected}（正确率 {_format_percent(accuracy)}）。")
        else:
            correct = int(_as_float(metrics.get("assessment_correct_count"), 0))
            basis.append(f"流程规则：关键操作正确 {correct}/{expected}（正确率 {_format_percent(accuracy)}）。")

        if recommendation == "increase":
            basis.append("难度规则：只有在完成率达到100%、正确率至少85%、且风险较低时才建议提高难度。")
        elif recommendation == "decrease":
            basis.append("难度规则：当完成率或正确率低于安全练习阈值时，建议降低难度巩固基础。")
        else:
            basis.append("难度规则：在表现稳定前，建议保持当前难度继续练习。")

        reasons = _as_list(risk.get("reasons"))
        if reasons:
            reason = _localize_report_item(str(reasons[0]).rstrip("."))
            basis.append(f"风险规则：本次被评为{_localized_risk(risk_level)}风险，主要原因是 {reason.rstrip('。')}。")
        else:
            basis.append(f"风险规则：根据完成率、正确率和安全指标，本次被评为{_localized_risk(risk_level)}风险。")

        recent_avg = metrics.get("recent_avg_accuracy_pct")
        trend = metrics.get("trend_accuracy_delta_pct")
        trend_parts = []
        if recent_avg is not None:
            trend_parts.append(f"近期平均正确率为 {_format_percent(recent_avg)}")
        if isinstance(trend, (int, float)):
            direction = "上升" if trend >= 0 else "下降"
            trend_parts.append(f"本次相比近期{direction} {abs(trend):.1f} 个百分点")
        if trend_parts:
            basis.append(f"趋势规则：{'，且'.join(trend_parts)}。")

        if profile["uses_pull_metrics"]:
            max_speed = _as_float(metrics.get("max_speed_cm_s"))
            if max_speed > 8:
                basis.append(f"安全规则：最大拔出速度为 {max_speed:.1f} cm/s，需要关注是否存在突然用力。")
            elif max_speed > 0:
                basis.append(f"安全规则：最大拔出速度为 {max_speed:.1f} cm/s，未触发速度风险提示。")
        else:
            basis.append("模块规则：换敷贴训练按流程练习统计，与拔管计分正确率分开计算。")
        return basis

    basis = [
        (
            f"{event_label_title} rule: {completed}/{expected} {event_label} completed "
            f"({_format_percent(completion)} completion)."
        )
    ]

    if profile["uses_quiz"]:
        correct = int(_as_float(metrics.get("quiz_correct_count"), 0))
        basis.append(
            f"Accuracy rule: {correct}/{expected} quiz responses correct "
            f"({_format_percent(accuracy)} accuracy)."
        )
    else:
        correct = int(_as_float(metrics.get("assessment_correct_count"), 0))
        basis.append(
            f"Procedure rule: {correct}/{expected} procedural steps correct "
            f"({_format_percent(accuracy)} accuracy)."
        )

    if recommendation == "increase":
        basis.append("Difficulty rule: increase only when completion is full, accuracy is at least 85%, and risk is low.")
    elif recommendation == "decrease":
        basis.append("Difficulty rule: decrease when completion or accuracy falls below the safe-practice threshold.")
    else:
        basis.append("Difficulty rule: keep the current level until accuracy is stable enough for a harder scenario.")

    reasons = _as_list(risk.get("reasons"))
    if reasons:
        basis.append(f"Risk rule: classified as {risk_level} risk because {str(reasons[0]).rstrip('.')}.")
    else:
        basis.append(f"Risk rule: classified as {risk_level} risk from completion, accuracy, and safety indicators.")

    recent_avg = metrics.get("recent_avg_accuracy_pct")
    trend = metrics.get("trend_accuracy_delta_pct")
    trend_parts = []
    if recent_avg is not None:
        trend_parts.append(f"recent average accuracy is {_format_percent(recent_avg)}")
    if isinstance(trend, (int, float)):
        direction = "up" if trend >= 0 else "down"
        trend_parts.append(f"latest attempt is {direction} by {abs(trend):.1f} percentage points")
    if trend_parts:
        basis.append(f"Trend rule: {', and '.join(trend_parts)}.")

    if profile["uses_pull_metrics"]:
        max_speed = _as_float(metrics.get("max_speed_cm_s"))
        if max_speed > 8:
            basis.append(f"Safety rule: peak pull speed is {_as_float(max_speed):.1f} cm/s, so abrupt motion needs attention.")
        elif max_speed > 0:
            basis.append(f"Safety rule: peak pull speed is {_as_float(max_speed):.1f} cm/s, with no speed warning triggered.")
    else:
        basis.append("Module rule: dressing-change attempts are counted as procedure practice and kept separate from scored removal accuracy.")

    return basis


def _memory_value(value: Any) -> str:
    text = str(value or "unknown").strip()
    if get_language() != "zh":
        return text
    mapping = {
        "new": "新建画像",
        "advanced": "进阶稳定",
        "intermediate": "中等水平",
        "foundation": "基础巩固",
        "high": "高",
        "moderate": "中等",
        "low": "低",
        "unknown": "未知",
        "stable": "稳定",
        "developing": "发展中",
        "needs repetition": "需要重复巩固",
    }
    return mapping.get(text.lower(), text)


def _join_memory_items(items: Iterable[Any], limit: int = 3) -> str:
    values = []
    for item in items or []:
        text = str(item or "").strip()
        if text:
            values.append(re.sub(r"\s+", " ", text))
        if len(values) >= limit:
            break
    return "; ".join(values)


def _render_memory_section(memory: Optional[Dict[str, Any]], audience: str = "student") -> str:
    compact = compact_memory_for_prompt(memory)
    count = int(_as_float(compact.get("sessions_remembered")))
    if count <= 0:
        return f"- {tr('report.memory_empty')}"

    profile = compact.get("learner_profile") if isinstance(compact.get("learner_profile"), dict) else {}
    lines = [
        tr("report.memory_sessions", count=count),
        tr("report.memory_level", level=_memory_value(profile.get("level", "new"))),
    ]
    focus = str(profile.get("primary_focus") or "").strip()
    if focus:
        lines.append(tr("report.memory_focus", focus=focus))

    strengths = _join_memory_items(compact.get("recurring_strengths", []))
    improvements = _join_memory_items(compact.get("recurring_improvements", []))
    next_steps = _join_memory_items(compact.get("preferred_next_steps", []))
    safety = _join_memory_items(compact.get("safety_watchpoints", []))
    teacher_focus = _join_memory_items(compact.get("teacher_focus_history", []))

    if strengths:
        lines.append(tr("report.memory_strengths", items=strengths))
    if improvements:
        lines.append(tr("report.memory_improvements", items=improvements))
    if audience == "teacher":
        if teacher_focus:
            lines.append(tr("report.memory_teacher_focus", items=teacher_focus))
        if safety:
            lines.append(tr("report.memory_safety", items=safety))
    elif next_steps:
        lines.append(tr("report.memory_next_steps", items=next_steps))

    return _bullets(lines)


def render_student_report(
    debrief: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
    risk: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    decision_basis: Optional[List[str]] = None,
    trace: Optional[List[Dict[str, Any]]] = None,
    memory: Optional[Dict[str, Any]] = None,
    backend: str = "sequential",
) -> str:
    metrics = metrics or {}
    risk = risk or {}
    plan = plan or {}
    profile = _training_profile(metrics.get("training_mode"))
    score = _localized_score_text(metrics, profile)
    if profile["uses_quiz"]:
        result_value = (
            f"{int(_as_float(metrics.get('quiz_correct_count')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}"
        )
    else:
        result_value = (
            f"{int(_as_float(metrics.get('assessment_correct_count')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}"
        )
    snapshot_rows = [
        (tr("report.training"), _display_training_label(profile)),
        (tr("report.accuracy"), _format_percent(metrics.get("accuracy_pct"))),
        (
            _localized_profile_label(profile, "count_label"),
            f"{int(_as_float(metrics.get('events_completed')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}",
        ),
        (_localized_profile_label(profile, "correct_label"), result_value),
        (tr("report.risk"), _localized_risk(risk.get("level", debrief.get("risk_level", "medium")))),
        (tr("report.difficulty_plan"), _localized_plan(plan.get("action", "keep"))),
    ]
    return (
        f"# {tr('report.student_title')}\n\n"
        f"**{tr('report.workflow')}:** {_localized_workflow_label(backend)}\n\n"
        f"## {tr('report.agent_workflow')}\n"
        f"{_trace_lines(trace or [], {'Memory Agent', 'Metrics Analyst', 'Risk Agent', 'Difficulty Planner', 'Student Debrief Agent', 'Report Writer'})}\n\n"
        f"## {tr('report.performance_snapshot')}\n"
        f"{_markdown_table(snapshot_rows)}\n\n"
        f"## {tr('report.memory_highlights')}\n"
        f"{_render_memory_section(memory, 'student')}\n\n"
        f"## {tr('report.decision_basis')}\n"
        f"{_localized_bullets(decision_basis or build_decision_basis(metrics, risk, plan))}\n\n"
        f"## {tr('report.summary')}\n"
        f"> {debrief.get('summary', tr('report.default_summary'))}\n\n"
        f"## {tr('report.score_risk')}\n"
        f"- **{tr('report.score')}:** {score}\n"
        f"- **{tr('report.risk_level')}:** {_localized_risk(debrief.get('risk_level', 'medium'))}\n\n"
        f"## {tr('report.strengths')}\n"
        f"{_localized_bullets(debrief.get('strengths', []))}\n\n"
        f"## {tr('report.areas_to_improve')}\n"
        f"{_localized_bullets(debrief.get('areas_to_improve', []))}\n\n"
        f"## {tr('report.next_steps')}\n"
        f"{_localized_bullets(debrief.get('next_steps', []))}"
    )


def render_teacher_report(
    advice: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
    risk: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    decision_basis: Optional[List[str]] = None,
    trace: Optional[List[Dict[str, Any]]] = None,
    memory: Optional[Dict[str, Any]] = None,
    backend: str = "sequential",
) -> str:
    metrics = metrics or {}
    risk = risk or {}
    plan = plan or {}
    profile = _training_profile(metrics.get("training_mode"))
    if profile["uses_quiz"]:
        result_value = (
            f"{int(_as_float(metrics.get('quiz_correct_count')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}"
        )
    else:
        result_value = (
            f"{int(_as_float(metrics.get('assessment_correct_count')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}"
        )
    snapshot_rows = [
        (tr("report.training"), _display_training_label(profile)),
        (tr("report.accuracy"), _format_percent(metrics.get("accuracy_pct"))),
        (
            _localized_profile_label(profile, "count_label"),
            f"{int(_as_float(metrics.get('events_completed')))}"
            f"/{int(_as_float(metrics.get('expected_events'), 4))}",
        ),
        (_localized_profile_label(profile, "correct_label"), result_value),
    ]
    return (
        f"# {tr('report.teacher_title')}\n\n"
        f"**{tr('report.workflow')}:** {_localized_workflow_label(backend)}\n\n"
        f"## {tr('report.agent_workflow')}\n"
        f"{_trace_lines(trace or [], {'Memory Agent', 'Metrics Analyst', 'Risk Agent', 'Difficulty Planner', 'Teacher Coaching Agent', 'Report Writer'})}\n\n"
        f"## {tr('report.student_snapshot')}\n"
        f"{_markdown_table(snapshot_rows)}\n\n"
        f"## {tr('report.memory_highlights')}\n"
        f"{_render_memory_section(memory, 'teacher')}\n\n"
        f"## {tr('report.decision_basis')}\n"
        f"{_localized_bullets(decision_basis or build_decision_basis(metrics, risk, plan))}\n\n"
        f"## {tr('report.recommendation')}\n"
        f"- **{tr('report.student_level')}:** {_localized_student_level(advice.get('student_level', 'developing'))}\n"
        f"- **{tr('report.difficulty_recommendation')}:** {_localized_plan(advice.get('difficulty_recommendation', 'keep'))}\n"
        f"- **{tr('report.rationale')}:** {advice.get('rationale', tr('report.default_rationale'))}\n\n"
        f"## {tr('report.teaching_focus')}\n"
        f"{_localized_bullets(advice.get('teaching_focus', []))}\n\n"
        f"## {tr('report.safety_notes')}\n"
        f"{_localized_bullets(advice.get('safety_notes', []))}"
    )


class TrainingAnalysisGraph:
    """Shared graph backend for student debriefs and teacher coaching."""

    def __init__(
        self,
        config: Optional[TrainingAgentConfig] = None,
        enable_llm: bool = True,
        memory_store: Optional[AgentMemoryStore] = None,
    ):
        self.config = config or TrainingAgentConfig.from_environment(enable_llm=enable_llm)
        self.memory_store = memory_store or AgentMemoryStore()
        self._compiled_graph = self._build_graph()

    @property
    def using_langgraph(self) -> bool:
        return self._compiled_graph is not None

    def analyze(
        self,
        username: str,
        session: Dict[str, Any],
        recent_records: Optional[List[Dict[str, Any]]] = None,
    ) -> TrainingAnalysisState:
        state: TrainingAnalysisState = {
            "username": username,
            "session": session or {},
            "recent_records": recent_records or [],
            "agent_trace": [],
            "errors": [],
            "graph_backend": "langgraph" if self.using_langgraph else "sequential",
        }

        if self._compiled_graph is not None:
            try:
                result = self._compiled_graph.invoke(state)
                return dict(result)
            except Exception as exc:
                state["errors"].append(f"LangGraph execution failed, using fallback runner: {exc}")

        return self._run_sequential(state)

    def _build_graph(self):
        if StateGraph is None:
            return None

        try:
            graph = StateGraph(TrainingAnalysisState)
            graph.add_node("memory_retriever", self._node_memory_retriever)
            graph.add_node("metrics_analyzer", self._node_metrics_analyzer)
            graph.add_node("risk_agent", self._node_risk_agent)
            graph.add_node("difficulty_planner", self._node_difficulty_planner)
            graph.add_node("student_debrief_agent", self._node_student_debrief_agent)
            graph.add_node("teacher_coaching_agent", self._node_teacher_coaching_agent)
            graph.add_node("memory_writer", self._node_memory_writer)
            graph.add_node("report_writer", self._node_report_writer)

            graph.set_entry_point("memory_retriever")
            graph.add_edge("memory_retriever", "metrics_analyzer")
            graph.add_edge("metrics_analyzer", "risk_agent")
            graph.add_edge("risk_agent", "difficulty_planner")
            graph.add_edge("difficulty_planner", "student_debrief_agent")
            graph.add_edge("student_debrief_agent", "teacher_coaching_agent")
            graph.add_edge("teacher_coaching_agent", "memory_writer")
            graph.add_edge("memory_writer", "report_writer")
            graph.add_edge("report_writer", END)
            return graph.compile()
        except Exception:
            return None

    def _run_sequential(self, state: TrainingAnalysisState) -> TrainingAnalysisState:
        for node in (
            self._node_memory_retriever,
            self._node_metrics_analyzer,
            self._node_risk_agent,
            self._node_difficulty_planner,
            self._node_student_debrief_agent,
            self._node_teacher_coaching_agent,
            self._node_memory_writer,
            self._node_report_writer,
        ):
            update = node(state)
            state.update(update)
        state["graph_backend"] = "sequential"
        return state

    def _node_memory_retriever(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        username = state.get("username") or "unknown"
        try:
            memory = self.memory_store.load(username)
            count = int(_as_float(memory.get("total_sessions_seen")))
            if get_language() == "zh":
                summary = f"读取到 {count} 次历史训练记忆" if count else "暂无历史训练记忆，建立新画像"
            else:
                summary = f"loaded {count} remembered training sessions" if count else "started a new learner memory"
            return {
                "agent_memory": memory,
                "agent_trace": self._add_trace(state, "Memory Agent", summary),
            }
        except Exception as exc:
            errors = list(state.get("errors", []))
            errors.append(f"Memory retrieval failed: {exc}")
            return {
                "agent_memory": {},
                "errors": errors,
                "agent_trace": self._add_trace(
                    state,
                    "Memory Agent",
                    "memory retrieval skipped after an error",
                ),
            }

    def _node_metrics_analyzer(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        metrics = build_training_metrics(state.get("session", {}), state.get("recent_records", []))
        profile = _training_profile(metrics.get("training_mode"))
        if get_language() == "zh":
            metric_summary = (
                f"计算出正确率 {_format_percent(metrics.get('accuracy_pct'))}，"
                f"{metrics.get('events_completed')}/{metrics.get('expected_events')} 个"
                f"{_localized_profile_label(profile, 'count_label')}"
            )
        else:
            metric_summary = (
                f"computed {_format_percent(metrics.get('accuracy_pct'))} accuracy, "
                f"{metrics.get('events_completed')}/{metrics.get('expected_events')} {profile['event_label']}"
            )
        return {
            "metrics": metrics,
            "agent_trace": self._add_trace(
                state,
                "Metrics Analyst",
                metric_summary,
            ),
        }

    def _node_risk_agent(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        metrics = state.get("metrics", {})
        risk = fallback_risk_assessment(metrics)
        return {
            "risk_assessment": risk,
            "agent_trace": self._add_trace(
                state,
                "Risk Agent",
                (
                    f"将本次训练评为{_localized_risk(risk.get('level', 'medium'))}风险"
                    if get_language() == "zh"
                    else f"classified this attempt as {risk.get('level', 'medium')} risk"
                ),
            ),
        }

    def _node_difficulty_planner(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        metrics = state.get("metrics", {})
        risk = state.get("risk_assessment", {})
        plan = fallback_difficulty_plan(metrics, risk)
        return {
            "difficulty_plan": plan,
            "agent_trace": self._add_trace(
                state,
                "Difficulty Planner",
                (
                    f"建议{_localized_plan(plan.get('action', 'keep'))}"
                    if get_language() == "zh"
                    else f"recommended to {plan.get('action', 'keep')} difficulty"
                ),
            ),
        }

    def _node_student_debrief_agent(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        metrics = state.get("metrics", {})
        risk = state.get("risk_assessment", {})
        plan = state.get("difficulty_plan", {})
        profile = _training_profile(metrics.get("training_mode"))
        fallback = fallback_student_debrief(metrics, risk, plan)

        llm_result = self._call_llm_json(
            system_prompt=(
                "You are a student-facing nursing training debrief agent. "
                f"{_llm_language_instruction()}"
                "Keep feedback encouraging and precise. "
                f"{_training_context_prompt(profile)} "
                "Use metrics.accuracy_pct as the authoritative score. "
                "When this training uses quiz data, quiz_correct_count / expected_events explains the score. "
                "When it does not use quiz data, assessment_correct_count / expected_events explains the score. "
                "Use agent_memory only for longitudinal learning patterns; do not invent history, "
                "and do not expose memory field names in the student-facing report. "
                "manual_reset_required is a hardware workflow note, not a student weakness. "
                "Return JSON with keys: summary, score, risk_level, strengths, "
                "areas_to_improve, next_steps. Lists must contain short strings."
            ),
            payload={
                "username": state.get("username"),
                "metrics": _metrics_for_llm(metrics),
                "agent_memory": compact_memory_for_prompt(state.get("agent_memory", {})),
                "training_context": profile,
                "risk_assessment": risk,
                "difficulty_plan": plan,
            },
        )
        debrief = self._sanitize_student_debrief(self._merge_agent_result(fallback, llm_result), metrics)
        return {
            "student_debrief": debrief,
            "agent_trace": self._add_trace(
                state,
                "Student Debrief Agent",
                "将指标转换为学生可读的训练反馈" if get_language() == "zh" else "converted metrics into student-facing feedback",
            ),
        }

    def _node_teacher_coaching_agent(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        metrics = state.get("metrics", {})
        risk = state.get("risk_assessment", {})
        plan = state.get("difficulty_plan", {})
        profile = _training_profile(metrics.get("training_mode"))
        fallback = fallback_teacher_advice(metrics, risk, plan)

        llm_result = self._call_llm_json(
            system_prompt=(
                "You are a teacher-facing clinical training supervisor. "
                f"{_llm_language_instruction()}"
                "Analyze the student's current level and recommend the next difficulty. "
                f"{_training_context_prompt(profile)} "
                "Use metrics.accuracy_pct as the authoritative score. "
                "When this training uses quiz data, quiz_correct_count / expected_events explains the score. "
                "When it does not use quiz data, assessment_correct_count / expected_events explains the score. "
                "Do not expose raw metric field names such as quiz_correct_count, expected_events, "
                "recent_avg_accuracy_pct, or trend_accuracy_delta_pct in the teacher-facing text. "
                "Use agent_memory only for longitudinal coaching patterns; do not invent history, "
                "and translate memory-derived insights into the requested language. "
                "Use teacher-friendly clinical language instead. "
                "Do not treat manual_reset_required as a student weakness; it is part of the current hardware workflow. "
                "Return JSON with keys: student_level, difficulty_recommendation, "
                "rationale, teaching_focus, safety_notes. Lists must contain short strings."
            ),
            payload={
                "username": state.get("username"),
                "metrics": _metrics_for_llm(metrics),
                "agent_memory": compact_memory_for_prompt(state.get("agent_memory", {})),
                "training_context": profile,
                "risk_assessment": risk,
                "difficulty_plan": plan,
            },
        )
        advice = self._sanitize_teacher_advice(self._merge_agent_result(fallback, llm_result), metrics, plan)
        return {
            "teacher_advice": advice,
            "agent_trace": self._add_trace(
                state,
                "Teacher Coaching Agent",
                "生成教师可用的教学指导" if get_language() == "zh" else "prepared teacher-facing coaching guidance",
            ),
        }

    def _node_memory_writer(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        username = state.get("username") or "unknown"
        metrics = state.get("metrics", {})
        risk = state.get("risk_assessment", {})
        plan = state.get("difficulty_plan", {})
        student = state.get("student_debrief", {})
        teacher = state.get("teacher_advice", {})

        try:
            memory = self.memory_store.update_from_analysis(
                username,
                metrics,
                risk=risk,
                plan=plan,
                student_debrief=student,
                teacher_advice=teacher,
            )
            count = int(_as_float(memory.get("total_sessions_seen")))
            if get_language() == "zh":
                summary = f"已更新长期学习画像，当前记住 {count} 次训练"
            else:
                summary = f"updated long-term learner memory with {count} remembered sessions"
            return {
                "updated_memory": memory,
                "agent_trace": self._add_trace(state, "Memory Agent", summary),
            }
        except Exception as exc:
            errors = list(state.get("errors", []))
            errors.append(f"Memory update failed: {exc}")
            return {
                "updated_memory": state.get("agent_memory", {}),
                "errors": errors,
                "agent_trace": self._add_trace(
                    state,
                    "Memory Agent",
                    "memory update skipped after an error",
                ),
            }

    def _node_report_writer(self, state: TrainingAnalysisState) -> Dict[str, Any]:
        student = state.get("student_debrief", {})
        teacher = state.get("teacher_advice", {})
        metrics = state.get("metrics", {})
        risk = state.get("risk_assessment", {})
        plan = state.get("difficulty_plan", {})
        memory = state.get("updated_memory") or state.get("agent_memory", {})
        decision_basis = build_decision_basis(metrics, risk, plan)
        trace = self._add_trace(
            state,
            "Report Writer",
            "整理学生端与教师端最终报告" if get_language() == "zh" else "assembled the final student and teacher reports",
        )
        return {
            "agent_trace": trace,
            "decision_basis": decision_basis,
            "final_student_report": render_student_report(
                student,
                metrics=metrics,
                risk=risk,
                plan=plan,
                decision_basis=decision_basis,
                trace=trace,
                memory=memory,
                backend=state.get("graph_backend", "sequential"),
            ),
            "final_teacher_report": render_teacher_report(
                teacher,
                metrics=metrics,
                risk=risk,
                plan=plan,
                decision_basis=decision_basis,
                trace=trace,
                memory=memory,
                backend=state.get("graph_backend", "sequential"),
            ),
        }

    def _add_trace(self, state: TrainingAnalysisState, agent: str, summary: str) -> List[Dict[str, Any]]:
        trace = list(state.get("agent_trace", []))
        trace.append({"agent": agent, "summary": summary})
        return trace

    def _merge_agent_result(self, fallback: Dict[str, Any], llm_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not llm_result:
            return fallback

        merged = dict(fallback)
        for key, value in llm_result.items():
            if value in (None, "", []):
                continue
            merged[key] = value
        return merged

    def _sanitize_student_debrief(self, debrief: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
        profile = _training_profile(metrics.get("training_mode"))
        cleaned = dict(debrief)
        cleaned["score"] = _localized_score_text(metrics, profile)
        cleaned["risk_level"] = cleaned.get("risk_level") or "medium"

        def keep_item(item: Any) -> bool:
            text = str(item).lower()
            blocked = ["manual reset", "hardware reset", "reset required"]
            if not profile["uses_quiz"]:
                blocked.extend(["quiz", "question", "answered", "checkpoint"])
            if not profile["uses_pull_metrics"]:
                blocked.extend(["pull", "starting position", "needle removal", "needle pull"])
            return not any(token in text for token in blocked)

        areas = [item for item in _as_list(cleaned.get("areas_to_improve")) if keep_item(item)]
        if not areas:
            trend = metrics.get("recent_avg_accuracy_pct")
            if trend is not None:
                areas.append(
                    f"Maintain consistency across sessions; recent average accuracy is {_format_percent(trend)}."
                )
            elif not profile["uses_pull_metrics"]:
                areas.append("Repeat the dressing placement while keeping the sterile field organized.")
            else:
                areas.append("Maintain the same smooth pull control in the next attempt.")
        cleaned["areas_to_improve"] = [_localize_report_item(item) for item in areas]

        strengths = [item for item in _as_list(cleaned.get("strengths")) if keep_item(item)]
        expected = int(_as_float(metrics.get("expected_events"), 4))
        if profile["uses_quiz"]:
            correct = int(_as_float(metrics.get("quiz_correct_count"), 0))
            if get_language() == "zh":
                result_line = f"检查点答题结果：{correct}/{expected} 正确。"
            else:
                result_line = f"Checkpoint quiz result: {correct}/{expected} correct."
        else:
            correct = int(_as_float(metrics.get("assessment_correct_count"), 0))
            if get_language() == "zh":
                result_line = f"换敷贴步骤结果：{correct}/{expected} 正确。"
            else:
                result_line = f"Dressing-change step result: {correct}/{expected} correct."
        result_token = f"{correct}/{expected}"
        if result_line not in strengths and not any(result_token in str(item) for item in strengths):
            strengths.append(result_line)
        cleaned["strengths"] = [_localize_report_item(item) for item in strengths]

        next_steps = [item for item in _as_list(cleaned.get("next_steps")) if keep_item(item)]
        for suggestion in profile["next_session_focus"]:
            if len(next_steps) >= 3:
                break
            if suggestion not in next_steps:
                next_steps.append(suggestion)
        cleaned["next_steps"] = [_localize_report_item(item) for item in next_steps]

        summary = str(cleaned.get("summary", "")).strip()
        summary_l = summary.lower()
        if (
            not summary
            or (not profile["uses_quiz"] and "quiz" in summary_l)
            or (not profile["uses_pull_metrics"] and any(token in summary_l for token in ("pull", "starting position", "needle removal")))
        ):
            cleaned["summary"] = _mode_summary(metrics)
        return cleaned

    def _sanitize_teacher_advice(self, advice: Dict[str, Any], metrics: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        profile = _training_profile(metrics.get("training_mode"))
        plan = plan or {}
        cleaned = dict(advice)

        def keep_item(item: Any) -> bool:
            text = str(item).lower()
            blocked = [
                "manual reset",
                "hardware reset",
                "reset required",
                "quiz_correct_count",
                "expected_events",
                "recent_avg_accuracy_pct",
                "trend_accuracy_delta_pct",
                "assessment_correct_count",
                "completion_rate_pct",
            ]
            if not profile["uses_quiz"]:
                blocked.extend(["quiz", "question", "answered", "checkpoint"])
            if not profile["uses_pull_metrics"]:
                blocked.extend(["pull", "starting position", "needle removal", "needle pull"])
            return not any(token in text for token in blocked)

        cleaned["difficulty_recommendation"] = self._normalize_difficulty_recommendation(
            cleaned.get("difficulty_recommendation"),
            plan.get("action", "keep"),
        )

        focus = [item for item in _as_list(cleaned.get("teaching_focus")) if keep_item(item)]
        for suggestion in profile["teacher_focus"]:
            if len(focus) >= 3:
                break
            if suggestion not in focus:
                focus.append(suggestion)
        cleaned["teaching_focus"] = [_localize_report_item(item) for item in focus]

        notes = [item for item in _as_list(cleaned.get("safety_notes")) if keep_item(item)]
        if not notes:
            notes = ["No obvious safety risk was detected from the saved metrics."]
        cleaned["safety_notes"] = [_localize_report_item(item) for item in notes]

        rationale = str(cleaned.get("rationale", "")).strip()
        if not rationale or not keep_item(rationale):
            cleaned["rationale"] = self._teacher_rationale_from_metrics(metrics, cleaned["difficulty_recommendation"])
        return cleaned

    def _normalize_difficulty_recommendation(self, value: Any, fallback: str = "keep") -> str:
        text = str(value or "").strip().lower()
        if any(token in text for token in ("increase", "advance", "next", "harder")):
            return "increase"
        if any(token in text for token in ("decrease", "lower", "foundation", "easier", "reduce")):
            return "decrease"
        if any(token in text for token in ("keep", "current", "maintain", "same", "repeat", "hold")):
            return "keep"
        fallback_text = str(fallback or "keep").strip().lower()
        return fallback_text if fallback_text in {"increase", "decrease", "keep"} else "keep"

    def _teacher_rationale_from_metrics(self, metrics: Dict[str, Any], recommendation: str) -> str:
        profile = _training_profile(metrics.get("training_mode"))
        accuracy = _as_float(metrics.get("accuracy_pct"))
        completion = _as_float(metrics.get("completion_rate_pct"))
        expected = int(_as_float(metrics.get("expected_events"), 4))
        recent_avg = metrics.get("recent_avg_accuracy_pct")
        trend = metrics.get("trend_accuracy_delta_pct")

        if profile["uses_quiz"]:
            correct = int(_as_float(metrics.get("quiz_correct_count"), 0))
            if get_language() == "zh":
                performance = (
                    f"最近一次训练完成率为 {_format_percent(completion)}，"
                    f"检查点答题正确 {correct}/{expected}（正确率 {_format_percent(accuracy)}）。"
                )
            else:
                performance = (
                    f"The latest attempt completed {_format_percent(completion)} of checkpoints, "
                    f"with {correct}/{expected} quiz responses correct ({_format_percent(accuracy)} accuracy)."
                )
        else:
            correct = int(_as_float(metrics.get("assessment_correct_count"), 0))
            if get_language() == "zh":
                performance = (
                    f"最近一次训练完成率为 {_format_percent(completion)}，"
                    f"流程步骤正确 {correct}/{expected}（正确率 {_format_percent(accuracy)}）。"
                )
            else:
                performance = (
                    f"The latest attempt completed {_format_percent(completion)} of procedural steps, "
                    f"with {correct}/{expected} steps correct ({_format_percent(accuracy)} accuracy)."
                )

        trend_parts = []
        if recent_avg is not None:
            trend_parts.append(
                f"近期平均正确率为 {_format_percent(recent_avg)}"
                if get_language() == "zh"
                else f"recent average is {_format_percent(recent_avg)}"
            )
        if isinstance(trend, (int, float)):
            if get_language() == "zh":
                direction = "上升" if trend >= 0 else "下降"
                trend_parts.append(f"本次相比近期{direction} {abs(trend):.1f} 个百分点")
            else:
                direction = "up" if trend >= 0 else "down"
                trend_parts.append(f"current attempt is {direction} by {abs(trend):.1f} percentage points")
        if get_language() == "zh":
            trend_text = f" 与近期训练相比，{'，且'.join(trend_parts)}。" if trend_parts else ""
        else:
            trend_text = f" Compared with recent attempts, {', and '.join(trend_parts)}." if trend_parts else ""

        if recommendation == "increase":
            decision = "可以提高难度，同时继续观察稳定性。" if get_language() == "zh" else "Advancing difficulty is reasonable while continuing to monitor consistency."
        elif recommendation == "decrease":
            decision = "建议降低难度，先巩固基础再增加复杂度。" if get_language() == "zh" else "Reduce difficulty and rebuild the foundation before adding complexity."
        else:
            decision = "建议保持当前难度，直到正确率更稳定。" if get_language() == "zh" else "Keep the current difficulty until accuracy is more stable."

        return f"{performance}{trend_text} {decision}"

    def _call_llm_json(self, system_prompt: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.config.enable_llm:
            return None

        if not self.config.api_key or self.config.api_key == "your-api-key-here":
            return None

        try:
            from openai import OpenAI
        except Exception:
            return None

        try:
            try:
                client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url or None, timeout=20)
            except TypeError:
                client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url or None)

            completion = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Analyze this training payload and return JSON only:\n"
                            + json.dumps(payload, ensure_ascii=False, indent=2)
                        ),
                    },
                ],
                temperature=self.config.temperature,
            )
            content = completion.choices[0].message.content
            return _parse_json_object(content)
        except Exception:
            return None
