"""Modos de operação estilo Cursor CLI: ask / plan / agent."""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class AgentMode(str, Enum):
  ASK = "ask"
  PLAN = "plan"
  AGENT = "agent"

  @classmethod
  def parse(cls, value: str | None, default: "AgentMode | None" = None) -> "AgentMode":
    raw = (value or "").strip().lower()
    if not raw:
      return default or cls.AGENT
    aliases = {
      "a": cls.ASK,
      "ask": cls.ASK,
      "p": cls.PLAN,
      "plan": cls.PLAN,
      "agent": cls.AGENT,
      "ag": cls.AGENT,
    }
    if raw not in aliases:
      raise ValueError(f"Modo inválido: {value}. Use ask | plan | agent")
    return aliases[raw]


ASK_TOOLS: FrozenSet[str] = frozenset({
  "read_file",
  "list_dir",
  "grep",
  "search",
  "tail_log",
})

PLAN_TOOLS: FrozenSet[str] = frozenset({
  "read_file",
  "list_dir",
  "grep",
  "search",
  "tail_log",
})

AGENT_TOOLS: FrozenSet[str] = frozenset({
  "read_file",
  "write_file",
  "replace_in_file",
  "insert_lines",
  "scaffold_php",
  "mkdir",
  "list_dir",
  "grep",
  "run_command",
  "tail_log",
  "search",
  "create_laravel_project",
})

MODE_TOOLS = {
  AgentMode.ASK: ASK_TOOLS,
  AgentMode.PLAN: PLAN_TOOLS,
  AgentMode.AGENT: AGENT_TOOLS,
}


def tools_for_mode(mode: AgentMode) -> FrozenSet[str]:
  return MODE_TOOLS.get(mode, AGENT_TOOLS)


MODE_INSTRUCTIONS = {
  AgentMode.ASK: "ASK: só leitura (search/read/grep). Não edite. Cite paths.",
  AgentMode.PLAN: "PLAN: plano numerado, sem editar. Usuário aprova com execute.",
  AgentMode.AGENT: (
    "AGENT: artisan make:* → scaffold_php ou replace_in_file. "
    "Nunca coloque PHP inteiro em content string. "
    "write_file só com lines curtas. "
    "Tarefa com testes: rode php artisan test antes do finish. "
    "Não finish se a tool falhou."
  ),
}
