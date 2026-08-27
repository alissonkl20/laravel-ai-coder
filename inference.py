"""Inferência interativa via CLI com modelo LoRA fine-tuned."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Tuple

import torch
from peft import PeftModel
from transformers import GenerationConfig

from config import AGENT_NAME, TrainingConfig
from utils.agent.llm_config import LLMBehaviorConfig, build_language_instructions
from utils.stdio_silence import silenced_output

logger = logging.getLogger(__name__)


def _inference_system_prompt() -> str:
  """System prompt para inferência simples (sem tools)."""
  lang = build_language_instructions(LLMBehaviorConfig())
  return (
    f"Você é {AGENT_NAME}, assistente especializado em PHP e Laravel 11+.\n"
    f"{lang}\n"
    "Gere código limpo, idiomático e pronto para uso. "
    "Inclua namespaces, imports e tipos quando aplicável."
  )


def _build_generation_config(
  tokenizer: Any,
  temperature: float,
  top_p: float,
  max_new_tokens: int,
) -> GenerationConfig:
  """Monta GenerationConfig sem conflito max_length / max_new_tokens."""
  return GenerationConfig(
    max_new_tokens=max_new_tokens,
    temperature=temperature,
    top_p=top_p,
    do_sample=temperature > 0,
    pad_token_id=tokenizer.eos_token_id,
  )


def load_lora_model() -> Tuple[Any, Any]:
  """Carrega modelo base + adaptador LoRA para inferência.

  O modelo é preparado com FastLanguageModel.for_inference() para
  acelerar a geração (2x mais rápido em Unsloth).

  Returns:
    Tupla (model, tokenizer) prontos para geração.

  Raises:
    RuntimeError: Se CUDA não estiver disponível ou falha ao carregar pesos.
    FileNotFoundError: Se o diretório do adaptador LoRA não existir.
  """
  config = TrainingConfig()

  if not torch.cuda.is_available():
    raise RuntimeError(
      "CUDA não disponível. Inferência requer GPU NVIDIA."
    )

  try:
    # Unsloth deve ser importado antes do uso intenso de peft/transformers
    # e emite bastante ruído no terminal — silenciamos o boot do agent CLI.
    lora_loaded = False
    with silenced_output():
      from unsloth import FastLanguageModel  # noqa: WPS451

      model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.model_name,
        max_seq_length=config.max_seq_length,
        dtype=None,
        load_in_4bit=config.load_in_4bit,
        device_map={"": 0},
      )

      lora_path = Path(config.output_dir)
      adapter_config = lora_path / "adapter_config.json"

      if adapter_config.is_file():
        model = PeftModel.from_pretrained(
          model, config.output_dir, is_trainable=False
        )
        lora_loaded = True

      FastLanguageModel.for_inference(model)

    if not lora_loaded:
      logger.warning(
        "LoRA não encontrado em '%s'. Usando modelo base (sem fine-tuning). "
        "Rode train.py para especialização Laravel.",
        config.output_dir,
      )

    return model, tokenizer

  except FileNotFoundError as exc:
    raise FileNotFoundError(
      f"Falha ao carregar pesos: {exc}. Verifique MODEL_NAME no .env."
    ) from exc
  except RuntimeError as exc:
    raise RuntimeError(f"Falha ao carregar modelo: {exc}") from exc


def generate_code(
  model: Any,
  tokenizer: Any,
  instruction: str,
  temperature: float = 0.7,
  top_p: float = 0.9,
  max_new_tokens: int = 1024,
) -> str:
  """Gera código PHP/Laravel a partir de uma instrução.

  Args:
    model: Modelo Unsloth com LoRA.
    tokenizer: Tokenizer do modelo.
    instruction: Instrução do usuário.
    temperature: Temperatura de amostragem (criatividade).
    top_p: Nucleus sampling top-p.
    max_new_tokens: Limite de tokens gerados.

  Returns:
    Código gerado pelo modelo (string).
  """
  messages = [
    {"role": "system", "content": _inference_system_prompt()},
    {"role": "user", "content": instruction},
  ]

  prompt = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
  )

  inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
  gen_config = _build_generation_config(tokenizer, temperature, top_p, max_new_tokens)

  with torch.no_grad():
    outputs = model.generate(
      **inputs,
      generation_config=gen_config,
    )

  generated = tokenizer.decode(
    outputs[0][inputs["input_ids"].shape[1]:],
    skip_special_tokens=True,
  )
  return generated.strip()


def interactive_loop(model: Any, tokenizer: Any) -> None:
  """Loop interativo no terminal para testar gerações.

  Args:
    model: Modelo carregado.
    tokenizer: Tokenizer carregado.
  """
  print(f"\n=== {AGENT_NAME} — CLI ===")
  print("Digite sua instrução (ou 'sair' para encerrar).\n")

  while True:
    try:
      instruction = input("Instrução: ").strip()
    except (EOFError, KeyboardInterrupt):
      print("\nEncerrando.")
      break

    if not instruction:
      continue
    if instruction.lower() in {"sair", "exit", "quit"}:
      print("Encerrando.")
      break

    try:
      print("Gerando... (30–60 s na primeira resposta)", flush=True)
      code = generate_code(model, tokenizer, instruction)
      print("\n--- Código gerado ---\n")
      print(code)
      print("\n---------------------\n")
    except RuntimeError as exc:
      logger.error("Erro na geração: %s", exc)


def main() -> None:
  """Ponto de entrada da inferência CLI."""
  logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
  )
  try:
    model, tokenizer = load_lora_model()
    interactive_loop(model, tokenizer)
  except (FileNotFoundError, RuntimeError) as exc:
    logger.error("%s", exc)
    sys.exit(1)


if __name__ == "__main__":
  main()
