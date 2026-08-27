"""Carregamento e cache de frames do GIF de referência."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

FrameArray = np.ndarray


def default_gif_path() -> Path:
  return Path(__file__).resolve().parents[2] / "static" / "assets" / "background.gif"


def load_gif_frames(gif_path: Path) -> Tuple[List[FrameArray], float]:
  """Carrega todos os frames do GIF como arrays grayscale uint8.

  Returns:
    Tupla (frames, fps_estimado).
  """
  if not gif_path.is_file():
    raise FileNotFoundError(f"GIF não encontrado: {gif_path}")

  img = Image.open(gif_path)
  n_frames = int(getattr(img, "n_frames", 1))
  duration_ms = float(img.info.get("duration", 33) or 33)
  fps = 1000.0 / max(duration_ms, 1.0)

  frames: List[FrameArray] = []
  for index in range(n_frames):
    img.seek(index)
    frame = img.convert("L")
    frames.append(np.asarray(frame, dtype=np.uint8))

  return frames, fps
