"""Controle de terminal ANSI para animação ASCII."""

from __future__ import annotations

import atexit
import os
import shutil
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

CSI = "\033["

HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
ALT_SCREEN_ON = CSI + "?1049h"
ALT_SCREEN_OFF = CSI + "?1049l"
HOME = CSI + "H"
CLEAR_DOWN = CSI + "J"
RESET = CSI + "0m"

MIN_COLS = 40
MIN_ROWS = 12
MAX_COLS = 200
MAX_ROWS = 60
CHAR_ASPECT = 0.5  # altura/largura efetiva do caractere no terminal


@dataclass(frozen=True)
class TerminalSize:
  cols: int
  rows: int


def supports_truecolor() -> bool:
  if os.environ.get("NO_COLOR"):
    return False
  colorterm = os.environ.get("COLORTERM", "").lower()
  if colorterm in {"truecolor", "24bit"}:
    return True
  term_program = os.environ.get("TERM_PROGRAM", "").lower()
  return term_program in {"iterm.app", "vscode", "cursor", "apple_terminal"}


def get_terminal_size(
  cols: Optional[int] = None,
  rows: Optional[int] = None,
) -> TerminalSize:
  if cols is not None and rows is not None:
    return TerminalSize(
      cols=max(MIN_COLS, min(cols, MAX_COLS)),
      rows=max(MIN_ROWS, min(rows, MAX_ROWS)),
    )

  size = shutil.get_terminal_size(fallback=(80, 24))
  return TerminalSize(
    cols=max(MIN_COLS, min(size.columns, MAX_COLS)),
    rows=max(MIN_ROWS, min(size.lines - 1, MAX_ROWS)),
  )


class TerminalSession:
  """Gerencia cursor, tela alternativa e restauração ao sair."""

  def __init__(self) -> None:
    self._active = False
    self._registered = False

  def enter(self) -> None:
    if self._active:
      return
    sys.stdout.write(ALT_SCREEN_ON + HIDE_CURSOR + HOME + CLEAR_DOWN)
    sys.stdout.flush()
    self._active = True
    if not self._registered:
      atexit.register(self.restore)
      self._registered = True

  def restore(self) -> None:
    if not self._active:
      return
    sys.stdout.write(SHOW_CURSOR + ALT_SCREEN_OFF + RESET)
    sys.stdout.flush()
    self._active = False

  def draw_frame(self, content: str) -> None:
    sys.stdout.write(HOME + content)
    if not content.endswith("\n"):
      sys.stdout.write("\n")
    sys.stdout.flush()


@contextmanager
def terminal_session() -> Iterator[TerminalSession]:
  session = TerminalSession()
  try:
    session.enter()
    yield session
  finally:
    session.restore()
