"""Agent CLI para debug de projetos Laravel com LLM local."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from config import AGENT_NAME, AgentConfig
from utils.agent.agent import LaravelAgent
from utils.agent.cache import AgentCache
from utils.agent.modes import AgentMode
from utils.agent.permissions import PermissionManager
from utils.agent.preflight import run_preflight
from utils.agent.search_index import SearchIndex
from utils.agent.session import SessionManager
from utils.agent.shortcuts import ShortcutRegistry
from utils.agent.step_metrics import (
  StepMetricsCollector,
  nvidia_smi_used_mb,
  torch_vram_mb,
)
from utils.agent.tools import ToolRegistry
from utils.agent.workspace import WorkspaceManager
from utils.stdio_silence import silenced_output

logging.basicConfig(
  level=logging.WARNING,
  format="%(asctime)s [%(levelname)s] %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
  force=True,
)
logger = logging.getLogger(__name__)

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"
RESET = "\033[0m"

_EXECUTE_HINTS = frozenset({
  "y", "yes", "s", "sim", "ok", "execute", "executar", "aprovar", "aprovado",
  "aplica", "aplicar", "go", "run",
})


def _quiet_boot_logging() -> None:
  root = logging.getLogger()
  root.setLevel(logging.WARNING)
  for handler in root.handlers:
    handler.setLevel(logging.WARNING)
  for name in (
    "inference",
    "utils.agent.cache",
    "utils.agent.search_index",
    "transformers",
    "torch",
    "accelerate",
    "peft",
  ):
    logging.getLogger(name).setLevel(logging.WARNING)


def _print_banner(
  workspace_mgr: WorkspaceManager,
  mode: AgentMode,
  session_id: str,
) -> None:
  ws = workspace_mgr.workspace
  print(f"{DIM}Projeto: {workspace_mgr.project_name} → {ws}{RESET}")
  print(f"{DIM}Base: {workspace_mgr.projects_root}{RESET}")
  print(f"{DIM}Modo: {mode.value} · sessão: {session_id}{RESET}")
  print(
    f"{DIM}Comandos: sair | help | /mode ask|plan|agent | /sessions | "
    f"/resume ID | limpar | /projects | /project NOME{RESET}\n"
  )


def _print_help(shortcuts: ShortcutRegistry, workspace_mgr: WorkspaceManager) -> None:
  print(
    f"{CYAN}Modos (Cursor-like):{RESET}\n"
    "  /mode ask     — só leitura + busca (Q&A)\n"
    "  /mode plan    — planeja e pergunta, sem editar\n"
    "  /mode agent   — executa com aprovação de write/shell\n\n"
    f"{CYAN}Sessões:{RESET}\n"
    "  /sessions     — lista conversas\n"
    "  /resume ID    — retoma conversa\n"
    "  limpar        — limpa histórico da sessão atual\n\n"
    f"{CYAN}Projetos:{RESET}\n"
    "  /projects | /project NOME | /new-project NOME\n\n"
  )
  print(workspace_mgr.format_project_list())
  print()
  print(shortcuts.format_help())


def _on_step(
  step: int,
  kind: str,
  detail: str,
  metrics: Optional[Dict[str, Any]] = None,
) -> None:
  if kind == "tool":
    print(f"\n{YELLOW}── step {step} · ferramenta ──{RESET}")
    print(detail[:4000])
  elif kind == "finish":
    print(f"\n{GREEN}── step {step} · concluído ──{RESET}")
  elif kind == "parse_error":
    print(f"\n{RED}── step {step} · JSON inválido, retentando ──{RESET}")
    print(detail[:500])
  if metrics:
    print(
      f"{DIM}llm: tokenize={metrics.get('t_tokenize_ms')}ms "
      f"generate={metrics.get('t_generate_ms')}ms "
      f"prompt={metrics.get('prompt_tokens')} "
      f"new={metrics.get('new_tokens')} "
      f"{metrics.get('tokens_per_s')} tok/s "
      f"trunc={metrics.get('truncated')} "
      f"vram={metrics.get('vram_max_alloc_mb')}MB{RESET}"
    )


def _run_shortcut(resolved, tools: ToolRegistry) -> Optional[str]:
  if resolved.type == "tool":
    result = tools.run(resolved.tool_name or "", resolved.tool_args or {})
    status = GREEN + "OK" + RESET if result.success else RED + "ERRO" + RESET
    return f"[{status}] {resolved.shortcut.name}\n{result.output}"

  if resolved.type == "command":
    result = tools.run("run_command", {"command": resolved.command or ""})
    status = GREEN + "OK" + RESET if result.success else RED + "ERRO" + RESET
    return f"[{status}] {resolved.command}\n{result.output}"

  return None


def _switch_project(
  workspace_mgr: WorkspaceManager,
  tools: ToolRegistry,
  agent: LaravelAgent,
  search_index: SearchIndex,
  name: str,
  force_reindex: bool = False,
) -> str:
  try:
    new_ws = workspace_mgr.set_project(name)
  except (FileNotFoundError, ValueError) as exc:
    return f"{RED}Erro:{RESET} {exc}"

  tools.set_workspace(new_ws)
  agent.tools = tools
  n = search_index.index_workspace(new_ws, force=force_reindex)
  return (
    f"{GREEN}Projeto ativo:{RESET} {workspace_mgr.project_name}\n"
    f"{DIM}{new_ws}{RESET}\n"
    f"Indexado: {n} arquivos"
  )


def _set_mode(agent: LaravelAgent, sessions: SessionManager, mode: AgentMode) -> str:
  agent.set_mode(mode)
  if sessions.current is not None:
    sessions.current.mode = mode.value
    sessions.save()
  return f"{GREEN}Modo:{RESET} {mode.value}"


def _run_agent_task(
  agent: LaravelAgent,
  tools: ToolRegistry,
  task: str,
  shortcut_name: Optional[str] = None,
  raw_args: str = "",
  workspace_mgr: Optional[WorkspaceManager] = None,
  search_index: Optional[SearchIndex] = None,
  sessions: Optional[SessionManager] = None,
) -> str:
  if agent.mode == AgentMode.AGENT:
    preflight = run_preflight(
      task,
      tools,
      shortcut_name=shortcut_name,
      raw_args=raw_args,
    )
    if preflight.handled and preflight.user_message:
      print(f"{CYAN}{preflight.user_message}{RESET}\n")

    if preflight.switch_project and workspace_mgr is not None and search_index is not None:
      switch_msg = _switch_project(
        workspace_mgr, tools, agent, search_index, preflight.switch_project
      )
      if preflight.finish:
        result = f"{preflight.user_message}\n\n{switch_msg}" if preflight.user_message else switch_msg
        if sessions is not None:
          sessions.append_turn(task, result)
        return result
      print(f"{GREEN}{switch_msg}{RESET}\n")

    if preflight.finish:
      result = preflight.user_message or "Concluído."
      if sessions is not None:
        sessions.append_turn(task, result)
      return result

    run_task = preflight.augmented_task if preflight.handled else task
  else:
    run_task = task

  result = agent.run(run_task, on_step=_on_step)
  if sessions is not None:
    sessions.append_turn(task, result)
  return result


def _maybe_execute_plan(
  task: str,
  agent: LaravelAgent,
  sessions: SessionManager,
) -> Optional[str]:
  """Se estiver em plan e o usuário aprovar, muda para agent e executa o último plano."""
  normalized = task.strip().lower()
  if agent.mode != AgentMode.PLAN:
    return None
  if normalized not in _EXECUTE_HINTS and not normalized.startswith("execute"):
    return None
  if not agent.conversation:
    return "Nenhum plano na sessão. Peça um plano primeiro."

  last_plan = agent.conversation[-1]["assistant"]
  agent.set_mode(AgentMode.AGENT)
  if sessions.current is not None:
    sessions.current.mode = AgentMode.AGENT.value
    sessions.save()
  print(f"{CYAN}Plano aprovado → modo agent{RESET}\n")
  return agent.run(
    "Execute o plano aprovado abaixo. Implemente as mudanças necessárias.\n\n"
    f"{last_plan}",
    on_step=_on_step,
  )


def _interactive_loop(
  agent: LaravelAgent,
  tools: ToolRegistry,
  shortcuts: ShortcutRegistry,
  workspace_mgr: WorkspaceManager,
  search_index: SearchIndex,
  sessions: SessionManager,
) -> None:
  while True:
    prompt = (
      f"{BOLD}{AGENT_NAME.lower()}:{workspace_mgr.project_name}"
      f"[{agent.mode.value}]>{RESET} "
    )
    try:
      task = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
      print("\nEncerrando.")
      sessions.save()
      break

    if not task:
      continue
    if task.lower() in {"sair", "exit", "quit", "q"}:
      print("Encerrando.")
      sessions.save()
      break
    if task.lower() == "help":
      _print_help(shortcuts, workspace_mgr)
      continue
    if task.lower() in {"atalhos", "shortcuts"}:
      print(shortcuts.format_help())
      continue
    if task.lower() == "limpar":
      agent.clear_conversation()
      sessions.clear_messages()
      print("Histórico limpo.")
      continue
    if task.lower() in {"projects", "/projects"}:
      print(workspace_mgr.format_project_list())
      continue
    if task.lower() in {"pwd", "/pwd"}:
      print(workspace_mgr.workspace)
      continue
    if task.lower() in {"sessions", "/sessions", "ls"}:
      print(sessions.format_list())
      continue

    if task.lower().startswith("/mode ") or task.lower().startswith("mode "):
      parts = task.split(maxsplit=1)
      if len(parts) < 2:
        print(f"{RED}Uso:{RESET} /mode ask|plan|agent")
        continue
      try:
        mode = AgentMode.parse(parts[1])
      except ValueError as exc:
        print(f"{RED}{exc}{RESET}")
        continue
      print(_set_mode(agent, sessions, mode))
      continue

    if task.lower().startswith("/resume ") or task.lower().startswith("resume "):
      parts = task.split(maxsplit=1)
      if len(parts) < 2:
        print(f"{RED}Uso:{RESET} /resume SESSION_ID")
        continue
      try:
        session = sessions.load(parts[1].strip())
      except FileNotFoundError as exc:
        print(f"{RED}{exc}{RESET}")
        continue
      agent.load_conversation(session.messages)
      try:
        agent.set_mode(AgentMode.parse(session.mode))
      except ValueError:
        agent.set_mode(AgentMode.AGENT)
      print(
        f"{GREEN}Sessão {session.id} retomada{RESET} "
        f"({len(session.messages)} msgs, mode={agent.mode.value})"
      )
      continue

    if task.lower().startswith("/project ") or task.lower().startswith("project "):
      parts = task.split(maxsplit=1)
      if len(parts) < 2:
        print(f"{RED}Uso:{RESET} /project my-app")
        continue
      print(_switch_project(workspace_mgr, tools, agent, search_index, parts[1]))
      if sessions.current is not None:
        sessions.current.project = workspace_mgr.project_name
        sessions.save()
      continue

    executed = _maybe_execute_plan(task, agent, sessions)
    if executed is not None:
      if sessions is not None:
        sessions.append_turn(task, executed)
      print(f"\n{BOLD}{GREEN}Resposta:{RESET}\n{executed}\n")
      continue

    resolved = shortcuts.resolve(task)
    shortcut_name: Optional[str] = None
    raw_args = ""
    if resolved is not None:
      shortcut_name = resolved.shortcut.name
      raw_args = resolved.raw_args
      if resolved.type == "task":
        task = resolved.task or task
        print(f"{DIM}Atalho /{resolved.shortcut.name} → {workspace_mgr.project_name}{RESET}")
      else:
        print(f"{DIM}Atalho /{resolved.shortcut.name} → {workspace_mgr.project_name}{RESET}")
        output = _run_shortcut(resolved, tools)
        if output:
          print(f"\n{output}\n")
        continue

    print(
      f"{DIM}Processando em {workspace_mgr.project_name} [{agent.mode.value}]...{RESET}"
    )
    try:
      result = _run_agent_task(
        agent,
        tools,
        task,
        shortcut_name=shortcut_name,
        raw_args=raw_args,
        workspace_mgr=workspace_mgr,
        search_index=search_index,
        sessions=sessions,
      )
      print(f"\n{BOLD}{GREEN}Resposta:{RESET}\n{result}\n")
    except RuntimeError as exc:
      logger.error("Erro: %s", exc)


def _run_once(
  agent: LaravelAgent,
  tools: ToolRegistry,
  task: str,
  sessions: Optional[SessionManager] = None,
  workspace_mgr: Optional[WorkspaceManager] = None,
  search_index: Optional[SearchIndex] = None,
  shortcut_name: Optional[str] = None,
  raw_args: str = "",
) -> int:
  try:
    result = _run_agent_task(
      agent,
      tools,
      task,
      shortcut_name=shortcut_name,
      raw_args=raw_args,
      workspace_mgr=workspace_mgr,
      search_index=search_index,
      sessions=sessions,
    )
    print(f"\n{BOLD}{GREEN}Resposta:{RESET}\n{result}\n")
    return 0
  except RuntimeError as exc:
    logger.error("Erro: %s", exc)
    return 1


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=f"{AGENT_NAME} — agent CLI Cursor-like para PHP/Laravel (offline).",
  )
  parser.add_argument(
    "-w",
    "--workspace",
    default=None,
    help="Caminho completo do projeto Laravel",
  )
  parser.add_argument(
    "-p",
    "--project",
    default=None,
    help="Nome do projeto em ~/Documentos",
  )
  parser.add_argument(
    "-t",
    "--task",
    default=None,
    help="Tarefa única (sem modo interativo)",
  )
  parser.add_argument(
    "--mode",
    default=None,
    help="Modo: ask | plan | agent (default: agent)",
  )
  parser.add_argument(
    "--force",
    action="store_true",
    help="Pula aprovações de write/shell (headless)",
  )
  parser.add_argument(
    "--continue",
    dest="continue_session",
    action="store_true",
    help="Continua a última sessão do projeto",
  )
  parser.add_argument(
    "--resume",
    default=None,
    help="Retoma sessão pelo ID",
  )
  parser.add_argument(
    "--list-sessions",
    action="store_true",
    help="Lista sessões e sai",
  )
  parser.add_argument(
    "--max-iterations",
    type=int,
    default=None,
    help="Máximo de passos do agente",
  )
  parser.add_argument(
    "--temperature",
    type=float,
    default=None,
    help="Temperatura de geração (0.1–1.0)",
  )
  parser.add_argument(
    "--reindex",
    action="store_true",
    help="Reindexa arquivos do workspace",
  )
  parser.add_argument(
    "--splash",
    action="store_true",
    help="Exibe animação ASCII ao iniciar",
  )
  return parser


def main() -> None:
  args = build_parser().parse_args()
  config = AgentConfig()
  _quiet_boot_logging()

  project_root = Path(__file__).parent
  sessions_path = Path(config.sessions_path)
  if not sessions_path.is_absolute():
    sessions_path = project_root / sessions_path
  sessions = SessionManager(sessions_path)

  if args.list_sessions:
    print(sessions.format_list())
    sys.exit(0)

  try:
    mode = AgentMode.parse(args.mode or config.default_mode)
  except ValueError as exc:
    logger.error("%s", exc)
    sys.exit(1)

  try:
    workspace_mgr, workspace = WorkspaceManager.resolve_startup(
      projects_root=config.projects_root,
      workspace_arg=args.workspace,
      project_arg=args.project,
      default_project=config.default_project or None,
      legacy_workspace=config.workspace,
    )
  except FileNotFoundError as exc:
    logger.error("%s", exc)
    sys.exit(1)

  max_iter = args.max_iterations or config.max_iterations
  temperature = args.temperature if args.temperature is not None else config.temperature

  bench_path: Optional[Path] = None
  if config.bench_jsonl.strip():
    bench_path = Path(config.bench_jsonl.strip())
    if not bench_path.is_absolute():
      bench_path = project_root / bench_path
  metrics = StepMetricsCollector(bench_path)

  try:
    t_boot = time.perf_counter()
    with silenced_output():
      from inference import load_lora_model

      t_model = time.perf_counter()
      model, tokenizer = load_lora_model()
      load_model_s = time.perf_counter() - t_model

      cache = AgentCache(
        redis_url=config.redis_url,
        enabled=config.cache_enabled,
        default_ttl=config.cache_ttl,
      )

      index_path = Path(config.search_index_path)
      if not index_path.is_absolute():
        index_path = project_root / index_path
      priorities_path = project_root / "config" / "search_priorities.json"

      t_index = time.perf_counter()
      search_index = SearchIndex(index_path, priorities_path, cache)
      search_index.load_global()
      search_index.index_workspace(workspace, force=args.reindex)
      search_index.index_reference(project_root, force=args.reindex)
      search_index_s = time.perf_counter() - t_index
    boot_s = time.perf_counter() - t_boot
    lora_ok = (
      Path(project_root) / "outputs_lora" / "adapter_config.json"
    ).is_file()
    metrics.record({
      "kind": "boot",
      "boot_s": round(boot_s, 3),
      "load_model_s": round(load_model_s, 3),
      "search_index_s": round(search_index_s, 3),
      "lora": lora_ok,
      "cache_backend": cache.backend,
      "vram_smi_used_mb": nvidia_smi_used_mb(),
      **torch_vram_mb(),
    })
    print(
      f"{DIM}boot={boot_s:.1f}s model={load_model_s:.1f}s "
      f"index={search_index_s:.1f}s lora={lora_ok} "
      f"cache={cache.backend} "
      f"vram_smi={nvidia_smi_used_mb()}MB{RESET}"
    )
  except (FileNotFoundError, RuntimeError) as exc:
    logger.error("%s", exc)
    sys.exit(1)

  permissions = PermissionManager(
    force=args.force or not config.require_approval,
    enabled=config.require_approval and not args.force,
  )

  tools = ToolRegistry(
    workspace=workspace,
    command_timeout=config.command_timeout,
    search_index=search_index,
    cache=cache,
    projects_root=Path(config.projects_root),
    permissions=permissions,
  )

  shortcuts_path = Path(config.shortcuts_path)
  if not shortcuts_path.is_absolute():
    shortcuts_path = project_root / shortcuts_path
  shortcuts = ShortcutRegistry(shortcuts_path)

  agent = LaravelAgent(
    model=model,
    tokenizer=tokenizer,
    tools=tools,
    max_iterations=max_iter,
    temperature=temperature,
    max_new_tokens=config.max_new_tokens,
    max_new_tokens_tool=config.max_new_tokens_tool,
    max_tool_output_chars=config.max_tool_output_chars,
    max_history_steps=config.history_steps,
    max_conversation_turns=config.conversation_turns,
    one_shot=bool(args.task),
    mode=mode,
    metrics=metrics,
  )

  if args.resume:
    try:
      session = sessions.load(args.resume)
      agent.load_conversation(session.messages)
      agent.set_mode(AgentMode.parse(session.mode, default=mode))
    except (FileNotFoundError, ValueError) as exc:
      logger.error("%s", exc)
      sys.exit(1)
  elif args.continue_session:
    session = sessions.latest(project=workspace_mgr.project_name)
    if session is None:
      session = sessions.create(workspace_mgr.project_name, mode.value)
    else:
      agent.load_conversation(session.messages)
      try:
        agent.set_mode(AgentMode.parse(session.mode, default=mode))
      except ValueError:
        agent.set_mode(mode)
  else:
    session = sessions.create(workspace_mgr.project_name, mode.value)

  if args.task:
    task_shortcut: Optional[str] = None
    task_raw_args = ""
    resolved = shortcuts.resolve(args.task)
    if resolved and resolved.type == "task":
      task_shortcut = resolved.shortcut.name
      task_raw_args = resolved.raw_args
      args.task = resolved.task or args.task
    elif resolved:
      output = _run_shortcut(resolved, tools)
      if output:
        print(output)
      sys.exit(0)
    code = _run_once(
      agent,
      tools,
      args.task,
      sessions=sessions,
      workspace_mgr=workspace_mgr,
      search_index=search_index,
      shortcut_name=task_shortcut,
      raw_args=task_raw_args,
    )
    sessions.save()
    sys.exit(code)

  if args.splash and config.ascii_splash:
    from utils.ascii_anim.splash import play_agent_splash

    play_agent_splash(
      AGENT_NAME,
      width=config.ascii_splash_width,
      height=config.ascii_splash_height,
    )

  _print_banner(workspace_mgr, agent.mode, sessions.current.id if sessions.current else "-")
  _interactive_loop(agent, tools, shortcuts, workspace_mgr, search_index, sessions)


if __name__ == "__main__":
  main()
