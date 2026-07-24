"""
Prompt registry — extracts prompt definitions from KI backend source files.
Used by /api/system/prompts to display live prompt templates in System Settings.

Now function-scoped: when a source file serves multiple tasks, prompts are
associated with their enclosing function so each task only sees its own.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Literal, NamedTuple

BACKEND_DIR = Path(__file__).resolve().parent

# Module → task → (filename, function hints)
MODULE_MAP: dict[str, dict[str, tuple[str, list[str]]]] = {
    "ingest_pipeline": {
        "summarize": (
            "summarizer.py",
            ["summarize_event", "generate_title", "generate_overview"],
        ),
        "classify": ("classifier.py", ["classify_event"]),
        "tag": ("tagger.py", ["extract_tags"]),
        "translate": ("translator.py", ["translate_to_en"]),
    },
    "series": {
        "discover": ("series_discovery_service.py", ["discover_series"]),
        "intro": ("series_generation_service.py", ["generate_series_intro"]),
        "summary": ("series_generation_service.py", ["generate_series_summary"]),
        "paper": ("series_generation_service.py", ["generate_series_paper"]),
        "auto_suggest": (
            "series_auto_suggest_service.py",
            ["auto_suggest_series"],
        ),
    },
    "brainstorm": {
        "answer": ("brainstorm_answer_service.py", ["get_answer_for_question"]),
        "summary": (
            "brainstorm_conversation_service.py",
            ["generate_conversation_summary", "start_conversation"],
        ),
        "contemplate": (
            "brainstorm_contemplation_service.py",
            ["_contemplate_question_to_events", "_contemplate_event_to_questions"],
        ),
        "concept_extract": ("routes/brainstorm_routes.py", ["precipitate_concept"]),
    },
    "briefing": {
        "briefing_quick": ("briefing.py", ["generate_briefing"]),
        "briefing_daily": ("briefing.py", ["generate_briefing"]),
    },
    "tasks": {
        "judge": ("routes/task_routes.py", ["_run_task_ai_judge"]),
    },
    "concept": {
        "auto_complete": ("classifier.py", ["classify_content"]),
    },
}


class PromptSource(NamedTuple):
    filename: str
    function: str
    extraction: Literal["scoped", "legacy_built"] = "scoped"


PROMPT_SOURCES: dict[str, dict[str, dict[str, PromptSource]]] = {
    "brainstorm": {
        "answer": {
            "prompt": PromptSource(
                "brainstorm_answer_service.py", "get_answer_for_question"
            ),
        },
        "summary": {
            "prompt": PromptSource(
                "brainstorm_answer_service.py",
                "get_answer_for_question",
                "legacy_built",
            ),
            "system_prompt": PromptSource(
                "brainstorm_conversation_service.py", "start_conversation"
            ),
        },
        "contemplate": {
            "prompt": PromptSource(
                "brainstorm_contemplation_service.py",
                "_contemplate_event_to_questions",
            ),
        },
        "concept_extract": {
            "prompt": PromptSource(
                "brainstorm_answer_service.py",
                "get_answer_for_question",
                "legacy_built",
            ),
        },
    },
}


def _extract_prompts_by_function(filepath: Path) -> dict[str, dict[str, str]]:
    """Extract prompt assignments grouped by enclosing function name.
    Returns {function_name: {varname: prompt_text}}.
    Module-level prompts go under key '__module__'.
    """
    if not filepath.exists():
        return {}
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return {}

    result: dict[str, dict[str, str]] = {"__module__": {}}
    tree = ast.parse(source)

    class ScopedVisitor(ast.NodeVisitor):
        def __init__(self):
            self._scope_stack: list[str] = []

        @property
        def _scope(self) -> str:
            return self._scope_stack[-1] if self._scope_stack else "__module__"

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._scope_stack.append(node.name)
            self.generic_visit(node)
            self._scope_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._scope_stack.append(node.name)
            self.generic_visit(node)
            self._scope_stack.pop()

        def visit_Assign(self, node: ast.Assign):
            scope = self._scope
            if scope not in result:
                result[scope] = {}
            for target in node.targets:
                if isinstance(target, ast.Name) and "prompt" in target.id.lower():
                    val = _safe_eval_ast(node.value, source)
                    if val:
                        result[scope][target.id] = val
            self.generic_visit(node)

    ScopedVisitor().visit(tree)

    # Also catch module-level multi-line prompts via regex
    _extract_built_prompts_regex(source, result.setdefault("__module__", {}))

    return result


def _safe_eval_ast(node: ast.AST, source: str) -> str | None:
    """Try to extract the string value of an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ast.get_source_segment(source, node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _safe_eval_ast(node.left, source)
        right = _safe_eval_ast(node.right, source)
        if left and right:
            return left + right
    if isinstance(node, ast.Call):
        return ast.get_source_segment(source, node)
    return None


def _extract_built_prompts_regex(source: str, prompts: dict[str, str]):
    """Catch multi-line prompt building patterns at module level."""
    pattern = re.compile(
        r'(prompt\w*)\s*=\s*\(\s*\n((?:\s*(?:f?["\']|["\']).*?\n)+)\s*\)',
        re.MULTILINE,
    )
    for match in pattern.finditer(source):
        varname = match.group(1)
        if varname in prompts:
            continue
        body = match.group(2)
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        if lines:
            prompts[varname] = "\n".join(lines)


def _extract_function_source(filepath: Path, function: str) -> str | None:
    if not filepath.exists():
        return None
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return None
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == function
        ):
            return ast.get_source_segment(source, node)
    return None


def _extract_mapped_prompts(
    sources: dict[str, PromptSource],
) -> dict[str, str]:
    prompts: dict[str, str] = {}
    for variable, source in sources.items():
        filepath = BACKEND_DIR / source.filename
        if source.extraction == "legacy_built":
            function_source = _extract_function_source(filepath, source.function)
            scoped_prompts: dict[str, str] = {}
            if function_source is not None:
                _extract_built_prompts_regex(function_source, scoped_prompts)
        else:
            scoped_prompts = _extract_prompts_by_function(filepath).get(
                source.function, {}
            )
        if variable in scoped_prompts:
            prompts[variable] = scoped_prompts[variable]
    return prompts


def _resolve_actual_function_name(filepath: Path, hint: str) -> str | None:
    """Given a hint like '_paper_analysis', find the actual function name in the file.
    Returns the actual name or None."""
    if not filepath.exists():
        return None
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return None
    # Exact match
    if re.search(rf"\bdef\s+{re.escape(hint)}\b", source):
        return hint
    # Try case-insensitive
    for m in re.finditer(r"\bdef\s+(\w+)", source):
        name = m.group(1)
        if name.lower() == hint.lower():
            return name
    return None


def get_all_prompts() -> dict[str, dict[str, dict[str, str]]]:
    """Return all prompts organized by module → task → {varname: content}."""
    result: dict[str, dict[str, dict[str, str]]] = {}

    for module, tasks in MODULE_MAP.items():
        result[module] = {}
        for task, (filename, hints) in tasks.items():
            mapped_sources = PROMPT_SOURCES.get(module, {}).get(task)
            if mapped_sources is not None:
                result[module][task] = _extract_mapped_prompts(mapped_sources)
                continue

            filepath = BACKEND_DIR / filename
            func_prompts = _extract_prompts_by_function(filepath)

            task_prompts: dict[str, str] = {}
            # Always include module-level prompts (constants, templates)
            task_prompts.update(func_prompts.get("__module__", {}))

            # If this file serves multiple tasks, scope prompts by function hints
            matched_any = False
            for hint in hints:
                actual = _resolve_actual_function_name(filepath, hint)
                if actual and actual in func_prompts:
                    task_prompts.update(func_prompts[actual])
                    matched_any = True

            # Fallback: if no function-scoped prompts matched, take all prompts
            if not matched_any:
                for scope, prompts in func_prompts.items():
                    if scope != "__module__":
                        task_prompts.update(prompts)

            result[module][task] = task_prompts
    return result
