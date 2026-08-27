# Animação ASCII no terminal

Reproduz a esfera numérica do `static/assets/background.gif` como animação ASCII no terminal Linux.

## Dependências

O projeto já inclui **Pillow** em `requirements.txt`. Com o venv ativo:

```bash
pip install Pillow>=10.0.0
```

Ou reinstale tudo:

```bash
pip install -r requirements.txt -c constraints.txt
```

## Como executar

```bash
cd laravel-ai-coder
source .venv/bin/activate

# Opção 1 — atalho shell
./ascii

# Opção 2 — script Python
python ascii_animation.py

# Opção 3 — módulo
python -m utils.ascii_anim
```

Pressione **CTRL+C** para sair. O cursor e o terminal são restaurados automaticamente.

## Integração com o DRAXY (agent CLI)

Ao rodar `./initial.sh` ou `python agent_cli.py`, uma **versão compacta** da esfera ASCII
(~44×10) aparece por ~2 segundos no topo do terminal, com o nome **DRAXY** centralizado.

Desativar:

```bash
./initial.sh --no-splash
# ou no .env:
AGENT_ASCII_SPLASH=false
```

Ajustar tamanho no `.env`:

```env
AGENT_ASCII_SPLASH_WIDTH=44
AGENT_ASCII_SPLASH_HEIGHT=10
```

## Opções úteis

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `--fps` | Velocidade da animação | `24` |
| `--width` | Largura fixa (colunas) | tamanho do terminal |
| `--height` | Altura fixa (linhas) | tamanho do terminal |
| `--chars` | Caracteres das partículas | `0123456789` |
| `--threshold` | Brilho mínimo (0–255) | `18` |
| `--density` | Densidade de partículas (0.2–1.0) | `1.0` |
| `--frame-skip` | Usar 1 a cada N frames do GIF | `2` |
| `--once` | Reproduzir uma vez (sem loop) | loop infinito |
| `--gif` | Caminho alternativo do GIF | `static/assets/background.gif` |

### Exemplos

```bash
# Mais rápido
./ascii --fps 30

# Terminal pequeno
./ascii --width 60 --height 20

# Apenas dígitos ímpares
./ascii --chars 13579

# Menos partículas (mais leve)
./ascii --density 0.6 --frame-skip 3

# Uma passagem só
./ascii --once
```

## Comportamento

1. Carrega o GIF (330 frames, 600×600).
2. Pré-processa os frames em memória (sem arquivos temporários).
3. Converte cada frame em grade ASCII com dígitos `0–9`.
4. Usa ANSI TrueColor quando disponível; fallback para cinza básico.
5. Adapta ao tamanho do terminal via `shutil.get_terminal_size()`.
6. Reproduz em loop até CTRL+C.

## Estrutura do código

```
utils/ascii_anim/
  loader.py      # leitura do GIF
  converter.py   # frame → ASCII com partículas numéricas
  terminal.py    # controle ANSI (cursor, tela alternativa)
  player.py      # loop de reprodução e CLI
ascii_animation.py
ascii            # wrapper shell
```

## Integração opcional

Para exibir a animação antes do Agent CLI, você pode adicionar manualmente ao seu `~/.bashrc`:

```bash
# Exemplo (NÃO é aplicado automaticamente pelo projeto)
alias laravel-ascii='cd ~/Documentos/IA-LARAVEL/laravel-ai-coder && ./ascii'
```
