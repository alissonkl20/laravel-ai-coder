from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_TYPE_METHODS = {
  "id": "id",
  "string": "string",
  "text": "text",
  "char": "char",
  "integer": "integer",
  "int": "integer",
  "unsignedinteger": "unsignedInteger",
  "unsignedbigint": "unsignedBigInteger",
  "unsignedbiginteger": "unsignedBigInteger",
  "bigint": "unsignedBigInteger",
  "boolean": "boolean",
  "bool": "boolean",
  "json": "json",
  "decimal": "decimal",
  "float": "float",
  "timestamp": "timestamp",
  "timestamps": "timestamps",
  "uuid": "uuid",
  "foreignid": "foreignId",
  "date": "date",
  "datetime": "dateTime",
}


def join_lines(lines: Any) -> str:
  if lines is None:
    return ""
  if isinstance(lines, str):
    return lines
  return "\n".join("" if item is None else str(item) for item in lines)


def parse_columns(spec: str) -> List[str]:
  if not spec.strip():
    return []
  chunks = [part.strip() for part in spec.split("|") if part.strip()]
  php: List[str] = []
  for chunk in chunks:
    php.append(column_to_php(chunk))
  return php


def column_to_php(spec: str) -> str:
  bits = [bit.strip() for bit in spec.split(":") if bit.strip()]
  if not bits:
    return "$table->string('col');"
  name = bits[0]
  typ = bits[1].lower() if len(bits) > 1 else "string"
  rest = bits[2:]
  method = _TYPE_METHODS.get(typ, typ)
  length: Optional[str] = None
  unique = False
  index = False
  nullable = False
  default: Optional[str] = None
  precision: Optional[str] = None
  idx = 0
  while idx < len(rest):
    token = rest[idx]
    low = token.lower()
    if low.isdigit() and length is None and method in {"char", "string"}:
      length = token
    elif low == "unique":
      unique = True
    elif low == "index":
      index = True
    elif low == "nullable":
      nullable = True
    elif low == "default" and idx + 1 < len(rest):
      default = rest[idx + 1]
      idx += 1
    elif low.startswith("default="):
      default = token.split("=", 1)[1]
    elif "-" in token and method == "decimal":
      precision = token.replace("-", ", ")
    idx += 1

  if method == "id":
    return "$table->id();"
  if method == "timestamps":
    return "$table->timestamps();"
  if method == "char" and length:
    call = f"$table->char('{name}', {length})"
  elif method == "string" and length:
    call = f"$table->string('{name}', {length})"
  elif method == "decimal":
    prec = precision or "8, 2"
    call = f"$table->decimal('{name}', {prec})"
  elif method == "foreignId":
    call = f"$table->foreignId('{name}')"
  else:
    call = f"$table->{method}('{name}')"
  if unique:
    call += "->unique()"
  if index:
    call += "->index()"
  if nullable:
    call += "->nullable()"
  if default is not None:
    call += f"->default({_php_default(default)})"
  if method == "foreignId":
    call += "->constrained()->cascadeOnDelete()"
  return call + ";"


def _php_default(value: str) -> str:
  low = value.lower()
  if low in {"true", "false", "null"}:
    return low
  if re.fullmatch(r"-?\d+(\.\d+)?", value):
    return value
  escaped = value.replace("\\", "\\\\").replace("'", "\\'")
  return f"'{escaped}'"


def _class_name(name: str) -> str:
  cleaned = name.strip().replace("\\", "/").split("/")[-1]
  cleaned = re.sub(r"\.php$", "", cleaned, flags=re.I)
  return cleaned


def _controller_parts(name: str) -> Tuple[str, str]:
  raw = name.strip().replace("\\", "/").removeprefix("App/Http/Controllers/")
  raw = re.sub(r"\.php$", "", raw, flags=re.I)
  parts = [p for p in raw.split("/") if p]
  class_name = parts[-1] if parts else "Controller"
  ns = "App\\Http\\Controllers"
  if len(parts) > 1:
    ns += "\\" + "\\".join(parts[:-1])
  return ns, class_name


def model_source(name: str, fillable: str = "", casts: str = "") -> str:
  class_name = _class_name(name)
  fields = [f.strip() for f in fillable.split(",") if f.strip()]
  if not fields:
    fields = ["name"]
  fill_block = ",\n        ".join(f"'{f}'" for f in fields)
  cast_pairs = [p.strip() for p in casts.split(",") if p.strip() and ":" in p]
  if cast_pairs:
    cast_lines = ",\n            ".join(
      f"'{k.strip()}': '{v.strip()}'" for k, v in (p.split(":", 1) for p in cast_pairs)
    )
    casts_fn = (
      "    protected function casts(): array\n"
      "    {\n"
      "        return [\n"
      f"            {cast_lines},\n"
      "        ];\n"
      "    }\n"
    )
  else:
    casts_fn = ""
  return (
    "<?php\n\n"
    "namespace App\\Models;\n\n"
    "use Illuminate\\Database\\Eloquent\\Model;\n\n"
    f"class {class_name} extends Model\n"
    "{\n"
    "    protected $fillable = [\n"
    f"        {fill_block},\n"
    "    ];\n"
    f"{chr(10) + casts_fn if casts_fn else ''}"
    "}\n"
  )


def form_request_source(name: str, rules: str = "") -> str:
  class_name = _class_name(name)
  rule_pairs = [p.strip() for p in rules.split(",") if p.strip() and ":" in p]
  if not rule_pairs:
    rule_pairs = ["name:required|string|max:255"]
  rule_lines = []
  for pair in rule_pairs:
    field, rule = pair.split(":", 1)
    rule_lines.append(f"            '{field.strip()}' => '{rule.strip()}',")
  rules_block = "\n".join(rule_lines)
  return (
    "<?php\n\n"
    "namespace App\\Http\\Requests;\n\n"
    "use Illuminate\\Foundation\\Http\\FormRequest;\n\n"
    f"class {class_name} extends FormRequest\n"
    "{\n"
    "    public function authorize(): bool\n"
    "    {\n"
    "        return true;\n"
    "    }\n\n"
    "    public function rules(): array\n"
    "    {\n"
    "        return [\n"
    f"{rules_block}\n"
    "        ];\n"
    "    }\n"
    "}\n"
  )


def service_source(name: str, model: str = "") -> str:
  class_name = _class_name(name)
  model_name = _class_name(model) if model else ""
  use_model = f"use App\\Models\\{model_name};\n" if model_name else ""
  return (
    "<?php\n\n"
    "namespace App\\Services;\n\n"
    f"{use_model}"
    "use Illuminate\\Support\\Facades\\Cache;\n\n"
    f"class {class_name}\n"
    "{\n"
    "    public function store(array $data): mixed\n"
    "    {\n"
    "        return $data;\n"
    "    }\n\n"
    "    public function find(string $key): mixed\n"
    "    {\n"
    "        return Cache::get($key);\n"
    "    }\n"
    "}\n"
  )


def api_controller_source(
  name: str,
  service: str = "",
  request: str = "",
  methods: str = "store,show",
) -> str:
  ns, class_name = _controller_parts(name)
  svc_class = _class_name(service) if service else ""
  req_class = _class_name(request) if request else "Request"
  use_svc = f"use App\\Services\\{svc_class};\n" if svc_class else ""
  use_req = (
    f"use App\\Http\\Requests\\{req_class};\n"
    if request
    else "use Illuminate\\Http\\Request;\n"
  )
  ctor = ""
  store_body = "        return response()->json($request->validated(), 201);"
  show_body = "        return response()->json(['id' => $id]);"
  redirect_fn = ""
  if svc_class:
    ctor = (
      f"    public function __construct(private {svc_class} $service)\n"
      "    {\n"
      "    }\n\n"
    )
    store_body = (
      "        $item = $this->service->store($request->validated());\n"
      "        return response()->json($item, 201);"
    )
    show_body = (
      "        $item = $this->service->find($id);\n"
      "        if ($item === null) {\n"
      "            abort(404);\n"
      "        }\n"
      "        return response()->json($item);"
    )
    if "redirect" in methods.lower():
      redirect_fn = (
        "\n    public function redirect(string $code)\n"
        "    {\n"
        "        $url = $this->service->find($code);\n"
        "        if ($url === null) {\n"
        "            abort(404);\n"
        "        }\n"
        "        $target = is_object($url) && isset($url->original_url)"
        " ? $url->original_url : (string) $url;\n"
        "        return redirect()->away($target);\n"
        "    }\n"
      )
  store_arg = req_class if request else "Request"
  wanted = {m.strip().lower() for m in methods.split(",") if m.strip()}
  fns = []
  if "store" in wanted:
    fns.append(
      f"    public function store({store_arg} $request): JsonResponse\n"
      "    {\n"
      f"{store_body}\n"
      "    }"
    )
  if "show" in wanted:
    fns.append(
      "    public function show(string $id): JsonResponse\n"
      "    {\n"
      f"{show_body}\n"
      "    }"
    )
  body = "\n\n".join(fns)
  return (
    "<?php\n\n"
    f"namespace {ns};\n\n"
    "use App\\Http\\Controllers\\Controller;\n"
    f"{use_req}{use_svc}"
    "use Illuminate\\Http\\JsonResponse;\n\n"
    f"class {class_name} extends Controller\n"
    "{\n"
    f"{ctor}{body}\n"
    f"{redirect_fn}"
    "}\n"
  )


def feature_test_source(
  name: str,
  post_path: str = "/api/v1/urls",
  post_body: str = "['url' => 'https://example.com']",
  post_status: str = "201",
  invalid_body: str = "['url' => 'not-a-url']",
  invalid_status: str = "422",
  get_path: str = "",
  get_status: str = "302",
  missing_path: str = "/zzzzzzz",
  missing_status: str = "404",
) -> str:
  class_name = _class_name(name)
  if not class_name.endswith("Test"):
    class_name += "Test"
  status_map = {"201": "assertCreated()", "200": "assertOk()", "422": "assertUnprocessable()"}
  post_assert = status_map.get(post_status, f"assertStatus({post_status})")
  invalid_assert = status_map.get(invalid_status, f"assertStatus({invalid_status})")
  get_block = ""
  if get_path:
    get_block = f"""
    public function test_show_or_redirect(): void
    {{
        $created = $this->postJson('{post_path}', {post_body});
        $created->{post_assert};
        $code = $created->json('code') ?? $created->json('id');
        $this->get('/' . $code)->assertStatus({get_status});
    }}
"""
  return (
    "<?php\n\n"
    "namespace Tests\\Feature;\n\n"
    "use Illuminate\\Foundation\\Testing\\RefreshDatabase;\n"
    "use Tests\\TestCase;\n\n"
    f"class {class_name} extends TestCase\n"
    "{\n"
    "    use RefreshDatabase;\n\n"
    "    public function test_store_creates_resource(): void\n"
    "    {\n"
    f"        $this->postJson('{post_path}', {post_body})->{post_assert};\n"
    "    }\n\n"
    "    public function test_store_rejects_invalid_payload(): void\n"
    "    {\n"
    f"        $this->postJson('{post_path}', {invalid_body})->{invalid_assert};\n"
    "    }\n"
    f"{get_block}"
    "    public function test_missing_resource_is_not_found(): void\n"
    "    {\n"
    f"        $this->get('{missing_path}')->assertStatus({missing_status});\n"
    "    }\n"
    "}\n"
  )


def fill_migration_text(existing: str, columns: str) -> str:
  php_cols = parse_columns(columns)
  has_id = any("->id(" in line for line in php_cols)
  has_ts = any("timestamps(" in line for line in php_cols)
  inner = []
  if not has_id:
    inner.append("            $table->id();")
  for line in php_cols:
    inner.append(f"            {line}")
  if not has_ts:
    inner.append("            $table->timestamps();")
  inner_block = "\n".join(inner)
  pattern = re.compile(
    r"(Schema::create\([^,]+,\s*function\s*\(Blueprint\s+\$table\)\s*\{)(.*?)(\n\s*\}\);)",
    re.DOTALL,
  )
  if pattern.search(existing):
    return pattern.sub(rf"\1\n{inner_block}\3", existing, count=1)
  return existing


def ensure_api_bootstrap(text: str) -> str:
  if "routes/api.php" in text:
    return text
  marker = "web: __DIR__.'/../routes/web.php',"
  if marker not in text:
    return text
  return text.replace(
    marker,
    marker + "\n        api: __DIR__.'/../routes/api.php',",
    1,
  )


def api_routes_stub() -> str:
  return "<?php\n\nuse Illuminate\\Support\\Facades\\Route;\n"


def append_route(existing: str, method: str, uri: str, action: str) -> str:
  method = method.lower().strip()
  if method not in {"get", "post", "put", "patch", "delete", "any"}:
    method = "get"
  line = f"Route::{method}('{uri}', {action});"
  if line in existing:
    return existing
  if "Illuminate\\Support\\Facades\\Route" not in existing:
    existing = "<?php\n\nuse Illuminate\\Support\\Facades\\Route;\n\n" + existing.lstrip()
  if not existing.endswith("\n"):
    existing += "\n"
  return existing + line + "\n"


def apply_scaffold(workspace: Path, args: Dict[str, Any]) -> Tuple[bool, str]:
  kind = str(args.get("kind", "")).strip().lower()
  name = str(args.get("name") or args.get("path") or "").strip()
  if not kind:
    return False, "kind obrigatório: model|fill_migration|form_request|service|api_controller|feature_test|ensure_api|add_route"

  if kind == "model":
    rel = f"app/Models/{_class_name(name)}.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      model_source(name, str(args.get("fillable") or ""), str(args.get("casts") or "")),
      encoding="utf-8",
    )
    return True, f"Escrito {rel}"

  if kind == "fill_migration":
    rel = str(args.get("path") or "")
    if not rel:
      return False, "path da migration obrigatório"
    path = workspace / rel
    if not path.is_file():
      return False, f"Arquivo não encontrado: {rel}"
    updated = fill_migration_text(path.read_text(encoding="utf-8"), str(args.get("columns") or ""))
    path.write_text(updated, encoding="utf-8")
    return True, f"Migration preenchida: {rel}"

  if kind == "form_request":
    rel = f"app/Http/Requests/{_class_name(name)}.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      form_request_source(name, str(args.get("rules") or "")),
      encoding="utf-8",
    )
    return True, f"Escrito {rel}"

  if kind == "service":
    rel = f"app/Services/{_class_name(name)}.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      service_source(name, str(args.get("model") or "")),
      encoding="utf-8",
    )
    return True, f"Escrito {rel}"

  if kind == "api_controller":
    ns, class_name = _controller_parts(name)
    sub = ns.replace("App\\Http\\Controllers", "app/Http/Controllers").replace("\\", "/")
    rel = f"{sub}/{class_name}.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      api_controller_source(
        name,
        service=str(args.get("service") or ""),
        request=str(args.get("request") or ""),
        methods=str(args.get("methods") or "store,show"),
      ),
      encoding="utf-8",
    )
    return True, f"Escrito {rel}"

  if kind == "feature_test":
    class_name = _class_name(name)
    if not class_name.endswith("Test"):
      class_name += "Test"
    rel = f"tests/Feature/{class_name}.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
      feature_test_source(
        class_name,
        post_path=str(args.get("post_path") or "/api/v1/urls"),
        post_body=str(args.get("post_body") or "['url' => 'https://example.com']"),
        post_status=str(args.get("post_status") or "201"),
        invalid_body=str(args.get("invalid_body") or "['url' => 'not-a-url']"),
        invalid_status=str(args.get("invalid_status") or "422"),
        get_path=str(args.get("get_path") or ""),
        get_status=str(args.get("get_status") or "302"),
        missing_path=str(args.get("missing_path") or "/zzzzzzz"),
        missing_status=str(args.get("missing_status") or "404"),
      ),
      encoding="utf-8",
    )
    return True, f"Escrito {rel}"

  if kind == "ensure_api":
    log: List[str] = []
    bootstrap = workspace / "bootstrap" / "app.php"
    if bootstrap.is_file():
      updated = ensure_api_bootstrap(bootstrap.read_text(encoding="utf-8"))
      bootstrap.write_text(updated, encoding="utf-8")
      log.append("bootstrap/app.php api")
    api = workspace / "routes" / "api.php"
    api.parent.mkdir(parents=True, exist_ok=True)
    if not api.is_file():
      api.write_text(api_routes_stub(), encoding="utf-8")
      log.append("routes/api.php criado")
    else:
      log.append("routes/api.php já existe")
    return True, "; ".join(log)

  if kind == "add_route":
    file_key = str(args.get("route_file") or "api").lower()
    rel = "routes/web.php" if file_key == "web" else "routes/api.php"
    path = workspace / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
      path.write_text(api_routes_stub(), encoding="utf-8")
    method = str(args.get("method") or "get")
    uri = str(args.get("uri") or "/")
    action = str(args.get("action") or "")
    if not action:
      return False, "action obrigatório (ex: [App\\\\Http\\\\Controllers\\\\Api\\\\UrlController::class, 'store'])"
    path.write_text(append_route(path.read_text(encoding="utf-8"), method, uri, action), encoding="utf-8")
    return True, f"Rota adicionada em {rel}"

  return False, f"kind desconhecido: {kind}"
