from __future__ import annotations

import json
from typing import Dict, List

from .case_context import case_context_from_metadata
from .models import CandidateCase


def _format_case_context(case: CandidateCase) -> str:
    ctx = case_context_from_metadata(case.metadata)
    if not ctx:
        return "_No `metadata.case_context` yet — add routing or provenance hints here._\n"
    lines: List[str] = []
    priority = [
        "application_name",
        "app_code",
        "environment",
        "region",
        "data_sources",
        "telemetry_channels",
        "related_services",
        "tags",
        "operator_notes",
    ]
    seen = set()
    for key in priority:
        if key in ctx:
            seen.add(key)
            val = ctx[key]
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            lines.append(f"- **{key}**: {val}")
    for key in sorted(k for k in ctx if k not in seen):
        val = ctx[key]
        if isinstance(val, (list, dict)):
            val = json.dumps(val, ensure_ascii=False)
        lines.append(f"- **{key}**: {val}")
    return "\n".join(lines) + "\n"


def render_case_markdown(case: CandidateCase) -> str:
    ctx_block = _format_case_context(case)
    return (
        f"# Case: `{case.case_id}`\n\n"
        "## Case context (metadata.case_context)\n"
        f"{ctx_block}\n"
        "## Symptoms\n"
        f"{case.symptom_summary or 'N/A'}\n\n"
        "## Diagnosis\n"
        f"{case.diagnosis or 'N/A'}\n\n"
        "## Root cause\n"
        f"{case.root_cause or 'N/A'}\n\n"
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
