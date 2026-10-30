-- ==============================================================================
-- Elliot Localization Framework - Database DDL Schema
-- Database Engine: SQLite 3
-- Description: Schema relacional para extração, orquestração de tradução,
--              auditoria LQA, controle de versões e histórico transacional de assets.
-- ==============================================================================

PRAGMA foreign_keys = ON;
PRAGMA encoding = 'UTF-8';
PRAGMA user_version = 2;

-- Tabela de Configurações Globais do Pipeline de Localização
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Tabela Central de Falas e Entradas Textuais Extraídas dos Binários
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,                -- Hash determinístico SHA-256 identificador da fala
    resource TEXT NOT NULL,             -- Caminho do asset Unreal Engine (ex: ST_StoryText.uasset)
    category TEXT NOT NULL,             -- Categoria / namespace do texto (ex: Story, NPC, UI, System)
    language TEXT NOT NULL,             -- Código de idioma de referência (EN, JA, ES)
    original TEXT NOT NULL,             -- Texto fonte original extraído dos assets
    source_hash TEXT NOT NULL,          -- Hash do texto fonte para detecção de alterações
    position INTEGER NOT NULL,          -- Ordem ordinal e cronológica dentro do asset original
    kind TEXT NOT NULL,                 -- Classificação semântica (dialogue, item, menu, quest, etc.)
    exclusion TEXT NOT NULL,            -- Regras de exclusão técnica (ex: tokens de controle, XML flags)
    meta TEXT NOT NULL,                 -- Metadados JSON (contexto, autoridade JA, chave de namespace)
    machine TEXT,                       -- Tradução prévia ou rascunho base
    machine_hash TEXT,                  -- Hash de verificação da tradução base
    draft TEXT,                         -- Tradução refinada e curada em PT-BR
    approved TEXT,                      -- Texto final homologado após LQA e segunda passagem
    approved_hash TEXT,                 -- Hash do texto aprovado para garantia de integridade
    stale INTEGER NOT NULL DEFAULT 0,   -- Flag booleana indicando obsolescência por alteração de fonte
    active INTEGER NOT NULL DEFAULT 1,  -- Flag de atividade no asset
    selected TEXT,                      -- Texto final selecionado para empacotamento
    selected_kind TEXT                  -- Origem do texto selecionado (draft, approved, manual)
);

CREATE INDEX IF NOT EXISTS entry_resource ON entries(resource, position);
CREATE INDEX IF NOT EXISTS entry_state ON entries(active, kind);
CREATE INDEX IF NOT EXISTS entry_lang ON entries(language, category);

-- Tabela de Histórico e Log de Auditoria de Modificações (Event Sourcing)
CREATE TABLE IF NOT EXISTS history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL,             -- ID da fala correspondente
    event TEXT NOT NULL,                -- Tipo de evento (import, curate, approve, reject, rollback)
    text TEXT,                          -- Conteúdo associado ao evento
    at REAL NOT NULL                    -- Timestamp Unix da ocorrência
);

CREATE INDEX IF NOT EXISTS history_entry ON history(entry_id);

-- Tabela de Requisições e Processamento Assíncrono / Caching de APIs
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    state TEXT NOT NULL,                -- pendente, enviando, concluida, falha
    payload TEXT NOT NULL,
    raw TEXT,
    error TEXT,
    translation TEXT,
    started REAL,
    finished REAL,
    elapsed REAL,
    http_status INTEGER
);

CREATE INDEX IF NOT EXISTS request_key ON requests(cache_key, state);

-- Tabela de Cache Determinístico de Traduções e Segmentos
CREATE TABLE IF NOT EXISTS cache (
    cache_key TEXT PRIMARY KEY,
    translation TEXT NOT NULL,
    request_id INTEGER
);

-- Tabela de Recursos Binários e Adapters
CREATE TABLE IF NOT EXISTS resources (
    path TEXT PRIMARY KEY,
    source_hash TEXT NOT NULL,
    adapter TEXT NOT NULL,
    base BLOB NOT NULL
);

-- Tabela de Inventário de Assets Físicos
CREATE TABLE IF NOT EXISTS inventory (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    details TEXT
);

-- Tabela de Respostas e Telemetria
CREATE TABLE IF NOT EXISTS request_responses (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    status INTEGER NOT NULL,
    raw TEXT NOT NULL,
    at REAL NOT NULL
);
