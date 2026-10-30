# Arquitetura do Sistema & Engenharia de Localização

O **Elliot Localization Framework** é uma suíte de software projetada para resolver um dos desafios mais complexos no ciclo de vida de jogos modernos em Unreal Engine: a **localização técnica e dramática de alta escala** com injeção binária em tempo de execução sem acesso ao código-fonte ou editor original.

---

## 1. Visão Geral da Arquitetura

O sistema é dividido em quatro camadas modulares desacopladas:

```mermaid
graph TB
    subgraph Layer1["1. Data Extraction & Reverse Engineering (ETL)"]
        PAK["Elliot-Windows.pak (3.68 GB)"] -->|Parser Binário| EXTRACT["extract_elliot.py"]
        EXTRACT -->|LocRes UTF-16/UTF-8 Parser| STRING_TABLES["String Tables (22 Assets)"]
    end

    subgraph Layer2["2. Relational Store & Data Governance"]
        STRING_TABLES -->|Transações ACID| SQLITE[("Elliot.sqlite (SQLite 3)<br/>16.914 Falas | 129 MB")]
        SQLITE <-->|Event Sourcing| AUDIT_LOG["Tabela history (Log Transacional)"]
        SQLITE <-->|Gestão Terminológica| GLOSSARY["Glossário Vivo (Global + Scene Spotlight)"]
    end

    subgraph Layer3["3. Multi-Agent AI & Curatorship Pipeline"]
        SQLITE -->|66 Blocos Estruturados (180-300 falas)| ORCHESTRATOR["Agentic Orchestrator"]
        ORCHESTRATOR -->|Tríade Soberana: JA, EN, ES| LLM_AGENTS["Subagentes de Curadoria LQA"]
        LLM_AGENTS -->|Handoff Dramático & Context Boundary| LLM_AGENTS
        LLM_AGENTS -->|Propostas Estruturadas| LINTER["Deterministic Syntax Linter<br/>(Tokens, Tags, Escapes)"]
        LINTER -->|Aprovação Segura| HOMOLOGATOR["apply_homologated_proposals.py"]
        HOMOLOGATOR -->|Atomic Commit| SQLITE
    end

    subgraph Layer4["4. Binary Reinsertion & Deployment (Automation)"]
        SQLITE -->|Exportação Serializada| LOCRES_PTBR["Game.locres (PT-BR Formatado)"]
        LOCRES_PTBR -->|Criptografia AES-ECB & Index Redirection| INJECTOR["build_pak_reinsertion.py (v2)"]
        INJECTOR -->|Injeção Atômica sem Corrupção| TARGET_PAK["Elliot-Windows.pak Atualizado"]
        TARGET_PAK -->|Empacotamento Standalone| APPLICATOR["Aplicador Portátil Desktop (Tkinter/PyInstaller)"]
    end
```

---

## 2. Descrição dos Módulos Principais (`src/`)

| Módulo | Responsabilidade Técnica |
|---|---|
| `core.py` | Motor de abstração de dados, camada de persistência SQLite, sanitização XML de placeholders e regras de validação. |
| `locres.py` | Parser e serializador determinístico para o formato binário de strings da Unreal Engine (`.locres`), suportando encoding dinâmico UTF-8 e UTF-16 LE. |
| `pak_physical.py` | Leitura e navegação no contêiner físico `.pak` da Unreal Engine, manipulação de índices e offsets absolutos. |
| `build_pak_reinsertion.py` | Algoritmo proprietário de injeção atômica v2 com cifragem AES-ECB, adicionando o payload traduzido no final do PAK e redirecionando a tabela de índice sem violar os demais blocos criptografados. |
| `build_translation_patch.py` | Gerador do patch overlay complementar de tradução (`Elliot_PTBR_P.pak`). |
| `applicator.py` | Lógica de runtime para o instalador desktop: verificação de integridade via SHA-256, auto-detecção do executável do jogo e backup/rollback atômico com um clique. |
| `studio.py` | Interface desktop interativa baseada em `tkinter` para busca, edição manual, auditoria e revisão de strings. |
| `elliot_tables.py` | Mapeador estrutural das 22 String Tables extraídas dos arquivos `.uasset`. |
| `extract_elliot.py` | Pipeline de extração direta de binários do jogo para carga no banco relacional. |
| `provider.py` | Camada de abstração e fila de orquestração para requisições de tradução com limitação de taxa (rate-limiting) e retry com backoff exponencial. |
| `selfcheck.py` | Diagnóstico automatizado de ambiente, permissões e estado do banco de dados. |

---

## 3. Garantias de Qualidade e Resiliência

1. **Atomicidade e Integridade (ACID):** Todas as mutações no banco de dados utilizam transações estritas com suporte a rollback imediato. Se uma única proposta falhar na validação sintática durante um lote de 300 falas, nenhuma alteração é persistida.
2. **Preservação de Integridade Binária:** O algoritmo de reinserção v2 não regrava os 3,68 GB do arquivo `.pak`. Ele realiza uma injeção atômica suplementada por redirecionamento criptográfico, reduzindo o tempo de instalação de minutos para meros **2 segundos**.
3. **Zero Dependências em Produção:** O instalador desktop entregue ao usuário final é totalmente autocontido, não exigindo Python, pip ou privilégios de administrador no Windows.
