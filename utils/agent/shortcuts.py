"""Atalhos configuráveis para o agent CLI (/mkdir, /model, etc.)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


@dataclass
class Shortcut:
  """Definição de um atalho do agente."""

  name: str
  aliases: List[str]
  description: str
  type: str
  template: str = ""
  tool: str = ""
  args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedShortcut:
  """Resultado ao resolver um atalho digitado pelo usuário."""

  shortcut: Shortcut
  raw_args: str
  type: str
  task: Optional[str] = None
  tool_name: Optional[str] = None
  tool_args: Optional[Dict[str, Any]] = None
  command: Optional[str] = None


class ShortcutRegistry:
  """Carrega e resolve atalhos de config/agent_shortcuts.json."""

  def __init__(self, config_path: Path) -> None:
    self.config_path = config_path.resolve()
    self._shortcuts: List[Shortcut] = []
    self._alias_map: Dict[str, Shortcut] = {}
    self.reload()

  def reload(self) -> None:
    """Recarrega atalhos do arquivo JSON."""
    self._shortcuts = []
    self._alias_map = {}

    if not self.config_path.is_file():
      logger.warning("Atalhos não encontrados: %s", self.config_path)
      return

    data = json.loads(self.config_path.read_text(encoding="utf-8"))
    for entry in data.get("shortcuts", []):
      shortcut = Shortcut(
        name=str(entry.get("name", "")),
        aliases=[str(a).lower().lstrip("/") for a in entry.get("aliases", [])],
        description=str(entry.get("description", "")),
        type=str(entry.get("type", "task")),
        template=str(entry.get("template", "")),
        tool=str(entry.get("tool", "")),
        args=dict(entry.get("args", {})),
      )
      if not shortcut.name:
        continue
      self._shortcuts.append(shortcut)
      for alias in shortcut.aliases:
        self._alias_map[alias] = shortcut
      self._alias_map[shortcut.name.lower()] = shortcut

  def list_shortcuts(self) -> List[Shortcut]:
    """Retorna todos os atalhos registrados."""
    return list(self._shortcuts)

  def format_help(self) -> str:
    """Texto de help com atalhos disponíveis."""
    if not self._shortcuts:
      return "Nenhum atalho configurado em config/agent_shortcuts.json"

    lines = ["Atalhos (edite config/agent_shortcuts.json):"]
    for sc in self._shortcuts:
      primary = sc.aliases[0] if sc.aliases else f"/{sc.name}"
      if not primary.startswith("/"):
        primary = f"/{primary}"
      lines.append(f"  {primary:<14} {sc.description}")
    lines.append("")
    lines.append("Exemplos:")
    lines.append("  /new-project ruff")
    lines.append("  /mkdir app/Services")
    lines.append("  /model Order")
    lines.append("  /migration tabela orders com client_id e total")
    return "\n".join(lines)

  def _substitute(self, template: str, raw_args: str, shortcut: Shortcut) -> str:
    """Substitui {args} e placeholders em templates/args."""
    context: Dict[str, str] = {
      "args": raw_args.strip(),
      "name": raw_args.strip(),
    }
    # Primeira palavra como {name} se houver múltiplos tokens
    parts = raw_args.strip().split()
    if parts:
      context["name"] = parts[0]
      if len(parts) > 1:
        context["rest"] = " ".join(parts[1:])

    def replacer(match: re.Match[str]) -> str:
      key = match.group(1)
      return context.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(replacer, template)

  def _substitute_args(self, args: Dict[str, Any], raw_args: str) -> Dict[str, Any]:
    """Substitui placeholders nos argumentos de ferramentas."""
    resolved: Dict[str, Any] = {}
    for key, value in args.items():
      if isinstance(value, str):
        resolved[key] = self._substitute(value, raw_args, Shortcut("", [], "", ""))
      else:
        resolved[key] = value
    if "path" in resolved and resolved["path"] == "":
      resolved["path"] = "."
    return resolved

  def parse_input(self, text: str) -> tuple[str, str]:
    """Separa comando e argumentos do input do usuário."""
    stripped = text.strip()
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower().lstrip("/")
    args = parts[1] if len(parts) > 1 else ""
    return cmd, args

  def resolve(self, text: str) -> Optional[ResolvedShortcut]:
    """Resolve texto se for um atalho conhecido.

    Args:
      text: Input do usuário (ex: '/mkdir app/Models' ou 'model Product').

    Returns:
      ResolvedShortcut se for atalho, None se for tarefa livre.
    """
    cmd, raw_args = self.parse_input(text)
    shortcut = self._alias_map.get(cmd)
    if shortcut is None:
      return None

    if shortcut.type == "task":
      task = self._substitute(shortcut.template, raw_args, shortcut)
      return ResolvedShortcut(
        shortcut=shortcut,
        raw_args=raw_args,
        type="task",
        task=task,
      )

    if shortcut.type == "tool":
      tool_args = self._substitute_args(shortcut.args, raw_args)
      return ResolvedShortcut(
        shortcut=shortcut,
        raw_args=raw_args,
        type="tool",
        tool_name=shortcut.tool,
        tool_args=tool_args,
      )

    if shortcut.type == "command":
      command = self._substitute(shortcut.template, raw_args, shortcut)
      return ResolvedShortcut(
        shortcut=shortcut,
        raw_args=raw_args,
        type="command",
        command=command,
      )

    return None
