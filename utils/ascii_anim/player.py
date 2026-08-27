"""Loop de reprodução da animação ASCII."""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from utils.ascii_anim.converter import AsciiFrameCache, RenderConfig, build_frame_cache
from utils.ascii_anim.loader import default_gif_path, load_gif_frames
from utils.ascii_anim.terminal import TerminalSession, get_terminal_size, terminal_session

DEFAULT_FPS = 24.0
FRAME_SKIP = 2  # GIF tem 330 frames; pular alguns mantém fluidez sem sobrecarga


class AnimationPlayer:
  def __init__(
    self,
    gif_path: Path,
    fps: float = DEFAULT_FPS,
    cols: Optional[int] = None,
    rows: Optional[int] = None,
    chars: str = "0123456789",
    threshold: int = 12,
    density: float = 1.0,
    frame_skip: int = FRAME_SKIP,
    loop: bool = True,
  ) -> None:
    self.gif_path = gif_path
    self.fps = max(1.0, min(fps, 60.0))
    self.cols = cols
    self.rows = rows
    self.chars = chars
    self.threshold = threshold
    self.density = max(0.2, min(density, 1.0))
    self.frame_skip = max(1, frame_skip)
    self.loop = loop
    self._stop = False
    self._cache: Optional[AsciiFrameCache] = None

  def request_stop(self, *_args) -> None:
    self._stop = True

  def _load_and_render(self) -> AsciiFrameCache:
    sys.stderr.write("Carregando GIF e pré-processando frames...\n")
    sys.stderr.flush()

    source_frames, _gif_fps = load_gif_frames(self.gif_path)
    if self.frame_skip > 1:
      source_frames = source_frames[:: self.frame_skip]

    size = get_terminal_size(self.cols, self.rows)
    config = RenderConfig(
      chars=self.chars,
      threshold=self.threshold,
      particle_density=self.density,
    )

    cache = build_frame_cache(source_frames, size, config)
    sys.stderr.write(
      f"Pronto: {len(cache.frames)} frames · {size.cols}x{size.rows} · "
      f"{self.fps:.0f} FPS\n"
    )
    sys.stderr.flush()
    return cache

  def run(self) -> int:
    signal.signal(signal.SIGINT, self.request_stop)
    signal.signal(signal.SIGTERM, self.request_stop)

    try:
      self._cache = self._load_and_render()
    except FileNotFoundError as exc:
      sys.stderr.write(f"Erro: {exc}\n")
      return 1

    frame_delay = 1.0 / self.fps
    frames = self._cache.frames
    if not frames:
      sys.stderr.write("Erro: nenhum frame para reproduzir.\n")
      return 1

    index = 0
    with terminal_session() as session:
      while not self._stop:
        session.draw_frame(frames[index])
        index += 1
        if index >= len(frames):
          if not self.loop:
            break
          index = 0

        time.sleep(frame_delay)

    return 0


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Animação ASCII da esfera numérica (baseada em background.gif).",
  )
  parser.add_argument(
    "--gif",
    type=Path,
    default=default_gif_path(),
    help="Caminho do GIF de referência",
  )
  parser.add_argument(
    "--fps",
    type=float,
    default=DEFAULT_FPS,
    help="Frames por segundo na reprodução (padrão: 24)",
  )
  parser.add_argument(
    "--width",
    type=int,
    default=None,
    help="Largura fixa em colunas (padrão: tamanho do terminal)",
  )
  parser.add_argument(
    "--height",
    type=int,
    default=None,
    help="Altura fixa em linhas (padrão: tamanho do terminal)",
  )
  parser.add_argument(
    "--chars",
    type=str,
    default="0123456789",
    help="Caracteres usados como partículas",
  )
  parser.add_argument(
    "--threshold",
    type=int,
    default=12,
    help="Limiar de brilho mínimo (0-255) para exibir partícula",
  )
  parser.add_argument(
    "--density",
    type=float,
    default=1.0,
    help="Densidade de partículas (0.2-1.0)",
  )
  parser.add_argument(
    "--frame-skip",
    type=int,
    default=FRAME_SKIP,
    help="Usar 1 a cada N frames do GIF (padrão: 2)",
  )
  parser.add_argument(
    "--once",
    action="store_true",
    help="Reproduzir apenas uma vez (sem loop)",
  )
  return parser


def main(argv: Optional[list[str]] = None) -> int:
  args = build_parser().parse_args(argv)

  if not args.chars:
    sys.stderr.write("Erro: --chars não pode ser vazio.\n")
    return 1

  player = AnimationPlayer(
    gif_path=args.gif,
    fps=args.fps,
    cols=args.width,
    rows=args.height,
    chars=args.chars,
    threshold=max(0, min(args.threshold, 255)),
    density=args.density,
    frame_skip=args.frame_skip,
    loop=not args.once,
  )
  return player.run()


if __name__ == "__main__":
  raise SystemExit(main())
