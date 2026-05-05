from __future__ import annotations

from typing import Dict, List

from .models import CandidateCase


SECTION_KEYS = [
    "scope",
    "symptoms",
    "effective steps",
    "failed or risky steps",
    "resolution",
    "metadata",
]


def render_case_markdown(case: CandidateCase) -> str:
    effective_steps = "\n".join(f"- {item}" for item in case.actions) or "- N/A"
    hypotheses = "\n".join(f"- {item}" for item in case.hypotheses) or "- N/A"
    return (
        f"# Case: {case.case_id}\n\n"
        "## Scope\n"
        f"- tenant_id: {case.tenant_id or 'N/A'}\n"
        f"- team_id: {case.team_id or 'N/A'}\n"
        f"- app_code: {case.app_code}\n"
        f"- environment: {case.environment}\n\n"
        "## Symptoms\n"
        f"{case.symptom_summary or 'N/A'}\n\n"
        "## Effective Steps\n"
        f"{effective_steps}\n\n"
        "## Failed or Risky Steps\n"
        f"{hypotheses}\n\n"
        "## Resolution\n"
        f"{case.resolution or 'N/A'}\n\n"
        "## Metadata\n"
        f"- confidence: {case.confidence:.3f}\n"
        f"- lifecycle: {case.lifecycle.value}\n"
        f"- source_conv_id: {case.source_conv_id or 'N/A'}\n"
    )


def parse_markdown_sections(markdown_text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    current = None
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer, current
        if current:
            parsed[current] = "\n".join(buffer).strip()
        buffer = []

    for line in markdown_text.splitlines():
        lower = line.strip().lower()
        if lower.startswith("## "):
            flush()
            current = lower[3:].strip()
            continue
        buffer.append(line)
    flush()
    return parsed

