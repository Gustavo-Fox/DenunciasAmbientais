"""Camada de acesso a dados: todo o SQL do sistema fica aqui. As rotas chamam estas funções e nunca escrevem SQL."""
import sqlite3
from datetime import date
from . import config as cfg
from .db import q, ex, transacao

# Campos da denúncia e do endereço (coluna, nome exibido no histórico de correções).
CAMPOS = [("criada", "Data de recebimento"), ("categoria_id", "Categoria"), ("prioridade", "Prioridade"),
          ("descricao", "Descrição"), ("legislacao", "Legislação"), ("reincidente", "Situação"), ("anonima", "Anonimato"),
          ("denunciante", "Denunciante"), ("contato", "Contato do denunciante"), ("resp_nome", "Responsável pelo local"),
          ("resp_cpf", "CPF do responsável"), ("resp_contato", "Contato do responsável"), ("fiscal", "Fiscal responsável")]
ENDS = [("logradouro", "Rua"), ("numero", "Número"), ("bairro", "Bairro"), ("municipio", "Município"),
        ("referencia", "Referência"), ("lat", "Latitude"), ("lon", "Longitude")]

_BASE_LISTA = """select d.*, c.nome cat, e.logradouro, e.numero, e.bairro from denuncias d
  left join categorias c on c.id=d.categoria_id left join enderecos e on e.id=d.endereco_id"""


def hoje():
    """Data de hoje no formato AAAA-MM-DD."""
    return date.today().isoformat()


def _marcas(n):
    return ",".join("?" * n)  # "?,?,?"


def _vazio(v):
    """Normaliza vazios (None, texto vazio e 0) para comparar o antes e o depois de uma edição."""
    return "" if v in (None, "", 0) else v


# --- Categorias -----------------------------------------------------------------
def categorias():
    """Todas as categorias, em ordem alfabética."""
    return q("select * from categorias order by nome")


def categorias_com_total():
    """Categorias com o total de chamados de cada uma."""
    return q("select c.*, (select count(*) from denuncias where categoria_id=c.id) n from categorias c order by nome")


def criar_categoria(nome):
    """Cria uma categoria; devolve False se ela já existir."""
    try:
        ex("insert into categorias(nome) values(?)", (nome,))
        return True
    except sqlite3.IntegrityError:
        return False


# --- Chamados ---------------------------------------------------------------------
def codigo_novo(origem="Denúncia"):
    """Próximo código único do ano: DEN-AAAA-00001 (denúncias) ou FIS-AAAA-00001 (fiscalizações), cada tipo com sua sequência."""
    pre = f"{cfg.PREFIXO[origem]}-{date.today().year}-"
    m = q("select max(codigo) m from denuncias where codigo like ?", (pre + "%",), True)["m"]
    return f"{pre}{(int(m[-5:]) + 1 if m else 1):05d}"


def contagens():
    """Totais do painel: (chamados em andamento, revisitas atrasadas)."""
    abertas = q("select count(*) n from denuncias where status not in ('Encerrada','Arquivada','Cancelada')", one=True)["n"]
    atras = q("""select count(*) n from revisitas r join denuncias d on d.id=r.denuncia_id
      where r.feita is null and r.prevista<? and d.status!='Cancelada'""", (hoje(),), True)["n"]
    return abertas, atras


def listar(status="", cat="", origem="", busca="", pagina=1):
    """Lista paginada de chamados com filtros; devolve um dicionário com rows, total, pag e paginas."""
    filtro, a = "", []
    if status:
        filtro += " and d.status=?"
        a.append(status)
    if origem in cfg.PREFIXO:
        filtro += " and d.origem=?"
        a.append(origem)
    if cat:
        filtro += " and d.categoria_id=?"
        a.append(cat)
    if busca:
        filtro += (" and (d.codigo like ? or d.descricao like ? or e.logradouro like ? or e.bairro like ?"
                   " or d.resp_nome like ? or d.resp_cpf like ?)")
        a += [f"%{busca}%"] * 6
    total = q("select count(*) n from denuncias d left join enderecos e on e.id=d.endereco_id where 1=1" + filtro, a, True)["n"]
    paginas = max(1, -(-total // cfg.POR_PAGINA))
    pag = min(max(1, pagina), paginas)
    rows = q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro,
      (select min(prevista) from revisitas r where r.denuncia_id=d.id and r.feita is null) prox,
      (select group_concat(distinct tipo) from desdobramentos x where x.denuncia_id=d.id) desd
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where 1=1""" + filtro + " order by d.id desc limit ? offset ?",
             a + [cfg.POR_PAGINA, (pag - 1) * cfg.POR_PAGINA])
    return dict(rows=rows, total=total, pag=pag, paginas=paginas)


def obter(did):
    """Um chamado com categoria e endereço (None se não existir)."""
    return q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro, e.municipio, e.referencia, e.lat, e.lon
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where d.id=?""", (did,), True)


def criar(novo, origem):
    """Cadastra endereço, chamado e primeiro registro do histórico numa transação; devolve (id, código).

    Se dois cadastros simultâneos gerarem o mesmo código, tenta de novo.
    """
    ce, cd, fisc = [k for k, _ in ENDS], [k for k, _ in CAMPOS], origem == "Fiscalização"
    status = "Em fiscalização" if fisc else "Recebida"
    for _ in range(5):
        try:
            with transacao() as cx:
                eid = cx.execute(f"insert into enderecos({','.join(ce)}) values({_marcas(len(ce))})",
                                 [novo[k] for k in ce]).lastrowid
                cols, codigo = ["codigo", "endereco_id", "status", "origem"] + cd, codigo_novo(origem)
                did = cx.execute(f"insert into denuncias({','.join(cols)}) values({_marcas(len(cols))})",
                                 [codigo, eid, status, origem] + [novo[k] for k in cd]).lastrowid
                cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,status_novo,autor) values(?,?,?,?,?,?)",
                           (did, novo["criada"], "Abertura" if fisc else "Recebimento",
                            "Fiscalização de ofício iniciada." if fisc else "Denúncia recebida.", status, novo["fiscal"]))
            return did, codigo
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Não foi possível gerar um código único.")


def atualizar(d, novo, autor=""):
    """Grava as correções do cadastro numa transação e lança no histórico o que mudou ("Correção").

    Devolve a lista com os nomes dos campos alterados.
    """
    mudou = [nome for k, nome in CAMPOS + ENDS if _vazio(d[k]) != _vazio(novo[k])]
    cd, ce = [k for k, _ in CAMPOS], [k for k, _ in ENDS]
    with transacao() as cx:
        cx.execute("update denuncias set " + ",".join(k + "=?" for k in cd) + " where id=?", [novo[k] for k in cd] + [d["id"]])
        cx.execute("update enderecos set " + ",".join(k + "=?" for k in ce) + " where id=?", [novo[k] for k in ce] + [d["endereco_id"]])
        if novo["criada"] != d["criada"]:
            cx.execute("update acompanhamentos set data=? where denuncia_id=? and tipo in ('Recebimento','Abertura')",
                       (novo["criada"], d["id"]))
        if mudou:
            cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)",
                       (d["id"], hoje(), "Correção", "Cadastro corrigido: " + ", ".join(mudou) + ".", autor))
    return mudou


def salvar_legislacao(did, texto):
    """Salva (ou apaga) o texto da legislação aplicável."""
    ex("update denuncias set legislacao=? where id=?", (texto, did))


def mesmo_endereco(d):
    """Outros chamados no mesmo endereço (rua e número) do chamado d."""
    return q("""select d2.id, d2.codigo, d2.criada from denuncias d2 join enderecos e2 on e2.id=d2.endereco_id
      where d2.id!=? and lower(e2.logradouro)=lower(?) and coalesce(e2.numero,'')=coalesce(?,'')""",
             (d["id"], d["logradouro"], d["numero"]))


def pontos_mapa():
    """Chamados com coordenadas (exceto os cancelados), para o mapa geral."""
    return [dict(r) for r in q("""select d.id, d.codigo, d.status, c.nome cat, e.lat, e.lon from denuncias d
      join enderecos e on e.id=d.endereco_id left join categorias c on c.id=d.categoria_id
      where e.lat is not null and d.status!='Cancelada'""")]


def centro_mapa():
    """Ponto inicial dos mapas: média das coordenadas já cadastradas ou o CENTRO padrão."""
    r = q("select avg(lat) a, avg(lon) o from enderecos where lat is not null", one=True)
    return (r["a"], r["o"], 12) if r["a"] is not None else cfg.CENTRO


# --- Histórico, cancelamento e desdobramentos ------------------------------------------------
def historico(did):
    """Histórico do chamado, do mais recente para o mais antigo."""
    return q("select * from acompanhamentos where denuncia_id=? order by data desc, id desc", (did,))


def registrar(did, data, tipo, texto, autor="", status=None):
    """Lança um registro no histórico (e, se informado, muda o status) numa transação; devolve o id do registro."""
    with transacao() as cx:
        aid = cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor,status_novo) values(?,?,?,?,?,?)",
                         (did, data, tipo, texto, autor, status)).lastrowid
        if status:
            cx.execute("update denuncias set status=? where id=?", (status, did))
    return aid


def cancelar(did, motivo, autor=""):
    """Cancela o chamado sem apagá-lo: guarda o status anterior e registra a justificativa no histórico."""
    with transacao() as cx:
        atual = cx.execute("select status from denuncias where id=?", (did,)).fetchone()["status"]
        cx.execute("update denuncias set status=?, status_anterior=? where id=?", (cfg.CANCELADA, atual, did))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor,status_novo) values(?,?,?,?,?,?)",
                   (did, hoje(), "Cancelamento", motivo, autor, cfg.CANCELADA))


def reativar(did, motivo, autor=""):
    """Reativa um chamado cancelado, devolvendo o status que ele tinha, e registra a justificativa."""
    with transacao() as cx:
        ant = cx.execute("select status_anterior a from denuncias where id=?", (did,)).fetchone()["a"] or "Recebida"
        cx.execute("update denuncias set status=?, status_anterior=null where id=?", (ant, did))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor,status_novo) values(?,?,?,?,?,?)",
                   (did, hoje(), "Reativação", motivo, autor, ant))


def ultimo_cancelamento(did):
    """Último registro de cancelamento do chamado (None se não houver)."""
    return q("select * from acompanhamentos where denuncia_id=? and tipo='Cancelamento' order by id desc limit 1", (did,), True)


def desdobramentos(did):
    """Processos, notificações, embargos e autuações do chamado."""
    return q("select * from desdobramentos where denuncia_id=? order by data", (did,))


def registrar_desdobramento(did, tipo, numero, data, obs):
    """Registra o desdobramento e lança o fato no histórico, numa transação."""
    txt = tipo + " registrado(a)" + (" nº " + numero if numero else "") + (": " + obs if obs else "")
    with transacao() as cx:
        cx.execute("insert into desdobramentos(denuncia_id,tipo,numero,data,obs) values(?,?,?,?,?)", (did, tipo, numero, data, obs))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto) values(?,?,?,?)", (did, data, "Atualização", txt))


# --- Revisitas --------------------------------------------------------------------
def revisitas_do_chamado(did):
    """Revisitas do chamado, por data prevista."""
    return q("select * from revisitas where denuncia_id=? order by prevista", (did,))


def revisitas_pendentes():
    """Revisitas ainda não feitas (de chamados não cancelados), da mais antiga para a mais nova."""
    return q("""select r.*, d.codigo, e.logradouro, e.numero, e.bairro
      from revisitas r join denuncias d on d.id=r.denuncia_id left join enderecos e on e.id=d.endereco_id
      where r.feita is null and d.status!='Cancelada' order by r.prevista""")


def agendar_revisita(did, prevista):
    """Agenda uma revisita."""
    ex("insert into revisitas(denuncia_id,prevista) values(?,?)", (did, prevista))


def revisita(rid):
    """Uma revisita (None se não existir)."""
    return q("select * from revisitas where id=?", (rid,), True)


def concluir_revisita(r, obs, fiscal):
    """Conclui a revisita e lança o que foi constatado no histórico, numa transação."""
    with transacao() as cx:
        cx.execute("update revisitas set feita=?, obs=?, fiscal=? where id=?", (hoje(), obs, fiscal, r["id"]))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)",
                   (r["denuncia_id"], hoje(), "Revisita", obs, fiscal))


# --- Anexos -----------------------------------------------------------------------
def anexos_por_acomp(did):
    """Anexos ativos do chamado, agrupados pelo id do registro do histórico (None = anexos do cadastro)."""
    an = {}
    for x in q("select * from anexos where denuncia_id=? and removido_em is null order by id", (did,)):
        an.setdefault(x["acomp_id"], []).append(x)
    return an


def anexo(aid):
    """Um anexo (inclusive removido); None se não existir."""
    return q("select * from anexos where id=?", (aid,), True)


def inserir_anexo(did, acomp_id, nome, arquivo, tamanho):
    """Registra um anexo já gravado em disco; devolve o id."""
    return ex("insert into anexos(denuncia_id,acomp_id,nome,arquivo,tamanho,criado_em) values(?,?,?,?,?,?)",
              (did, acomp_id, nome, arquivo, tamanho, hoje()))


def marcar_anexo_removido(a, motivo, autor, no_historico=True):
    """Marca o anexo como removido (com motivo e autor) e, se pedido, lança o fato no histórico."""
    with transacao() as cx:
        cx.execute("update anexos set removido_em=?, removido_por=?, removido_motivo=? where id=?", (hoje(), autor, motivo, a["id"]))
        if no_historico:
            cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)",
                       (a["denuncia_id"], hoje(), "Anexo", f"Anexo removido: {a['nome']}. Motivo: {motivo}", autor))


# --- Relatório mensal -----------------------------------------------------------------------
def relatorio(mes, fiscal=""):
    """Dados do relatório mensal (mes = AAAA-MM; fiscal filtra registros, revisitas e fiscalizações)."""
    m, ts = mes + "%", cfg.TIPOS_SISTEMA
    nt = _marcas(len(ts))
    return dict(
        den=q(_BASE_LISTA + " where d.criada like ? and d.origem='Denúncia' order by d.criada", (m,)),
        fis=q(_BASE_LISTA + " where d.origem='Fiscalização' and d.criada like ? and (?='' or d.fiscal=?) order by d.criada", (m, fiscal, fiscal)),
        porfis=q("""select coalesce(nullif(fiscal,''),'(sem fiscal)') f, count(*) n from denuncias
          where origem='Fiscalização' and criada like ? group by f order by n desc""", (m,)),
        reg=q(f"""select a.*, d.codigo from acompanhamentos a join denuncias d on d.id=a.denuncia_id
          where a.data like ? and a.tipo not in ({nt}) and (?='' or a.autor=?) order by a.data""", (m, *ts, fiscal, fiscal)),
        rev=q("""select r.*, d.codigo from revisitas r join denuncias d on d.id=r.denuncia_id
          where r.feita like ? and (?='' or r.fiscal=?) order by r.feita""", (m, fiscal, fiscal)),
        desd=q("""select x.*, d.codigo from desdobramentos x join denuncias d on d.id=x.denuncia_id
          where x.data like ? order by x.data""", (m,)),
        prev=q("select count(*) n from revisitas where prevista like ? and feita is null", (m,), True)["n"],
        porcat=q("""select c.nome, count(*) n from denuncias d left join categorias c on c.id=d.categoria_id
          where d.criada like ? and d.origem='Denúncia' group by c.nome order by n desc""", (m,)),
        porfiscal=q(f"""select coalesce(nullif(autor,''),'(sem fiscal)') f, count(*) n,
          sum(tipo in ('Vistoria','Revisita')) v from acompanhamentos
          where data like ? and tipo not in ({nt}) group by f order by n desc""", (m, *ts)),
        fiscais=[r["autor"] for r in q("""select autor from acompanhamentos where coalesce(autor,'')!=''
          union select fiscal from denuncias where coalesce(fiscal,'')!='' order by 1""")])
