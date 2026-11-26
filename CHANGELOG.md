# Histórico de versões

## 2.0
- Nova estrutura do código, pronta para trabalho em equipe: pacote `sistema/` (config, banco, camada de acesso a dados `repo.py`, serviço de anexos), rotas por assunto (blueprints em `sistema/rotas/`), `templates/` e `static/` (CSS e JavaScript em arquivos próprios) e testes automáticos em `tests/`
- Cancelar chamado com justificativa obrigatória, sem apagar (e reativar, também com justificativa); o chamado cancelado fica bloqueado para alterações e sai das contagens, revisitas pendentes e mapa
- Anexos: limite de tamanho por tipo (imagens 15 MB, documentos 25 MB, vídeos 100 MB) e de 20 arquivos por envio, só tipos permitidos (com conferência do conteúdo), miniaturas das imagens (Pillow), e substituir ou remover um anexo com motivo; o arquivo removido fica guardado em `uploads/_removidos` e o fato entra no histórico
- Ao atualizar de versões anteriores: troque os arquivos do programa e mantenha `denuncias.db`, `uploads/` e `backups/`; o banco é atualizado sozinho

## 1.4
- Atalho para a área de trabalho (criar_atalho.bat, com ícone) e inicializador (iniciar.bat); o sistema abre o navegador sozinho
- Fiscalizações de ofício (que não vieram de denúncia): código próprio FIS-AAAA-00001, fiscal responsável, histórico, anexos, revisitas, mapa, ficha e seção própria no relatório mensal

## 1.3.1
- Correção: os mapas voltam a carregar (o cabeçalho de privacidade da 1.3 fazia o OpenStreetMap bloquear os blocos do mapa)

## 1.3
- Editar o cadastro de denúncias já registradas (dados, responsável e local com mapa); cada correção entra no histórico como "Correção" e não conta na produtividade
- Backup com um clique: .zip com banco e anexos, com as 5 últimas cópias guardadas na pasta backups
- Segurança: os textos digitados passam a ser exibidos de forma segura (escape de HTML)
- Revisão geral: código documentado (docstrings e comentários) e README.md
- Listagem paginada (50 por página) e índices no banco, para continuar rápido com muitos chamados
- Cadastro, edição e demais gravações em transação única; código único protegido contra cadastros simultâneos
- Correções: revisita concluída duas vezes duplicava o registro; datas, coordenadas, status e tipos agora são validados; chamados inexistentes respondem 404
- Segurança: anexos HTML/SVG não são mais executados (só imagens e PDF abrem no navegador), proteção contra envios de outros sites e cabeçalhos de segurança
- Mensagens de confirmação, páginas de erro amigáveis e título por página (o PDF da ficha já sai com o código no nome)
- Configuração por variáveis de ambiente: DENUNCIAS_DIR, DENUNCIAS_HOST e DENUNCIAS_PORT

## 1.2
- Ficha de impressão/PDF da denúncia, compacta, que omite as seções vazias
- Cores distintas para cada status (etiquetas, lista e cartão do chamado) e legenda na lista
- Novos status: Recebida, Em fiscalização, Notificada, Embargada, Autuada e Arquivada ("Aberta" vira "Recebida" automaticamente)
- Campo de legislação aplicável (texto livre, com **negrito** e *itálico*), editável a qualquer momento

## 1.1
- Responsável pelo local (nome, CPF, contato), com busca por esses dados
- Denúncia anônima
- Primeira vez ou reincidência; lista de outros chamados no mesmo endereço
- Registro de processo, notificação, embargo ou autuação
- Relatório mensal imprimível (denúncias, revisitas, registros e produtividade por fiscal)
- Campo "Fiscal" ao concluir revisitas; versão exibida no rodapé
- Bancos da versão 1.0 são atualizados automaticamente

## 1.0
- Chamados de denúncias, endereços com latitude/longitude, categorias, código único
- Histórico do chamado, anexos de fotos e documentos, revisitas e mapa
