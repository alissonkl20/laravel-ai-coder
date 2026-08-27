"""Ferramentas executáveis pelo agente CLI."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING

from utils.agent.scaffold import apply_scaffold, join_lines

if TYPE_CHECKING:
  from utils.agent.permissions import PermissionManager
  from utils.agent.search_index import SearchIndex

ALL_TOOL_NAMES = (
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
)


@dataclass
class ToolResult:
  """Resultado padronizado de uma ferramenta."""

  success: bool
  output: str


class ToolRegistry:
  """Registro e execução segura de ferramentas do agente."""

    ARTISAN_STANDALONE = frozenset({
    "migrate",
    "migrate:fresh",
    "migrate:rollback",
    "migrate:status",
    "db:seed",
    "route:list",
    "config:clear",
    "cache:clear",
    "optimize:clear",
  })

  HANG_TOKENS = (
    "tinker",
    "serve",
    "queue:work",
    "queue:listen",
    "horizon",
    "reverb:start",
    "pail",
  )

  BLOCKED_PATTERNS = (
    "rm ",
    "sudo",
    "curl",
    "wget",
    "chmod",
    "chown",
    "> /",
    "| sh",
    "&& rm",
    "mkfs",
    "dd ",
  )

  ALLOWED_COMMAND_PREFIXES = (
    "php",
    "composer",
    "laravel",
    "grep",
    "find",
    "ls",
    "mkdir",
    "cat",
    "head",
    "tail",
    "pwd",
    "test",
    "which",
    "env",
    "tree",
  )

  PROJECT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

  def __init__(
    self,
    workspace: Path,
    command_timeout: int = 60,
    search_index: Optional["SearchIndex"] = None,
    cache: Optional[Any] = None,
    projects_root: Optional[Path] = None,
    create_project_timeout: int = 600,
    permissions: Optional["PermissionManager"] = None,
    allowed_tools: Optional[Set[str]] = None,
  ) -> None:
    self.command_timeout = command_timeout
    self.create_project_timeout = create_project_timeout
    self.search_index = search_index
    self.cache = cache
    self.permissions = permissions
    self.allowed_tools = allowed_tools
    root = projects_root or workspace.parent
    self.projects_root = root.expanduser().resolve()
    self.set_workspace(workspace)
    self._tools: Dict[str, Callable[..., ToolResult]] = {
      "read_file": self.read_file,
      "write_file": self.write_file,
      "replace_in_file": self.replace_in_file,
      "insert_lines": self.insert_lines,
      "scaffold_php": self.scaffold_php,
      "mkdir": self.mkdir,
      "list_dir": self.list_dir,
      "grep": self.grep,
      "run_command": self.run_command,
      "tail_log": self.tail_log,
      "search": self.search,
      "create_laravel_project": self.create_laravel_project,
    }

  def set_allowed_tools(self, allowed: Optional[Set[str]]) -> None:
    self.allowed_tools = allowed

  def set_permissions(self, permissions: Optional["PermissionManager"]) -> None:
    self.permissions = permissions

  def set_workspace(self, workspace: Path) -> None:
    """Atualiza o projeto ativo (ex.: após /project my-app)."""
    self.workspace = workspace.resolve()
    self._file_index_key = f"file_index:{self.workspace}"

  def describe_tools(self) -> str:
    """Retorna descrição das ferramentas para o prompt (respeita modo)."""
    catalog = {
      "read_file": "read_file(path,start_line?,end_line?)",
      "write_file": "write_file(path,lines=[...]) arquivo NOVO; lines=array de strings",
      "replace_in_file": "replace_in_file(path,old_text,new_text) trecho único curto",
      "insert_lines": "insert_lines(path,after,lines) insere após trecho único",
      "scaffold_php": "scaffold_php(kind,name,...) gera PHP Laravel válido. kinds: model,fill_migration,form_request,service,api_controller,feature_test,ensure_api,add_route",
      "mkdir": "mkdir(path)",
      "list_dir": "list_dir(path) path relativo ex. app/Http/Controllers",
      "grep": "grep(pattern,path?)",
      "run_command": "run_command(command) php artisan ...",
      "tail_log": "tail_log(lines?)",
      "search": "search(query)",
      "create_laravel_project": "create_laravel_project(name,database?)",
    }
    names = self.allowed_tools or set(catalog.keys())
    return " | ".join(catalog[n] for n in catalog if n in names)

  def run(self, name: str, args: Dict[str, Any]) -> ToolResult:
    """Executa ferramenta por nome (modo + permissões)."""
    if self.allowed_tools is not None and name not in self.allowed_tools:
      return ToolResult(
        False,
        f"Ferramenta '{name}' bloqueada neste modo. "
        f"Permitidas: {', '.join(sorted(self.allowed_tools))}",
      )
    if name not in self._tools:
      return ToolResult(False, f"Ferramenta desconhecida: {name}")

    args = self._normalize_args(name, args)
    if self.permissions is not None:
      denied = self.permissions.allow_tool(name, args, self.workspace)
      if denied is not None:
        return denied

    try:
      return self._tools[name](**args)
    except TypeError as exc:
      return ToolResult(False, f"Argumentos inválidos para {name}: {exc}")
    except Exception as exc:
      return ToolResult(False, f"Erro em {name}: {exc}")

  def _resolve_path(self, path: str) -> Path:
    """Resolve path relativo ao workspace; bloqueia escape."""
    candidate = Path(path)
    if not candidate.is_absolute():
      candidate = self.workspace / candidate
    resolved = candidate.resolve()
    if not str(resolved).startswith(str(self.workspace)):
      raise ValueError(f"Path fora do workspace: {path}")
    return resolved

  def read_file(
    self,
    path: str = "",
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
  ) -> ToolResult:
    if not str(path).strip():
      return ToolResult(False, "path obrigatório (ex: routes/web.php)")
    file_path = self._resolve_path(path)
    if file_path.is_dir():
      return ToolResult(
        False,
        f"{path} é um diretório. Use list_dir('{path}') ou leia um arquivo "
        f"(ex: {path.rstrip('/')}/Nome.php).",
      )
    if not file_path.is_file():
      return ToolResult(False, f"Arquivo não encontrado: {path}")

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if start_line is not None or end_line is not None:
      start = max((start_line or 1) - 1, 0)
      end = end_line if end_line is not None else len(lines)
      selected = lines[start:end]
      numbered = [
        f"{start + idx + 1:4d}| {line}" for idx, line in enumerate(selected)
      ]
      return ToolResult(True, "\n".join(numbered))

    numbered = [f"{idx + 1:4d}| {line}" for idx, line in enumerate(lines)]
    return ToolResult(True, "\n".join(numbered))

  def _normalize_args(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name != "write_file":
      return args
    out = dict(args)
    if not str(out.get("content") or "") and out.get("lines") is not None:
      out["content"] = join_lines(out["lines"])
    out.pop("lines", None)
    return out

  def write_file(
    self,
    path: str,
    content: str = "",
    lines: Optional[Any] = None,
    mode: str = "replace",
  ) -> ToolResult:
    file_path = self._resolve_path(path)
    body = join_lines(lines) if lines is not None else str(content or "")
    if not body and lines is None and not content:
      return ToolResult(False, "content ou lines obrigatório")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and file_path.is_file():
      previous = file_path.read_text(encoding="utf-8")
      if previous and not previous.endswith("\n"):
        previous += "\n"
      body = previous + body
    if body and not body.endswith("\n"):
      body += "\n"
    file_path.write_text(body, encoding="utf-8")
    return ToolResult(True, f"Escrito {len(body)} bytes em {path}")

  def insert_lines(self, path: str, after: str, lines: Any) -> ToolResult:
    file_path = self._resolve_path(path)
    if not file_path.is_file():
      return ToolResult(False, f"Arquivo não encontrado: {path}")
    text = file_path.read_text(encoding="utf-8")
    if after not in text:
      return ToolResult(False, "after não encontrado")
    if text.count(after) != 1:
      return ToolResult(False, f"after aparece {text.count(after)} vezes; precisa ser único")
    block = join_lines(lines)
    idx = text.find(after)
    line_end = text.find("\n", idx)
    if line_end < 0:
      line_end = len(text)
      suffix = "\n"
    else:
      suffix = ""
    updated = text[: line_end + 1] + block + "\n" + suffix + text[line_end + 1 :]
    file_path.write_text(updated, encoding="utf-8")
    return ToolResult(True, f"Inserido em {path}")

  def scaffold_php(self, kind: str, name: str = "", **kwargs: Any) -> ToolResult:
    payload = {"kind": kind, "name": name, **kwargs}
    ok, message = apply_scaffold(self.workspace, payload)
    return ToolResult(ok, message)

  def replace_in_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
    file_path = self._resolve_path(path)
    if not file_path.is_file():
      return ToolResult(False, f"Arquivo não encontrado: {path}")
    text = file_path.read_text(encoding="utf-8")
    if old_text not in text:
      return ToolResult(False, "old_text não encontrado")
    count = text.count(old_text)
    if count != 1:
      return ToolResult(False, f"old_text aparece {count} vezes; precisa ser único")
    file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return ToolResult(True, f"Substituído em {path}")

  def mkdir(self, path: str) -> ToolResult:
    dir_path = self._resolve_path(path or ".")
    if dir_path.exists() and not dir_path.is_dir():
      return ToolResult(False, f"Já existe como arquivo: {path}")
    dir_path.mkdir(parents=True, exist_ok=True)
    return ToolResult(True, f"Diretório criado: {dir_path.relative_to(self.workspace)}")

  def list_dir(self, path: str = ".") -> ToolResult:
    dir_path = self._resolve_path(path)
    if not dir_path.is_dir():
      return ToolResult(False, f"Diretório não encontrado: {path}")

    entries: List[str] = []
    for item in sorted(dir_path.iterdir(), key=lambda p: p.name):
      suffix = "/" if item.is_dir() else ""
      entries.append(f"{item.name}{suffix}")
    return ToolResult(True, "\n".join(entries) if entries else "(vazio)")

  def grep(self, pattern: str, path: str = ".") -> ToolResult:
    target = self._resolve_path(path)
    regex = re.compile(pattern)
    matches: List[str] = []
    files = self._list_searchable_files(target)

    for file_path in files:
      try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
      except OSError:
        continue
      rel = file_path.relative_to(self.workspace)
      for line_no, line in enumerate(text.splitlines(), start=1):
        if regex.search(line):
          matches.append(f"{rel}:{line_no}: {line.strip()}")
      if len(matches) >= 200:
        break

    if not matches:
      return ToolResult(True, "Nenhuma correspondência.")
    return ToolResult(True, "\n".join(matches[:200]))

  def _list_searchable_files(self, target: Path) -> List[Path]:
    if target.is_file():
      return [target]

    if self.cache is not None:
      cached = self.cache.get("grep_files", self._file_index_key)
      if cached is not None:
        return [Path(p) for p in cached if Path(p).is_file()]

    files = [
      p
      for p in target.rglob("*")
      if p.is_file() and ".git" not in p.parts and "vendor" not in p.parts
    ]

    if self.cache is not None:
      self.cache.set(
        "grep_files",
        self._file_index_key,
        [str(p) for p in files],
        ttl=300,
      )
    return files

  def search(self, query: str, limit: int = 10) -> ToolResult:
    if self.search_index is None:
      return ToolResult(False, "Índice de busca não configurado. Rode build_search_index.py")
    hits = self.search_index.search(query, limit=limit)
    return ToolResult(True, self.search_index.format_results(hits))

  def _normalize_command(self, command: str) -> str:
    """Converte atalhos artisan (make:model, migrate, artisan ...) em php artisan."""
    stripped = command.strip()
    if not stripped:
      return stripped

    lower = stripped.lower()
    if lower.startswith("artisan ") or lower == "artisan":
      rest = stripped[7:].strip() if lower.startswith("artisan ") else ""
      return f"php artisan {rest}".strip()

    first_token = lower.split()[0]
    if ":" in first_token or first_token in self.ARTISAN_STANDALONE:
      return f"php artisan {stripped}"

    return stripped

  def _is_command_allowed(self, command: str) -> bool:
    stripped = command.strip().lower()
    for blocked in self.BLOCKED_PATTERNS:
      if blocked in stripped:
        return False
    first_token = stripped.split()[0] if stripped else ""
    return any(
      first_token == prefix or first_token.endswith(f"/{prefix}")
      for prefix in self.ALLOWED_COMMAND_PREFIXES
    )

  def run_command(self, command: str) -> ToolResult:
    if not command.strip():
      return ToolResult(False, "Comando vazio.")

    normalized = self._normalize_command(command)
    if not self._is_command_allowed(normalized):
      return ToolResult(
        False,
        "Comando bloqueado. Use: php artisan make:model, php artisan migrate, "
        "composer, grep, ls, etc.",
      )
    lower = normalized.lower()
    if any(token in lower for token in self.HANG_TOKENS):
      return ToolResult(
        False,
        "Comando interativo/longo bloqueado (serve/tinker/queue). "
        "No loop do agent use migrate, test, route:list, make:*.",
      )

    timeout = self.command_timeout
    if "artisan test" in lower or "phpunit" in lower:
      timeout = max(timeout, 180)

    try:
      completed = subprocess.run(
        normalized,
        shell=True,
        cwd=self.workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
      )
      output_parts = []
      if completed.stdout:
        output_parts.append(completed.stdout)
      if completed.stderr:
        output_parts.append(f"[stderr]\n{completed.stderr}")
      output = "\n".join(output_parts).strip() or "(sem saída)"
      if normalized != command.strip():
        output = f"[normalizado: {normalized}]\n{output}"
      if completed.returncode != 0:
        output = f"[exit {completed.returncode}]\n{output}"
      return ToolResult(completed.returncode == 0, output[:8000])
    except subprocess.TimeoutExpired:
      return ToolResult(False, f"Timeout após {timeout}s")

  def tail_log(self, lines: int = 80) -> ToolResult:
    log_path = self.workspace / "storage" / "logs" / "laravel.log"
    if not log_path.is_file():
      return ToolResult(False, "laravel.log não encontrado em storage/logs/")
    all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = all_lines[-max(lines, 1):]
    return ToolResult(True, "\n".join(tail))

  def create_laravel_project(
    self,
    name: str,
    database: str = "sqlite",
  ) -> ToolResult:
    """Cria um projeto Laravel novo em projects_root/<name> via laravel new."""
    project_name = (name or "").strip().strip("/").split("/")[-1]
    if not self.PROJECT_NAME_RE.match(project_name):
      return ToolResult(
        False,
        "Nome inválido. Use letras/números/_/- (ex: ruff, my-app).",
      )

    target = (self.projects_root / project_name).resolve()
    if not str(target).startswith(str(self.projects_root)):
      return ToolResult(False, f"Destino fora de {self.projects_root}")

    if target.exists() and any(target.iterdir()):
      if (target / "artisan").is_file():
        return ToolResult(
          True,
          f"Projeto já existe: {target}\nUse /project {project_name} para ativar.",
        )
      return ToolResult(
        False,
        f"Pasta {target} já existe e não está vazia. Escolha outro nome.",
      )

    db = (database or "sqlite").strip().lower()
    if db not in {"sqlite", "mysql", "mariadb", "pgsql", "sqlsrv"}:
      db = "sqlite"

    cmd = (
      f"laravel new {project_name} --no-interaction "
      f"--database={db} --phpunit --no-node --no-boost --no-authentication"
    )

    try:
      completed = subprocess.run(
        cmd,
        shell=True,
        cwd=self.projects_root,
        capture_output=True,
        text=True,
        timeout=self.create_project_timeout,
      )
    except subprocess.TimeoutExpired:
      return ToolResult(
        False,
        f"Timeout após {self.create_project_timeout}s ao criar {project_name}.",
      )
    except FileNotFoundError:
      return ToolResult(
        False,
        "Comando 'laravel' não encontrado. Instale: composer global require laravel/installer",
      )

    parts: List[str] = [f"[cmd] {cmd}", f"[cwd] {self.projects_root}"]
    if completed.stdout:
      parts.append(completed.stdout.strip())
    if completed.stderr:
      parts.append(f"[stderr]\n{completed.stderr.strip()}")

    if completed.returncode != 0:
      parts.insert(0, f"[exit {completed.returncode}]")
      return ToolResult(False, "\n".join(parts)[:8000])

    if not (target / "artisan").is_file():
      return ToolResult(
        False,
        "laravel new terminou sem criar artisan.\n" + "\n".join(parts)[:4000],
      )

    parts.append(f"OK: projeto criado em {target}")
    parts.append(f"Ative com: /project {project_name}")
    return ToolResult(True, "\n".join(parts)[:8000])
