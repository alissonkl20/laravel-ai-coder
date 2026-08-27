from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from utils.agent.agent import LaravelAgent
from utils.agent.preflight import (
  _extract_model_name,
  _is_login_task,
  _is_model_task,
)
from utils.agent.scaffold import apply_scaffold, column_to_php, fill_migration_text
from utils.agent.tools import ToolRegistry


class PreflightGapsTest(unittest.TestCase):
  def test_authorize_is_not_login(self) -> None:
    task = (
      "Crie Form Request StoreUrlRequest (url required). "
      "ERRO: StoreUrlRequest authorize=false e rules vazias."
    )
    self.assertFalse(_is_login_task(task))

  def test_implemente_is_not_model_scaffold(self) -> None:
    task = (
      "Implemente App\\Models\\ShortUrl com fillable e casts. "
      "Implemente App\\Services\\UrlShortenerService."
    )
    self.assertFalse(_is_model_task(task))
    self.assertEqual(_extract_model_name(task), "ShortUrl")

  def test_nao_crie_login_is_not_login(self) -> None:
    task = (
      "Implemente App\\Models\\Widget com fillable name,sku. "
      "Use scaffold_php kind=model. Não crie login."
    )
    self.assertFalse(_is_login_task(task))
    self.assertFalse(_is_model_task(task))

  def test_explicit_create_login_still_matches(self) -> None:
    self.assertTrue(_is_login_task("Crie login JSON com email e senha"))

  def test_explicit_make_model_still_works(self) -> None:
    task = "Crie um model Product com migration"
    self.assertTrue(_is_model_task(task))
    self.assertEqual(_extract_model_name(task), "Product")


class ScaffoldTest(unittest.TestCase):
  def test_char_unique_column(self) -> None:
    self.assertEqual(
      column_to_php("code:char:7:unique"),
      "$table->char('code', 7)->unique();",
    )

  def test_fill_migration_keeps_id_and_timestamps(self) -> None:
    stub = """<?php
use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('short_urls', function (Blueprint $table) {
            $table->id();
            $table->timestamps();
        });
    }
};
"""
    out = fill_migration_text(
      stub,
      "code:char:7:unique|original_url:text|hits:unsignedBigInteger:default:0",
    )
    self.assertIn("->char('code', 7)->unique()", out)
    self.assertIn("->text('original_url')", out)
    self.assertIn("->unsignedBigInteger('hits')->default(0)", out)

  def test_form_request_authorize_true(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      ok, msg = apply_scaffold(root, {
        "kind": "form_request",
        "name": "StoreUrlRequest",
        "rules": "url:required|url|max:2048",
      })
      self.assertTrue(ok, msg)
      text = (root / "app/Http/Requests/StoreUrlRequest.php").read_text()
      self.assertIn("return true;", text)
      self.assertIn("'url' => 'required|url|max:2048'", text)

  def test_ensure_api_bootstrap(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      boot = root / "bootstrap"
      boot.mkdir(parents=True)
      (boot / "app.php").write_text(
        "return Application::configure(basePath: dirname(__DIR__))\n"
        "    ->withRouting(\n"
        "        web: __DIR__.'/../routes/web.php',\n"
        "        commands: __DIR__.'/../routes/console.php',\n"
        "    )->create();\n",
        encoding="utf-8",
      )
      ok, msg = apply_scaffold(root, {"kind": "ensure_api"})
      self.assertTrue(ok, msg)
      text = (boot / "app.php").read_text()
      self.assertIn("routes/api.php", text)
      self.assertTrue((root / "routes/api.php").is_file())


class ToolsWriteLinesTest(unittest.TestCase):
  def test_write_file_lines(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      tools = ToolRegistry(Path(tmp), command_timeout=5)
      result = tools.run("write_file", {
        "path": "app/Demo.php",
        "lines": ["<?php", "", "echo 1;"],
      })
      self.assertTrue(result.success, result.output)
      text = (Path(tmp) / "app/Demo.php").read_text()
      self.assertEqual(text, "<?php\n\necho 1;\n")


class ParseAndFinishTest(unittest.TestCase):
  def _agent(self) -> LaravelAgent:
    agent = LaravelAgent.__new__(LaravelAgent)
    agent._proof_writes = 0
    agent._tests_passed = False
    agent._last_tool_ok = True
    return agent

  def test_parse_scaffold_json(self) -> None:
    agent = self._agent()
    raw = (
      '{"action":"tool","tool":"scaffold_php",'
      '"args":{"kind":"model","name":"ShortUrl",'
      '"fillable":"code,original_url"}}'
    )
    parsed = LaravelAgent._parse_action(agent, raw)
    self.assertEqual(parsed["tool"], "scaffold_php")
    self.assertEqual(parsed["args"]["name"], "ShortUrl")

  def test_recover_truncated_lines(self) -> None:
    agent = self._agent()
    raw = (
      '{"action":"tool","tool":"write_file","args":{"path":"app/Models/X.php",'
      '"lines":["<?php","namespace App\\\\Models;","class X"]'
    )
    parsed = LaravelAgent._parse_action(agent, raw)
    self.assertIsNotNone(parsed)
    self.assertEqual(parsed["tool"], "write_file")
    self.assertEqual(parsed["args"]["path"], "app/Models/X.php")
    self.assertGreaterEqual(len(parsed["args"]["lines"]), 2)

  def test_finish_blocked_without_writes(self) -> None:
    agent = self._agent()
    blocked = LaravelAgent._can_finish(
      agent,
      "Implemente App\\Models\\ShortUrl e rode os testes.",
    )
    self.assertIsNotNone(blocked)

  def test_finish_ok_after_write_and_tests(self) -> None:
    agent = self._agent()
    agent._proof_writes = 2
    agent._tests_passed = True
    blocked = LaravelAgent._can_finish(
      agent,
      "Escreva testes Feature e rode php artisan test.",
    )
    self.assertIsNone(blocked)


if __name__ == "__main__":
  unittest.main()
