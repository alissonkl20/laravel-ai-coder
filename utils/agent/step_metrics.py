from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch


def nvidia_smi_used_mb() -> Optional[float]:
  try:
    out = subprocess.check_output(
      [
        "nvidia-smi",
        "--query-gpu=memory.used",
        "--format=csv,noheader,nounits",
      ],
      text=True,
      timeout=5,
    )
    return float(out.strip().splitlines()[0])
  except (OSError, ValueError, subprocess.SubprocessError):
    return None


def torch_vram_mb() -> Dict[str, Optional[float]]:
  if not torch.cuda.is_available():
    return {"vram_alloc_mb": None, "vram_max_alloc_mb": None}
  return {
    "vram_alloc_mb": round(torch.cuda.memory_allocated() / (1024 ** 2), 1),
    "vram_max_alloc_mb": round(
      torch.cuda.max_memory_allocated() / (1024 ** 2), 1
    ),
  }


class StepMetricsCollector:
  def __init__(self, path: Optional[Path] = None) -> None:
    self.path = path
    self.rows: List[Dict[str, Any]] = []
    if self.path is not None:
      self.path.parent.mkdir(parents=True, exist_ok=True)

  def record(self, row: Dict[str, Any]) -> None:
    self.rows.append(row)
    if self.path is None:
      return
    with self.path.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(row, ensure_ascii=False) + "\n")
