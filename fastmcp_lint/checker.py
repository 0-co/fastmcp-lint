"""Core AST-based checker for FastMCP tool quality."""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ToolIssue:
    code: str
    severity: str  # "error", "warning", "info"
    message: str
    line: int


@dataclass
class ToolResult:
    name: str
    line: int
    docstring: Optional[str]
    params: list[str]
    issues: list[ToolIssue] = field(default_factory=list)

    @property
    def score(self) -> int:
        """0-100 quality score.

        F001 (missing docstring) = -60 (matches agent-friend Correctness: 0).
        Other errors = -20 each. Warnings = -10 each.
        """
        base = 100
        for issue in self.issues:
            if issue.code == "F001":
                base -= 60
            elif issue.severity == "error":
                base -= 20
            elif issue.severity == "warning":
                base -= 10
        return max(0, base)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 90: return "A+"
        if s >= 80: return "A"
        if s >= 70: return "B"
        if s >= 60: return "C"
        if s >= 50: return "D"
        return "F"

    @property
    def description_preview(self) -> str:
        """What FastMCP will use as the tool description."""
        if not self.docstring:
            return "(empty — no docstring)"
        # FastMCP uses first paragraph of docstring as description
        first_para = self.docstring.strip().split("\n\n")[0].strip()
        # Clean up indentation
        lines = [l.strip() for l in first_para.splitlines()]
        return " ".join(l for l in lines if l)

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate for this tool's schema contribution."""
        name_tokens = len(self.name) // 4
        desc = self.description_preview
        desc_tokens = len(desc) // 4 if desc != "(empty — no docstring)" else 0
        param_tokens = sum(len(p) // 4 + 5 for p in self.params)
        return name_tokens + desc_tokens + param_tokens + 20  # overhead


def _is_mcp_tool_decorator(node: ast.expr) -> bool:
    """Check if a decorator is @mcp.tool() or similar FastMCP patterns."""
    if isinstance(node, ast.Call):
        func = node.func
        # @mcp.tool()
        if isinstance(func, ast.Attribute) and func.attr == "tool":
            return True
        # @app.tool() or similar
        if isinstance(func, ast.Name) and func.id == "tool":
            return True
    return False


def _check_tool(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ToolResult:
    """Run all quality checks on a FastMCP tool function."""
    params = [a.arg for a in node.args.args if a.arg not in ("self", "ctx")]
    # Also check keyword-only args
    params += [a.arg for a in (node.args.kwonlyargs or []) if a.arg not in ("self", "ctx")]

    docstring = ast.get_docstring(node)
    result = ToolResult(
        name=node.name,
        line=node.lineno,
        docstring=docstring,
        params=params,
    )

    issues = result.issues

    # F001: Missing docstring → FastMCP generates empty description
    if not docstring:
        issues.append(ToolIssue(
            code="F001",
            severity="error",
            message="Missing docstring. FastMCP will generate an empty tool description. "
                    "Agents can't select this tool reliably.",
            line=node.lineno,
        ))
        return result  # No point checking further

    # F002: Docstring too short (under 20 chars = probably useless)
    first_line = docstring.strip().split("\n")[0].strip()
    if len(first_line) < 20:
        issues.append(ToolIssue(
            code="F002",
            severity="warning",
            message=f"Docstring too short ({len(first_line)} chars). "
                    f"Agents rely on descriptions to decide when to call tools.",
            line=node.lineno,
        ))

    # F003: Parameters not documented
    if params:
        doc_lower = docstring.lower()
        undocumented = [p for p in params if p not in doc_lower]
        if undocumented:
            issues.append(ToolIssue(
                code="F003",
                severity="warning",
                message=f"Parameters not mentioned in docstring: {', '.join(undocumented)}. "
                        f"FastMCP uses docstrings for parameter descriptions.",
                line=node.lineno,
            ))

    # F004: Tool name not snake_case
    if not re.match(r'^[a-z][a-z0-9_]*$', node.name):
        issues.append(ToolIssue(
            code="F004",
            severity="warning",
            message=f"Tool name '{node.name}' should be snake_case. "
                    f"MCP naming convention requires lowercase with underscores.",
            line=node.lineno,
        ))

    # F005: Tool name too long (over 60 chars causes Claude Desktop truncation)
    if len(node.name) > 60:
        issues.append(ToolIssue(
            code="F005",
            severity="error",
            message=f"Tool name '{node.name}' is {len(node.name)} chars. "
                    f"Claude Desktop truncates tool names at 60 chars.",
            line=node.lineno,
        ))

    # F006: Description contains model-directing language (prompt override risk)
    directive_patterns = [
        r"\byou must\b", r"\balways call\b", r"\bnever\b skip",
        r"\bignore previous\b", r"\bmust always\b", r"\bdo not\b.*first",
    ]
    desc_lower = result.description_preview.lower()
    for pattern in directive_patterns:
        if re.search(pattern, desc_lower):
            issues.append(ToolIssue(
                code="F006",
                severity="warning",
                message=f"Description contains model-directing language ('{pattern}'). "
                        f"OWASP MCP Top 10: prompt injection risk.",
                line=node.lineno,
            ))
            break

    # F007: Description is a single word or generic placeholder
    if docstring.strip().lower() in ("todo", "fixme", "...", "pass", "tbd", "placeholder"):
        issues.append(ToolIssue(
            code="F007",
            severity="error",
            message=f"Docstring is a placeholder. FastMCP will generate a useless description.",
            line=node.lineno,
        ))

    return result


def check_file(path: Path) -> list[ToolResult]:
    """Parse a Python file and check all FastMCP tool functions."""
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise ValueError(f"Syntax error in {path}: {e}")

    results = []
    for node in ast.walk(tree):
        # Handle both sync and async functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if _is_mcp_tool_decorator(dec):
                    results.append(_check_tool(node))
                    break

    return results
