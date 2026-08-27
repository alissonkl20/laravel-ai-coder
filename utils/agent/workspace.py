"""Resolução de workspace e projetos em ~/Documentos."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


class WorkspaceManager:
  """Gerencia pasta base (Documentos) e projeto Laravel ativo."""

  def __init__(self, projects_root: Path) -> None:
    self.projects_root = projects_root.expanduser().resolve()
    if not self.projects_root.is_dir():
      raise FileNotFoundError(f"Pasta de projetos não existe: {self.projects_root}")
    self._workspace: Optional[Path] = None

  @property
  def workspace(self) -> Path:
    if self._workspace is None:
      raise RuntimeError("Nenhum projeto selecionado. Use -p my-app ou /project my-app")
    return self._workspace

  @property
  def project_name(self) -> str:
    return self.workspace.name

  def is_laravel_project(self, path: Path) -> bool:
    return (path / "artisan").is_file() or (path / "composer.json").is_file()

  def list_projects(self) -> List[Path]:
    projects: List[Path] = []
    for item in sorted(self.projects_root.iterdir(), key=lambda p: p.name.lower()):
      if not item.is_dir():
        continue
      if item.name.startswith(".") or item.name == "IA-LARAVEL":
        continue
      if self.is_laravel_project(item):
        projects.append(item)
    return projects

  def format_project_list(self) -> str:
    projects = self.list_projects()
    if not projects:
      return f"Nenhum projeto Laravel em {self.projects_root}"
    lines = [f"Projetos em {self.projects_root}:"]
    for p in projects:
      marker = " *" if self._workspace and p.resolve() == self._workspace.resolve() else ""
      lines.append(f"  {p.name}{marker}")
    lines.append("")
    lines.append("Trocar: /project my-app   ou   -p my-app ao iniciar")
    return "\n".join(lines)

  def resolve(self, target: str) -> Path:
    """Resolve nome de projeto, subpath ou caminho absoluto."""
    raw = target.strip()
    if not raw:
      raise ValueError("Nome do projeto vazio.")

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
      resolved = candidate.resolve()
    else:
      resolved = (self.projects_root / raw).resolve()

    if not resolved.is_dir():
      raise FileNotFoundError(f"Projeto não encontrado: {raw} → {resolved}")

    if not str(resolved).startswith(str(self.projects_root)):
      raise ValueError(f"Projeto fora de {self.projects_root}: {resolved}")

    return resolved

  def set_project(self, name: str) -> Path:
    self._workspace = self.resolve(name)
    return self._workspace

  def set_workspace_path(self, path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
      raise FileNotFoundError(f"Workspace inválido: {resolved}")
    self._workspace = resolved
    return resolved

  @staticmethod
  def resolve_startup(
    projects_root: str,
    workspace_arg: Optional[str] = None,
    project_arg: Optional[str] = None,
    default_project: Optional[str] = None,
    legacy_workspace: Optional[str] = None,
  ) -> tuple[WorkspaceManager, Path]:
    """Define workspace inicial a partir de flags CLI e .env."""
    manager = WorkspaceManager(Path(projects_root))

    if workspace_arg:
      path = Path(workspace_arg).expanduser().resolve()
      if not path.is_dir():
        raise FileNotFoundError(f"Workspace inválido: {path}")
      manager.set_workspace_path(path)
      return manager, manager.workspace

    if project_arg:
      manager.set_project(project_arg)
      return manager, manager.workspace

    if default_project:
      manager.set_project(default_project)
      return manager, manager.workspace

    if legacy_workspace:
      legacy = Path(legacy_workspace).expanduser().resolve()
      if legacy.is_dir() and manager.is_laravel_project(legacy):
        manager.set_workspace_path(legacy)
        return manager, manager.workspace
      if legacy.resolve() == manager.projects_root.resolve():
        projects = manager.list_projects()
        if len(projects) == 1:
          manager.set_workspace_path(projects[0])
          return manager, manager.workspace

    projects = manager.list_projects()
    if projects:
      names = ", ".join(p.name for p in projects[:8])
      raise FileNotFoundError(
        f"Selecione um projeto com -p NOME (ex: -p my-app).\n"
        f"Projetos em {manager.projects_root}: {names}"
      )

    raise FileNotFoundError(
      f"Nenhum projeto Laravel em {manager.projects_root}. "
      "Use -w com caminho completo."
    )
