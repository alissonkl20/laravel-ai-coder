"""Carregamento e formatação do dataset JSONL para SFTTrainer."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from datasets import Dataset
import pyarrow as pa

logger = logging.getLogger(__name__)

# Tokens do template de chat Qwen2.5 (im_start / im_end)
_IM_START = "<|" + "im_start" + "|>"
_IM_END = "<|" + "im_end" + "|>"


_AGENT_SYSTEM = (
  "Você é DRAXY, agente CLI Laravel 11+. "
  "Responda um JSON por turno: "
  '{"action":"tool","tool":"...","args":{...}} '
  'ou {"action":"finish","message":"..."}. Sem markdown. '
  "Prefira scaffold_php e replace_in_file. Não coloque PHP longo em content."
)


def _format_qwen_chat(instruction: str, output: str) -> str:
  stripped = output.strip()
  if stripped.startswith("{") and '"action"' in stripped:
    return (
      f"{_IM_START}system\n{_AGENT_SYSTEM}{_IM_END}\n"
      f"{_IM_START}user\n{instruction}{_IM_END}\n"
      f"{_IM_START}assistant\n{output}{_IM_END}"
    )
  return (
    f"{_IM_START}user\n{instruction}{_IM_END}\n"
    f"{_IM_START}assistant\n{output}{_IM_END}"
  )


def _read_jsonl(file_path: Path) -> List[Dict[str, Any]]:
  """Lê registros de um arquivo JSONL.

  Args:
    file_path: Caminho ao arquivo .jsonl.

  Returns:
    Lista de dicionários com chaves 'instruction' e 'output'.

  Raises:
    FileNotFoundError: Se o arquivo não existir.
    ValueError: Se um registro não tenha as chaves obrigatórias.
  """
  records: List[Dict[str, Any]] = []

  if not file_path.exists():
    raise FileNotFoundError(f"Dataset não encontrado: {file_path}")

  with file_path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      line = line.strip()
      if not line:
        continue

      try:
        record = json.loads(line)
      except json.JSONDecodeError as exc:
        raise ValueError(
          f"JSON inválido na linha {line_number} de {file_path}: {exc}"
        ) from exc

      if "instruction" not in record or "output" not in record:
        raise ValueError(
          f"Linha {line_number}: registro deve conter 'instruction' e 'output'."
        )

      records.append(record)

  if not records:
    raise ValueError(f"Nenhum registro válido encontrado em {file_path}")

  logger.info("Lidos %d registros de %s", len(records), file_path)
  return records


def load_and_format_dataset(file_path: str) -> Dataset:
  """Carrega JSONL e retorna Dataset HuggingFace com campo 'text'.

  O campo 'text' contém o template de chat Qwen2.5 completo, pronto para
  o SFTTrainer (dataset_text_field="text").

  Args:
    file_path: Caminho ao arquivo raw_dataset.jsonl.

  Returns:
    Dataset HuggingFace com coluna 'text'.

  Raises:
    FileNotFoundError: Se o arquivo não existir.
    ValueError: Se o JSONL estiver malformado ou vazio.
  """
  path = Path(file_path)
  records = _read_jsonl(path)

  formatted_texts: List[str] = [
    _format_qwen_chat(
      instruction=str(record["instruction"]),
      output=str(record["output"]),
    )
    for record in records
  ]

  # fingerprint fixo: evita bug dill/pickle do datasets em Python 3.14
  arrow_table = pa.table({"text": formatted_texts})
  dataset = Dataset(arrow_table, fingerprint="laravel-ai-coder-dataset-v1")
  logger.info("Dataset formatado: %d exemplos prontos para SFT.", len(dataset))
  return dataset
