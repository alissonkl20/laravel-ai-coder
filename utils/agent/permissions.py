"""Aprovações interativas (diff / shell) estilo Cursor."""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from utils.agent.tools import ToolResult

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

_DESTRUCTIVE_RE = re.compile(
  r"\b(migrate:fresh|migrate:refresh|db:wipe|db:seed|migrate:reset)\b",
  re.IGNORECASE,
)


class PermissionManager:
  """Pede confirmação antes de writes e comandos destrutivos."""

  WRITE_TOOLS = frozenset({
    "write_file", "replace_in_file", "insert_lines", "scaffold_php",
    "mkdir", "create_laravel_project",
  })
  SHELL_TOOLS = frozenset({"run_command"})

  def __init__(self, *, force: bool = False, enabled: bool = True) -> None:
    self.force = force
    self.enabled = enabled

  def allow_tool(
    self,
    name: str,
    args: Dict[str, Any],
    workspace: Path,
  ) -> ToolResult | None:
    """Retorna ToolResult de rejeição, ou None se pode seguir."""
    if self.force or not self.enabled:
      return None

    if name == "write_file":
      return self._confirm_write(args, workspace)
    if name == "replace_in_file":
      return self._confirm_simple(
        f"Editar {args.get('path', '')}",
        "replace_in_file",
      )
    if name == "insert_lines":
      return self._confirm_simple(
        f"Inserir em {args.get('path', '')}",
        "insert_lines",
      )
    if name == "scaffold_php":
      return self._confirm_simple(
        f"scaffold_php {args.get('kind', '')} {args.get('name', args.get('path', ''))}",
        "scaffold_php",
      )
    if name == "mkdir":
      return self._confirm_simple(
        f"Criar diretório: {args.get('path', '')}",
        "mkdir",
      )
    if name == "create_laravel_project":
      return self._confirm_simple(
        f"Criar projeto Laravel: {args.get('name', '')}",
        "create_laravel_project",
      )
    if name == "run_command":
      command = str(args.get("command", ""))
      if _DESTRUCTIVE_RE.search(command) or self._looks_mutating(command):
        return self._confirm_simple(f"Executar comando: {command}", "run_command")
    return None

  def _looks_mutating(self, command: str) -> bool:
    lower = command.lower()
    return any(
      token in lower
      for token in (
        "make:",
        "migrate",
        "db:",
        "composer require",
        "composer remove",
        "npm install",
      )
    )

  def _confirm_simple(self, summary: str, kind: str) -> Optional[ToolResult]:
    print(f"\n{YELLOW}── aprovação · {kind} ──{RESET}")
    print(summary)
    answer = self._ask("Aplicar? [y/N] ")
    if answer in {"y", "yes", "s", "sim"}:
      return None
    return ToolResult(False, f"Operação {kind} rejeitada pelo usuário.")

  def _confirm_write(self, args: Dict[str, Any], workspace: Path) -> Optional[ToolResult]:
    path = str(args.get("path", ""))
    content = str(args.get("content", ""))
    try:
      file_path = (workspace / path).resolve() if not Path(path).is_absolute() else Path(path)
      if not str(file_path).startswith(str(workspace.resolve())):
        return ToolResult(False, f"Path fora do workspace: {path}")
    except Exception as exc:
      return ToolResult(False, f"Path inválido: {exc}")

    old = ""
    if file_path.is_file():
      old = file_path.read_text(encoding="utf-8", errors="replace")

    diff = self._unified_diff(old, content, path)
    print(f"\n{YELLOW}── aprovação · write_file ──{RESET}")
    print(f"{DIM}{path}{RESET}")
    print(diff[:6000] if diff.strip() else f"{DIM}(arquivo novo / sem diff textual){RESET}")
    answer = self._ask("Aplicar write? [y/N] ")
    if answer in {"y", "yes", "s", "sim"}:
      return None
    return ToolResult(False, f"write_file rejeitado pelo usuário: {path}")

  def _unified_diff(self, old: str, new: str, path: str) -> str:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    lined = difflib.unified_diff(
      old_lines,
      new_lines,
      fromfile=f"a/{path}",
      tofile=f"b/{path}",
      lineterm="",
    )
    colored = []
    for line in lined:
      if line.startswith("+") and not line.startswith("+++"):
        colored.append(f"{GREEN}{line}{RESET}")
      elif line.startswith("-") and not line.startswith("---"):
        colored.append(f"{RED}{line}{RESET}")
      elif line.startswith("@@"):
        colored.append(f"{YELLOW}{line}{RESET}")
      else:
        colored.append(line)
    return "\n".join(colored)

  def _ask(self, prompt: str) -> str:
    if not sys.stdin.isatty():
      return "n"
    try:
      return input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
      print()
      return "n"
