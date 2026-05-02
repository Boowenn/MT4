"""AST-based safety validation for Vibe Coding generated strategies."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable


DEFAULT_ALLOWED_IMPORTS = {
    "math",
    "statistics",
    "datetime",
    "pandas",
    "numpy",
    "talib",
    "ta",
    "pandas_ta",
    "tools.vibe_coding.strategy_template",
    "vibe_coding.strategy_template",
}

DANGEROUS_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "ftplib",
    "paramiko",
    "shutil",
    "pathlib",
    "importlib",
    "pickle",
    "marshal",
    "ctypes",
    "multiprocessing",
    "threading",
    "asyncio",
    "webbrowser",
}

DANGEROUS_CALLS = {
    "open",
    "exec",
    "eval",
    "compile",
    "input",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "breakpoint",
    "help",
    "exit",
    "quit",
}

DANGEROUS_ATTRS = {
    "system",
    "popen",
    "spawn",
    "remove",
    "unlink",
    "rmdir",
    "rename",
    "replace",
    "write",
    "writelines",
    "send",
    "sendall",
    "connect",
    "request",
    "urlopen",
    "exec",
    "eval",
    "load",
    "loads",
}


@dataclass
class ValidationIssue:
    severity: str
    message: str
    lineno: int | None = None

    def to_dict(self) -> dict:
        return {"severity": self.severity, "message": self.message, "lineno": self.lineno}


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    class_name: str | None = None
    imports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [issue.to_dict() for issue in self.issues],
            "class_name": self.class_name,
            "imports": self.imports,
        }


def _module_root(name: str) -> str:
    return str(name or "").split(".")[0]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def validate_strategy_code(
    code: str,
    *,
    allowed_imports: Iterable[str] | None = None,
    max_code_bytes: int = 64 * 1024,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    imports: list[str] = []
    allowed = set(allowed_imports or DEFAULT_ALLOWED_IMPORTS)

    if len(code.encode("utf-8")) > max_code_bytes:
        issues.append(ValidationIssue("error", f"code exceeds {max_code_bytes} bytes"))
        return ValidationResult(False, issues, None, imports)

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        issues.append(ValidationIssue("error", f"syntax error: {exc.msg}", exc.lineno))
        return ValidationResult(False, issues, None, imports)

    class_name = None
    has_base_strategy_subclass = False
    has_evaluate = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                root = _module_root(alias.name)
                if root in DANGEROUS_MODULES or (alias.name not in allowed and root not in allowed):
                    issues.append(ValidationIssue("error", f"import not allowed: {alias.name}", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
            root = _module_root(module)
            if root in DANGEROUS_MODULES or (module not in allowed and root not in allowed):
                issues.append(ValidationIssue("error", f"from import not allowed: {module}", node.lineno))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            tail = name.split(".")[-1]
            if name in DANGEROUS_CALLS or tail in DANGEROUS_CALLS:
                issues.append(ValidationIssue("error", f"dangerous call not allowed: {name}", getattr(node, "lineno", None)))
            if tail in DANGEROUS_ATTRS:
                issues.append(ValidationIssue("error", f"dangerous API not allowed: {name}", getattr(node, "lineno", None)))
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                issues.append(ValidationIssue("error", f"dunder attribute not allowed: {node.attr}", getattr(node, "lineno", None)))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            issues.append(ValidationIssue("error", "global/nonlocal mutation not allowed", getattr(node, "lineno", None)))
        elif isinstance(node, ast.ClassDef):
            if class_name is None:
                class_name = node.name
            for base in node.bases:
                base_name = _call_name(base)
                if base_name.endswith("BaseStrategy"):
                    has_base_strategy_subclass = True
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "evaluate":
                    has_evaluate = True

    if not has_base_strategy_subclass:
        issues.append(ValidationIssue("error", "generated code must subclass BaseStrategy"))
    if not has_evaluate:
        issues.append(ValidationIssue("error", "generated strategy must implement evaluate()"))

    return ValidationResult(ok=not any(issue.severity == "error" for issue in issues), issues=issues, class_name=class_name, imports=imports)
