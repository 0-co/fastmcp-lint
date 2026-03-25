"""CLI entry point for fastmcp-lint."""
import sys
import argparse
from pathlib import Path
from .checker import check_file


GRADE_COLORS = {
    "A+": "\033[92m",  # bright green
    "A": "\033[92m",
    "B": "\033[93m",   # yellow
    "C": "\033[93m",
    "D": "\033[91m",   # red
    "F": "\033[91m",
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def colored_grade(grade: str) -> str:
    color = GRADE_COLORS.get(grade, "")
    return f"{BOLD}{color}{grade}{RESET}"


def main():
    parser = argparse.ArgumentParser(
        prog="fastmcp-lint",
        description="Static analysis for FastMCP servers. Catches schema quality issues before they ship.",
    )
    parser.add_argument("files", nargs="+", help="FastMCP server Python file(s) to lint")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any warnings found (not just errors)")
    parser.add_argument("--ci", action="store_true", help="CI mode: exit 1 on any issues, no color output")

    args = parser.parse_args()

    no_color = args.ci or not sys.stdout.isatty()
    if no_color:
        global RESET, BOLD, DIM
        RESET = BOLD = DIM = ""
        for k in GRADE_COLORS:
            GRADE_COLORS[k] = ""

    all_results = []
    total_issues = 0
    total_errors = 0
    files_ok = 0

    for file_path in args.files:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: {file_path} not found", file=sys.stderr)
            sys.exit(2)

        try:
            results = check_file(path)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)

        all_results.append((path, results))

    if args.json:
        import json
        output = []
        for path, results in all_results:
            for r in results:
                output.append({
                    "file": str(path),
                    "tool": r.name,
                    "line": r.line,
                    "grade": r.grade,
                    "score": r.score,
                    "description_preview": r.description_preview,
                    "estimated_tokens": r.estimated_tokens,
                    "issues": [
                        {"code": i.code, "severity": i.severity, "message": i.message}
                        for i in r.issues
                    ],
                })
        print(json.dumps(output, indent=2))
        sys.exit(0)

    for path, results in all_results:
        if not results:
            print(f"{DIM}{path}: no @mcp.tool() functions found{RESET}")
            continue

        file_errors = sum(1 for r in results for i in r.issues if i.severity == "error")
        file_warnings = sum(1 for r in results for i in r.issues if i.severity == "warning")
        file_score = sum(r.score for r in results) // len(results) if results else 100
        file_grade = results[0].__class__(name="", line=0, docstring="", params=[])

        print(f"\n{BOLD}{path}{RESET}")
        print(f"  {len(results)} tools  |  avg score: {file_score}/100  |  {file_errors} errors, {file_warnings} warnings")
        print()

        for r in results:
            grade_str = colored_grade(r.grade)
            print(f"  {BOLD}{r.name}{RESET}  (line {r.line})  [{grade_str}] {r.score}/100")
            desc = r.description_preview
            if len(desc) > 80:
                desc = desc[:77] + "..."
            print(f"  {DIM}description: {desc}{RESET}")
            if r.estimated_tokens:
                print(f"  {DIM}~{r.estimated_tokens} tokens{RESET}")

            if r.issues:
                for issue in r.issues:
                    icon = "✗" if issue.severity == "error" else "⚠"
                    color = "\033[91m" if issue.severity == "error" else "\033[93m"
                    if no_color:
                        color = ""
                    print(f"    {color}{icon} [{issue.code}] {issue.message}{RESET}")
                    total_issues += 1
                    if issue.severity == "error":
                        total_errors += 1
            else:
                print(f"    \033[92m✓ No issues found{RESET}" if not no_color else "    ✓ No issues")
                files_ok += 1
            print()

    total_tools = sum(len(results) for _, results in all_results)
    print(f"{'─' * 50}")
    print(f"  {total_tools} tools checked  |  {total_issues} issues  |  {total_errors} errors")

    if total_errors > 0:
        print(f"\n  {BOLD}Fix errors: empty descriptions cause agents to skip your tools.{RESET}")
        print(f"  Run:  pip install agent-friend && agent-friend grade <schema.json>")

    if args.ci and total_issues > 0:
        sys.exit(1)
    elif args.strict and total_issues > 0:
        sys.exit(1)
    elif total_errors > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
