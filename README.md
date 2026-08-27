# Laravel AI Coder

Assistente de código local especializado em PHP/Laravel 11+, com fine-tuning QLoRA via Unsloth sobre **Qwen/Qwen2.5-Coder-7B-Instruct**.

**Hardware alvo:** RTX 3060 12GB VRAM, 16GB RAM.

## Ubuntu 26.04 (Python 3.14)

Este sistema **não tem Python 3.12** no apt. Use o **Python 3.14** nativo com venv — não tente `python3.12`.

## Instalação (obrigatório: venv)

O `pip` do sistema está bloqueado (PEP 668). **Nunca** rode `pip install` sem ativar o venv.

```bash
cd laravel-ai-coder
python3 -m venv .venv
source .venv/bin/activate          # ← OBRIGATÓRIO antes de pip/python

pip install --upgrade pip setuptools wheel
pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt -c constraints.txt
cp .env.example .env
```

## Uso diário

**Sempre** ative o venv primeiro:

```bash
cd laravel-ai-coder
source .venv/bin/activate
```

Ou use o atalho (ativa venv e abre o Agent CLI):

```bash
./initial.sh
# workspace específico:
./initial.sh -w ~/Documentos/my-app
```

Confirme que está no venv: o prompt deve mostrar `(.venv)` ou rode `which python` — deve apontar a `.venv/bin/python`.

```bash
python build_dataset.py  # gera data/raw_dataset.jsonl das fontes locais
python train.py          # fine-tuning (~30-40 min, 300 steps)
python agent_cli.py      # agent CLI (tipo Cursor Agent)
python inference.py      # CLI simples (só geração, sem tools)
```

> Dentro do venv, `python` funciona. Fora do venv, use `python3` (o comando `python` pode não existir no sistema).

## Erros comuns

| Erro | Causa | Solução |
|------|--------|---------|
| `externally-managed-environment` | `pip` fora do venv | `source .venv/bin/activate` |
| `.venv/bin/activate: não existe` | venv não criado ou foi apagado | recrie o venv (seção Instalação) |
| `python3.12 não encontrado` | Ubuntu 26 só tem 3.14 | use `python3` |
| `No matching distribution found for torch` | cu124/cu121 sem wheels para Py 3.14 | use `cu126` (ver Instalação) |
| `ModuleNotFoundError: No module named 'torch'` | instalação falhou no meio | `pip cache purge` e reinstale |
| `Cota da disco excedida` / errno 122 | disco cheio ao baixar PyTorch | libere ~8 GB; `pip cache purge` |

## OOM (CUDA Out of Memory)

Em `config.py`:

- `batch_size = 1`
- `gradient_accumulation_steps = 8`

## Dataset

### Regenerar dataset (só se for retreinar)

```bash
python build_dataset.py   # lê fontes locais e gera data/raw_dataset.jsonl
```

Clone manualmente o que quiser usar (`docs-laravel/`, `laravel_source/`, `php_manual_en/`).

Fontes usadas por `build_dataset.py` (ignora o que não existir):

| Diretório / arquivo | Conteúdo |
|---------------------|----------|
| `docs-laravel/` | Documentação Laravel (Markdown) |
| `php_manual_en/` | Manual PHP em HTML |
| `laravel_source/` | Código fonte Laravel (`.php`) |
| `Posts.xml` | Dump Stack Overflow (~10 GB, manual) |

O treino lê `data/raw_dataset.jsonl` (chaves `instruction` e `output`).
Variável de ambiente opcional: `DATASET_PATH`.

## Agent CLI (debug)

Assistente tipo Cursor Agent, rodando 100% local com seu LoRA:

```bash
# Projeto em ~/Documentos (recomendado)
python agent_cli.py -p my-app
python agent_cli.py -p atendimento-whatsapp

# Ou caminho completo
python agent_cli.py -w ~/Documentos/my-app

# Dentro do agent (trocar projeto sem reiniciar)
/projects          # lista projetos
/project my-app    # ativa my-app
/pwd               # mostra caminho atual
/mkdir app/Services
/model Krip
```

Configure no `.env`:

```env
AGENT_PROJECTS_ROOT=/home/alisson/Documentos
AGENT_DEFAULT_PROJECT=my-app
```

Atalho: `./initial.sh my-app`

Modo tarefa única:

```bash
python agent_cli.py -w ./meu-app -t "Erro 500 ao registrar usuário — investigar"
```

Ferramentas do agente: `read_file`, `write_file`, `list_dir`, `grep`, `run_command`, `tail_log`, `search`.

### Índice de busca + cache Redis

Consultas repetidas não reabrem o `raw_dataset.jsonl` linha por linha — usam índice invertido + cache.

```bash
# 1. Gera índice do dataset (uma vez, ou após atualizar o JSONL)
python build_search_index.py

# 2. Redis opcional (sem Redis usa cache em memória)
sudo apt install redis-server   # ou docker run -p 6379:6379 redis
pip install redis

# 3. No agent CLI
python agent_cli.py -w ~/Documentos/my-app
/search model fillable          # busca indexada
```

Prioridades de busca em `config/search_priorities.json` (ex.: `mkdir`, `model`, `controller` recebem boost).

Reindexar arquivos do projeto Laravel: `python agent_cli.py --reindex -w ./meu-app`

Variáveis `.env`: `AGENT_SEARCH_INDEX`, `REDIS_URL`, `AGENT_CACHE_ENABLED`, `AGENT_CACHE_TTL`.

## Arquitetura e agente CLI

### ARCH.md

O arquivo [`ARCH.md`](ARCH.md) descreve a arquitetura completa do projeto:

- Visão geral, módulos e fluxos
- Integração com a LLM local
- Como o agente interage com projetos Laravel
- Pontos de atenção para evitar regressões

**Todo agente de IA deve ler `ARCH.md` antes de contribuir com código.**

### Skill laravel-best-practices

A skill em `.cursor/skills/laravel-best-practices/` contém boas práticas Laravel/PHP:

| Arquivo | Conteúdo |
|---------|----------|
| `SKILL.md` | Entrada da skill (metadados + fluxo) |
| `instructions.md` | Clean code, performance, segurança, testes |
| `tools.md` | Artisan, debug, interpretação de logs |

No **Cursor IDE**, a regra `.cursor/rules/laravel-agent.mdc` associa automaticamente a skill e o `ARCH.md` a sessões neste projeto.

No **agent CLI (DRAXY)**, as instruções multilíngues são injetadas via `utils/agent/llm_config.py` → `utils/agent/prompts.py`.

### Comunicação com a LLM (pt/en + typos)

Configure no `.env`:

```env
LLM_MULTILINGUAL=true
LLM_DEFAULT_LANGUAGE=pt
LLM_TYPO_TOLERANCE=true
LLM_RESPOND_IN_PROMPT_LANGUAGE=true
```

Exemplos de prompts:

```text
# Português
Corrija o erro 500 no login — verifique AuthController e o log.

# English
Create a Product model with migration and JSON controller.

# Com erros de digitação (aceito)
crie um cntroler UserController com metodos index e store
```

A LLM responde no idioma do prompt (fallback: português).

### Ativar a skill manualmente (Cursor)

1. Abra o projeto `laravel-ai-coder` no Cursor
2. A regra `laravel-agent.mdc` já está com `alwaysApply: true`
3. Para forçar a skill: mencione "laravel-best-practices" ou peça para seguir `instructions.md`
4. Consulte `ARCH.md` para contexto de arquitetura

### Fluxo recomendado para o agente

```
1. Ler ARCH.md
2. Ler skill laravel-best-practices (instructions.md se for implementar)
3. Inspecionar projeto alvo (read_file / grep / search)
4. Implementar mudança mínima
5. php artisan test
```
