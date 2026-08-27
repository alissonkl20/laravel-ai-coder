"""Script principal de fine-tuning QLoRA com Unsloth para Laravel/PHP."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Unsloth deve ser importado antes de transformers/peft (otimizações de memória)
from unsloth import FastLanguageModel

import torch
from trl import SFTTrainer
from transformers import TrainingArguments

from config import TrainingConfig
from utils.dataset_loader import load_and_format_dataset

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def _log(message: str) -> None:
  """Emite log com timestamp via logger configurado."""
  logger.info(message)


def train(config: TrainingConfig) -> None:
  """Executa o pipeline completo de fine-tuning QLoRA.

  Args:
    config: Parâmetros de treino vindos de TrainingConfig.

  Raises:
    RuntimeError: Em falhas de GPU/CUDA, incluindo OOM.
    FileNotFoundError: Se o dataset não existir.
  """
  _log(f"Iniciando treino — modelo: {config.model_name}")
  _log(
    f"VRAM estimada: batch={config.batch_size}, "
    f"grad_accum={config.gradient_accumulation_steps}, "
    f"max_seq={config.max_seq_length}"
  )

  if not torch.cuda.is_available():
    raise RuntimeError(
      "CUDA não disponível. Este projeto requer GPU NVIDIA com suporte CUDA."
    )

  _log(f"GPU detectada: {torch.cuda.get_device_name(0)}")
  _log(
    "Dica: feche apps que usam GPU (Firefox, etc.) se o treino falhar por VRAM."
  )

  try:
    torch.cuda.empty_cache()

    _log(f"Baixando/carregando modelo (pode levar 5-15 min na 1ª vez): {config.model_name}")
    _log("Sem barra de progresso é normal — aguarde. VRAM sobe após o download.")

    # dtype=None: Unsloth detecta automaticamente (4-bit não usa fp16/bf16 no forward)
    model, tokenizer = FastLanguageModel.from_pretrained(
      model_name=config.model_name,
      max_seq_length=config.max_seq_length,
      dtype=None,
      load_in_4bit=config.load_in_4bit,
      # Evita offload parcial em CPU/disk quando a VRAM está no limite
      device_map={"": 0},
    )

    # use_gradient_checkpointing="unsloth" reduz VRAM ~30% com overhead mínimo
    model = FastLanguageModel.get_peft_model(
      model,
      r=config.lora_r,
      lora_alpha=config.lora_alpha,
      lora_dropout=config.lora_dropout,
      target_modules=config.target_modules,
      use_gradient_checkpointing="unsloth",
    )

    dataset_path = Path(config.dataset_path)
    if not dataset_path.is_absolute():
      dataset_path = Path(__file__).parent / dataset_path
    dataset = load_and_format_dataset(str(dataset_path))

    # fp16/bf16 desativados: modelo em 4-bit já é quantizado; mixed precision
    # não traz ganho e pode causar instabilidade em QLoRA
    training_args = TrainingArguments(
      output_dir=config.output_dir,
      per_device_train_batch_size=config.batch_size,
      gradient_accumulation_steps=config.gradient_accumulation_steps,
      learning_rate=config.learning_rate,
      max_steps=config.max_steps,
      logging_steps=10,
      save_steps=100,
      save_total_limit=2,
      fp16=False,
      bf16=False,
      optim="adamw_8bit",
      warmup_steps=10,
      report_to="none",
      seed=42,
    )

    trainer = SFTTrainer(
      model=model,
      tokenizer=tokenizer,
      train_dataset=dataset,
      dataset_text_field="text",
      max_seq_length=config.max_seq_length,
      args=training_args,
    )

    _log(f"Treinando por {config.max_steps} steps...")
    trainer.train()

    output_path = Path(config.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(config.output_dir)
    tokenizer.save_pretrained(config.output_dir)

    _log(f"Adaptador LoRA salvo em: {config.output_dir}")
    _log("Treino concluído com sucesso.")

  except torch.cuda.OutOfMemoryError as exc:
    _log("ERRO: CUDA Out of Memory (OOM).")
    _log(
      "Sugestões: reduza batch_size para 1 e aumente "
      "gradient_accumulation_steps para 8 em config.py"
    )
    raise RuntimeError(f"CUDA OOM durante treino: {exc}") from exc
  except FileNotFoundError:
    raise
  except RuntimeError as exc:
    err = str(exc).lower()
    if "cuda" in err or "out of memory" in err or "dispatched on the cpu" in err:
      _log("ERRO: VRAM insuficiente ou modelo parcial na CPU.")
      _log(
        "Sugestões: MAX_SEQ_LENGTH=1024 no .env, feche apps na GPU, "
        "batch_size=1 em config.py"
      )
    raise


def main() -> None:
  """Ponto de entrada do script de treino."""
  config = TrainingConfig()
  try:
    train(config)
  except (FileNotFoundError, RuntimeError, ValueError) as exc:
    logger.error("Falha no treino: %s", exc)
    sys.exit(1)


if __name__ == "__main__":
  main()
