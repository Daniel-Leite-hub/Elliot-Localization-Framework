# Elliot — Aplicador PT-BR v2

Esta versão substitui o recurso espanhol diretamente no PAK original. O pacote separado da v1 não produziu português no teste do usuário; a causa exata de montagem não foi comprovada. Não use o aplicador v1 para esta reinserção.

Nesta pasta do projeto, a reinserção v2 já foi instalada. Abra o jogo e selecione Espanhol. O usuário confirmou português no menu após selecionar Espanhol. Diálogos, acentos e encaixe nas janelas durante o restante do jogo ainda não foram verificados.

## Instalar em outra cópia compatível

Feche o jogo. Abra Abrir-Aplicador-v2.cmd, selecione a pasta que contém Elliot.exe e clique em Verificar e Instalar tradução. Preserve bin/ElliotAplicadorPTBRv2 inteiro: EXE, _internal, manifest.json e payload. Reserve aproximadamente 4 GB livres para preparar a cópia reconstruída. Não exige Python nem chave AES informada pelo usuário.

O original é movido para TraducaoBackups/reinsercao-*/original.pak somente depois de a nova cópia passar por hash integral. O pacote separado da v1, se reconhecido pelo hash, também é retirado da pasta Paks e preservado no backup. Um arquivo conflitante ou uma base incompatível é recusado.

## Restaurar

Feche o jogo e clique em Restaurar original no aplicador v2. Ele verifica o hash do backup, devolve o PAK original e preserva a cópia traduzida no diretório do backup. Não apague TraducaoBackups enquanto precisar de restauração. Não altera saves, executável, UCAS ou UTOC.

## Estrutura e alcance

Somente ../../../Elliot/Content/Localization/Game/es/Game.locres foi redirecionado no índice do PAK. O recurso foi acrescentado ao final, com cifra compatível e novo índice principal cifrado; os índices secundários e todas as outras entradas foram preservados. Chaves, CRC de origem, comandos e quebras de linha da localização permanecem validados. Há 16.914 registros; a seleção editorial é a mesma da v1.

O PAK preparado foi relido integralmente pelo leitor de índices, e o recurso espanhol extraído dele corresponde byte a byte ao LocRes PT-BR. O backup original e a instalação também foram conferidos por SHA-256. Testes em base fictícia confirmam backup, instalação, reinstalação, restauração e recusa de corrupção ou base divergente. O EXE é compilado com PyInstaller.

A releitura do arquivo não comprova renderização no jogo. O teste real do menu foi confirmado pelo usuário; game_validated permanece false para a validação integral, e runtime_menu_confirmed registra a confirmação parcial. VALIDACAO.json registra instalação e verificações atuais. A chave AES local nunca foi copiada para a distribuição.

Fontes do formato: https://github.com/trumank/repak/blob/master/repak/src/entry.rs e https://github.com/trumank/repak/blob/master/repak/src/data.rs.
Códigos: ../src/build_pak_reinsertion.py e ../src/elliot_reinsertion_installer.py.
