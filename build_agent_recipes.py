"""Receitas SFT: tool-calling E2E (JSON curto, sem PHP longo)."""

from __future__ import annotations

import json
from pathlib import Path


def tool(tool_name: str, **args: object) -> str:
  return json.dumps({"action": "tool", "tool": tool_name, "args": args}, ensure_ascii=False)


def finish(message: str) -> str:
  return json.dumps({"action": "finish", "message": message}, ensure_ascii=False)


RECIPES: list[dict[str, str]] = [
  {
    "instruction": "Tarefa: ler routes/web.php antes de editar.",
    "output": tool("read_file", path="routes/web.php"),
  },
  {
    "instruction": "Tarefa: listar controllers do projeto.",
    "output": tool("list_dir", path="app/Http/Controllers"),
  },
  {
    "instruction": "Tarefa: buscar no índice fillable Eloquent e Form Request.",
    "output": tool("search", query="model fillable form request authorize true"),
  },
  {
    "instruction": "Tarefa: gerar model Product com migration.",
    "output": tool("run_command", command="php artisan make:model Product -m"),
  },
  {
    "instruction": "Tarefa: gerar controller Api/ProductController.",
    "output": tool("run_command", command="php artisan make:controller Api/ProductController --api"),
  },
  {
    "instruction": "Tarefa: gerar Form Request StoreProductRequest.",
    "output": tool("run_command", command="php artisan make:request StoreProductRequest"),
  },
  {
    "instruction": "Tarefa: listar rotas.",
    "output": tool("run_command", command="php artisan route:list"),
  },
  {
    "instruction": "Tarefa: rodar migrations.",
    "output": tool("run_command", command="php artisan migrate --force"),
  },
  {
    "instruction": "Tarefa: rodar a suíte de testes.",
    "output": tool("run_command", command="php artisan test"),
  },
  {
    "instruction": "Tarefa: ver o log Laravel.",
    "output": tool("tail_log", lines=80),
  },
  {
    "instruction": "Erro: resposta inválida, use action tool ou finish.",
    "output": tool("read_file", path="app/Models/Product.php"),
  },
  {
    "instruction": "JSON inválido. Um objeto tool ou finish.",
    "output": tool("read_file", path="routes/api.php"),
  },
  {
    "instruction": "Resultado write_file: JSON inválido/cortado. Continue.",
    "output": tool("scaffold_php", kind="model", name="Product", fillable="name,price", casts="price:decimal"),
  },
  {
    "instruction": "Tarefa: implementar App\\Models\\Product com fillable. Não recrie o model.",
    "output": tool("scaffold_php", kind="model", name="Product", fillable="name,sku,price", casts="price:decimal"),
  },
  {
    "instruction": "Implemente App\\Models\\ShortUrl com fillable e casts.",
    "output": tool(
      "scaffold_php",
      kind="model",
      name="ShortUrl",
      fillable="code,original_url,url_hash,hits",
      casts="hits:integer",
    ),
  },
  {
    "instruction": "Preencha a migration de short_urls: code char 7 unique, original_url text, url_hash char 64 index, hits unsignedBigInteger default 0.",
    "output": tool(
      "scaffold_php",
      kind="fill_migration",
      path="database/migrations/2026_01_01_000000_create_short_urls_table.php",
      columns="code:char:7:unique|original_url:text|url_hash:char:64:index|hits:unsignedBigInteger:default:0",
    ),
  },
  {
    "instruction": "Crie Form Request StoreUrlRequest (url required, url, max:2048). authorize deve ser true.",
    "output": tool(
      "scaffold_php",
      kind="form_request",
      name="StoreUrlRequest",
      rules="url:required|url|max:2048",
    ),
  },
  {
    "instruction": "StoreUrlRequest authorize=false e rules vazias. Corrija sem criar login.",
    "output": tool(
      "scaffold_php",
      kind="form_request",
      name="StoreUrlRequest",
      rules="url:required|url|max:2048",
    ),
  },
  {
    "instruction": "Registre rotas API no Laravel 11+ (bootstrap/app.php).",
    "output": tool("scaffold_php", kind="ensure_api"),
  },
  {
    "instruction": "Adicione POST /urls no api.php para UrlController@store.",
    "output": tool(
      "scaffold_php",
      kind="add_route",
      route_file="api",
      method="post",
      uri="/urls",
      action="[App\\Http\\Controllers\\Api\\UrlController::class, 'store']",
    ),
  },
  {
    "instruction": "Em routes/web.php GET /{code} redirect 302.",
    "output": tool(
      "scaffold_php",
      kind="add_route",
      route_file="web",
      method="get",
      uri="/{code}",
      action="[App\\Http\\Controllers\\Api\\UrlController::class, 'redirect']",
    ),
  },
  {
    "instruction": "Gere Api/UrlController store 201 e show, injetando UrlShortenerService.",
    "output": tool(
      "scaffold_php",
      kind="api_controller",
      name="Api/UrlController",
      service="UrlShortenerService",
      request="StoreUrlRequest",
      methods="store,show,redirect",
    ),
  },
  {
    "instruction": "Crie o service UrlShortenerService (classe base).",
    "output": tool("scaffold_php", kind="service", name="UrlShortenerService", model="ShortUrl"),
  },
  {
    "instruction": "Escreva testes Feature: POST cria, inválida 422, GET 302, missing 404.",
    "output": tool(
      "scaffold_php",
      kind="feature_test",
      name="UrlShortenerTest",
      post_path="/api/v1/urls",
      post_body="['url' => 'https://example.com']",
      post_status="201",
      get_path="/{code}",
      get_status="302",
      missing_path="/zzzzzzz",
      missing_status="404",
    ),
  },
  {
    "instruction": "Resultado scaffold_php: Escrito tests/Feature/UrlShortenerTest.php. Continue.",
    "output": tool("run_command", command="php artisan test"),
  },
  {
    "instruction": "Resultado run_command:\n[exit 0]\nTests: 4 passed (8 assertions)\nContinue ou finish.",
    "output": finish("Testes verdes: POST 201, 422, redirect 302, missing 404."),
  },
  {
    "instruction": "Resultado run_command:\n[exit 1]\nFAIL tests/Feature/UrlShortenerTest.php\nContinue ou finish.",
    "output": tool("read_file", path="tests/Feature/UrlShortenerTest.php"),
  },
  {
    "instruction": "Tarefa: escrever testes e finish só com testes verdes. Ainda não rodou php artisan test.",
    "output": tool("run_command", command="php artisan test"),
  },
]


_MODELS = [
  ("Product", "name,sku,price", "price:decimal", "name:string|sku:string:unique|price:decimal:8-2"),
  ("Order", "number,total,status", "total:decimal", "number:string:unique|total:decimal:10-2|status:string"),
  ("Invoice", "number,amount,paid", "paid:boolean,amount:decimal", "number:string:unique|amount:decimal:10-2|paid:boolean:default:false"),
  ("Link", "code,target,hits", "hits:integer", "code:char:7:unique|target:text|hits:unsignedBigInteger:default:0"),
  ("Category", "name,slug", "", "name:string|slug:string:unique"),
]

for model, fillable, casts, columns in _MODELS:
  snake = "".join(["_" + c.lower() if c.isupper() else c for c in model]).lstrip("_")
  table = snake + "s"
  RECIPES.append({
    "instruction": f"Tarefa: CRUD {model}. Passo 1 — gerar model com migration.",
    "output": tool("run_command", command=f"php artisan make:model {model} -m"),
  })
  RECIPES.append({
    "instruction": f"Resultado run_command: Model created. Migration database/migrations/2026_01_01_000000_create_{table}_table.php",
    "output": tool("scaffold_php", kind="model", name=model, fillable=fillable, casts=casts),
  })
  RECIPES.append({
    "instruction": f"Preencha a migration de {table} com {columns}.",
    "output": tool(
      "scaffold_php",
      kind="fill_migration",
      path=f"database/migrations/2026_01_01_000000_create_{table}_table.php",
      columns=columns,
    ),
  })
  RECIPES.append({
    "instruction": f"Resultado scaffold_php: Migration preenchida. Continue.",
    "output": tool("run_command", command="php artisan migrate --force"),
  })
  RECIPES.append({
    "instruction": f"Tarefa: CRUD {model}. Gerar controller API.",
    "output": tool("run_command", command=f"php artisan make:controller Api/{model}Controller --api"),
  })
  RECIPES.append({
    "instruction": f"Crie Form Request Store{model}Request.",
    "output": tool(
      "scaffold_php",
      kind="form_request",
      name=f"Store{model}Request",
      rules="name:required|string|max:255",
    ),
  })
  RECIPES.append({
    "instruction": f"Implemente App\\Http\\Controllers\\Api\\{model}Controller store/show.",
    "output": tool(
      "scaffold_php",
      kind="api_controller",
      name=f"Api/{model}Controller",
      request=f"Store{model}Request",
      methods="store,show",
    ),
  })
  RECIPES.append({
    "instruction": f"Escreva teste Feature para {model} API.",
    "output": tool(
      "scaffold_php",
      kind="feature_test",
      name=f"{model}ApiTest",
      post_path=f"/api/v1/{table}",
      post_body="['name' => 'demo']",
      post_status="201",
    ),
  })
  RECIPES.append({
    "instruction": f"Tarefa concluída: CRUD {model} com rotas api e testes verdes.",
    "output": finish(f"CRUD {model} pronto: model, migration, controller API, Form Request e testes."),
  })

RECIPES.extend([
  {
    "instruction": "Como registrar api no Laravel 11 bootstrap/app.php?",
    "output": (
      "Em bootstrap/app.php, withinRouting deve ter:\n"
      "web: __DIR__.'/../routes/web.php',\n"
      "api: __DIR__.'/../routes/api.php',\n"
      "Depois use scaffold_php kind=ensure_api."
    ),
  },
  {
    "instruction": "Como evitar N+1 em listagem de posts com autor?",
    "output": "Use eager loading: Post::with('author')->paginate(15);",
  },
  {
    "instruction": "Como cachear lookup por code sem query no hit?",
    "output": (
      "Cache::remember('url:'.$code, 3600, fn () => ShortUrl::query()->where('code', $code)->first());\n"
      "Increment de hits: ShortUrl::where('code', $code)->increment('hits'); "
      "ou dispatch()->afterResponse() para não bloquear o 302."
    ),
  },
  {
    "instruction": "Otimize o hot path de redirect: cache hit sem query; miss por code indexado; 302; hits sem bloquear.",
    "output": tool("read_file", path="app/Services/UrlShortenerService.php"),
  },
  {
    "instruction": "Resultado read_file: service sem cache. Continue.",
    "output": tool(
      "replace_in_file",
      path="app/Services/UrlShortenerService.php",
      old_text="return ShortUrl::query()->where('code', $code)->first();",
      new_text="return Cache::remember('url:'.$code, 3600, fn () => ShortUrl::query()->where('code', $code)->first());",
    ),
  },
  {
    "instruction": "Qual JSON usar para scaffold de model?",
    "output": tool("scaffold_php", kind="model", name="Person", fillable="name,age", casts="age:integer"),
  },
  {
    "instruction": "Qual JSON usar para editar um trecho único?",
    "output": tool(
      "replace_in_file",
      path="app/Http/Requests/StoreUrlRequest.php",
      old_text="return false;",
      new_text="return true;",
    ),
  },
  {
    "instruction": "write_file com PHP longo quebrou o JSON. O que fazer?",
    "output": tool("scaffold_php", kind="form_request", name="StoreUrlRequest", rules="url:required|url|max:2048"),
  },
  {
    "instruction": "Não finish: nenhum arquivo foi escrito nesta tarefa.",
    "output": tool("scaffold_php", kind="ensure_api"),
  },
  {
    "instruction": "Finish bloqueado: a tarefa pede testes. Rode php artisan test.",
    "output": tool("run_command", command="php artisan test"),
  },
  {
    "instruction": "Implemente a classe ShortUrl — isso NÃO é dump do framework. Use tool.",
    "output": tool("read_file", path="app/Models/ShortUrl.php"),
  },
  {
    "instruction": "Crie um model chamado Invoice (intenção explícita).",
    "output": tool("run_command", command="php artisan make:model Invoice -m"),
  },
])

_AUTH = [
  (
    "Tarefa: login API — gerar AuthController.",
    tool("run_command", command="php artisan make:controller AuthController"),
  ),
  (
    "Tarefa: login JSON com email e senha. Não misturar com Form Request de URL.",
    tool("run_command", command="php artisan make:controller AuthController"),
  ),
]
for inst, out in _AUTH:
  RECIPES.append({"instruction": inst, "output": out})

_ALIASES = [
  ("read_file", {"path": "bootstrap/app.php"}),
  ("list_dir", {"path": "app/Services"}),
  ("grep", {"pattern": "Route::", "path": "routes"}),
  ("run_command", {"command": "php artisan migrate:status"}),
  ("scaffold_php", {"kind": "ensure_api"}),
]
for name, args in _ALIASES:
  RECIPES.append({
    "instruction": f"Use a ferramenta {name} agora.",
    "output": tool(name, **args),
  })

_PREFIXES = [
  "Tarefa: ",
  "No projeto Laravel: ",
  "Agent, execute: ",
  "Continue a tarefa: ",
]
_CORE = [row for row in RECIPES if row["output"].startswith("{")]
for prefix in _PREFIXES:
  for row in list(_CORE):
    inst = row["instruction"]
    if inst.startswith(prefix):
      continue
    RECIPES.append({"instruction": prefix + inst, "output": row["output"]})


def main() -> None:
  out = Path(__file__).parent / "data" / "agent_recipes.jsonl"
  out.parent.mkdir(parents=True, exist_ok=True)
  with out.open("w", encoding="utf-8") as fh:
    for row in RECIPES:
      fh.write(json.dumps(row, ensure_ascii=False) + "\n")
  print(f"Receitas do agent: {len(RECIPES)} exemplos → {out}")


if __name__ == "__main__":
  main()
