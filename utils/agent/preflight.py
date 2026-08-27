"""Pré-execução determinística: projeto, model, login/auth."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
  from utils.agent.tools import ToolRegistry

_MODEL_INTENT_RE = re.compile(
  r"(?:/model\b|make:model|"
  r"(?:crie|criar|create|gerar)\s+(?:um\s+)?(?:model|modelo)\b|"
  r"\bmodel(?:o)?\s+[A-Z][a-zA-Z0-9_]*)",
  re.IGNORECASE,
)
_MODEL_FQN_RE = re.compile(
  r"App\\+Models\\+([A-Z][a-zA-Z0-9_]*)",
)
_MODEL_NAME_RE = re.compile(
  r"(?:model|modelo)\s+([A-Z][a-zA-Z0-9_]*)",
  re.IGNORECASE,
)
_MIGRATION_PATH_RE = re.compile(
  r"database/migrations/([^\]\s]+\.php)",
  re.IGNORECASE,
)
_LOGIN_INTENT_RE = re.compile(
  r"(?:(?:crie|criar|implemente|gere|gerar|fa[cç]a|adicion[ea]|monte)\s+"
  r"(?:um\s+)?(?:login|auth)\b|"
  r"\blogar\b|\bautenticar\b|\bautenticação\b|"
  r"\bAuthController\b|\bsessão de usu|"
  r"\blogout\b|registrar\s+usu[aá]rio|POST\s+/login)",
  re.IGNORECASE,
)
_LOGIN_NEGATION_RE = re.compile(
  r"(?:n[aã]o\s+(?:crie|criar|gere|gerar|fa[cç]a|fazer|implemente)\s+"
  r"(?:um\s+)?login|"
  r"sem\s+login|don'?t\s+(?:create\s+)?login|not\s+(?:a\s+)?login)",
  re.IGNORECASE,
)
_NOT_LOGIN_RE = re.compile(
  r"form\s*request|storeurl|short.?url|encurtad|fill_migration|"
  r"feature test|php artisan test|authorize\s*=|scaffold_php|"
  r"urlshortener|widget",
  re.IGNORECASE,
)
_IMPLEMENT_VERB_RE = re.compile(
  r"^(implemente|preencha|escreva|otimize|adicione|atualize|corrija)\b",
  re.IGNORECASE,
)
_RESERVED_MODEL_TOKENS = frozenset({
  "Laravel", "Model", "Schema", "Http", "Request", "AuthController",
  "Implemente", "Crie", "Criar", "Escreva", "Preencha", "Adicione",
  "Atualize", "Corrija", "App", "Services", "Controllers", "Api",
  "Form", "Illuminate", "Json", "Blueprint", "Migration", "Tarefa",
  "Finish", "Models", "Namespace", "Otimize", "Use", "Class",
})
_USER_NAME_RE = re.compile(
  r"(?:usu[aá]rio|user|nome)\s+(?:de\s+|com\s+nome\s+)?[`'\"]?([a-zA-Z][a-zA-Z0-9_-]{1,30})[`'\"]?",
  re.IGNORECASE,
)
_PASSWORD_RE = re.compile(
  r"(?:senha|password)\s+(?:de\s+)?[`'\"]?([^\s`'\".]{3,64})[`'\".]?",
  re.IGNORECASE,
)

_NEW_PROJECT_INTENT_RE = re.compile(
  r"(?:novo\s+projeto|projeto\s+novo|projeto\s+do\s+zero|"
  r"laravel\s+new|create-project|/new-project|new-project|"
  r"criar?\s+(?:um\s+)?projeto|crie\s+(?:um\s+)?projeto|iniciar\s+projeto)",
  re.IGNORECASE,
)
_PROJECT_NAME_PATTERNS = (
  re.compile(
    r"chamad[oa]\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]{0,63})[`'\"]?",
    re.IGNORECASE,
  ),
  re.compile(
    r"(?:com\s+nome|nome)\s+[:=]?\s*[`'\"]?"
    r"([a-zA-Z][a-zA-Z0-9_-]{0,63})[`'\"]?",
    re.IGNORECASE,
  ),
  re.compile(
    r"(?:pasta|diret[oó]rio|folder)\s+(?:chamad[oa]\s+)?"
    r"[`'\"]?([a-zA-Z][a-zA-Z0-9_-]{0,63})[`'\"]?",
    re.IGNORECASE,
  ),
  re.compile(
    r"(?:laravel\s+new|/new-project|new-project)\s+"
    r"([a-zA-Z][a-zA-Z0-9_-]{0,63})",
    re.IGNORECASE,
  ),
  re.compile(
    r"projeto\s+[`'\"]?([a-zA-Z][a-zA-Z0-9_-]{0,63})[`'\"]?",
    re.IGNORECASE,
  ),
)
_RESERVED_PROJECT_TOKENS = frozenset({
  "laravel", "projeto", "project", "pasta", "documents", "documentos",
  "default", "zero", "novo", "new", "app", "sqlite", "mysql", "do", "da",
  "de", "em", "na", "no", "uma", "um", "nela", "nele", "chamado", "chamada",
  "login", "crud", "auth",
})


@dataclass
class PreflightResult:
  handled: bool
  user_message: str = ""
  augmented_task: str = ""
  finish: bool = False
  switch_project: Optional[str] = None


def _extract_model_name(task: str, raw_args: str = "") -> Optional[str]:
  combined = f"{task} {raw_args}".strip()
  fqn = _MODEL_FQN_RE.search(combined)
  if fqn:
    return fqn.group(1)
  match = _MODEL_NAME_RE.search(combined)
  if match:
    token = match.group(1)
    if token not in _RESERVED_MODEL_TOKENS:
      return token
  for token in re.findall(r"\b([A-Z][a-zA-Z0-9_]*)\b", combined):
    if token not in _RESERVED_MODEL_TOKENS:
      return token
  parts = raw_args.strip().split()
  if parts and re.match(r"^[A-Z][a-zA-Z0-9_]*$", parts[0]):
    if parts[0] not in _RESERVED_MODEL_TOKENS:
      return parts[0]
  return None


def _is_new_project_task(task: str, shortcut_name: Optional[str] = None) -> bool:
  if shortcut_name in {"new-project", "laravel-new"}:
    return True
  return bool(_NEW_PROJECT_INTENT_RE.search(task))


def _is_model_task(task: str, shortcut_name: Optional[str] = None) -> bool:
  if shortcut_name == "model":
    return True
  if _is_new_project_task(task, shortcut_name) or _is_login_task(task):
    return False
  if _IMPLEMENT_VERB_RE.search(task.strip()):
    if not re.search(
      r"make:model|(?:crie|criar|create|gerar)\s+(?:um\s+)?(?:model|modelo)\b",
      task,
      re.IGNORECASE,
    ):
      return False
  return bool(_MODEL_INTENT_RE.search(task))


def _is_login_task(task: str) -> bool:
  if _LOGIN_NEGATION_RE.search(task) or _NOT_LOGIN_RE.search(task):
    return False
  return bool(_LOGIN_INTENT_RE.search(task))


def _extract_project_name(task: str, raw_args: str = "") -> Optional[str]:
  if raw_args.strip():
    candidate = raw_args.strip().split()[0].strip("`/'\"")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$", candidate):
      if candidate.lower() not in _RESERVED_PROJECT_TOKENS:
        return candidate
  combined = f"{task} {raw_args}".strip()
  for pattern in _PROJECT_NAME_PATTERNS:
    match = pattern.search(combined)
    if not match:
      continue
    name = match.group(1)
    if name.lower() in _RESERVED_PROJECT_TOKENS:
      continue
    return name
  return None


def _extract_login_credentials(task: str) -> tuple[str, str, str]:
  name_match = _USER_NAME_RE.search(task)
  pass_match = _PASSWORD_RE.search(task)
  name = name_match.group(1).capitalize() if name_match else "Lucas"
  password = pass_match.group(1) if pass_match else "mod123"
  email = f"{name.lower()}@example.com"
  return name, email, password


def _migration_for_model(workspace: Path, name: str) -> Optional[Path]:
  migrations = workspace / "database" / "migrations"
  if not migrations.is_dir():
    return None
  snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
  patterns = (f"*_{snake}_table.php", f"*_{snake}s_table.php", f"*_{name.lower()}_table.php")
  matches: list[Path] = []
  for pattern in patterns:
    matches.extend(migrations.glob(pattern))
  if not matches:
    return None
  return max(matches, key=lambda p: p.stat().st_mtime)


def _auth_controller_content() -> str:
  return '''<?php

declare(strict_types=1);

namespace App\\Http\\Controllers;

use App\\Models\\User;
use Illuminate\\Http\\JsonResponse;
use Illuminate\\Http\\Request;
use Illuminate\\Support\\Facades\\Auth;
use Illuminate\\Support\\Facades\\Hash;
use Illuminate\\Validation\\ValidationException;

class AuthController extends Controller
{
    public function login(Request $request): JsonResponse
    {
        $credentials = $request->validate([
            'email' => ['required', 'email'],
            'password' => ['required', 'string'],
        ]);

        if (! Auth::attempt($credentials)) {
            throw ValidationException::withMessages([
                'email' => ['Credenciais inválidas.'],
            ]);
        }

        return response()->json([
            'message' => 'Login realizado.',
            'user' => Auth::user(),
        ]);
    }

    public function logout(Request $request): JsonResponse
    {
        Auth::logout();

        return response()->json(['message' => 'Logout realizado.']);
    }

    public function register(Request $request): JsonResponse
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'max:255', 'unique:users,email'],
            'password' => ['required', 'string', 'min:6'],
        ]);

        $user = User::create([
            'name' => $data['name'],
            'email' => $data['email'],
            'password' => Hash::make($data['password']),
        ]);

        return response()->json(['user' => $user], 201);
    }
}
'''


def _api_routes_content() -> str:
  return '''<?php

use App\\Http\\Controllers\\AuthController;
use Illuminate\\Support\\Facades\\Route;

Route::post('/login', [AuthController::class, 'login']);
Route::post('/logout', [AuthController::class, 'logout']);
Route::post('/register', [AuthController::class, 'register']);
'''


def _database_seeder_content(name: str, email: str, password: str) -> str:
  return f'''<?php

namespace Database\\Seeders;

use App\\Models\\User;
use Illuminate\\Database\\Seeder;
use Illuminate\\Support\\Facades\\Hash;

class DatabaseSeeder extends Seeder
{{
    public function run(): void
    {{
        User::updateOrCreate(
            ['email' => '{email}'],
            ['name' => '{name}', 'password' => Hash::make('{password}')]
        );
    }}
}}
'''


def _ensure_api_routing(workspace: Path, tools: "ToolRegistry", log: list[str]) -> None:
  bootstrap = workspace / "bootstrap" / "app.php"
  if not bootstrap.is_file():
    return
  text = bootstrap.read_text(encoding="utf-8")
  if "routes/api.php" in text:
    return
  marker = "web: __DIR__.'/../routes/web.php',"
  if marker not in text:
    return
  updated = text.replace(
    marker,
    marker + "\n        api: __DIR__.'/../routes/api.php',",
    1,
  )
  tools.run("write_file", {"path": "bootstrap/app.php", "content": updated})
  log.append("bootstrap/app.php: rotas API registradas")


def try_create_project(
  task: str,
  tools: "ToolRegistry",
  shortcut_name: Optional[str] = None,
  raw_args: str = "",
) -> PreflightResult:
  if not _is_new_project_task(task, shortcut_name):
    return PreflightResult(handled=False)

  name = _extract_project_name(task, raw_args)
  if not name:
    return PreflightResult(
      handled=True,
      finish=True,
      user_message=(
        "Para criar um projeto Laravel, informe o nome da pasta.\n"
        "Ex.: /new-project login-app   ou   crie um projeto chamado login-app"
      ),
    )

  result = tools.create_laravel_project(name)
  if not result.success:
    return PreflightResult(
      handled=True,
      finish=True,
      user_message=f"Falha ao criar projeto '{name}':\n{result.output}",
    )

  also_login = _is_login_task(task)
  return PreflightResult(
    handled=True,
    finish=not also_login,
    switch_project=name,
    user_message=(
      f"Projeto Laravel '{name}' pronto em {tools.projects_root / name}\n"
      f"{result.output[-1200:]}"
    ),
  )


def try_scaffold_login(
  task: str,
  tools: "ToolRegistry",
) -> PreflightResult:
  """Monta login (AuthController, rotas, seeder) de forma determinística."""
  if not _is_login_task(task):
    return PreflightResult(handled=False)

  workspace = tools.workspace
  if not (workspace / "artisan").is_file():
    return PreflightResult(
      handled=True,
      finish=True,
      user_message="Login requer projeto Laravel (artisan não encontrado no workspace).",
    )

  name, email, password = _extract_login_credentials(task)
  log: list[str] = []

  ctrl_path = workspace / "app/Http/Controllers/AuthController.php"
  if not ctrl_path.is_file():
    mk = tools.run_command("php artisan make:controller AuthController")
    log.append(mk.output)

  wr = tools.run("write_file", {
    "path": "app/Http/Controllers/AuthController.php",
    "content": _auth_controller_content(),
  })
  log.append(wr.output)

  _ensure_login_api_routes(workspace, tools, log)
  _ensure_api_routing(workspace, tools, log)

  tools.run("write_file", {
    "path": "database/seeders/DatabaseSeeder.php",
    "content": _database_seeder_content(name, email, password),
  })
  log.append(f"Seeder: usuário {name} ({email})")

  mig = tools.run_command("php artisan migrate --force")
  log.append(mig.output)
  seed = tools.run_command("php artisan db:seed --force")
  log.append(seed.output)

  routes = tools.run_command("php artisan route:list --path=api")
  log.append(routes.output[-800:])

  summary = (
    f"Login CRUD pronto em {workspace.name}:\n"
    f"- AuthController (login, logout, register)\n"
    f"- routes/api.php: POST /api/login, /api/logout, /api/register\n"
    f"- Usuário seed: {name} | email: {email} | senha: {password}\n"
    f"- Model User (padrão Laravel)\n\n"
    + "\n".join(log[-6:])
  )
  return PreflightResult(handled=True, finish=True, user_message=summary)


def _ensure_login_api_routes(workspace: Path, tools: "ToolRegistry", log: list[str]) -> None:
  routes_path = workspace / "routes/api.php"
  if not routes_path.is_file():
    tools.run("write_file", {"path": "routes/api.php", "content": _api_routes_content()})
    log.append("routes/api.php criado")
    return
  text = routes_path.read_text(encoding="utf-8")
  if "AuthController" in text and "/login" in text:
    log.append("rotas login já existem")
    return
  extra = []
  if "AuthController" not in text:
    extra.append("use App\\Http\\Controllers\\AuthController;")
  extra.append("Route::post('/login', [AuthController::class, 'login']);")
  extra.append("Route::post('/logout', [AuthController::class, 'logout']);")
  extra.append("Route::post('/register', [AuthController::class, 'register']);")
  if not text.endswith("\n"):
    text += "\n"
  tools.run("write_file", {"path": "routes/api.php", "content": text + "\n".join(extra) + "\n"})
  log.append("rotas login anexadas em routes/api.php")


def try_scaffold_model(
  task: str,
  tools: "ToolRegistry",
  shortcut_name: Optional[str] = None,
  raw_args: str = "",
) -> PreflightResult:
  if not _is_model_task(task, shortcut_name):
    return PreflightResult(handled=False)

  model_name = _extract_model_name(task, raw_args)
  if not model_name:
    return PreflightResult(handled=False)

  workspace = tools.workspace
  model_rel = f"app/Models/{model_name}.php"
  model_path = workspace / model_rel
  scaffold_output: list[str] = []

  if model_path.is_file():
    scaffold_output.append(f"Model já existe: {model_rel}")
  else:
    result = tools.run_command(f"php artisan make:model {model_name} -m")
    scaffold_output.append(result.output)
    if not result.success:
      return PreflightResult(
        handled=True,
        user_message=f"Falha ao gerar model {model_name}:\n{result.output}",
        augmented_task=task,
      )

  migration_rel: Optional[str] = None
  migration_match = _MIGRATION_PATH_RE.search("\n".join(scaffold_output))
  if migration_match:
    migration_rel = f"database/migrations/{migration_match.group(1)}"
  else:
    migration_file = _migration_for_model(workspace, model_name)
    if migration_file:
      migration_rel = str(migration_file.relative_to(workspace))

  files_hint = f"- {model_rel}"
  if migration_rel:
    files_hint += f"\n- {migration_rel}"

  augmented = (
    f"Arquivos do model {model_name} (já gerados pelo artisan):\n{files_hint}\n\n"
    f"Tarefa: {task}\n\n"
    "Use read_file nos arquivos acima, scaffold_php ou replace_in_file para editar, action=finish ao concluir.\n"
    'Formato: {"action":"tool","tool":"scaffold_php","args":{"kind":"model","name":"' + model_name + '"}} '
  )
  return PreflightResult(
    handled=True,
    user_message=f"Scaffold: model {model_name}\n" + "\n".join(scaffold_output[-3:]),
    augmented_task=augmented,
  )


def _switch_tools_workspace(tools: "ToolRegistry", project_name: str) -> None:
  target = tools.projects_root / project_name
  if target.is_dir():
    tools.set_workspace(target)


def run_preflight(
  task: str,
  tools: "ToolRegistry",
  shortcut_name: Optional[str] = None,
  raw_args: str = "",
) -> PreflightResult:
  created = try_create_project(task, tools, shortcut_name=shortcut_name, raw_args=raw_args)
  if created.handled and created.switch_project:
    _switch_tools_workspace(tools, created.switch_project)

  if created.handled and created.finish:
    return created

  login = try_scaffold_login(task, tools)
  if login.handled:
    if created.handled and created.user_message:
      login.user_message = created.user_message + "\n\n" + login.user_message
    return login

  if created.handled:
    return created

  return try_scaffold_model(task, tools, shortcut_name=shortcut_name, raw_args=raw_args)
