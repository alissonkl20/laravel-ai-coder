"""Silencia stdout/stderr temporariamente (ex.: boot Unsloth/tqdm)."""

from __future__ import annotations

import os
import sys
import warnings
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def silenced_output(*, also_warnings: bool = True) -> Iterator[None]:
  """Redireciona fds 1/2 para /dev/null no bloco (inclui tqdm/C-extensions).

  Exceções ainda sobem; só a poluição visual some.
  """
  env_overrides = {
    "TRANSFORMERS_VERBOSITY": "error",
    "TRANSFORMERS_NO_ADVISORY_WARNINGS": "1",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "TQDM_DISABLE": "1",
    "TOKENIZERS_PARALLELISM": "false",
  }
  previous_env = {key: os.environ.get(key) for key in env_overrides}
  for key, value in env_overrides.items():
    os.environ[key] = value

  devnull_fd = os.open(os.devnull, os.O_WRONLY)
  saved_stdout = os.dup(1)
  saved_stderr = os.dup(2)
  sys.stdout.flush()
  sys.stderr.flush()

  try:
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)
    if also_warnings:
      with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield
    else:
      yield
  finally:
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(saved_stdout, 1)
    os.dup2(saved_stderr, 2)
    os.close(saved_stdout)
    os.close(saved_stderr)
    os.close(devnull_fd)
    for key, old in previous_env.items():
      if old is None:
        os.environ.pop(key, None)
      else:
        os.environ[key] = old
