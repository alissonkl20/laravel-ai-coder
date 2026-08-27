"""Sessões persistentes do agent CLI (histórico multi-turn)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Session:
  """Conversa persistida em disco."""

  id: str
  project: str
  mode: str
  created_at: str
  updated_at: str
  messages: List[Dict[str, str]] = field(default_factory=list)
  meta: Dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> Dict[str, Any]:
    return {
      "id": self.id,
      "project": self.project,
      "mode": self.mode,
      "created_at": self.created_at,
      "updated_at": self.updated_at,
      "messages": self.messages,
      "meta": self.meta,
    }

  @classmethod
  def from_dict(cls, data: Dict[str, Any]) -> "Session":
    return cls(
      id=str(data["id"]),
      project=str(data.get("project", "")),
      mode=str(data.get("mode", "agent")),
      created_at=str(data.get("created_at", _utc_now())),
      updated_at=str(data.get("updated_at", _utc_now())),
      messages=list(data.get("messages") or []),
      meta=dict(data.get("meta") or {}),
    )


class SessionManager:
  """CRUD de sessões em data/sessions/*.json."""

  def __init__(self, root: Path) -> None:
    self.root = root.expanduser().resolve()
    self.root.mkdir(parents=True, exist_ok=True)
    self.current: Optional[Session] = None

  def _path(self, session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return self.root / f"{safe}.json"

  def create(self, project: str, mode: str = "agent") -> Session:
    now = _utc_now()
    session = Session(
      id=uuid.uuid4().hex[:12],
      project=project,
      mode=mode,
      created_at=now,
      updated_at=now,
    )
    self.current = session
    self.save(session)
    return session

  def save(self, session: Optional[Session] = None) -> None:
    session = session or self.current
    if session is None:
      return
    session.updated_at = _utc_now()
    path = self._path(session.id)
    path.write_text(
      json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
      encoding="utf-8",
    )

  def load(self, session_id: str) -> Session:
    path = self._path(session_id)
    if not path.is_file():
      raise FileNotFoundError(f"Sessão não encontrada: {session_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    session = Session.from_dict(data)
    self.current = session
    return session

  def latest(self, project: Optional[str] = None) -> Optional[Session]:
    sessions = self.list_sessions(project=project)
    if not sessions:
      return None
    return self.load(sessions[0]["id"])

  def list_sessions(self, project: Optional[str] = None, limit: int = 20) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
      try:
        data = json.loads(path.read_text(encoding="utf-8"))
      except (OSError, json.JSONDecodeError):
        continue
      if project and data.get("project") != project:
        continue
      preview = ""
      messages = data.get("messages") or []
      if messages:
        preview = str(messages[-1].get("content", ""))[:80].replace("\n", " ")
      rows.append({
        "id": str(data.get("id", path.stem)),
        "project": str(data.get("project", "")),
        "mode": str(data.get("mode", "agent")),
        "updated_at": str(data.get("updated_at", "")),
        "turns": str(len(messages)),
        "preview": preview,
      })
      if len(rows) >= limit:
        break
    return rows

  def format_list(self, project: Optional[str] = None) -> str:
    rows = self.list_sessions(project=project)
    if not rows:
      return "Nenhuma sessão salva."
    lines = ["Sessões:"]
    for row in rows:
      marker = " *" if self.current and row["id"] == self.current.id else ""
      lines.append(
        f"  {row['id']}{marker}  {row['project']:<20}  mode={row['mode']:<5}  "
        f"{row['updated_at']}  ({row['turns']} msgs)"
      )
      if row["preview"]:
        lines.append(f"      {row['preview']}")
    lines.append("")
    lines.append("Retomar: /resume ID   ou   --continue")
    return "\n".join(lines)

  def append_turn(self, user: str, assistant: str) -> None:
    if self.current is None:
      return
    self.current.messages.append({"role": "user", "content": user})
    self.current.messages.append({"role": "assistant", "content": assistant})
    # Mantém contexto utilizável na VRAM (últimos N pares)
    max_msgs = 24
    if len(self.current.messages) > max_msgs:
      self.current.messages = self.current.messages[-max_msgs:]
    self.save()

  def clear_messages(self) -> None:
    if self.current is None:
      return
    self.current.messages = []
    self.save()
