from __future__ import annotations

import json
import logging
import re
import time
import warnings
from typing import Any, Callable, Dict, List, Optional

import torch

from config import AGENT_NAME, TrainingConfig
from utils.agent.modes import AgentMode, MODE_INSTRUCTIONS, tools_for_mode
from utils.agent.prompts import SYSTEM_PROMPT, USER_TASK_PREFIX, _LANGUAGE_BLOCK
from utils.agent.step_metrics import StepMetricsCollector, torch_vram_mb
from utils.agent.tools import ALL_TOOL_NAMES, ToolRegistry

logger = logging.getLogger(__name__)
_WRITE_HINT_RE = re.compile(
  r"write_file|replace_in_file|insert_lines|scaffold_php|implemente|"
  r"implement|preencha|escreva|criar |crie |"
  r"migration|controller|teste|test\b",
  re.IGNORECASE,
)
_WRITE_TASK_RE = re.compile(
  r"implemente|preencha|escreva|crie |criar |teste|test\b|migration|"
  r"controller|form request|scaffold|otimize",
  re.IGNORECASE,
)
_TEST_TASK_RE = re.compile(
  r"\btestes?\b|\bphp artisan test\b|\bphpunit\b",
  re.IGNORECASE,
)
_PROOF_TOOLS = frozenset({
  "write_file", "replace_in_file", "insert_lines", "scaffold_php",
})
_PARSE_RETRY = (
  'JSON inválido. Um objeto: {"action":"tool","tool":"...","args":{}} '
  'ou {"action":"finish","message":"..."}. '
  'Prefira scaffold_php com args curtos. Nunca PHP longo em content.'
)


def clip_chars(text: str, limit: int) -> str:
  if limit <= 0 or len(text) <= limit:
    return text
  return text[:limit] + f"\n[truncated {len(text) - limit} chars]"


def last_n(items: List[Any], n: int) -> List[Any]:
  if n <= 0:
    return []
  return items[-n:]


class LaravelAgent:
  def __init__(
    self,
    model: Any,
    tokenizer: Any,
    tools: ToolRegistry,
    max_iterations: int = 20,
    temperature: float = 0.1,
    max_new_tokens: int = 1024,
    max_new_tokens_tool: int = 256,
    max_tool_output_chars: int = 2000,
    max_history_steps: int = 6,
    max_conversation_turns: int = 2,
    one_shot: bool = False,
    mode: AgentMode = AgentMode.AGENT,
    metrics: Optional[StepMetricsCollector] = None,
    max_seq_length: Optional[int] = None,
  ) -> None:
    self.model = model
    self.tokenizer = tokenizer
    self.tools = tools
    self.max_iterations = max_iterations
    self.temperature = temperature
    self.max_new_tokens = max_new_tokens
    self.max_new_tokens_tool = max_new_tokens_tool
    self.max_tool_output_chars = max_tool_output_chars
    self.max_history_steps = max_history_steps
    self.max_conversation_turns = max_conversation_turns
    self.one_shot = one_shot
    self.mode = mode
    self.metrics = metrics
    self.max_seq_length = (
      max_seq_length
      if max_seq_length is not None
      else TrainingConfig().max_seq_length
    )
    self.conversation: List[Dict[str, str]] = []
    self.history: List[Dict[str, str]] = []
    self.last_generate: Dict[str, Any] = {}
    self._original_task = ""
    self._force_full_new_tokens = False
    self._proof_writes = 0
    self._tests_passed = False
    self._last_tool_ok = True
    gen_config = getattr(self.model, "generation_config", None)
    if gen_config is not None and getattr(gen_config, "max_length", None):
      gen_config.max_length = None
    self.set_mode(mode)

  def set_mode(self, mode: AgentMode) -> None:
    self.mode = mode
    self.tools.set_allowed_tools(set(tools_for_mode(mode)))

  def clear_conversation(self) -> None:
    self.conversation = []
    self.history = []

  def load_conversation(self, messages: List[Dict[str, str]]) -> None:
    self.conversation = []
    pending_user: Optional[str] = None
    for msg in messages:
      role = msg.get("role")
      content = str(msg.get("content", ""))
      if role == "user":
        pending_user = content
      elif role == "assistant" and pending_user is not None:
        self.conversation.append({"user": pending_user, "assistant": content})
        pending_user = None

  def export_conversation(self) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for entry in self.conversation:
      out.append({"role": "user", "content": entry["user"]})
      out.append({"role": "assistant", "content": entry["assistant"]})
    return out

  def _build_system_prompt(self) -> str:
    return SYSTEM_PROMPT.format(
      agent_name=AGENT_NAME,
      workspace=str(self.tools.workspace),
      tools_description=self.tools.describe_tools(),
      mode_name=self.mode.value,
      language_instructions=_LANGUAGE_BLOCK,
      mode_instructions=MODE_INSTRUCTIONS[self.mode],
    )

  def _conversation_window(self) -> List[Dict[str, str]]:
    if self.one_shot:
      return []
    return last_n(self.conversation, self.max_conversation_turns)

  def _select_max_new_tokens(self, pending: str) -> int:
    if self._force_full_new_tokens:
      return self.max_new_tokens
    blob = f"{self._original_task}\n{pending}"
    if _WRITE_HINT_RE.search(blob):
      return self.max_new_tokens
    for entry in self.history[-2:]:
      if "write_file" in entry.get("assistant", ""):
        return self.max_new_tokens
    return self.max_new_tokens_tool

  def _count_prompt_tokens(self, messages: List[Dict[str, str]]) -> int:
    prompt = self.tokenizer.apply_chat_template(
      messages,
      tokenize=False,
      add_generation_prompt=True,
    )
    return len(self.tokenizer.encode(prompt, add_special_tokens=False))

  def _fit_messages_to_context(
    self,
    messages: List[Dict[str, str]],
  ) -> List[Dict[str, str]]:
    budget = max(self.max_seq_length - 64, 256)
    fitted = list(messages)
    while len(fitted) > 3 and self._count_prompt_tokens(fitted) > budget:
      drop_at = 1
      if fitted[1].get("role") == "user" and "Tarefa:" in fitted[1].get("content", ""):
        if len(fitted) > 4 and fitted[2].get("role") == "assistant":
          drop_at = 2
        else:
          break
      if drop_at + 1 < len(fitted) - 1 and fitted[drop_at].get("role") == "user":
        del fitted[drop_at:drop_at + 2]
      else:
        break
    return fitted

  def _messages_for_turn(self, pending: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [
      {"role": "system", "content": self._build_system_prompt()},
    ]
    for entry in self._conversation_window():
      messages.append({"role": "user", "content": clip_chars(entry["user"], self.max_tool_output_chars)})
      messages.append({"role": "assistant", "content": clip_chars(entry["assistant"], self.max_tool_output_chars)})

    hist = last_n(self.history, self.max_history_steps)
    original = clip_chars(self._original_task, 500)
    has_original = any(entry.get("user") == self._original_task for entry in hist)
    if not hist:
      messages.append({"role": "user", "content": USER_TASK_PREFIX.format(task=pending)})
      return self._fit_messages_to_context(messages)

    if not has_original:
      messages.append({"role": "user", "content": USER_TASK_PREFIX.format(task=original)})
    for entry in hist:
      messages.append({
        "role": "user",
        "content": clip_chars(entry["user"], self.max_tool_output_chars),
      })
      messages.append({
        "role": "assistant",
        "content": clip_chars(entry["assistant"], self.max_tool_output_chars),
      })
    messages.append({
      "role": "user",
      "content": USER_TASK_PREFIX.format(
        task=clip_chars(pending, self.max_tool_output_chars)
      ),
    })
    return self._fit_messages_to_context(messages)

  def _generate(self, messages: List[Dict[str, str]], max_new_tokens: int) -> str:
    t0 = time.perf_counter()
    prompt = self.tokenizer.apply_chat_template(
      messages,
      tokenize=False,
      add_generation_prompt=True,
    )
    untrunc = self.tokenizer(prompt, return_tensors="pt", truncation=False)
    prompt_tokens_raw = int(untrunc["input_ids"].shape[1])
    truncated = prompt_tokens_raw > self.max_seq_length
    if truncated:
      inputs = self.tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=self.max_seq_length,
      )
    else:
      inputs = untrunc
    inputs = inputs.to(self.model.device)
    if torch.cuda.is_available():
      torch.cuda.synchronize()
    t_tokenize_ms = (time.perf_counter() - t0) * 1000.0
    prompt_tokens = int(inputs["input_ids"].shape[1])
    room = self.max_seq_length - prompt_tokens
    max_new = max(32, min(max_new_tokens, max(room - 8, 32)))

    gen_kwargs: Dict[str, Any] = {
      "max_new_tokens": max_new,
      "do_sample": self.temperature > 0,
      "pad_token_id": self.tokenizer.eos_token_id,
      "use_cache": True,
    }
    if gen_kwargs["do_sample"]:
      gen_kwargs["temperature"] = self.temperature
      gen_kwargs["top_p"] = 0.9

    if torch.cuda.is_available():
      torch.cuda.reset_peak_memory_stats()
      torch.cuda.synchronize()
    t1 = time.perf_counter()
    with torch.no_grad():
      with warnings.catch_warnings():
        warnings.filterwarnings(
          "ignore",
          message=".*max_new_tokens.*max_length.*",
        )
        outputs = self.model.generate(**inputs, **gen_kwargs)
    if torch.cuda.is_available():
      torch.cuda.synchronize()
    t_generate_ms = (time.perf_counter() - t1) * 1000.0
    new_tokens = int(outputs.shape[1] - prompt_tokens)
    tokens_per_s = (
      new_tokens / (t_generate_ms / 1000.0) if t_generate_ms > 0 else 0.0
    )
    vram = torch_vram_mb()
    self.last_generate = {
      "t_tokenize_ms": round(t_tokenize_ms, 2),
      "t_generate_ms": round(t_generate_ms, 2),
      "prompt_tokens": prompt_tokens,
      "prompt_tokens_raw": prompt_tokens_raw,
      "new_tokens": new_tokens,
      "tokens_per_s": round(tokens_per_s, 2),
      "truncated": truncated,
      "max_seq_length": self.max_seq_length,
      "max_new_tokens": max_new,
      "prompt_chars": len(prompt),
      **vram,
    }
    if new_tokens >= max_new:
      self._force_full_new_tokens = True

    return self.tokenizer.decode(
      outputs[0][prompt_tokens:],
      skip_special_tokens=True,
    ).strip()

  def _normalize_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(data.get("action", "")).strip().lower()
    if action_type in ALL_TOOL_NAMES:
      args = data.get("args") or {}
      if not isinstance(args, dict):
        args = {}
      for key, value in data.items():
        if key not in {"action", "tool", "args"} and key not in args:
          args[key] = value
      args = self._coerce_tool_args(action_type, args)
      return {"action": "tool", "tool": action_type, "args": args}
    if action_type == "tool":
      tool_name = str(data.get("tool", "")).strip()
      args = data.get("args") or {}
      if not isinstance(args, dict):
        args = {}
      data = {
        "action": "tool",
        "tool": tool_name,
        "args": self._coerce_tool_args(tool_name, args),
      }
    return data

  def _coerce_tool_args(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    lines = out.get("lines")
    if isinstance(lines, str):
      out["lines"] = lines.split("\n")
    if tool_name == "write_file" and not out.get("content") and not out.get("lines"):
      if "path" in out and len(out) == 1:
        pass
    return out

  def _recover_truncated(self, text: str) -> Optional[Dict[str, Any]]:
    tool_match = re.search(
      r'"tool"\s*:\s*"(write_file|replace_in_file|insert_lines|scaffold_php|run_command|read_file)"',
      text,
    )
    if not tool_match:
      kind_match = re.search(r'"kind"\s*:\s*"(\w+)"', text)
      if kind_match:
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
        path_match = re.search(r'"path"\s*:\s*"([^"]+)"', text)
        args: Dict[str, Any] = {"kind": kind_match.group(1)}
        if name_match:
          args["name"] = name_match.group(1)
        if path_match:
          args["path"] = path_match.group(1)
        return {"action": "tool", "tool": "scaffold_php", "args": args}
      return None
    tool_name = tool_match.group(1)
    path_match = re.search(r'"path"\s*:\s*"([^"]+)"', text)
    args: Dict[str, Any] = {}
    if path_match:
      args["path"] = path_match.group(1)
    recovered = self._recover_lines_array(text)
    if recovered:
      args["lines"] = recovered
      if tool_name == "write_file":
        args["mode"] = "append"
    if tool_name == "run_command":
      cmd = re.search(r'"command"\s*:\s*"([^"]*)', text)
      if cmd:
        args["command"] = cmd.group(1)
    if not args:
      return None
    return {"action": "tool", "tool": tool_name, "args": args}

  def _recover_lines_array(self, text: str) -> Optional[List[str]]:
    match = re.search(r'"lines"\s*:\s*\[', text)
    if not match:
      return None
    rest = text[match.end():]
    decoder = json.JSONDecoder()
    lines: List[str] = []
    idx = 0
    while idx < len(rest):
      while idx < len(rest) and rest[idx] in " \n\r\t,":
        idx += 1
      if idx >= len(rest) or rest[idx] == "]":
        break
      if rest[idx] != '"':
        break
      try:
        value, offset = decoder.raw_decode(rest[idx:])
      except json.JSONDecodeError:
        break
      lines.append(str(value))
      idx += max(offset, 1)
    return lines or None

  def _parse_action(self, text: str) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    found: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(text):
      start = text.find("{", idx)
      if start < 0:
        break
      try:
        data, offset = decoder.raw_decode(text[start:])
      except json.JSONDecodeError:
        idx = start + 1
        continue
      idx = start + max(offset, 1)
      if not isinstance(data, dict) or "action" not in data:
        continue
      found.append(self._normalize_action(data))
    if found:
      return found[-1]
    return self._recover_truncated(text)

  def _can_finish(self, task: str) -> Optional[str]:
    if _WRITE_TASK_RE.search(task) and self._proof_writes < 1:
      return (
        "Finish bloqueado: nenhum arquivo foi escrito nesta tarefa. "
        "Use scaffold_php ou replace_in_file, depois continue."
      )
    if _TEST_TASK_RE.search(task) and not self._tests_passed:
      return (
        "Finish bloqueado: a tarefa pede testes. "
        "Rode php artisan test e só finish se passarem."
      )
    if not self._last_tool_ok:
      return (
        "Finish bloqueado: a última tool falhou. "
        "Corrija com outra tool antes de finish."
      )
    return None

  def _emit_step(
    self,
    task: str,
    step: int,
    action_name: str,
    on_step: Optional[Callable[..., None]],
    detail: str,
  ) -> None:
    row = {
      "kind": "step",
      "task": task[:300],
      "step": step,
      "action": action_name,
      "history_len": len(self.history),
      "conversation_len": len(self.conversation),
      **self.last_generate,
    }
    if self.metrics is not None:
      self.metrics.record(row)
    if on_step:
      kind = action_name if action_name in {"parse_error", "finish", "tool"} else "tool"
      on_step(step, kind, detail, row)

  def run(self, task: str, on_step: Optional[Callable[..., None]] = None) -> str:
    self.history = []
    self._original_task = task
    self._force_full_new_tokens = False
    self._proof_writes = 0
    self._tests_passed = False
    self._last_tool_ok = True
    pending_context = task

    for step in range(1, self.max_iterations + 1):
      messages = self._messages_for_turn(pending_context)
      raw = self._generate(messages, self._select_max_new_tokens(pending_context))
      action = self._parse_action(raw)

      if action is None:
        self._emit_step(task, step, "parse_error", on_step, raw)
        pending_context = _PARSE_RETRY
        self.history.append({"user": pending_context, "assistant": "(parse_error)"})
        self._last_tool_ok = False
        continue

      action_type = action.get("action")

      if action_type == "finish":
        blocked = self._can_finish(task)
        if blocked:
          self._emit_step(task, step, "finish_blocked", on_step, blocked)
          pending_context = blocked
          self.history.append({
            "user": pending_context,
            "assistant": json.dumps({"action": "finish"}, ensure_ascii=False),
          })
          continue
        message = str(action.get("message", "")).strip()
        self._emit_step(task, step, "finish", on_step, message)
        final = message or raw
        self.conversation.append({"user": task, "assistant": final})
        if len(self.conversation) > 12:
          self.conversation = self.conversation[-12:]
        return final

      if action_type == "tool":
        tool_name = str(action.get("tool", ""))
        tool_args = action.get("args") or {}
        if not isinstance(tool_args, dict):
          tool_args = {}
        result = self.tools.run(tool_name, tool_args)
        self._last_tool_ok = result.success
        if result.success and tool_name in _PROOF_TOOLS:
          self._proof_writes += 1
        command = str(tool_args.get("command", "")).lower()
        if tool_name == "run_command" and ("artisan test" in command or "phpunit" in command):
          self._tests_passed = result.success
        clipped = clip_chars(result.output, self.max_tool_output_chars)
        detail = f"[{tool_name}] success={result.success}\n{clipped}"
        self._emit_step(task, step, tool_name, on_step, detail)
        assistant_json = json.dumps(action, ensure_ascii=False)
        user_feedback = (
          f"Resultado {tool_name}:\n{clipped}\n"
          "Continue com a próxima tool. Finish só se a tarefa estiver feita de verdade."
        )
        self.history.append({"user": pending_context, "assistant": assistant_json})
        pending_context = user_feedback
        continue

      pending_context = f"Ação desconhecida: {action_type}. Use tool ou finish."
      self._emit_step(task, step, "unknown", on_step, pending_context)
      self.history.append({
        "user": pending_context,
        "assistant": json.dumps({"action": action_type}),
      })

    if self.metrics is not None:
      self.metrics.record({
        "kind": "max_iterations",
        "task": task[:300],
        "steps": self.max_iterations,
        "history_len": len(self.history),
      })
    return (
      "Limite de iterações atingido. "
      "Revise o histórico e refine a tarefa."
    )
