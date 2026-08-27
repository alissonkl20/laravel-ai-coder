"""Conversão de frames do GIF para grade ASCII com dígitos 0-9."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image

from utils.ascii_anim.loader import FrameArray
from utils.ascii_anim.terminal import CHAR_ASPECT, TerminalSize, supports_truecolor

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"

# Fallback ANSI 256 / básico por faixa de luminosidade
ANSI_LEVELS = (
  "\033[90m",   # muito escuro
  "\033[90m",
  "\033[37m",   # médio
  "\033[97m",   # brilhante
)


@dataclass(frozen=True)
class RenderConfig:
  chars: str = "0123456789"
  threshold: int = 12
  particle_density: float = 1.0
  flicker_strength: float = 0.35
  use_truecolor: bool = True


@dataclass
class AsciiFrameCache:
  size: TerminalSize
  config: RenderConfig
  frames: List[str]


def _resize_frame(frame: FrameArray, width: int, height: int) -> FrameArray:
  image = Image.fromarray(frame, mode="L")
  # Nearest preserva traços finos dos dígitos no GIF original
  resized = image.resize((width, height), Image.Resampling.NEAREST)
  return np.asarray(resized, dtype=np.uint8)


def _stable_noise(x: int, y: int, frame_idx: int, salt: int = 0) -> float:
  raw = f"{x}:{y}:{frame_idx}:{salt}".encode()
  digest = hashlib.md5(raw).digest()
  return digest[0] / 255.0


def _brightness_to_digit(
  brightness: float,
  x: int,
  y: int,
  frame_idx: int,
  chars: str,
) -> str:
  norm = max(0.0, min(1.0, brightness / 255.0))
  # Curva que privilegia dígitos maiores nas bordas iluminadas
  shaped = norm ** 0.72
  idx = int(shaped * (len(chars) - 1) + 0.5)
  idx = max(0, min(len(chars) - 1, idx))

  flicker = _stable_noise(x, y, frame_idx, salt=7)
  if flicker < 0.12:
    idx = (idx + int(_stable_noise(x, y, frame_idx, salt=3) * 3) + 1) % len(chars)

  return chars[idx]


def _ansi_for_brightness(brightness: float, use_truecolor: bool) -> str:
  norm = max(0.0, min(1.0, brightness / 255.0))

  if use_truecolor:
    # Esfera digital: núcleo mais escuro, borda mais clara
    value = int(40 + norm * 215)
    if norm > 0.82:
      return f"\033[38;2;{value};{value};{value}{BOLD}m"
    if norm > 0.45:
      return f"\033[38;2;{value};{value};{value}m"
    return f"\033[38;2;{max(20, value - 25)};{max(20, value - 25)};{max(20, value - 25)}{DIM}m"

  if norm > 0.75:
    return ANSI_LEVELS[3] + BOLD
  if norm > 0.35:
    return ANSI_LEVELS[2]
  return ANSI_LEVELS[0] + DIM


def _should_place_particle(
  brightness: float,
  x: int,
  y: int,
  frame_idx: int,
  threshold: int,
  density: float,
) -> bool:
  if brightness < threshold:
    return False
  if density >= 1.0:
    return True

  noise = _stable_noise(x, y, frame_idx, salt=11)
  cutoff = density * (brightness / 255.0)
  return noise < cutoff


def frame_to_ascii(
  frame: FrameArray,
  size: TerminalSize,
  frame_idx: int,
  config: RenderConfig,
) -> str:
  """Converte um frame para string ANSI com dígitos posicionados em grade."""
  pixel_width = size.cols
  pixel_height = max(8, int(size.rows / CHAR_ASPECT))

  resized = _resize_frame(frame, pixel_width, pixel_height)

  use_truecolor = config.use_truecolor and supports_truecolor()
  lines: List[str] = []

  for row in range(size.rows):
    src_y = min(pixel_height - 1, int((row + 0.5) * pixel_height / size.rows))
    cells: List[str] = []
    prev_ansi = ""

    for col in range(size.cols):
      src_x = min(pixel_width - 1, int((col + 0.5) * pixel_width / size.cols))
      brightness = float(resized[src_y, src_x])

      # Bloom leve: captura partículas vizinhas após resize
      if brightness < config.threshold and src_x > 0 and src_y > 0:
        neighborhood = resized[
          max(0, src_y - 1) : src_y + 2,
          max(0, src_x - 1) : src_x + 2,
        ]
        brightness = float(neighborhood.max()) * 0.82

      if not _should_place_particle(
        brightness,
        col,
        row,
        frame_idx,
        config.threshold,
        config.particle_density,
      ):
        cells.append(" ")
        prev_ansi = ""
        continue

      digit = _brightness_to_digit(brightness, col, row, frame_idx, config.chars)
      ansi = _ansi_for_brightness(brightness, use_truecolor)

      if ansi != prev_ansi:
        cells.append(f"{ansi}{digit}")
        prev_ansi = ansi
      else:
        cells.append(digit)

    line = "".join(cells).rstrip()
    lines.append(line + RESET)

  return "\n".join(lines)


def build_frame_cache(
  source_frames: Sequence[FrameArray],
  size: TerminalSize,
  config: RenderConfig,
) -> AsciiFrameCache:
  rendered = [
    frame_to_ascii(frame, size, index, config)
    for index, frame in enumerate(source_frames)
  ]
  return AsciiFrameCache(size=size, config=config, frames=rendered)


def cache_key(size: TerminalSize, config: RenderConfig) -> Tuple[int, int, str, int, float, float, bool]:
  return (
    size.cols,
    size.rows,
    config.chars,
    config.threshold,
    config.particle_density,
    config.flicker_strength,
    config.use_truecolor,
  )
