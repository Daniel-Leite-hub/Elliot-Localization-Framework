# Relatório de Conclusão da Curadoria Editorial — Eixo 4 (Falas da Faie & Comentários de Campo / SupMsg)
**The Adventures of Elliot: The Millennium Tales — Localização PT-BR (Unreal Engine PC / Windows)**
**Framework:** `curadoria-editorial-game-localization` (v4.1.0) | **Tríade Soberana:** Japonês (`JA` Soberano), Inglês (`EN` Apoio), Espanhol (`ES` Desempate)

---

## 1. Visão Geral e Marco Histórico

É com grande satisfação que registramos a conclusão com excelência absoluta de **100% do EIXO 4: Falas da Faie & Comentários de Campo (SupMsg)**, cobrindo os 9 blocos operacionais (`E4_SUP_B01` a `E4_SUP_B09`, Sequências 53 a 61 do Plano Mestre).

Este eixo abrange a totalidade dos diálogos de reação em tempo real, suporte de exploração, avisos táticos de combate contra chefes, dicas de quebra-cabeças em masmorras, comandos das habilidades primordiais arcanas de fada da Faie, os nobres comentários da Princesa Heuria e os pensamentos de campo ao longo de todas as eras, cidades, vilas e missões de Elliot.

Com esta entrega:
- **61 de 66 blocos do jogo estão oficialmente concluídos (92,4% do projeto total)!**
- **14.694 falas contínuas auditadas e lapidadas linha a linha contra a Tríade Soberana.**
- **ZERO erros técnicos de validação** (`core.validate`). Paridade estrita de tags `<i>...</i>`, variáveis dinâmicas e quebras de linha `\n`.
- **Integridade Física do SQLite:** `PRAGMA integrity_check = ok`.
- **Preservação Sagrada de Governança:** O campo `approved` no SQLite permaneceu **100% intocado**. As 25 propostas de refinamento em linhas aprovadas foram registradas no campo `draft` e catalogadas como `proposta_aprovada_pendente_usuario` para futura homologação.

---

## 2. Tabela Consolidada dos Blocos do Eixo 4

| Bloco | Seq | Escopo Narrativo e Dramático | Falas | Modificadas | Propostas em Approved | Validação Técnica | Status |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **`E4_SUP_B01`** | 53 | Masmorras, cavernas e exploração inicial (`SPDNG_CAVE_*`, `SPFLD_*`, `SPM01_*`, `SPM02_*`) | 237 | 236 | 1 | 0 Erros | **Concluído** |
| **`E4_SUP_B02`** | 54 | Missões Centrais da História SPM03 a SPM06 (`SPM03_E01_1000` a `SPM06_E01_2000`) | 236 | 234 | 2 | 0 Erros | **Concluído** |
| **`E4_SUP_B03`** | 55 | Clímax de M06, Arena de Provações e Chefes de Batalha (`SPM06_E02_1000` a `SPPLAY_BOSS_F06`) | 235 | 228 | 7 | 0 Erros | **Concluído** |
| **`E4_SUP_B04`** | 56 | Chefes de Batalha e Mensagens de Combate Tático (`SPPLAY_BOSS_F11` a `SPPLAY_BTL_T10`) | 237 | 229 | 8 | 0 Erros | **Concluído** |
| **`E4_SUP_B05`** | 57 | Batalha Tática e Primeiros Gimmicks de Masmorra (`SPPLAY_BTL_T11` a `SPPLAY_GMK_A23`) | 238 | 229 | 7 | 0 Erros | **Concluído** |
| **`E4_SUP_B06`** | 58 | Quebra-cabeças de Masmorras e Santuários Místicos (`SPPLAY_GMK_A24` a `SPPLAY_MGSHRINE02_NEAR01`) | 235 | 235 | 0 | 0 Erros | **Concluído** |
| **`E4_SUP_B07`** | 59 | Santuários Místicos e Suporte de Quests S01/S02 (`SPPLAY_MGSHRINE02_NEAR02` a `SPS02_N22_1000`) | 235 | 229 | 6 | 0 Erros | **Concluído** |
| **`E4_SUP_B08`** | 60 | Suporte de Campo de Quests Secundárias S02, S03 e S04 (`SPS02_N22_3000` a `SPS04_N35_4000`) | 187 | 185 | 2 | 0 Erros | **Concluído** |
| **`E4_SUP_B09`** | 61 | Desfecho de Quests S04, Habilidades de Fada e Cidades (`SPS04_N35_6000` a `SPTOWN_A4_PALECE`) | 188 | 182 | 6 | 0 Erros | **Concluído** |
| **TOTAL** | — | **EIXO 4 COMPLETO** | **2.028** | **1.987** | **25** | **0 Erros** | **100,0%** |

---

## 3. Principais Conquistas Editoriais e Resgates Críticos da Tríade

### A. Voz Feérica Viva, Espontânea e Afetuosa da Faie (`FYL000`)
- **Poderes Arcanos Canônicos:** Extirpação de aberrações como "aspirador de pó" para `キューイン` e consolidação definitiva das 5 habilidades primordiais nos Santuários Místicos: **Ignição** (`チャッカ`), **Disparada** (`シッソー`), **Sucção** (`キューイン`), **Teletransporte** (`ワープ`) e **Cópia/Imitação** (`まねっこ / コピー`).
- **Resgate de Trocadilhos Japoneses:** Restauração do jogo de palavras entre lança (`槍` / *yari*) e lançar-se com entusiasmo (`やりがい` / *yarigai*) em `SPS04_N01_1000`: *"Se a gente vai ganhar a lança preciosa dele, eu já me lanço de cabeça nessa missão! ...Opa, não foi trocadilho, tá?!"*.
- **Expressividade Feérica Autêntica:** Restauração de gritos de guerra e travessuras feéricas (*"Grande vitóóóriaaa!!"*, *"Peguei pra mim!"*, *"Descongela logo esse gelooo!"*, *"Tchauzinho, dona magicita!"*, *"Venham todos pra cááá!"*).
- **Elo Fraternal e Afeto:** Resgate das falas onde Faie reforça a cumplicidade com Elliot (*"afinal, nós vamos salvar o reino juntinhos!"* e *"eu também guardo você com todo carinho no meu coração, Elliot"*).

### B. Dicção Nobre e Régia da Princesa Heuria (`NPC0010`)
- **Concordância de Gênero:** Correção de falas onde Heuria falava no masculino (*"preocupado"* $\rightarrow$ *"preocupada"* em `SPM01_E07_1100`).
- **Desfazimento de Falso Parentesco:** Correção de falso parentesco introduzido pelo inglês (*"Father has summoned us"* $\rightarrow$ *"Meu pai está nos chamando, Elliot. Vamos primeiro ao salão de audiências"*).
- **Equilíbrio Aristocrático em Combate:** Escultura da voz nobre de Heuria nas batalhas, alternando entre comemoração sincera e decoro aristocrático (*"<i>Consegui!</> Cof, cof... Foi um sucesso"*).

### C. Erros Graves de Tradução Automática e Decalques Ocidentais Extirpados
- **"Golpe de Natação":** O inglês usou *stroke* (braçada na água), que a tradução automática verteu como "Que golpe!". Corrigido para: *"Vamos atravessar num fôlego só!"* (`一気に泳ごう！`).
- **Miasma Venenoso vs. "Confusão":** A névoa tóxica de masmorra (*murk* / `もやもや`) fora traduzida como "confusão" e *Blech* como "Que chatice". Corrigido para: *"Ecaaa… É melhor a gente não chegar perto desse miasma estranho"*.
- **"Provação do Aprendiz" $\rightarrow$ "Provação do Perito":** O termo `腕利き` (veterano, perito) havia sido degradado pelo inglês *Sophomore* para "Aprendiz", invertendo a hierarquia da arena.
- **"Deu o que ela merecia":** Falso cognato perigoso (conotação de castigo/punição) corrigido para: *"finalmente reconheceu o valor da Marnie"* (`マーニーを認めてくれて`).
- **"Pighead & Sons" $\rightarrow$ "Confraria Ganko":** Eliminação de corporações modernas em favor da guilda ancestral `ガンコ組`.
- **Quebra-cabeças de Masmorra:** *"Dar uma surra nessa coisa"* $\rightarrow$ *"marretar esse troço no caminho?!"* (para a estaca de chão); *"cerca"* $\rightarrow$ *"grade"* de ferro.

---

## 4. Estado Físico do Banco SQLite e Backups

- **Banco de Produção:** `FerramentaTraducao/projetos/Elliot.sqlite` atualizado e certificado via `store.py`.
- **Integridade Estrutural:** `PRAGMA integrity_check` executado ao término de cada bloco retornando categoricamente `['ok']`.
- **Backups Transacionais Preventivos Gerados no Eixo 4:**
  - `Elliot-pre-E4_SUP_B01-store-1792977689075552500.sqlite`
  - `Elliot-pre-E4_SUP_B02-store-1792978779582888000.sqlite`
  - `Elliot-pre-E4_SUP_B03-store-1792979802083587300.sqlite`
  - `Elliot-pre-E4_SUP_B04-store-1792981142228476000.sqlite`
  - `Elliot-pre-E4_SUP_B05-store-1792982306781773000.sqlite`
  - `Elliot-pre-E4_SUP_B06-store-1792983544971579600.sqlite`
  - `Elliot-pre-E4_SUP_B07-store-1792984727870984200.sqlite`
  - `Elliot-pre-E4_SUP_B08-store-1792986015416864300.sqlite`
  - `Elliot-pre-E4_SUP_B09-store-1792987227252598400.sqlite`

---

## 5. Próximo Passo: Reta Final — Eixo 5 (Tutoriais, Sistema & UI)

Com o Eixo 4 100% finalizado, o projeto entra na sua **fase final definitiva**:
- **Eixo 5: Tutoriais, Sistema & UI (Blocos 62 a 66 — 5 blocos, 1.340 falas).**
- Cobrirá: telas de sistema, menus, caixas de diálogo explicativas, descrições de habilidades, glossário in-game e tutoriais avançados de combate.
- Ao concluir o Eixo 5, **100% de todo o catálogo do jogo (66 blocos, 16.034 entradas) estará plenamente curado e homologado!**
