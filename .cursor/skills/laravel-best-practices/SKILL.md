---
name: laravel-best-practices
description: >-
  Boas práticas Laravel/PHP para implementação segura e performática.
  Use antes de escrever ou alterar código PHP, migrations, controllers,
  models, testes, ou ao debugar projetos Laravel com o agent CLI DRAXY.
version: "1.0.0"
tools_allowed:
  - read_file
  - write_file
  - grep
  - search
  - list_dir
  - run_command
  - tail_log
  - mkdir
  - create_laravel_project
input_format: >-
  Tarefa em linguagem natural (pt/en) descrevendo o que implementar,
  corrigir ou investigar em um projeto Laravel. Inclua contexto: erro,
  arquivo, endpoint ou comportamento esperado quando possível.
output_format: >-
  Código PHP/Laravel seguindo convenções do projeto; explicação concisa
  das mudanças; comandos artisan executados; paths dos arquivos alterados.
  No agent CLI DRAXY: JSON {"action":"tool"|"finish",...} durante execução.
---

# Laravel Best Practices

Skill obrigatória para o agente CLI e para qualquer implementação PHP/Laravel neste ecossistema.

## Quando usar

- Antes de criar ou editar Models, Controllers, Migrations, Requests, Policies
- Ao investigar bugs (500, validação, N+1, auth)
- Ao rodar ou escrever testes PHPUnit/Pest
- Ao otimizar queries ou configurar cache/filas

## Fluxo obrigatório

1. Ler `ARCH.md` na raiz de `laravel-ai-coder/` para contexto do agente
2. Ler [instructions.md](instructions.md) — regras detalhadas
3. Consultar [tools.md](tools.md) — comandos e debug
4. Inspecionar o código existente (`read_file`, `grep`, `search`) antes de editar
5. Implementar mudança mínima necessária
6. Validar com `php artisan test` ou teste específico quando aplicável

## Princípios resumidos

| Área | Regra |
|------|-------|
| Clean Code | Nomes significativos, funções pequenas, DRY, comentários só quando necessário |
| Performance | Eager loading, chunking, cache, índices, queues para trabalho pesado |
| Segurança | Form Requests, Policies, mass assignment, CSRF, sem SQL raw sem bindings |
| Laravel | Artisan make:*, Form Requests, Resources, Events quando desacoplar |
| Testes | Feature para HTTP; Unit para lógica pura; factories para dados |
| Debug | `tail_log`, Telescope se instalado, `php artisan route:list` |

## Recursos

- Regras completas: [instructions.md](instructions.md)
- Comandos e ferramentas: [tools.md](tools.md)
- Arquitetura do agente: `ARCH.md`
