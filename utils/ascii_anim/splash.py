"""Splash ASCII compacto para o terminal do agente DRAXY."""

from __future__ import annotations

import re
import sys
import time
from functools import lru_cache
from typing import List, Optional

from utils.ascii_anim.converter import RenderConfig, build_frame_cache
from utils.ascii_anim.loader import default_gif_path, load_gif_frames
from utils.ascii_anim.terminal import HIDE_CURSOR, RESET, SHOW_CURSOR, TerminalSize

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

# Esfera pequena — cabe acima do prompt do agente
DEFAULT_WIDTH = 44
DEFAULT_HEIGHT = 10
DEFAULT_FPS = 18.0
DEFAULT_FRAME_SKIP = 8
DEFAULT_MAX_FRAMES = 28
DEFAULT_DURATION_SEC = 2.0

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"


def _visible_len(text: str) -> int:
  return len(_ANSI_RE.sub("", text))


def _center(text: str, width: int) -> str:
  pad = max(0, (width - _visible_len(text)) // 2)
  return f"{' ' * pad}{text}"


def _center_block(lines: List[str], term_width: int) -> List[str]:
  return [_center(line, term_width) for line in lines]


def _frame_lines(frame: str) -> List[str]:
  return frame.split("\n")


@lru_cache(maxsize=4)
def _load_splash_cache(width: int, height: int, frame_skip: int, max_frames: int) -> tuple[str, ...]:
  source_frames, _ = load_gif_frames(default_gif_path())
  sampled = source_frames[::frame_skip][:max_frames]
  if not sampled:
    return ()

  size = TerminalSize(cols=width, rows=height)
  config = RenderConfig(threshold=10, particle_density=0.92)
  cache = build_frame_cache(sampled, size, config)
  return tuple(cache.frames)


def _draw_block(lines: List[str], move_up: int = 0) -> None:
  if move_up > 0:
    sys.stdout.write(f"\033[{move_up}A")
  for line in lines:
    sys.stdout.write("\033[2K\r")
    sys.stdout.write(line + "\n")
  sys.stdout.flush()


def _build_footer(agent_name: str, term_width: int) -> List[str]:
  title = f"{BOLD}{CYAN}{agent_name}{RESET}"
  rule = f"{DIM}{'─' * min(term_width, 52)}{RESET}"
  return [
    "",
    _center(title, term_width),
    _center(rule, term_width),
    "",
  ]


def play_agent_splash(
  agent_name: str = "DRAXY",
  *,
  width: int = DEFAULT_WIDTH,
  height: int = DEFAULT_HEIGHT,
  fps: float = DEFAULT_FPS,
  frame_skip: int = DEFAULT_FRAME_SKIP,
  max_frames: int = DEFAULT_MAX_FRAMES,
  duration_sec: float = DEFAULT_DURATION_SEC,
  animate: bool = True,
) -> bool:
  """Reproduz splash compacto inline. Retorna False se não puder exibir."""
  if not sys.stdout.isatty():
    return False

  try:
    frames = _load_splash_cache(width, height, frame_skip, max_frames)
  except (FileNotFoundError, OSError):
    return False

  if not frames:
    return False

  term_width = max(width + 8, 72)
  sphere_lines = _frame_lines(frames[-1])
  footer = _build_footer(agent_name, term_width)
  block_height = len(sphere_lines) + len(footer)

  sys.stdout.write(HIDE_CURSOR)
  try:
    if animate and len(frames) > 1:
      delay = min(1.0 / fps, duration_sec / len(frames))
      deadline = time.monotonic() + duration_sec
      index = 0
      first = True

      while time.monotonic() < deadline:
        centered = _center_block(_frame_lines(frames[index]), term_width)
        block = centered + footer
        _draw_block(block, move_up=0 if first else block_height)
        first = False
        index = (index + 1) % len(frames)
        time.sleep(delay)

    final_sphere = _center_block(_frame_lines(frames[-1]), term_width)
    final_block = final_sphere + footer
    _draw_block(final_block, move_up=block_height if animate else 0)
  finally:
    sys.stdout.write(SHOW_CURSOR)
    sys.stdout.flush()

  return True


def render_static_logo(
  agent_name: str = "DRAXY",
  *,
  width: int = DEFAULT_WIDTH,
  height: int = DEFAULT_HEIGHT,
) -> Optional[str]:
  """Retorna logo ASCII estático (sem animação) para impressão."""
  try:
    frames = _load_splash_cache(width, height, DEFAULT_FRAME_SKIP, 1)
  except (FileNotFoundError, OSError):
    return None

  if not frames:
    return None

  term_width = max(width + 8, 72)
  lines = _center_block(_frame_lines(frames[0]), term_width)
  lines.extend(_build_footer(agent_name, term_width))
  return "\n".join(lines) + "\n"
