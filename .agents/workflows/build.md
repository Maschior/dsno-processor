---
description: Build the DSNO Processor for production using PyInstaller
---

# Build para Produção

## Pré-requisitos

Certifique-se de estar no virtual environment do projeto com todas as dependências instaladas.

// turbo-all

## Passos

1. Instale o PyInstaller (caso ainda não tenha):

```bash
pip install pyinstaller
```

2. Gere o executável a partir do spec file:

```bash
pyinstaller main.spec --clean --noconfirm
```

3. O executável será gerado em:

```
dist/DSNO Processor/DSNO Processor.exe
```

4. Para distribuir, copie **toda** a pasta `dist/DSNO Processor/` para o destino. A pasta contém:
   - `DSNO Processor.exe` — o executável principal
   - Todas as DLLs e dependências necessárias
   - Assets do CustomTkinter (temas, fontes)
   - `config.toml.example` — arquivo de configuração modelo

5. No destino, o usuário deve:
   - Copiar `config.toml.example` para `config.toml`
   - Editá-lo com os caminhos corretos para o ambiente de produção
   - Executar `DSNO Processor.exe`

## Notas

- O flag `--clean` limpa cache de builds anteriores
- O flag `--noconfirm` sobrescreve a pasta `dist/` sem perguntar
- `console=False` no spec garante que NÃO aparece janela de terminal
- Para debug, altere `console=False` para `console=True` no `main.spec`
