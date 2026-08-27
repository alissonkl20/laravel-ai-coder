# Ferramentas — Laravel Best Practices

Comandos, ferramentas de debug e como interpretar resultados no ecossistema DRAXY + Laravel.

---

## 1. Agent CLI (DRAXY)

### Inicialização

```bash
cd laravel-ai-coder
source .venv/bin/activate
python agent_cli.py -p <projeto>    # projeto em ~/Documentos
python agent_cli.py -w /caminho/completo
./initial.sh <projeto>
```

### Modos

| Comando | Efeito |
|---------|--------|
| `/mode ask` | Somente leitura |
| `/mode plan` | Planeja sem editar |
| `/mode agent` | Executa com aprovação |
| `execute` / `sim` | Em plan: aprova e executa plano |

### Atalhos integrados

| Atalho | Ação |
|--------|------|
| `/model Product` | Scaffold model + migration |
| `/migration create_x_table` | Gera migration |
| `/controller FooController` | Gera controller |
| `/artisan route:list` | Roda artisan |
| `/log` | Últimas linhas de laravel.log |
| `/search query` | Busca indexada |
| `/ls app/Models` | Lista diretório |
| `/new-project my-app` | Cria Laravel em Documentos |
| `/project my-app` | Troca workspace |

### Ferramentas internas (JSON)

```json
{"action": "tool", "tool": "read_file", "args": {"path": "routes/api.php"}}
{"action": "tool", "tool": "grep", "args": {"pattern": "Route::", "path": "routes"}}
{"action": "tool", "tool": "run_command", "args": {"command": "php artisan route:list"}}
{"action": "tool", "tool": "write_file", "args": {"path": "...", "content": "..."}}
{"action": "tool", "tool": "tail_log", "args": {"lines": 100}}
{"action": "tool", "tool": "search", "args": {"query": "fillable casts"}}
{"action": "finish", "message": "Resumo das alterações..."}
```

### Interpretar saída do agent

| Saída | Significado |
|-------|-------------|
| `── step N · ferramenta ──` | Tool executada neste passo |
| `── aprovação · write_file ──` | Aguardando y/n do usuário |
| `JSON inválido, retentando` | Modelo não seguiu formato; retry automático |
| `Limite de iterações` | Aumente `AGENT_MAX_ITERATIONS` ou simplifique tarefa |
| `[exit 1]` em run_command | Comando falhou; leia stderr |

---

## 2. Artisan — comandos essenciais

### Scaffolding

```bash
php artisan make:model Product -m          # Model + migration
php artisan make:controller ProductController --api
php artisan make:request StoreProductRequest
php artisan make:resource ProductResource
php artisan make:policy ProductPolicy --model=Product
php artisan make:seeder ProductSeeder
php artisan make:factory ProductFactory
php artisan make:migration create_products_table
php artisan make:event OrderPlaced
php artisan make:listener SendConfirmation --event=OrderPlaced
```

### Database

```bash
php artisan migrate                        # Aplica migrations
php artisan migrate:status                 # Status
php artisan migrate:rollback               # Desfaz último batch
php artisan migrate:fresh --seed           # ⚠️ apaga tudo + seed
php artisan db:seed                        # Roda seeders
```

### Cache e otimização

```bash
php artisan config:clear
php artisan cache:clear
php artisan route:clear
php artisan view:clear
php artisan optimize:clear                 # Limpa tudo (dev)
php artisan config:cache                   # Produção
php artisan route:cache                    # Produção
```

### Inspeção

```bash
php artisan route:list
php artisan route:list --path=api
php artisan about
php artisan model:show Product
php artisan tinker                         # REPL (cuidado em prod)
```

### Testes

```bash
php artisan test
php artisan test --filter=ProductTest
php artisan test --parallel
```

---

## 3. Composer

```bash
composer install
composer require laravel/sanctum
composer dump-autoload
composer test                              # se script definido
vendor/bin/pint                            # formatação PSR-12
```

---

## 4. Debug PHP/Laravel

### dump / dd

| Função | Comportamento |
|--------|---------------|
| `dump($x)` | Exibe e continua |
| `dd($x)` | Exibe e para (die) |
| `ray($x)` | Se spatie/ray instalado |

### Log facade

```php
use Illuminate\Support\Facades\Log;

Log::debug('message', ['key' => 'value']);
Log::error('failed', ['exception' => $e->getMessage()]);
```

Níveis: `emergency`, `alert`, `critical`, `error`, `warning`, `notice`, `info`, `debug`

Config: `config/logging.php`, canal default em `LOG_CHANNEL` (.env)

### laravel.log

Local: `storage/logs/laravel.log`

```bash
tail -n 80 storage/logs/laravel.log
grep -i "error" storage/logs/laravel.log | tail -20
```

Interpretação:

- `Stack trace` → origem do erro (arquivo:linha)
- `SQLSTATE` → problema de DB (constraint, coluna, conexão)
- `TokenMismatchException` → CSRF
- `ModelNotFoundException` → registro inexistente (404)

### Telescope

Se instalado (`composer require laravel/telescope --dev`):

- Acesse `/telescope`
- Abas: Requests, Queries, Exceptions, Jobs, Logs
- Útil para N+1 (muitas queries iguais), slow queries

### Pail (Laravel 11+)

```bash
php artisan pail
```

- Stream de logs em tempo real no terminal

---

## 5. Busca e índice (DRAXY)

```bash
# Rebuild índice global (dataset)
python build_search_index.py

# Reindexar workspace
python agent_cli.py --reindex -p my-app

# No agent
/search model fillable
/search migration foreignId
```

Prioridades em `config/search_priorities.json` — termos como `model`, `controller` recebem boost.

---

## 6. Treino e inferência (LLM)

```bash
python build_dataset.py      # Regenera dataset
python train.py              # Fine-tuning LoRA (~30-40 min)
python inference.py          # CLI simples sem tools
```

Variáveis: `MODEL_NAME`, `LORA_OUTPUT_DIR`, `AGENT_TEMPERATURE`

---

## 7. Redis (cache do agent)

```bash
sudo apt install redis-server
# ou: docker run -p 6379:6379 redis

# .env
REDIS_URL=redis://127.0.0.1:6379/0
AGENT_CACHE_ENABLED=true
```

Sem Redis: cache em memória (perde ao reiniciar).

---

## 8. Tabela de diagnóstico rápido

| Problema | Comando / ferramenta |
|----------|---------------------|
| Erro 500 | `/log` ou `tail_log` |
| Rota não existe | `php artisan route:list` |
| Migration pendente | `php artisan migrate:status` |
| Autoload quebrado | `composer dump-autoload` |
| Config desatualizada | `php artisan config:clear` |
| Permissão negada | Verificar Policy / middleware `auth` |
| N+1 | Telescope ou `DB::listen()` em dev |
| Código mal formatado | `vendor/bin/pint` |
| Teste falhou | `php artisan test --filter=NomeTest` |

---

## 9. Comandos bloqueados pelo agent

Por segurança, estes **não** passam em `run_command`:

- `rm`, `sudo`, `curl`, `wget`, `chmod`, `chown`
- `migrate:fresh` requer aprovação explícita

Use alternativas seguras e peça confirmação ao usuário para operações destrutivas.
