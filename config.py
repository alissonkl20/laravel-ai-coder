"""Configuração central do projeto Laravel AI Coder."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()

AGENT_NAME = os.getenv("AGENT_NAME", "DRAXY")


@dataclass
class TrainingConfig:
  """Parâmetros de treino QLoRA para o assistente Laravel.

  Valores padrão otimizados para RTX 3060 12GB VRAM com modelo 7B em 4-bit.
  """

  model_name: str = field(
    default_factory=lambda: os.getenv(
      "MODEL_NAME",
      # Versão Unsloth 4-bit: ocupa menos VRAM que quantizar na carga
      "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
    )
  )
  max_seq_length: int = field(
    default_factory=lambda: int(os.getenv("MAX_SEQ_LENGTH", "1536"))
  )
  load_in_4bit: bool = True
  # rank 16: bom trade-off entre qualidade e VRAM para fine-tuning LoRA
  lora_r: int = 16
  lora_alpha: int = 16
  lora_dropout: float = 0.0
  target_modules: List[str] = field(
    default_factory=lambda: [
      "q_proj",
      "k_proj",
      "v_proj",
      "o_proj",
      "gate_proj",
      "up_proj",
      "down_proj",
    ]
  )
  # batch 1 + grad_accum 8: estável na RTX 3060 12GB com apps no desktop
  batch_size: int = 1
  gradient_accumulation_steps: int = 8
  learning_rate: float = 2e-4
  max_steps: int = field(
    default_factory=lambda: int(os.getenv("MAX_STEPS", "400"))
  )
  output_dir: str = field(
    default_factory=lambda: os.getenv("LORA_OUTPUT_DIR", "./outputs_lora")
  )
  dataset_path: str = field(
    default_factory=lambda: os.getenv("DATASET_PATH", "./data/raw_dataset.jsonl")
  )


@dataclass
class AgentConfig:
  """Parâmetros do agent CLI de debug."""

  workspace: str = field(
    default_factory=lambda: os.getenv("AGENT_WORKSPACE", os.getcwd())
  )
  projects_root: str = field(
    default_factory=lambda: os.getenv(
      "AGENT_PROJECTS_ROOT",
      os.path.expanduser("~/Documentos"),
    )
  )
  default_project: str = field(
    default_factory=lambda: os.getenv("AGENT_DEFAULT_PROJECT", "")
  )
  max_iterations: int = field(
    default_factory=lambda: int(os.getenv("AGENT_MAX_ITERATIONS", "20"))
  )
  temperature: float = field(
    default_factory=lambda: float(os.getenv("AGENT_TEMPERATURE", "0.2"))
  )
  max_new_tokens: int = field(
    default_factory=lambda: int(os.getenv("AGENT_MAX_NEW_TOKENS", "1024"))
  )
  max_new_tokens_tool: int = field(
    default_factory=lambda: int(os.getenv("AGENT_MAX_NEW_TOKENS_TOOL", "256"))
  )
  max_tool_output_chars: int = field(
    default_factory=lambda: int(os.getenv("AGENT_MAX_TOOL_OUTPUT_CHARS", "2000"))
  )
  history_steps: int = field(
    default_factory=lambda: int(os.getenv("AGENT_HISTORY_STEPS", "6"))
  )
  conversation_turns: int = field(
    default_factory=lambda: int(os.getenv("AGENT_CONVERSATION_TURNS", "2"))
  )
  command_timeout: int = field(
    default_factory=lambda: int(os.getenv("AGENT_COMMAND_TIMEOUT", "60"))
  )
  shortcuts_path: str = field(
    default_factory=lambda: os.getenv(
      "AGENT_SHORTCUTS_PATH", "./config/agent_shortcuts.json"
    )
  )
  search_index_path: str = field(
    default_factory=lambda: os.getenv(
      "AGENT_SEARCH_INDEX", "./data/search_index.json"
    )
  )
  redis_url: str = field(
    default_factory=lambda: os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
  )
  cache_enabled: bool = field(
    default_factory=lambda: os.getenv("AGENT_CACHE_ENABLED", "true").lower()
    in ("1", "true", "yes")
  )
  cache_ttl: int = field(
    default_factory=lambda: int(os.getenv("AGENT_CACHE_TTL", "86400"))
  )
  ascii_splash: bool = field(
    default_factory=lambda: os.getenv("AGENT_ASCII_SPLASH", "false").lower()
    in ("1", "true", "yes")
  )
  ascii_splash_width: int = field(
    default_factory=lambda: int(os.getenv("AGENT_ASCII_SPLASH_WIDTH", "44"))
  )
  ascii_splash_height: int = field(
    default_factory=lambda: int(os.getenv("AGENT_ASCII_SPLASH_HEIGHT", "10"))
  )
  default_mode: str = field(
    default_factory=lambda: os.getenv("AGENT_DEFAULT_MODE", "agent")
  )
  sessions_path: str = field(
    default_factory=lambda: os.getenv("AGENT_SESSIONS_PATH", "./data/sessions")
  )
  require_approval: bool = field(
    default_factory=lambda: os.getenv("AGENT_REQUIRE_APPROVAL", "true").lower()
    in ("1", "true", "yes")
  )
  bench_jsonl: str = field(
    default_factory=lambda: os.getenv("AGENT_BENCH_JSONL", "")
  )
