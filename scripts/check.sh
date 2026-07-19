#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  else
    echo "FAIL: Python 3.12 is required; set PYTHON_BIN=/path/to/python3.12" >&2
    exit 1
  fi
fi

run_retired_feature_scan() {
  local mode="${1:-scan}"
  PYTHONPATH=src "$PYTHON_BIN" - "$ROOT" "$mode" <<'PY'
from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(sys.argv[1])
MODE = sys.argv[2]
SOURCE_SUFFIXES = {".js", ".jsx", ".mjs", ".py", ".ts", ".tsx"}
SKIPPED_PARTS = {".git", ".venv", "dist", "node_modules", "tmp"}
RETIRED_TABLES = "event_entities|entity_relations|entities|digests|topics"
RETIRED_TABLE_SET = {"event_entities", "entity_relations", "entities", "digests", "topics"}
RETIRED_IDENTIFIER_PATTERN = re.compile(rf"\b(?:{RETIRED_TABLES})\b")
FRONTEND_PREFIXES = ("app/frontend/src/", "app/frontend/scripts/")
STRING_LITERAL = re.compile(r"(?P<quote>['\"`])(?P<value>[^'\"`\n]*)(?P=quote)")
OLD_ROUTE_SEGMENT = re.compile(r"(?:^|/)[^/?#]*-old(?:$|[/?#])", re.IGNORECASE)
ROUTE_CONTEXT = re.compile(r"(?:\b(?:path|route|href|url)\s*[:=]\s*|\bpath\s*=\s*)$", re.IGNORECASE)
RETIRED_DEMO_IMPORTS = {
    "BrandDepthDemo",
    "BrandLockupDemo",
    "CircularGalleryDemo",
    "DockPopupVisualDemo",
    "DualNavigationDemo",
}

SQL_IDENTIFIER_QUOTE = r"(?:[\"'`]\s*{name}\s*[\"'`]|\[\s*{name}\s*\]|{name})"
SQL_SCHEMA = SQL_IDENTIFIER_QUOTE.format(name=r"(?:main|temp)")
SQL_TABLE = SQL_IDENTIFIER_QUOTE.format(name=rf"(?:{RETIRED_TABLES})")

RULES = (
    (
        "retired entity or digest API/module",
        re.compile(
            r"/api/entities(?:/[A-Za-z0-9._~-]+)*/?(?=$|[?#'\"`\s])|"
            r"/api/digest(?:/[A-Za-z0-9._~-]+)*/?(?=$|[?#'\"`\s])|"
            r"\b(?:entity_routes|digest_routes)\b|"
            r"(?:from|import)\s+(?:zhiji_backend\.)?(?:entity|entities|digest|digest_ai)\b"
        ),
    ),
    ("retired knowledge graph", re.compile(r"\bknowledge_graph\b")),
    (
        "retired table creation",
        re.compile(
            rf"\bCREATE\s+(?:(?:TEMP|TEMPORARY)\s+)?TABLE\s+"
            rf"(?:IF\s+NOT\s+EXISTS\s+)?(?:{SQL_SCHEMA}\s*\.\s*)?{SQL_TABLE}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    ),
)


def is_test_or_spec(path: Path) -> bool:
    relative = path.as_posix()
    return (
        relative.startswith("tests/")
        or relative.startswith("docs/superpowers/plans/")
        or relative.startswith("docs/superpowers/specs/")
        or ".test." in path.name
        or ".spec." in path.name
    )


def source_paths(root: Path):
    for base in (root / "app/frontend/src", root / "app/frontend/scripts", root / "src/zhiji_backend"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if any(part in SKIPPED_PARTS for part in relative.parts):
                continue
            if is_test_or_spec(relative):
                continue
            yield relative, path


def retired_frontend_route_matches(relative: Path, source: str):
    if not relative.as_posix().startswith(FRONTEND_PREFIXES):
        return
    for match in STRING_LITERAL.finditer(source):
        value = match.group("value")
        basename = value.rsplit("/", 1)[-1].split(".", 1)[0]
        context = source[max(0, match.start() - 100):match.start()]
        is_path_literal = value.startswith(("/", "#/")) or bool(ROUTE_CONTEXT.search(context))
        retired = (
            "ingest-previous" in value
            or "/demo/" in value
            or (is_path_literal and OLD_ROUTE_SEGMENT.search(value))
            or (basename in RETIRED_DEMO_IMPORTS and not value.endswith(".css"))
        )
        if retired:
            yield match


def allowed_match(
    relative: Path,
    label: str,
    match: re.Match[str],
    line: int,
    column: int,
    allowed_ranges: dict[tuple[str, str], list[tuple[int, int, int, int]]],
) -> bool:
    path = relative.as_posix()
    if label == "retired entity or digest API/module" and path == "src/zhiji_backend/main.py":
        return match.group(0) in {"/api/digest/latest", "/api/digest/generate"}
    return any(position_in_span(line, column, span) for span in allowed_ranges.get((path, label), []))


def parse_python(path: Path, label: str) -> tuple[ast.Module | None, list[str]]:
    try:
        return ast.parse(path.read_text(encoding="utf-8")), []
    except SyntaxError as exc:
        return None, [f"{path}: cannot validate {label}: {exc.msg}"]


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def node_range(node: ast.AST) -> tuple[int, int, int, int]:
    return (
        node.lineno,
        node.col_offset,
        getattr(node, "end_lineno", node.lineno),
        getattr(node, "end_col_offset", node.col_offset + 1),
    )


def position_in_span(line: int, column: int, span: tuple[int, int, int, int]) -> bool:
    start_line, start_column, end_line, end_column = span
    if line < start_line or line > end_line:
        return False
    if line == start_line and column < start_column:
        return False
    if line == end_line and column >= end_column:
        return False
    return True


def assignment_map(nodes: list[ast.stmt]) -> dict[str, ast.AST]:
    assignments = {}
    for node in nodes:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            assignments[node.target.id] = node.value
    return assignments


def resolve_reference(
    node: ast.AST,
    function_assignments: dict[str, ast.AST],
    module_assignments: dict[str, ast.AST],
    seen: set[str] | None = None,
) -> ast.AST:
    if not isinstance(node, ast.Name):
        return node
    seen = set() if seen is None else set(seen)
    if node.id in seen:
        return node
    seen.add(node.id)
    target = function_assignments.get(node.id, module_assignments.get(node.id))
    if target is None:
        return node
    return resolve_reference(target, function_assignments, module_assignments, seen)


def resolve_string(
    node: ast.AST,
    function_assignments: dict[str, ast.AST],
    module_assignments: dict[str, ast.AST],
) -> tuple[str | None, list[ast.Constant]]:
    resolved = resolve_reference(node, function_assignments, module_assignments)
    if isinstance(resolved, ast.Constant) and isinstance(resolved.value, str):
        return resolved.value, [resolved]
    if isinstance(resolved, ast.BinOp) and isinstance(resolved.op, ast.Add):
        left, left_nodes = resolve_string(resolved.left, function_assignments, module_assignments)
        right, right_nodes = resolve_string(resolved.right, function_assignments, module_assignments)
        if left is not None and right is not None:
            return left + right, left_nodes + right_nodes
    return None, []


def resolve_string_set(
    node: ast.AST,
    function_assignments: dict[str, ast.AST],
    module_assignments: dict[str, ast.AST],
) -> tuple[set[str] | None, list[ast.Constant]]:
    resolved = resolve_reference(node, function_assignments, module_assignments)
    if isinstance(resolved, (ast.Tuple, ast.List, ast.Set)):
        values = set()
        constants = []
        for item in resolved.elts:
            value, value_nodes = resolve_string(item, function_assignments, module_assignments)
            if value is None:
                return None, []
            values.add(value)
            constants.extend(value_nodes)
        return values, constants
    if isinstance(resolved, ast.BinOp) and isinstance(resolved.op, ast.Add):
        left, left_nodes = resolve_string_set(resolved.left, function_assignments, module_assignments)
        right, right_nodes = resolve_string_set(resolved.right, function_assignments, module_assignments)
        if left is not None and right is not None:
            return left | right, left_nodes + right_nodes
    return None, []


def drop_template_shape(
    node: ast.AST,
    loop_variable: str,
    function_assignments: dict[str, ast.AST],
    module_assignments: dict[str, ast.AST],
) -> str | None:
    resolved = resolve_reference(node, function_assignments, module_assignments)
    template_shape = None
    if isinstance(resolved, ast.JoinedStr):
        pieces = []
        formatted_count = 0
        for value in resolved.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                pieces.append(value.value)
                continue
            if (
                isinstance(value, ast.FormattedValue)
                and isinstance(value.value, ast.Name)
                and value.value.id == loop_variable
                and value.conversion == -1
                and value.format_spec is None
            ):
                formatted_count += 1
                pieces.append("{table}")
                continue
            return None
        if formatted_count == 1:
            template_shape = "".join(pieces)
    elif isinstance(resolved, ast.Call) and isinstance(resolved.func, ast.Attribute) and resolved.func.attr == "format":
        template, _constants = resolve_string(resolved.func.value, function_assignments, module_assignments)
        placeholders = re.findall(r"\{(?:0)?\}", template or "")
        if (
            template
            and len(placeholders) == 1
            and len(resolved.args) == 1
            and not resolved.keywords
            and isinstance(resolved.args[0], ast.Name)
            and resolved.args[0].id == loop_variable
        ):
            template_shape = re.sub(r"\{(?:0)?\}", "{table}", template, count=1)
    if template_shape is None:
        return None
    return re.sub(r"\s+", " ", template_shape.strip().rstrip(";"))


def is_exact_drop_template(template_shape: str) -> bool:
    identifier = r"(?:\{table\}|[\"'`]\{table\}[\"'`]|\[\{table\}\])"
    return bool(re.fullmatch(rf"DROP TABLE IF EXISTS (?:MAIN\s*\.\s*)?{identifier}", template_shape, re.IGNORECASE))


def is_exact_usage_cleanup(sql: str) -> bool:
    compact = re.sub(r"\s+", "", sql.strip().rstrip(";")).lower().replace('"', "'")
    expected = {
        "deletefromai_usagewheremodule='knowledge_graph'or(modulein('digest_briefing','briefing')andtask='digest')",
        "deletefromai_usagewheremodule='knowledge_graph'or(modulein('briefing','digest_briefing')andtask='digest')",
    }
    return compact in expected


def is_retired_api_path(value: str, base: str) -> bool:
    return value == base or value.startswith(f"{base}/")


def decorator_route(node: ast.AST) -> tuple[str, str, bool] | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "app":
        return None
    if node.func.attr not in {"get", "post"} or not node.args:
        return None
    path = node.args[0]
    if not isinstance(path, ast.Constant) or not isinstance(path.value, str):
        return None
    hidden = any(
        keyword.arg == "include_in_schema"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in node.keywords
    )
    return node.func.attr, path.value, hidden


def returns_json_404(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    returns = [node for node in function.body if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Call):
        return False
    call = returns[0].value
    if call_name(call.func) != "JSONResponse":
        return False
    return any(
        keyword.arg == "status_code"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value == 404
        for keyword in call.keywords
    )


def validate_digest_tombstone(root: Path) -> list[str]:
    main_path = root / "src/zhiji_backend/main.py"
    if not main_path.exists():
        return []
    source = main_path.read_text(encoding="utf-8")
    tree, violations = parse_python(main_path, "digest tombstone")
    if violations:
        return violations
    assert tree is not None
    paths = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and is_retired_api_path(node.value, "/api/digest")
    ]
    if sorted(paths) != ["/api/digest/generate", "/api/digest/latest"]:
        return ["src/zhiji_backend/main.py: only the two retired digest tombstone paths are allowed"]
    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "retired_digest_endpoint"
    ]
    if len(functions) != 1:
        return ["src/zhiji_backend/main.py: retired digest paths must use one hidden 404 tombstone"]
    routes = [decorator_route(node) for node in functions[0].decorator_list]
    expected_routes = {
        ("get", "/api/digest/latest", True),
        ("post", "/api/digest/generate", True),
    }
    if set(filter(None, routes)) != expected_routes or not returns_json_404(functions[0]):
        return ["src/zhiji_backend/main.py: retired digest paths must remain hidden and return 404"]
    return []


def validate_named_compatibility(
    root: Path,
) -> tuple[list[str], dict[tuple[str, str], list[tuple[int, int, int, int]]]]:
    violations = []
    allowed_ranges: dict[tuple[str, str], list[tuple[int, int, int, int]]] = {}
    config_path = root / "src/zhiji_backend/config_manager.py"
    if config_path.exists():
        tree, errors = parse_python(config_path, "knowledge_graph config cleanup")
        violations.extend(errors)
        if tree is not None:
            functions = [
                node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_normalize_persisted_config"
            ]
            valid_constants = []
            if len(functions) == 1:
                for statement in functions[0].body:
                    if isinstance(statement, (ast.Return, ast.Raise)):
                        break
                    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                        continue
                    call = statement.value
                    if (
                        isinstance(call.func, ast.Attribute)
                        and call.func.attr == "pop"
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "normalized"
                        and len(call.args) == 2
                        and not call.keywords
                        and isinstance(call.args[0], ast.Constant)
                        and call.args[0].value == "knowledge_graph"
                        and isinstance(call.args[1], ast.Constant)
                        and call.args[1].value is None
                    ):
                        valid_constants.append(call.args[0])
            if len(valid_constants) != 1:
                violations.append(
                    "src/zhiji_backend/config_manager.py: knowledge_graph config cleanup requires exactly one "
                    "reachable normalized.pop('knowledge_graph', None) in _normalize_persisted_config"
                )
            else:
                key = ("src/zhiji_backend/config_manager.py", "retired knowledge graph")
                allowed_ranges[key] = [node_range(node) for node in valid_constants]

    migration_path = root / "src/zhiji_backend/migrations.py"
    if migration_path.exists():
        tree, errors = parse_python(migration_path, "retired feature migration")
        violations.extend(errors)
        if tree is not None:
            module_assignments = assignment_map(tree.body)
            migration = next(
                (
                    node for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any(
                        isinstance(decorator, ast.Call)
                        and call_name(decorator.func) == "register"
                        and decorator.args
                        and isinstance(decorator.args[0], ast.Constant)
                        and decorator.args[0].value == "20260719_remove_retired_features"
                        for decorator in node.decorator_list
                    )
                ),
                None,
            )
            function_assignments = assignment_map(migration.body) if migration is not None else {}
            table_loop = None
            table_names = None
            table_constants = []
            if migration is not None:
                for candidate in (node for node in ast.walk(migration) if isinstance(node, ast.For)):
                    if not isinstance(candidate.target, ast.Name):
                        continue
                    candidate_names, candidate_constants = resolve_string_set(
                        candidate.iter,
                        function_assignments,
                        module_assignments,
                    )
                    if candidate_names == RETIRED_TABLE_SET:
                        table_loop = candidate
                        table_names = candidate_names
                        table_constants = candidate_constants
                        break
            drop_templates = []
            if table_loop is not None:
                for call in (
                    node for node in ast.walk(table_loop)
                    if isinstance(node, ast.Call) and call_name(node.func) == "execute" and node.args
                ):
                    shape = drop_template_shape(
                        call.args[0],
                        table_loop.target.id,
                        function_assignments,
                        module_assignments,
                    )
                    if shape and shape.upper().startswith("DROP TABLE"):
                        drop_templates.append(shape)
            drops_loop_table = len(drop_templates) == 1 and is_exact_drop_template(drop_templates[0])
            if table_names != RETIRED_TABLE_SET or not drops_loop_table:
                violations.append("src/zhiji_backend/migrations.py: named migration must drop the exact retired tables")
            usage_deletes = []
            graph_nodes = []
            if migration is not None:
                for call in (
                    node for node in ast.walk(migration)
                    if isinstance(node, ast.Call) and call_name(node.func) == "execute" and node.args
                ):
                    sql, sql_nodes = resolve_string(call.args[0], function_assignments, module_assignments)
                    if sql and re.match(r"\s*DELETE\s+FROM\s+ai_usage\b", sql, re.IGNORECASE):
                        usage_deletes.append(sql)
                        if is_exact_usage_cleanup(sql):
                            graph_nodes.extend(node for node in sql_nodes if "knowledge_graph" in node.value)
            graph_cleanup = len(usage_deletes) == 1 and is_exact_usage_cleanup(usage_deletes[0])
            if not graph_cleanup:
                violations.append("src/zhiji_backend/migrations.py: knowledge_graph is allowed only in ai_usage cleanup")
            if graph_cleanup:
                key = ("src/zhiji_backend/migrations.py", "retired knowledge graph")
                allowed_ranges[key] = [node_range(node) for node in graph_nodes]
            if table_names == RETIRED_TABLE_SET and drops_loop_table:
                key = ("src/zhiji_backend/migrations.py", "retired persistence identifier")
                allowed_ranges[key] = [node_range(node) for node in table_constants]
    return violations, allowed_ranges


def scan(root: Path) -> list[str]:
    compatibility_violations, allowed_ranges = validate_named_compatibility(root)
    violations = validate_digest_tombstone(root) + compatibility_violations
    retired_files = {
        "app/frontend/src/pages/BrandDepthDemo.tsx",
        "app/frontend/src/pages/BrandLockupDemo.tsx",
        "app/frontend/src/pages/CircularGalleryDemo.tsx",
        "app/frontend/src/pages/DockPopupVisualDemo.tsx",
        "app/frontend/src/pages/DualNavigationDemo.tsx",
        "src/zhiji_backend/entity.py",
        "src/zhiji_backend/entities.py",
        "src/zhiji_backend/digest.py",
        "src/zhiji_backend/digest_ai.py",
        "src/zhiji_backend/routes/entity_routes.py",
        "src/zhiji_backend/routes/digest_routes.py",
    }
    for relative, path in source_paths(root):
        relative_name = relative.as_posix()
        if relative_name in retired_files:
            violations.append(f"{relative_name}: retired business module must not exist")
        source = path.read_text(encoding="utf-8")
        for match in retired_frontend_route_matches(relative, source):
            line = source.count("\n", 0, match.start()) + 1
            violations.append(f"{relative_name}:{line}: retired frontend route or demo import: {match.group(0)!r}")
        for label, pattern in RULES:
            for match in pattern.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                line_start = source.rfind("\n", 0, match.start()) + 1
                column = match.start() - line_start
                if allowed_match(relative, label, match, line, column, allowed_ranges):
                    continue
                violations.append(f"{relative_name}:{line}: {label}: {match.group(0)!r}")
        if relative_name == "src/zhiji_backend/migrations.py":
            label = "retired persistence identifier"
            for match in RETIRED_IDENTIFIER_PATTERN.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                line_start = source.rfind("\n", 0, match.start()) + 1
                column = match.start() - line_start
                if allowed_match(relative, label, match, line, column, allowed_ranges):
                    continue
                violations.append(f"{relative_name}:{line}: {label}: {match.group(0)!r}")
    return violations


def write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def self_test() -> None:
    bad_cases = {
        "app/frontend/src/App.tsx": 'const route = "/demo/dual-nav";\n',
        "src/zhiji_backend/routes/entity_routes.py": 'router.get("/api/entities")\n',
        "src/zhiji_backend/service.py": 'module = "knowledge_graph"\n',
        "src/zhiji_backend/db.py": 'CREATE TABLE IF NOT EXISTS digests (id TEXT);\n',
    }
    with tempfile.TemporaryDirectory(prefix="zhiji-retired-scan-") as temp_dir:
        root = Path(temp_dir)
        for relative, source in bad_cases.items():
            write(root, relative, source)
        violations = scan(root)
        expected = {
            "retired frontend route or demo import",
            "retired entity or digest API/module",
            "retired knowledge graph",
            "retired table creation",
        }
        missing = sorted(label for label in expected if not any(label in item for item in violations))
        if missing:
            raise SystemExit(f"FAIL retired feature scan self-test missed: {', '.join(missing)}")

    retired_route_cases = {
        "app/frontend/src/LegacyRoute.jsx": 'const path = "/reports-old";\n',
        "app/frontend/src/App.tsx": 'const path = "ingest-previous";\n',
        "app/frontend/scripts/qa-retired.mjs": 'const route = "/demo/dual-nav";\n',
        "app/frontend/scripts/qa-retired.js": 'const href = "/#/archive-old";\n',
    }
    for relative, source in retired_route_cases.items():
        with tempfile.TemporaryDirectory(prefix="zhiji-retired-route-") as temp_dir:
            root = Path(temp_dir)
            write(root, relative, source)
            if not any("retired frontend route" in item for item in scan(root)):
                raise SystemExit(f"FAIL retired feature scan missed route fixture: {relative}")

    retired_table_cases = (
        'CREATE TEMP TABLE digests (id TEXT);',
        'create temporary table if not exists main."entities" (id text);',
        'CREATE TEMPORARY TABLE [temp] . [topics] (id TEXT);',
        "CrEaTe TaBlE `main` . 'event_entities' (id TEXT);",
    )
    for index, source in enumerate(retired_table_cases):
        with tempfile.TemporaryDirectory(prefix="zhiji-retired-table-") as temp_dir:
            root = Path(temp_dir)
            write(root, f"src/zhiji_backend/table_case_{index}.py", source)
            if not any("retired table creation" in item for item in scan(root)):
                raise SystemExit(f"FAIL retired feature scan missed table fixture: {source}")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-api-boundary-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/api_names.py",
            '''NEW_DIGEST = "/api/digests-v2"
NEW_ENTITY = "/api/entities-v2"
COLON_DIGEST = "/api/digest:v2"
AT_ENTITY = "/api/entities@v2"
ENCODED_DIGEST = "/api/digest%2Flatest"
''',
        )
        if any("retired entity or digest API" in item for item in scan(root)):
            raise SystemExit("FAIL retired feature scan rejected non-retired API prefixes")
        write(
            root,
            "src/zhiji_backend/retired_api_names.py",
            '''OLD_DIGEST = "/api/digest"
OLD_ENTITY = "/api/entities/by-id"
QUERY_DIGEST = "/api/digest?limit=1"
FRAGMENT_ENTITY = "/api/entities#legacy"
''',
        )
        findings = scan(root)
        if sum("retired entity or digest API" in item for item in findings) < 4:
            raise SystemExit("FAIL retired feature scan missed exact or subpath retired APIs")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-config-unrelated-function-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def cleanup_legacy_config(normalized):
    normalized.pop("knowledge_graph", None)

def _normalize_persisted_config(raw):
    return dict(raw), False
''',
        )
        if not any("knowledge_graph config cleanup" in item for item in scan(root)):
            raise SystemExit("FAIL config checker accepted an unrelated function decoy")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-config-if-false-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(raw):
    normalized = dict(raw)
    if False:
        normalized.pop("knowledge_graph", None)
    return normalized, False
''',
        )
        if not any("knowledge_graph config cleanup" in item for item in scan(root)):
            raise SystemExit("FAIL config checker accepted an unreachable if False decoy")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-config-three-args-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(raw):
    normalized = dict(raw)
    normalized.pop("knowledge_graph", None, None)
    return normalized, False
''',
        )
        if not any("knowledge_graph config cleanup" in item for item in scan(root)):
            raise SystemExit("FAIL config checker accepted normalized.pop with three arguments")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-config-formatting-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(
    raw: dict[str, object],
) -> tuple[dict[str, object], bool]:
    normalized: dict[str, object] = dict(raw)
    normalized.pop( 'knowledge_graph' , None )
    return normalized, False
''',
        )
        if violations := scan(root):
            raise SystemExit("FAIL harmless config cleanup formatting was rejected:\n" + "\n".join(violations))

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-config-missing-pop-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(raw):
    normalized = dict(raw)
    return normalized, False
''',
        )
        if not any("knowledge_graph config cleanup" in item for item in scan(root)):
            raise SystemExit("FAIL config checker accepted a missing real cleanup pop")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-allowlist-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(raw: dict) -> tuple[dict, bool]:
    normalized: dict = dict(raw)
    normalized.pop( 'knowledge_graph' , None )
    return normalized, False
''',
        )
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''@register('20260719_remove_retired_features')
def remove_retired_features(conn) -> None:
    for table_name in ('event_entities', 'entity_relations', 'entities', 'digests', 'topics'):
        conn.execute(f'DROP TABLE IF EXISTS {table_name}')
    conn.execute("DELETE FROM ai_usage WHERE module = 'knowledge_graph' OR (module IN ('digest_briefing', 'briefing') AND task = 'digest')")
''',
        )
        write(root, "app/frontend/src/pages/KiNavigationShell.tsx", "import './DualNavigationDemo.css';\n")
        write(root, "app/frontend/scripts/qa-method.mjs", 'const method = "clear-old";\n')
        write(
            root,
            "src/zhiji_backend/main.py",
            '''@app.get('/api/digest/latest', include_in_schema = False)
@app.post('/api/digest/generate', include_in_schema = False)
async def retired_digest_endpoint() -> JSONResponse:
    return JSONResponse(content={'detail': 'Not Found'}, status_code = 404)
''',
        )
        write(root, "app/frontend/src/App.test.mjs", 'assert.match(app, /\\/demo\\//);\n')
        if violations := scan(root):
            raise SystemExit("FAIL retired feature allowlist self-test:\n" + "\n".join(violations))

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-allowlist-drift-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/main.py",
            '''@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    """Keep retired digest API paths from falling through to static mounts."""
    return JSONResponse({"detail": "Not Found"}, status_code=404)

EXTRA_ROUTE = "/api/digest/admin"
''',
        )
        write(
            root,
            "src/zhiji_backend/config_manager.py",
            '''def _normalize_persisted_config(raw):
    normalized = dict(raw)
    normalized.pop("knowledge_graph", None)
    return normalized, False

ACTIVE_MODULE = "knowledge_graph"
''',
        )
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    for table_name in ("event_entities", "entity_relations", "entities", "digests"):
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute("DELETE FROM ai_usage WHERE module = 'knowledge_graph'")
''',
        )
        violations = scan(root)
        if not any("digest" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed digest tombstone drift")
        if not any("knowledge graph" in item or "knowledge_graph" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed knowledge graph drift")
        if not any("retired tables" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed migration table drift")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-migration-equivalent-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''RETIRED_TABLE_NAMES = ("event_entities", "entity_relations", "entities", "digests", "topics")
DROP_RETIRED_TABLE = "DROP TABLE IF EXISTS {}"
RETIRED_USAGE_CLEANUP = "DELETE FROM ai_usage WHERE module = 'knowledge_graph' OR (module IN ('digest_briefing', 'briefing') AND task = 'digest')"

@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    tables = RETIRED_TABLE_NAMES
    for table_name in tables:
        conn.execute(DROP_RETIRED_TABLE.format(table_name))
    conn.execute(RETIRED_USAGE_CLEANUP)
''',
        )
        if violations := scan(root):
            raise SystemExit("FAIL equivalent retired migration was rejected:\n" + "\n".join(violations))

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-migration-scope-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''RETIRED_TABLE_NAMES = ("event_entities", "entity_relations", "entities", "digests", "topics")
RETIRED_USAGE_CLEANUP = "DELETE FROM ai_usage WHERE module = 'knowledge_graph' OR (module IN ('digest_briefing', 'briefing') AND task = 'digest')"
ACTIVE_MODULE = "knowledge_graph"
ACTIVE_TABLE = "entities"

@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    for table_name in RETIRED_TABLE_NAMES:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(RETIRED_USAGE_CLEANUP)
''',
        )
        if not any("retired knowledge graph" in item for item in scan(root)):
            raise SystemExit("FAIL migration path blanket-allowed unrelated knowledge_graph")
        if not any("retired persistence identifier" in item for item in scan(root)):
            raise SystemExit("FAIL migration path blanket-allowed unrelated retired table identifier")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-drop-prefix-bypass-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''RETIRED_TABLE_NAMES = ("event_entities", "entity_relations", "entities", "digests", "topics")
RETIRED_USAGE_CLEANUP = "DELETE FROM ai_usage WHERE module = 'knowledge_graph' OR (module IN ('digest_briefing', 'briefing') AND task = 'digest')"

@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    for table_name in RETIRED_TABLE_NAMES:
        conn.execute(f"DROP TABLE IF EXISTS archived_{table_name}")
    conn.execute(RETIRED_USAGE_CLEANUP)
''',
        )
        if not any("drop the exact retired tables" in item for item in scan(root)):
            raise SystemExit("FAIL migration scanner allowed prefixed DROP target")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-usage-tautology-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''RETIRED_TABLE_NAMES = ("event_entities", "entity_relations", "entities", "digests", "topics")
RETIRED_USAGE_CLEANUP = "DELETE FROM ai_usage WHERE module = 'knowledge_graph' OR 1=1"

@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    for table_name in RETIRED_TABLE_NAMES:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(RETIRED_USAGE_CLEANUP)
''',
        )
        if not any("ai_usage cleanup" in item for item in scan(root)):
            raise SystemExit("FAIL migration scanner allowed broadened usage DELETE")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-migration-equivalent-drift-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/migrations.py",
            '''RETIRED_TABLE_NAMES = ("event_entities", "entity_relations", "entities", "digests")
RETIRED_USAGE_CLEANUP = "DELETE FROM ai_usage WHERE module = 'knowledge_graph_archive'"

@register("20260719_remove_retired_features")
def remove_retired_features(conn):
    for table_name in RETIRED_TABLE_NAMES:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    conn.execute(RETIRED_USAGE_CLEANUP)
''',
        )
        findings = scan(root)
        if not any("retired tables" in item for item in findings):
            raise SystemExit("FAIL equivalent migration drift missed retired table set")
        if not any("ai_usage cleanup" in item for item in findings):
            raise SystemExit("FAIL equivalent migration drift missed usage cleanup")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-tombstone-drift-") as temp_dir:
        root = Path(temp_dir)
        write(
            root,
            "src/zhiji_backend/main.py",
            '''@app.get("/api/digest/latest", include_in_schema=False)
@app.post("/api/digest/generate", include_in_schema=False)
async def retired_digest_endpoint():
    return JSONResponse({"detail": "Gone"}, status_code=410)
''',
        )
        if not any("404" in item for item in scan(root)):
            raise SystemExit("FAIL retired feature self-test allowed non-404 digest tombstone")

    with tempfile.TemporaryDirectory(prefix="zhiji-retired-compatibility-removed-") as temp_dir:
        root = Path(temp_dir)
        write(root, "src/zhiji_backend/main.py", "app = object()\n")
        write(root, "src/zhiji_backend/migrations.py", "def unrelated_migration():\n    return None\n")
        violations = scan(root)
        if not any("tombstone" in item or "digest" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed tombstone removal")
        if not any("retired tables" in item for item in violations):
            raise SystemExit("FAIL retired feature self-test allowed cleanup migration removal")

    print("retired feature scan self-test ok")


if MODE == "self-test":
    self_test()
else:
    findings = scan(ROOT)
    if findings:
        raise SystemExit("FAIL: stale retired feature found:\n" + "\n".join(findings))
    print("retired feature scan ok")
PY
}

if [[ "${1:-}" == "--self-test-retired-feature-scan" ]]; then
  run_retired_feature_scan self-test
  exit 0
fi

PYTHON_VERSION="$($PYTHON_BIN - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
if [[ "$PYTHON_VERSION" != "3.12" ]]; then
  echo "FAIL: Python 3.12 is required, got $PYTHON_VERSION from $PYTHON_BIN" >&2
  exit 1
fi

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION=$($PYTHON_BIN - <<'PY'
from pathlib import Path
ns = {}
exec(Path('src/zhiji_backend/__init__.py').read_text(), ns)
print(ns['__version__'])
PY
)
fi

echo "== 知几检查: v$VERSION =="

echo "== Python syntax =="
PYTHONPATH=src $PYTHON_BIN -m compileall -q src/zhiji_backend

echo "== Version consistency =="
PYTHONPATH=src $PYTHON_BIN - "$VERSION" <<'PY'
from pathlib import Path
import re
import sys
version = sys.argv[1]
checks = {
    'src/zhiji_backend/__init__.py': f'__version__ = "{version}"',
    'pyproject.toml': f'version = "{version}"',
    'app/frontend/src/constants.ts': f'APP_VERSION = "{version}"',
    'app/frontend/vite.config.ts': f"appVersion = '{version}'",
    'desktop/lib/main.dart': f"_desktopVersion = '{version}'",
    'app/frontend/public/about.html': f'v{version}',
}
for rel, needle in checks.items():
    text = Path(rel).read_text()
    if needle not in text:
        raise SystemExit(f'FAIL version mismatch: {rel} missing {needle!r}')
pubspec = Path('desktop/pubspec.yaml').read_text()
if not re.search(rf'^version:\s*{re.escape(version)}\+\d+\s*$', pubspec, re.M):
    raise SystemExit('FAIL version mismatch: desktop/pubspec.yaml')
main = Path('src/zhiji_backend/main.py').read_text()
if 'version=__version__' not in main:
    raise SystemExit('FAIL FastAPI app must use zhiji_backend.__version__')
dashboard = Path('src/zhiji_backend/routes/dashboard_routes.py').read_text()
if '"version": __version__' not in dashboard:
    raise SystemExit('FAIL /api/health must use zhiji_backend.__version__')
print('version consistency ok')
PY

echo "== Stale code scan =="
if [[ -d app/backend ]]; then
  echo "FAIL: legacy backend directory app/backend must not exist; archive under app/_archive/ if needed" >&2
  exit 1
fi
if grep -R "from backend\.\|import backend\.\|ROOT / \"app\" / \"backend\"" tests scripts app/scripts 2>/dev/null; then
  echo "FAIL: stale legacy backend import/path found" >&2
  exit 1
fi
if grep -R "__TAURI_INTERNALS__\|@tauri-apps\|check_updates\|tauriInvoke\|tauriListen\|get_desktop_version" \
  app/frontend/src app/frontend/public app/frontend/package.json desktop/lib 2>/dev/null; then
  echo "FAIL: stale Tauri/update residue found" >&2
  exit 1
fi
if grep -R "patch_.*\.bsdiff\|bsdiff .*zhiji\|bspatch .*zhiji\|manifest.json.*gh release\|install_helper\.sh\|10\.8\.0\.105:9120/releases\|后端 DMG 分发\|BACKEND_DMG_URL\|RELEASES_DIR_LOCAL" scripts/build_release.py scripts/release-check.py 2>/dev/null; then
  echo "FAIL: stale patch-update implementation found in active release scripts" >&2
  exit 1
fi
run_retired_feature_scan

echo "== Frontend build =="
(cd app/frontend && npm run build)

echo "== Frontend dist version =="
if ! grep -q "index-${VERSION}-" app/frontend/dist/index.html; then
  echo "FAIL: dist/index.html does not reference versioned assets for $VERSION" >&2
  exit 1
fi

echo "== Cinematic QA baseline =="
if [[ "${ZHIJI_RUN_CINEMATIC_QA:-}" == "1" ]]; then
  ZHIJI_QA_BASE_URL="${ZHIJI_QA_BASE_URL:-http://10.8.0.105:9120}"
  (cd app/frontend && npm run qa:cinematic-pages "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages)
  (cd app/frontend && npm run qa:cinematic-pages:compact "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-compact)
  (cd app/frontend && npm run qa:cinematic-pages:perf "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-perf)
  (cd app/frontend && npm run qa:cinematic-pages:journey "$ZHIJI_QA_BASE_URL" tmp/check-cinematic-pages-journey)
else
  echo "skip cinematic QA: set ZHIJI_RUN_CINEMATIC_QA=1"
fi

echo "== Optional release artifact check =="
if [[ "${ZHIJI_SKIP_RELEASE_CHECK:-}" == "1" ]]; then
  echo "skip release-check: ZHIJI_SKIP_RELEASE_CHECK=1"
elif [[ -f "desktop/build/release/zhiji_${VERSION}.dmg" ]]; then
  PYTHONPATH=src $PYTHON_BIN scripts/release-check.py "$VERSION"
else
  echo "skip release-check: desktop/build/release/zhiji_${VERSION}.dmg not found"
fi

echo "== check ok =="
