"""Constrói índice invertido para buscas rápidas do agent."""

from __future__ import annotations

import json
from pathlib import Path

from utils.agent.search_index import SearchIndex

PROJECT_ROOT = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "data" / "raw_dataset.jsonl"
PRIORITIES_PATH = PROJECT_ROOT / "config" / "search_priorities.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "search_index.json"


def main() -> None:
  OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
  index = SearchIndex.build_from_dataset(
    dataset_path=DATASET_PATH,
    priorities_path=PRIORITIES_PATH,
    output_path=OUTPUT_PATH,
  )
  OUTPUT_PATH.write_text(
    json.dumps(index, ensure_ascii=False),
    encoding="utf-8",
  )
  stats = index["stats"]
  print(f"Índice salvo: {OUTPUT_PATH}")
  print(f"  documentos: {stats['documents']}")
  print(f"  termos: {stats['terms']}")
  print(f"  version: {index['version']}")


if __name__ == "__main__":
  main()
