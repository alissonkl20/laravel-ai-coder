"""Configuração de comportamento da LLM local (idioma, tolerância a erros)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMBehaviorConfig:
  """Parâmetros de comunicação e interpretação de prompts."""

  multilingual: bool = field(
    default_factory=lambda: os.getenv("LLM_MULTILINGUAL", "true").lower()
    in ("1", "true", "yes")
  )
  default_language: str = field(
    default_factory=lambda: os.getenv("LLM_DEFAULT_LANGUAGE", "pt").strip().lower()
  )
  typo_tolerance: bool = field(
    default_factory=lambda: os.getenv("LLM_TYPO_TOLERANCE", "true").lower()
    in ("1", "true", "yes")
  )
  respond_in_prompt_language: bool = field(
    default_factory=lambda: os.getenv("LLM_RESPOND_IN_PROMPT_LANGUAGE", "true").lower()
    in ("1", "true", "yes")
  )


def build_language_instructions(cfg: LLMBehaviorConfig) -> str:
  fallback = "português" if cfg.default_language.startswith("pt") else "inglês"
  if not cfg.multilingual:
    return f"- Responda sempre em {fallback}."
  reply = (
    f"- Responda no idioma do prompt (fallback {fallback})."
    if cfg.respond_in_prompt_language
    else f"- Responda sempre em {fallback}."
  )
  typos = (
    "- Interprete intenção mesmo com typos (cntroler→controller)."
    if cfg.typo_tolerance
    else ""
  )
  return "\n".join(
    part for part in (
      "- Aceite PT e EN; termos técnicos em qualquer idioma.",
      reply,
      typos,
    ) if part
  )
