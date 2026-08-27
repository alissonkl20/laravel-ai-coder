from __future__ import annotations

import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = "http://127.0.0.1:8000"
TIMEOUT = 10


class NoRedirect(HTTPRedirectHandler):
  def redirect_request(self, *args: Any, **kwargs: Any) -> None:
    return None


_OPENER = build_opener(NoRedirect)


def percentiles(samples: List[float]) -> Dict[str, float]:
  if not samples:
    return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
  ordered = sorted(samples)
  def at(p: float) -> float:
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 2)
  return {"p50": at(50), "p95": at(95), "p99": at(99)}


def request(method: str, path: str, body: bytes | None = None) -> Dict[str, Any]:
  headers = {"Accept": "application/json"}
  if body is not None:
    headers["Content-Type"] = "application/json"
  req = Request(BASE + path, data=body, headers=headers, method=method)
  started = time.perf_counter()
  try:
    with _OPENER.open(req, timeout=TIMEOUT) as response:
      payload = response.read()
      ms = (time.perf_counter() - started) * 1000.0
      return {
        "ok": True,
        "status": int(response.status),
        "ms": ms,
        "body": payload[:300],
        "error": None,
      }
  except HTTPError as exc:
    ms = (time.perf_counter() - started) * 1000.0
    status = int(exc.code)
    return {
      "ok": status < 500,
      "status": status,
      "ms": ms,
      "body": exc.read()[:300],
      "error": None if status < 500 else f"http_{status}",
    }
  except URLError as exc:
    ms = (time.perf_counter() - started) * 1000.0
    return {"ok": False, "status": 0, "ms": ms, "body": b"", "error": str(exc.reason)}
  except Exception as exc:
    ms = (time.perf_counter() - started) * 1000.0
    return {"ok": False, "status": 0, "ms": ms, "body": b"", "error": str(exc)}


def summarize(name: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
  statuses: Dict[str, int] = {}
  errors = 0
  timeout_like = 0
  server_err = 0
  latencies = []
  for row in rows:
    status = str(row["status"])
    statuses[status] = statuses.get(status, 0) + 1
    latencies.append(row["ms"])
    err = row.get("error")
    if row["status"] >= 500 or row["status"] == 0:
      errors += 1
      server_err += 1 if row["status"] >= 500 else 0
    if err and ("timed out" in err.lower() or "timeout" in err.lower()):
      timeout_like += 1
  return {
    "name": name,
    "n": len(rows),
    "statuses": statuses,
    "error_rate_5xx_or_conn": round(errors / len(rows), 4) if rows else 0,
    "timeouts": timeout_like,
    "server_err": server_err,
    **percentiles(latencies),
    "mean_ms": round(statistics.fmean(latencies), 2) if latencies else 0,
  }


def burst_a() -> tuple[Dict[str, Any], str]:
  def one(i: int) -> Dict[str, Any]:
    payload = json.dumps({"url": f"https://stress.example/{i}-{uuid.uuid4()}"}).encode()
    return request("POST", "/api/v1/urls", payload)
  with ThreadPoolExecutor(max_workers=40) as pool:
    rows = list(pool.map(one, range(200)))
  code = ""
  for row in rows:
    if row["status"] == 201:
      try:
        code = json.loads(row["body"].decode()).get("code") or code
      except Exception:
        pass
  return summarize("burst_a_post_200", rows), code


def burst_b(code: str) -> Dict[str, Any]:
  def one(_: int) -> Dict[str, Any]:
    return request("GET", f"/{code}")
  with ThreadPoolExecutor(max_workers=50) as pool:
    rows = list(pool.map(one, range(500)))
  return summarize("burst_b_get_500", rows)


def burst_c(hot_code: str) -> Dict[str, Any]:
  def job(kind: str, i: int) -> Dict[str, Any]:
    if kind == "post":
      payload = json.dumps({"url": f"https://mix.example/{i}-{uuid.uuid4()}"}).encode()
      return request("POST", "/api/v1/urls", payload)
    return request("GET", f"/{hot_code}")
  tasks = [("post", i) for i in range(100)] + [("get", i) for i in range(400)]
  rows: List[Dict[str, Any]] = []
  with ThreadPoolExecutor(max_workers=50) as pool:
    futs = [pool.submit(job, kind, i) for kind, i in tasks]
    for fut in as_completed(futs):
      rows.append(fut.result())
  return summarize("burst_c_mixed_500", rows)


def main() -> None:
  t0 = time.perf_counter()
  a_summary, code = burst_a()
  if not code:
    probe = request("POST", "/api/v1/urls", json.dumps({"url": "https://hot.example/b"}).encode())
    code = json.loads(probe["body"].decode())["code"]
  b_summary = burst_b(code)
  c_summary = burst_c(code)
  out = {
    "elapsed_s": round(time.perf_counter() - t0, 2),
    "hot_code": code,
    "bursts": [a_summary, b_summary, c_summary],
  }
  print(json.dumps(out, indent=2))


if __name__ == "__main__":
  main()
