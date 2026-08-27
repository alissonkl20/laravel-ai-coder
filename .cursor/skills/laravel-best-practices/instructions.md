# Instruções — Laravel Best Practices

Regras detalhadas para implementação em projetos Laravel 11+ gerenciados pelo agent CLI DRAXY.

---

## 1. Clean Code

### Nomes significativos

- Classes refletem responsabilidade: `StoreProductRequest`, `ProductController`, `ProductService`
- Evite abreviações obscuras (`$usr`, `proc`)
- Métodos com verbos: `createOrder`, `resolveUser`, `isPublished`
- Booleans com prefixo: `isActive`, `hasPermission`, `canDelete`

### Funções pequenas e focadas

- Controller: orquestra request → service/action → response (idealmente < 15 linhas por action)
- Extraia lógica complexa para Actions, Services ou métodos privados
- Um nível de abstração por método

### DRY (Don't Repeat Yourself)

- Validação repetida → Form Request
- Transformação de resposta repetida → API Resource
- Query repetida → scope no Model ou Repository (se o projeto já usa)
- Não crie abstrações prematuras para uso único

### Comentários

- Código deve ser autoexplicativo
- Comente **por quê**, não **o quê**
- PHPDoc em métodos públicos de bibliotecas internas; evite em CRUD trivial

---

## 2. Performance

### Eloquent

```php
// ❌ N+1
$orders = Order::all();
foreach ($orders as $order) {
    echo $order->user->name;
}

// ✅ Eager loading
$orders = Order::with('user')->get();
```

- Use `select()` para limitar colunas em listagens grandes
- `lazy()` / `cursor()` / `chunk()` para processar muitos registros sem estourar memória
- Evite `Model::all()` em tabelas grandes

### Caching

```php
Cache::remember('products.active', 3600, fn () => Product::active()->get());
```

- Cache de config/routes em produção: `php artisan config:cache`, `route:cache`
- Em desenvolvimento, limpe após mudanças: `php artisan optimize:clear`
- Use tags de cache quando o driver suportar (Redis)

### Queries

- Índices em colunas de `where`, `orderBy`, foreign keys
- `exists()` em vez de `count() > 0` para checagens booleanas
- `pluck()` quando só precisa de uma coluna

### Filas (Queues)

- E-mail, notificações, processamento de imagem → `ShouldQueue`
- Jobs idempotentes quando possível
- Configure `QUEUE_CONNECTION` no `.env` (database, redis)

---

## 3. Segurança

### Validação de input

```php
// ✅ Form Request (preferido)
public function store(StoreProductRequest $request): JsonResponse
{
    $product = Product::create($request->validated());
    return response()->json($product, 201);
}
```

- Nunca confie em `$request->all()` sem validação
- Regras de validação no Form Request, não no Controller

### SQL Injection

```php
// ❌
DB::select("SELECT * FROM users WHERE email = '$email'");

// ✅
User::where('email', $email)->first();
DB::select('SELECT * FROM users WHERE email = ?', [$email]);
```

### XSS

- Blade escapa por padrão: `{{ $name }}`
- `{!! $html !!}` só com conteúdo sanitizado
- APIs JSON: não renderizar HTML do usuário sem escape no frontend

### CSRF

- Rotas `web` protegidas automaticamente
- APIs stateless: Sanctum/Passport; sem CSRF em token bearer

### Mass Assignment

```php
class Product extends Model
{
    protected $fillable = ['name', 'price', 'category_id'];
    // ou protected $guarded = ['id'];
}
```

### Policies e Gates

```php
// Controller
$this->authorize('update', $product);

// Blade
@can('update', $product)
```

- Registre Policies em `AppServiceProvider` ou auto-discovery
- Gate para regras globais simples

### Secrets

- Nunca commitar `.env`
- Use `config()` em código, não `env()` fora de arquivos config

---

## 4. Padrões Laravel

### Service Providers

- Bindings de interface → implementação em `AppServiceProvider::register()`
- Boot: macros, observers globais, config de paginação

### Form Requests

```bash
php artisan make:request StoreProductRequest
```

```php
public function rules(): array
{
    return [
        'name' => ['required', 'string', 'max:255'],
        'price' => ['required', 'numeric', 'min:0'],
    ];
}
```

### API Resources

```bash
php artisan make:resource ProductResource
```

```php
public function toArray(Request $request): array
{
    return [
        'id' => $this->id,
        'name' => $this->name,
        'price' => $this->formatPrice(),
    ];
}
```

### Observers

```php
// AppServiceProvider::boot()
Product::observe(ProductObserver::class);
```

- Side effects em create/update/delete (log, cache invalidation)

### Events / Listeners

- Desacoplar domínio: `OrderPlaced` → `SendOrderConfirmation`
- Listeners em fila quando lento

### Repositories (se usados no projeto)

- Só introduza se o projeto já seguir esse padrão
- Não force Repository em CRUD simples

### Rotas (Laravel 11+/13)

```php
// bootstrap/app.php
->withRouting(
    web: __DIR__.'/../routes/web.php',
    api: __DIR__.'/../routes/api.php',
    ...
)
```

- API: prefixo `/api` automático
- Agrupe rotas autenticadas com middleware

### Migrations

```php
Schema::create('products', function (Blueprint $table) {
    $table->id();
    $table->string('name');
    $table->decimal('price', 10, 2);
    $table->foreignId('category_id')->constrained()->cascadeOnDelete();
    $table->timestamps();
});
```

- Sempre `down()` reversível
- Nunca edite migration já aplicada em produção — crie nova migration

---

## 5. Testes

### Estrutura

```
tests/
├── Feature/     # HTTP, integração DB
└── Unit/        # Lógica isolada
```

### Feature test

```php
public function test_user_can_create_product(): void
{
    $user = User::factory()->create();

    $response = $this->actingAs($user)->postJson('/api/products', [
        'name' => 'Widget',
        'price' => 19.99,
    ]);

    $response->assertCreated()
        ->assertJsonPath('name', 'Widget');

    $this->assertDatabaseHas('products', ['name' => 'Widget']);
}
```

### Factories

```php
Product::factory()->count(10)->create(['category_id' => $category->id]);
```

- Use factories em vez de fixtures manuais
- States para variações: `User::factory()->unverified()`

### Quando testar

- Toda nova rota API com auth/validação
- Regras de negócio não triviais
- Regressões de bugs corrigidos

### Executar

```bash
php artisan test
php artisan test --filter=ProductTest
php artisan test tests/Feature/ProductTest.php
```

---

## 6. Debug

### Logs

```bash
# Via agent CLI
/log
# ou tail_log tool

# Manual
tail -f storage/logs/laravel.log
```

```php
Log::info('Order created', ['order_id' => $order->id]);
Log::channel('daily')->error('Payment failed', ['exception' => $e]);
```

### Dump e DD

```php
dump($variable);   // continua execução
dd($variable);     // die — só em dev
```

- Remova `dd()` antes de commit
- Prefira logging em produção

### Rastrear execução

```php
// Medir tempo
$start = microtime(true);
// ... código ...
Log::debug('duration_ms', ['ms' => (microtime(true) - $start) * 1000]);
```

### Parâmetros de execução (tarefas complexas)

Ao finalizar tarefas complexas, reporte:

| Parâmetro | Exemplo |
|-----------|---------|
| Arquivos alterados | `app/Http/Controllers/ProductController.php` |
| Comandos rodados | `php artisan make:model Product -m` |
| Migrations | `2026_08_13_create_products_table` |
| Testes | `php artisan test --filter=ProductTest` → passou |
| Tempo estimado | ~2 min |

### Telescope (se instalado)

```bash
composer require laravel/telescope --dev
php artisan telescope:install
```

- UI em `/telescope` (dev only)
- Queries, requests, jobs, exceptions

### Erros comuns Laravel

| Sintoma | Verificar |
|---------|-----------|
| 500 genérico | `storage/logs/laravel.log` |
| 419 | CSRF token / sessão |
| 403 | Policy, middleware auth |
| Class not found | `composer dump-autoload` |
| Route not defined | `php artisan route:list` |
| Config antiga | `php artisan config:clear` |

---

## 7. Checklist pré-commit (agent)

- [ ] Código segue PSR-12 (rode `vendor/bin/pint` se disponível)
- [ ] Validação em Form Request
- [ ] `$fillable` / `casts()` no Model
- [ ] Sem `dd()` ou secrets
- [ ] Testes passam
- [ ] Migration reversível
- [ ] Rotas registradas em `bootstrap/app.php` se nova API
