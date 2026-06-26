# Deploy — DSNO Processor (Windows 11)

Guia de alto nível para **empacotar, instalar e configurar** o DSNO Processor em
estações Windows 11. Cobre desde a geração do instalador (feita uma vez por quem
faz o build) até a configuração na primeira execução em cada máquina.

---

## 1. Visão geral

O DSNO Processor é uma aplicação desktop. O fluxo de trabalho tem 4 etapas:

1. **Pendências** — sincroniza DSNOs pendentes do banco Oracle EBS para o banco
   interno (SQLite). **Requer Java** (embarcado no instalador).
2. **Download** — baixa arquivos do EBS (automação web via Selenium / Chrome).
3. **Processar** — edita os arquivos DSNO em lote conforme as planilhas/banco.
4. **Upload** — envia os arquivos processados de volta ao EBS.

Pontos importantes para o deploy:

- **Banco compartilhado:** o SQLite interno pode ficar em uma pasta de rede
  (UNC), permitindo que a equipe use um único banco. Configurável em
  *Configurações → Caminhos → Pasta do Banco*.
- **Autoria dos registros:** todo registro criado no banco recebe o usuário do
  Windows automaticamente — nada a configurar.
- **Java embarcado:** o instalador extrai o **Java 21** para `\java\jdk-21.0.10`
  dentro da pasta da aplicação e o driver Oracle JDBC para `\java\ojdbc17.jar`.
  A configuração padrão já aponta para esses caminhos (relativos).

---

## 2. Pré-requisitos da estação (end-user)

| Item | Necessário para | Observação |
|---|---|---|
| Windows 11 | Tudo | Instalação por usuário, **sem privilégios de admin**. |
| Google Chrome | Download / Upload (EBS) | Usado pela automação Selenium. |
| WebView2 / Edge | Interface web (padrão) | Já presente no Windows 11. Necessário para a UI padrão. |
| Drive de rede mapeado (ex.: `Z:`) | Caminhos das planilhas / DSNOs | Ou ajustar os caminhos na configuração. |
| Acesso à pasta de rede do banco | Banco compartilhado | UNC `\\servidor\...`. |
| Java | Pendências (Oracle) | **Já vai embarcado** — nada a instalar. |

---

## 3. Gerar o instalador (build — feito uma vez)

Pré-requisitos da máquina de build:

- Python 3.12+, Node.js (para o frontend web), **Inno Setup 6**.
- A pasta `java/` na raiz do projeto contendo:
  - `ojdbc17.jar` (driver Oracle JDBC)
  - `jdk-21.0.10_windows-x64_bin.zip` (JDK 21 para Windows x64)

  > Esses binários são versionados via **Git LFS**. Tenha o
  > [git-lfs](https://git-lfs.com) instalado **antes** de clonar (`git lfs install`);
  > um clone sem LFS traz apenas ponteiros, não os arquivos reais.

Passos:

```bash
# 1. Ambiente Python
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. (Opcional, recomendado) rodar os testes
pytest tests/

# 3. Build completo: frontend (Vite) + executável (PyInstaller) + instalador (Inno)
python scripts/build_all.py
```

O `build_all.py` executa, em ordem: `npm run build` do frontend, o PyInstaller
(`main.spec`) e o Inno Setup (`installer_setup.iss`). O instalador final fica em
`Output/DSNO Processor Installer.exe`.

> O instalador embarca a pasta `java/` (jar + zip do JDK) e, durante a
> instalação, **extrai o Java 21** para `{app}\java\jdk-21.0.10` e remove o zip.

---

## 4. Instalar na estação

1. Copie o `DSNO Processor Installer.exe` para a máquina.
2. Execute. A instalação é **por usuário** (`%USERPROFILE%\Softwares\DSNO Processor`),
   sem necessidade de admin.
3. Aguarde a etapa "Extraindo Java 21..." concluir.
4. Atalhos são criados no Menu Iniciar (e na Área de Trabalho, se marcado).

> **Importante:** inicie sempre pelo atalho criado. Ele define o diretório de
> trabalho como a pasta da aplicação, garantindo que os caminhos relativos
> (`config.toml`, `java\...`) sejam resolvidos corretamente.

---

## 5. Configurar na primeira execução

Na primeira execução o app cria um `config.toml` a partir do padrão. Abra
**Configurações** e preencha os campos em branco:

| Seção | Campo | O que preencher |
|---|---|---|
| Credenciais | E-mail / Senha | Login **pessoal** do EBS (SSO Cummins). |
| Oracle | Usuário / Senha / DSN | Conexão do banco Oracle EBS (etapa Pendências). |
| EBS | URL de download / URL de upload | URLs das telas do EBS. |
| Caminhos | Pasta do Banco | Pasta de rede (UNC) do banco compartilhado. Vazio = banco local. |
| Caminhos | Diretório DSNO / Planilhas | Confirmar conforme o drive de rede da estação. |

Campos que **já vêm prontos** e normalmente não precisam mudar:

- `oracle.jdbc_jar = java\ojdbc17.jar` e `oracle.jvm_path = java\jdk-21.0.10`
  (apontam para o Java embarcado).
- `customer_id`, colunas das planilhas, índices de pastas do EBS.

> A senha do Oracle e o login do EBS ficam **apenas** no `config.toml` local da
> máquina (não versionado). O padrão distribuído não contém credenciais.

---

## 6. Verificação (smoke test)

Após configurar, valide cada etapa:

1. **Pendências** → executar a sincronização. Se o Java/Oracle estiverem ok,
   retorna os DSNOs pendentes e grava os novos no banco.
2. **Registros** → abrir a aba e conferir que as tabelas (Controle/Cliente) são
   exibidas e que a coluna `AUTHOR` traz o usuário do Windows.
3. **Download → Processar → Upload** → rodar um lote pequeno e conferir os
   arquivos em `Processed/`.

---

## 7. Atualização e troubleshooting

- **Atualizar versão:** rode o novo instalador por cima. O `config.toml` existente
  **não é sobrescrito** (`onlyifdoesntexist`), preservando as credenciais.
- **Pendências falha com erro de JVM:** confirme que `{app}\java\jdk-21.0.10\bin`
  existe (extração do instalador) e que `oracle.jvm_path` aponta para lá. Em
  último caso, deixe `jvm_path` vazio para auto-detecção de um Java instalado.
- **Caminhos não encontrados:** verifique o drive de rede mapeado e o acesso à
  pasta UNC do banco.
- **Banco compartilhado bloqueado:** SQLite em rede suporta múltiplos leitores;
  escritas simultâneas são serializadas. Para muitos usuários concorrentes,
  avalie migrar o backend de armazenamento.
