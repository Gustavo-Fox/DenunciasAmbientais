"""Conexão com o SQLite: uma conexão por requisição, transações, esquema e migrações de bancos antigos."""
import sqlite3
from flask import current_app, g

SCHEMA = """
create table if not exists categorias(id integer primary key, nome text unique not null);
create table if not exists enderecos(id integer primary key, logradouro text, numero text, bairro text,
  municipio text, referencia text, lat real, lon real);
create table if not exists denuncias(id integer primary key, codigo text unique not null, criada text not null,
  categoria_id integer references categorias(id), endereco_id integer references enderecos(id), descricao text,
  denunciante text, contato text, prioridade text default 'Normal', status text default 'Recebida');
create table if not exists acompanhamentos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, data text not null, tipo text, texto text, autor text, status_novo text);
create table if not exists revisitas(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, prevista text not null, feita text, obs text);
create table if not exists desdobramentos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, tipo text, numero text, data text, obs text);
create table if not exists anexos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, acomp_id integer, nome text, arquivo text);
create index if not exists ix_den_status on denuncias(status);
create index if not exists ix_den_criada on denuncias(criada);
create index if not exists ix_den_end on denuncias(endereco_id);
create index if not exists ix_acomp_den on acompanhamentos(denuncia_id, data);
create index if not exists ix_rev_den on revisitas(denuncia_id, feita);
create index if not exists ix_desd_den on desdobramentos(denuncia_id);
create index if not exists ix_anx_den on anexos(denuncia_id);
create index if not exists ix_end_log on enderecos(logradouro);
"""

# Colunas acrescentadas depois da versão 1.0: iniciar() as cria em bancos antigos (e nos novos).
NOVAS = {
    "denuncias": [("anonima", "integer default 0"), ("reincidente", "integer default 0"), ("resp_nome", "text"),
                  ("resp_cpf", "text"), ("resp_contato", "text"), ("legislacao", "text"),
                  ("origem", "text default 'Denúncia'"), ("fiscal", "text"), ("status_anterior", "text")],
    "revisitas": [("fiscal", "text")],
    "anexos": [("tamanho", "integer"), ("criado_em", "text"), ("removido_em", "text"),
               ("removido_por", "text"), ("removido_motivo", "text")]}

CATEGORIAS_INICIAIS = ("Queimada", "Descarte irregular de resíduos", "Desmatamento", "Poluição hídrica",
                       "Poluição sonora", "Poluição do ar", "Maus-tratos a animais", "Outros")


def conexao():
    """Conexão SQLite da requisição atual (aberta no primeiro uso, fechada ao fim da requisição)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys=on")
    return g.db


def fechar(_=None):
    """Fecha a conexão com o banco ao terminar a requisição."""
    d = g.pop("db", None)
    if d:
        d.close()


def q(sql, a=(), one=False):
    """Consulta: devolve todas as linhas (ou só a primeira, com one=True; None se não houver)."""
    r = conexao().execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r


def ex(sql, a=()):
    """Escrita simples: executa, confirma (commit) e devolve o id da linha criada."""
    c = conexao().execute(sql, a)
    conexao().commit()
    return c.lastrowid


def transacao():
    """Várias escritas juntas: `with transacao() as cx: cx.execute(...)` grava tudo ou nada."""
    return conexao()


def iniciar(caminho):
    """Cria tabelas e índices, atualiza bancos de versões antigas e insere as categorias iniciais. Pode rodar várias vezes."""
    c = sqlite3.connect(caminho)
    c.executescript(SCHEMA)
    for tabela, cols in NOVAS.items():
        existentes = {r[1] for r in c.execute(f"pragma table_info({tabela})")}
        for nome, tipo in cols:
            if nome not in existentes:
                c.execute(f"alter table {tabela} add column {nome} {tipo}")
    c.execute("update denuncias set status='Recebida' where status='Aberta'")
    c.execute("update acompanhamentos set status_novo='Recebida' where status_novo='Aberta'")
    if not c.execute("select 1 from categorias").fetchone():
        c.executemany("insert into categorias(nome) values(?)", [(n,) for n in CATEGORIAS_INICIAIS])
    c.commit()
    c.close()
