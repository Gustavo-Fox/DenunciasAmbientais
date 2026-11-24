# Sistema de Denúncias Ambientais

Sistema de chamados para registrar e acompanhar denúncias ambientais: código único, endereço com mapa, categorias,
histórico, anexos, revisitas, desdobramentos (processo, notificação, embargo, autuação), ficha para impressão,
relatório mensal por fiscal, edição de cadastro e backup. Feito com Python (Flask) e SQLite, rodando no próprio computador.

## Como rodar

1. Instale o Python 3.9 ou mais novo.
2. Na pasta do projeto: `pip install -r requirements.txt`
3. Inicie: `python app.py`
4. Abra `http://127.0.0.1:5000` no navegador.

Na primeira execução o banco é criado, e bancos de versões anteriores são atualizados sozinhos.

## Onde ficam os dados

| Item | Local |
|---|---|
| Banco de dados | `denuncias.db` |
| Fotos e documentos | pasta `uploads/` |
| Cópias de segurança | pasta `backups/` (as 5 mais recentes) |

Para guardar os dados em outra pasta, defina `DENUNCIAS_DIR` antes de iniciar. Também existem `DENUNCIAS_HOST`
(padrão `127.0.0.1`, só este computador) e `DENUNCIAS_PORT` (padrão `5000`).

## Backup e restauração

- **Fazer:** menu **Backup > Gerar e baixar backup agora**. Guarde o arquivo também fora do computador.
- **Restaurar:** feche o sistema, extraia o `.zip`, substitua `denuncias.db` e a pasta `uploads` pelos do backup e abra de novo.

## Atualizar para uma nova versão

1. Faça um backup. 2. Feche o sistema. 3. Substitua o `app.py` (e o `CHANGELOG.md`). 4. Rode `python app.py`.
Os dados não são afetados, porque ficam fora do código.

## GitHub

Envie só o código. O banco, os anexos e os backups têm dados pessoais (LGPD) e **nunca** devem ir para o repositório.
Crie um `.gitignore` com:

```
denuncias.db
uploads/
backups/
__pycache__/
```

Para marcar versões: `git tag -a v1.3 -m "Versão 1.3"` e `git push origin v1.3`.

## Segurança e privacidade

- O sistema **ainda não tem login**. Por isso só aceita acessos do próprio computador. Antes de abrir para a rede,
  implemente usuários e senhas.
- Guarda CPF e dados de denunciantes: mantenha a pasta em computador de acesso restrito.
- Textos digitados são exibidos de forma segura, anexos HTML/SVG nunca são executados e envios de outros sites são bloqueados.

## Estrutura do `app.py`

Tudo em um arquivo, nesta ordem (procure pelos comentários `# ---`):

1. **Configuração:** pastas, variáveis de ambiente, listas de status, tipos e cores.
2. **Banco de dados:** tabelas, índices e atualização de bancos antigos (`SCHEMA`, `NOVAS`, `init()`).
3. **Utilitários:** acesso ao banco (`db`, `q`, `ex`), validação de formulário (`dados_form`, `iso`), código único (`novo_codigo`).
4. **Segurança, erros e filtros:** proteção de formulários, cabeçalhos, páginas de erro e filtros dos modelos.
5. **Rotas:** painel e cadastro, chamado e histórico, revisitas, mapa, categorias, relatório, edição e backup.
6. **Visual:** CSS e modelos HTML (`T`), com o `base` compartilhado por todas as telas.

Regra para gravar: uma escrita simples usa `ex()`; várias escritas que devem acontecer juntas usam `with db() as cx:`
(tudo é gravado ou nada é).
