# Sistema de Denúncias Ambientais

Sistema de chamados para registrar e acompanhar denúncias e fiscalizações de ofício: código único, endereço com mapa,
categorias, histórico, anexos, revisitas, processo/notificação/embargo/autuação, ficha para impressão, relatório mensal
por fiscal, edição de cadastro, cancelamento com justificativa e backup. Python (Flask) + SQLite, rodando no próprio computador.

## Como rodar

1. Instale o Python 3.9 ou mais novo.
2. Na pasta do projeto: `pip install -r requirements.txt` (Flask e Pillow, esta para as miniaturas).
3. Inicie: `python app.py`. O navegador abre em `http://127.0.0.1:5000`.

**Atalho no Windows:** dê dois cliques em `criar_atalho.bat`. Ele cria na área de trabalho o atalho *Denuncias Ambientais*,
que inicia o sistema e abre o navegador (se já estiver aberto, só abre o navegador). Mantenha a janela do sistema aberta
(minimizada); para encerrar, feche-a. Sem o atalho, use `iniciar.bat`.

## Recursos principais

- **Denúncias e fiscalizações de ofício:** cada tipo tem sua sequência de código (`DEN-AAAA-00001` e `FIS-AAAA-00001`).
- **Cancelar chamado:** exige justificativa (mínimo de 10 caracteres) e não apaga nada. O chamado vira "Cancelada", fica
  bloqueado para alterações e pode ser reativado, também com justificativa. Tudo fica no histórico.
- **Anexos:** imagens até 15 MB, documentos até 25 MB, vídeos até 100 MB, 20 arquivos por envio (limites em
  `sistema/config.py`). Só tipos permitidos, com conferência do conteúdo. Imagens têm miniatura. É possível **substituir**
  ou **remover** um anexo informando o motivo: o arquivo vai para `uploads/_removidos` (não é apagado) e o fato entra no histórico.
- **Relatório mensal** por fiscal, **ficha** para imprimir/PDF, **mapa**, **backup** de um clique.

## Onde ficam os dados

| Item | Local |
|---|---|
| Banco de dados | `denuncias.db` |
| Fotos e documentos | `uploads/` (miniaturas em `uploads/_mini`, removidos em `uploads/_removidos`) |
| Cópias de segurança | `backups/` (as 5 mais recentes) |

Outra pasta de dados: defina `DENUNCIAS_DIR`. Também existem `DENUNCIAS_HOST` (padrão `127.0.0.1`, só este computador)
e `DENUNCIAS_PORT` (padrão `5000`).

**Backup:** menu *Backup > Gerar e baixar backup agora* (guarde o arquivo também fora do computador).
**Restaurar:** feche o sistema, extraia o `.zip`, substitua `denuncias.db` e a pasta `uploads` e abra de novo.

## Atualizar para uma nova versão

1. Faça um backup e feche o sistema.
2. Copie os arquivos novos por cima (`app.py`, `sistema/`, `templates/`, `static/`, `tests/` e os `.bat`), **sem apagar**
   `denuncias.db`, `uploads/` e `backups/`.
3. Rode de novo. O banco é atualizado sozinho. Veja o `CHANGELOG.md`.

## Organização do código (para trabalhar em equipe)

```
app.py                  ponto de entrada (abre o navegador, roda o servidor)
sistema/
  __init__.py           create_app(): configuração, segurança, erros e registro das rotas
  config.py             constantes: status e cores, tipos, limites de anexos, variáveis de ambiente
  db.py                 conexão SQLite, transações, esquema e migrações de bancos antigos
  repo.py               camada de acesso a dados: TODO o SQL fica aqui
  armazenamento.py      anexos: validação, gravação, miniaturas, remoção sem apagar
  util.py, filters.py   leitura de formulários, datas, filtros dos modelos
  rotas/                uma "blueprint" por assunto: painel, chamados, revisitas, anexos, relatorios, backup
templates/              telas (HTML/Jinja); arquivos começados por _ são pedaços reutilizados
static/css, static/js   estilos e scripts (mapa)
tests/                  testes automáticos
```

Regras: rota não escreve SQL (chama `repo`); várias gravações que devem andar juntas usam `with transacao() as cx:`;
mudanças de tela ficam em `templates/` e `static/`, sem HTML dentro de Python. Para criar uma coluna nova, acrescente-a em
`NOVAS` (`db.py`). Rode os testes antes de enviar mudanças: `python -m unittest discover -t . -s tests`.

## GitHub

Envie só o código (o `.gitignore` já exclui `denuncias.db`, `uploads/`, `backups/` e `__pycache__/`: eles têm dados
pessoais e nunca devem ir para o repositório). Para marcar versões: `git tag -a v2.0 -m "Versão 2.0"` e `git push origin v2.0`.

## Segurança e privacidade

- Ainda **não há login**; por isso o sistema só aceita acessos do próprio computador. Antes de abrir para a rede, implemente usuários e senhas.
- Guarda CPF e dados de denunciantes (LGPD): mantenha a pasta em computador de acesso restrito.
- Textos digitados são exibidos de forma segura, anexos HTML/SVG nunca são executados, envios de outros sites são bloqueados.
