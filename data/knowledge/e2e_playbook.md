# Playbook E2E do DRAXY (Laravel 11+)

O agente não gera PHP longo dentro de JSON. PHP longo quebra o parser e trunca.

## Sequência obrigatória para uma feature

1. `list_dir` / `read_file` no que já existe.
2. `php artisan make:model Nome -m` e `make:controller Api/NomeController --api` e `make:request StoreNomeRequest`.
3. `scaffold_php` com args curtos (nunca `write_file` com classe inteira):
   - `kind=model` fillable e casts
   - `kind=fill_migration` columns `a:char:7:unique|b:text`
   - `kind=form_request` rules `url:required|url|max:2048` e authorize true
   - `kind=service` classe base
   - `kind=api_controller` service + request + methods
   - `kind=ensure_api` registra `api:` em `bootstrap/app.php`
   - `kind=add_route` method/uri/action
   - `kind=feature_test`
4. `replace_in_file` só para um trecho único (cache, alphabet, hash).
5. `php artisan migrate --force`
6. `php artisan test` — finish só com testes verdes.

## Laravel 11 rotas

`bootstrap/app.php` precisa de:

```
web: __DIR__.'/../routes/web.php',
api: __DIR__.'/../routes/api.php',
```

Sem isso, POST `/api/v1/...` dá 404.

## Form Request

`authorize(): bool { return true; }` não é login. Não dispare AuthController.

## Nomes

`Implemente App\Models\ShortUrl` → model `ShortUrl`, nunca `Implemente`.
`Preencha` / `Escreva` / `Crie` não são classes.

## Redirect rápido

Lookup por `code` indexado. `Cache::remember`. Hits com `increment` ou job `afterResponse`, sem N+1.

## Finish mentiroso

Se a tool falhou ou os testes não rodaram, não finish.
