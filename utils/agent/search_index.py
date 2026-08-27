"""Índice invertido para buscas rápidas com cache Redis."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.agent.cache import AgentCache

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}", re.I)
_STOPWORDS = frozenset({
  "a", "o", "as", "os", "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
  "um", "uma", "uns", "umas", "e", "ou", "para", "por", "com", "sem", "the", "and", "or",
  "to", "in", "on", "at", "is", "it", "be", "an", "of", "php", "laravel", "use", "class",
  "function", "public", "private", "protected", "return", "true", "false", "null", "new",
})
_SKIP_DIRS = {
  ".git",
  "vendor",
  "node_modules",
  ".venv",
  "storage",
  "bootstrap/cache",
  "outputs_lora",
  "unsloth_compiled_cache",
  "__pycache__",
  "static",
}
_INDEXABLE_EXT = {".php", ".json", ".md", ".env", ".blade.php", ".py", ".txt"}
_REFERENCE_ALLOWED_PREFIXES = (
  "README.md",
  "docs-laravel",
  "config",
  "utils/agent",
  "data/knowledge",
)


@dataclass
class SearchHit:
  """Um resultado de busca indexada."""

  doc_id: str
  score: float
  source: str
  path: str
  preview: str
  tags: List[str]


class SearchIndex:
  """Índice invertido global (dataset) + workspace com cache de consultas."""

  def __init__(
    self,
    global_index_path: Path,
    priorities_path: Path,
    cache: AgentCache,
  ) -> None:
    self.global_index_path = global_index_path
    self.priorities_path = priorities_path
    self.cache = cache
    self.version = "0"
    self.documents: Dict[str, Dict[str, Any]] = {}
    self.inverted: Dict[str, List[str]] = {}
    self.priorities: List[Dict[str, Any]] = []
    self._workspace_docs: Dict[str, Dict[str, Any]] = {}
    self._workspace_inverted: Dict[str, List[str]] = {}
    self._workspace_key: str = ""
    self._reference_docs: Dict[str, Dict[str, Any]] = {}
    self._reference_inverted: Dict[str, List[str]] = {}
    self._reference_key: str = ""

  def load_global(self) -> None:
    self.priorities = self._load_priorities()
    if not self.global_index_path.is_file():
      logger.warning(
        "Índice global não encontrado: %s — rode build_search_index.py",
        self.global_index_path,
      )
      return

    data = json.loads(self.global_index_path.read_text(encoding="utf-8"))
    self.version = str(data.get("version", "0"))
    self.documents = data.get("documents", {})
    self.inverted = data.get("inverted", {})
    logger.info(
      "Índice global: %d docs, %d termos (v%s)",
      len(self.documents),
      len(self.inverted),
      self.version,
    )

  def _load_priorities(self) -> List[Dict[str, Any]]:
    if not self.priorities_path.is_file():
      return []
    data = json.loads(self.priorities_path.read_text(encoding="utf-8"))
    return data.get("priorities", [])

  def index_workspace(self, workspace: Path, force: bool = False) -> int:
    """Indexa arquivos do projeto Laravel no workspace."""
    workspace = workspace.resolve()
    self._workspace_key = str(workspace)

    cache_key = f"ws_index:{workspace}"
    if not force:
      cached = self.cache.get("workspace_index", cache_key)
      if cached is not None:
        self._workspace_docs = cached.get("documents", {})
        self._workspace_inverted = cached.get("inverted", {})
        logger.info("Workspace index do cache: %d docs", len(self._workspace_docs))
        return len(self._workspace_docs)

    docs: Dict[str, Dict[str, Any]] = {}
    inverted: Dict[str, List[str]] = {}

    for file_path in self._iter_workspace_files(workspace):
      rel = str(file_path.relative_to(workspace))
      doc_id = f"ws:{rel}"
      try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
      except OSError:
        continue
      if not text.strip():
        continue

      tags = self._detect_tags(text, rel)
      preview = text[:600].replace("\n", " ").strip()
      docs[doc_id] = {
        "source": "workspace",
        "path": rel,
        "preview": preview,
        "tags": tags,
        "priority": max((t.get("boost", 0) for t in self.priorities if t["tag"] in tags), default=0),
      }
      self._index_text(doc_id, text[:8000], inverted)

    self._workspace_docs = docs
    self._workspace_inverted = inverted
    self.cache.set(
      "workspace_index",
      cache_key,
      {"documents": docs, "inverted": inverted},
      ttl=3600,
    )
    logger.info("Workspace indexado: %d arquivos", len(docs))
    return len(docs)

  def index_reference(self, reference_root: Path, force: bool = False) -> int:
    """Indexa docs/atalhos do agent-CLI (somente leitura) para consultas de 'como criar'."""
    reference_root = reference_root.resolve()
    self._reference_key = str(reference_root)

    cache_key = f"ref_index:{reference_root}"
    if not force:
      cached = self.cache.get("reference_index", cache_key)
      if cached is not None:
        self._reference_docs = cached.get("documents", {})
        self._reference_inverted = cached.get("inverted", {})
        logger.info("Reference index do cache: %d docs", len(self._reference_docs))
        return len(self._reference_docs)

    docs: Dict[str, Dict[str, Any]] = {}
    inverted: Dict[str, List[str]] = {}

    for file_path in self._iter_reference_files(reference_root):
      rel = str(file_path.relative_to(reference_root))
      doc_id = f"ref:{rel}"
      try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
      except OSError:
        continue
      if not text.strip():
        continue

      tags = self._detect_tags(text, rel)
      if "agent" not in tags:
        tags.append("agent")
      preview = text[:600].replace("\n", " ").strip()
      docs[doc_id] = {
        "source": "reference",
        "path": rel,
        "preview": preview,
        "tags": tags,
        "priority": max(
          (t.get("boost", 0) for t in self.priorities if t["tag"] in tags),
          default=50,
        ),
      }
      self._index_text(doc_id, text[:8000], inverted)

    self._reference_docs = docs
    self._reference_inverted = inverted
    self.cache.set(
      "reference_index",
      cache_key,
      {"documents": docs, "inverted": inverted},
      ttl=3600,
    )
    logger.info("Reference (agent-CLI) indexado: %d arquivos", len(docs))
    return len(docs)

  def _iter_reference_files(self, root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*"):
      if not path.is_file():
        continue
      if any(part in _SKIP_DIRS for part in path.parts):
        continue
      try:
        rel = str(path.relative_to(root))
      except ValueError:
        continue
      if not any(
        rel == prefix or rel.startswith(f"{prefix}/")
        for prefix in _REFERENCE_ALLOWED_PREFIXES
      ):
        continue
      if path.suffix in _INDEXABLE_EXT or path.name.endswith(".blade.php"):
        files.append(path)
    return files

  def _iter_workspace_files(self, workspace: Path) -> List[Path]:
    files: List[Path] = []
    for path in workspace.rglob("*"):
      if not path.is_file():
        continue
      if any(part in _SKIP_DIRS for part in path.parts):
        continue
      if path.suffix in _INDEXABLE_EXT or path.name.endswith(".blade.php"):
        files.append(path)
    return files

  def _tokenize(self, text: str) -> List[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in _STOPWORDS]

  def _index_text(
    self,
    doc_id: str,
    text: str,
    inverted: Dict[str, List[str]],
    weight: int = 1,
  ) -> None:
    tokens = set(self._tokenize(text))
    for token in tokens:
      for _ in range(weight):
        inverted.setdefault(token, [])
        if doc_id not in inverted[token]:
          inverted[token].append(doc_id)

  def _detect_tags(self, text: str, path: str) -> List[str]:
    blob = f"{path} {text[:500]}".lower()
    tags: List[str] = []
    for rule in self.priorities:
      tag = rule.get("tag", "")
      keywords = rule.get("keywords", [])
      if any(kw.lower() in blob for kw in keywords):
        tags.append(tag)
    return tags

  def _priority_boost(self, query_tokens: List[str]) -> Dict[str, int]:
    boosts: Dict[str, int] = {}
    for rule in self.priorities:
      tag = str(rule.get("tag", ""))
      boost = int(rule.get("boost", 0))
      keywords = [k.lower() for k in rule.get("keywords", [])]
      for token in query_tokens:
        if token in keywords or any(token in kw for kw in keywords):
          boosts[tag] = max(boosts.get(tag, 0), boost)
    return boosts

  def search(
    self,
    query: str,
    limit: int = 10,
    sources: Optional[List[str]] = None,
  ) -> List[SearchHit]:
    """Busca no índice com cache Redis/memória."""
    sources = sources or ["global", "workspace", "reference"]
    cache_key = f"v{self.version}:{self._workspace_key}:{self._reference_key}:{query}:{','.join(sources)}"
    cached = self.cache.get("search_query", cache_key)
    if cached is not None:
      return [SearchHit(**item) for item in cached]

    query_tokens = self._tokenize(query)
    if not query_tokens:
      return []

    tag_boosts = self._priority_boost(query_tokens)
    scores: Dict[str, float] = {}
    matched_tokens: Dict[str, int] = {}

    def score_inverted(inverted: Dict[str, List[str]], docs: Dict[str, Any]) -> None:
      for token in query_tokens:
        doc_ids = inverted.get(token, [])
        if not doc_ids:
          continue
        # IDF simplificado: termos raros valem mais
        idf = max(1.0, 3.0 - min(len(doc_ids) / 500.0, 2.5))
        for doc_id in doc_ids:
          scores[doc_id] = scores.get(doc_id, 0) + (8 * idf)
          matched_tokens[doc_id] = matched_tokens.get(doc_id, 0) + 1
          doc = docs.get(doc_id, {})
          doc_priority = float(doc.get("priority", 0))
          if doc_priority:
            scores[doc_id] += doc_priority * 0.05
          for tag in doc.get("tags", []):
            scores[doc_id] += tag_boosts.get(tag, 0)

    if "global" in sources:
      score_inverted(self.inverted, self.documents)
    if "workspace" in sources:
      score_inverted(self._workspace_inverted, self._workspace_docs)
    if "reference" in sources:
      score_inverted(self._reference_inverted, self._reference_docs)

    # Bônus por cobertura da query (multi-token)
    query_len = len(query_tokens)
    if query_len > 1:
      for doc_id, count in matched_tokens.items():
        coverage = count / query_len
        scores[doc_id] += coverage * 25

    hits: List[SearchHit] = []
    all_docs = {**self.documents, **self._workspace_docs, **self._reference_docs}

    for doc_id, score in sorted(scores.items(), key=lambda x: -x[1]):
      doc = all_docs.get(doc_id)
      if not doc:
        continue
      hits.append(
        SearchHit(
          doc_id=doc_id,
          score=score,
          source=str(doc.get("source", "")),
          path=str(doc.get("path", "")),
          preview=str(doc.get("preview", ""))[:500],
          tags=list(doc.get("tags", [])),
        )
      )
      if len(hits) >= limit:
        break

    self.cache.set("search_query", cache_key, [h.__dict__ for h in hits])
    return hits

  def format_results(self, hits: List[SearchHit]) -> str:
    if not hits:
      return "Nenhum resultado no índice."
    lines = []
    for hit in hits:
      tag_str = ",".join(hit.tags) if hit.tags else "-"
      lines.append(
        f"[{hit.source}] score={hit.score:.0f} tags={tag_str}\n"
        f"path={hit.path or hit.doc_id}\n{hit.preview}"
      )
    return "\n\n".join(lines)

  @staticmethod
  def build_from_dataset(
    dataset_path: Path,
    priorities_path: Path,
    output_path: Path,
    max_docs: int = 15000,
    preview_chars: int = 800,
  ) -> Dict[str, Any]:
    """Constrói índice invertido a partir do JSONL de treino."""
    priorities = []
    if priorities_path.is_file():
      priorities = json.loads(
        priorities_path.read_text(encoding="utf-8")
      ).get("priorities", [])

    documents: Dict[str, Dict[str, Any]] = {}
    inverted: Dict[str, List[str]] = {}
    token_re = _TOKEN_RE

    def detect_tags(text: str) -> List[str]:
      blob = text.lower()
      tags: List[str] = []
      for rule in priorities:
        tag = rule.get("tag", "")
        keywords = rule.get("keywords", [])
        if any(kw.lower() in blob for kw in keywords):
          tags.append(tag)
      return tags

    def index_doc(doc_id: str, instruction: str, output_preview: str) -> None:
      # Peso maior na instruction (pergunta) — menos ruído do output longo
      index_doc_tokens = set(token_re.findall(instruction.lower()))
      index_doc_tokens = {t for t in index_doc_tokens if t not in _STOPWORDS and len(t) >= 2}
      for token in index_doc_tokens:
        for _ in range(3):
          inverted.setdefault(token, [])
          if doc_id not in inverted[token]:
            inverted[token].append(doc_id)
      output_tokens = set(token_re.findall(output_preview.lower()))
      output_tokens = {t for t in output_tokens if t not in _STOPWORDS and len(t) >= 2}
      for token in output_tokens:
        inverted.setdefault(token, [])
        if doc_id not in inverted[token]:
          inverted[token].append(doc_id)

    count = 0
    if dataset_path.is_file():
      with dataset_path.open(encoding="utf-8") as fh:
        for line in fh:
          if count >= max_docs:
            break
          line = line.strip()
          if not line:
            continue
          try:
            record = json.loads(line)
          except json.JSONDecodeError:
            continue

          instruction = str(record.get("instruction", ""))
          output = str(record.get("output", ""))
          combined = f"{instruction}\n{output[:preview_chars]}"
          doc_id = f"ds:{count}"
          tags = detect_tags(combined)
          priority = max(
            (r.get("boost", 0) for r in priorities if r.get("tag") in tags),
            default=0,
          )
          documents[doc_id] = {
            "source": "dataset",
            "path": f"raw_dataset.jsonl#{count}",
            "preview": instruction[:400] or combined[:preview_chars],
            "instruction": instruction[:600],
            "tags": tags,
            "priority": priority,
          }
          index_doc(doc_id, instruction, output[:preview_chars])
          count += 1

    from datetime import datetime, timezone

    return {
      "version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
      "documents": documents,
      "inverted": inverted,
      "stats": {"documents": len(documents), "terms": len(inverted)},
    }
