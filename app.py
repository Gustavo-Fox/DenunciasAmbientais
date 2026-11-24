"""Sistema de denúncias ambientais (chamados de fiscalização) - Flask + SQLite, 100% local.

Como rodar:  python app.py   ->  http://127.0.0.1:5000

Tudo está neste arquivo, na ordem: configuração, banco de dados, utilitários, filtros dos modelos,
rotas (painel, chamado, histórico, revisitas, mapa, categorias, relatório, edição, backup) e, por fim,
o visual (CSS e modelos HTML). Os dados ficam em denuncias.db, uploads/ e backups/ (pasta definida por
DENUNCIAS_DIR; por padrão, a mesma do app.py). Veja o README.md e o CHANGELOG.md.
"""
import os, re, sqlite3, uuid, zipfile
from urllib.parse import urlencode, urlsplit
from datetime import date, datetime
from flask import Flask, g, request, redirect, url_for, render_template, flash, send_file, send_from_directory, abort
from jinja2 import DictLoader
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

# --- Configuração -----------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DENUNCIAS_DIR", BASE)           # pasta dos dados (banco, anexos e backups)
DB = os.path.join(DATA, "denuncias.db")
UP = os.path.join(DATA, "uploads")                     # fotos e documentos anexados
BK = os.path.join(DATA, "backups")                     # cópias de segurança (.zip)
HOST = os.environ.get("DENUNCIAS_HOST", "127.0.0.1")   # 127.0.0.1 = acessível só neste computador
PORT = int(os.environ.get("DENUNCIAS_PORT", "5000"))
POR_PAGINA = 50                                        # chamados por página na listagem
os.makedirs(UP, exist_ok=True)
STATUS = ["Recebida", "Em análise", "Em fiscalização", "Vistoriada", "Notificada", "Embargada", "Autuada",
          "Aguardando retorno", "Encerrada", "Arquivada"]
COR = {  # status: (cor do texto/borda, cor de fundo)
    "Recebida": ("#1d5fa8", "#dce9f7"), "Em análise": ("#6b3fa0", "#ece3f6"), "Em fiscalização": ("#0b7285", "#d5f0f4"),
    "Vistoriada": ("#2e7d32", "#dff0d8"), "Notificada": ("#8a5a00", "#fcefc7"), "Embargada": ("#b04a0b", "#fde3d0"),
    "Autuada": ("#b3261e", "#fadbd8"), "Aguardando retorno": ("#a1296b", "#f8dceb"),
    "Encerrada": ("#37474f", "#dde4e8"), "Arquivada": ("#6d4c41", "#ede4e0")}
PRIORIDADES = ["Baixa", "Normal", "Alta"]
TIPOS = ["Atualização", "Vistoria", "Revisita", "Contato", "Encerramento"]
VERSAO = "1.3"
DESD = ["Processo", "Notificação", "Embargo", "Autuação"]
CENTRO = (-14.2, -51.9, 4)  # centro inicial do mapa (lat, lon, zoom); ajuste para sua região
LEAF = ('<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')

# --- Banco de dados ---------------------------------------------------------
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

# Colunas acrescentadas depois da versão 1.0: init() as cria em bancos antigos.
NOVAS = {"denuncias": [("anonima", "integer default 0"), ("reincidente", "integer default 0"),
    ("resp_nome", "text"), ("resp_cpf", "text"), ("resp_contato", "text"), ("legislacao", "text")], "revisitas": [("fiscal", "text")]}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.secret_key = os.urandom(24)  # usada só nas mensagens de aviso (flash); muda a cada reinício


# --- Acesso ao banco e utilitários -------------------------------------------
def db():
    """Conexão SQLite da requisição atual (aberta no primeiro uso, fechada ao fim da requisição)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys=on")
    return g.db

@app.teardown_appcontext
def close(_):
    """Fecha a conexão com o banco ao terminar a requisição."""
    d = g.pop("db", None)
    if d:
        d.close()

def q(sql, a=(), one=False):
    """Consulta: devolve todas as linhas (ou só a primeira, com one=True; None se não houver)."""
    r = db().execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r

def ex(sql, a=()):
    """Escrita simples: executa, confirma (commit) e devolve o id da linha criada. Para várias escritas juntas, use with db()."""
    c = db().execute(sql, a)
    db().commit()
    return c.lastrowid

def init():
    """Cria tabelas e índices, atualiza bancos de versões antigas e insere as categorias iniciais. Pode rodar várias vezes."""
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    for t, cols in NOVAS.items():
        have = {r[1] for r in c.execute(f"pragma table_info({t})")}
        for n, tp in cols:
            if n not in have:
                c.execute(f"alter table {t} add column {n} {tp}")
    c.execute("update denuncias set status='Recebida' where status='Aberta'")
    c.execute("update acompanhamentos set status_novo='Recebida' where status_novo='Aberta'")
    if not c.execute("select 1 from categorias").fetchone():
        c.executemany("insert into categorias(nome) values(?)", [(n,) for n in (
            "Queimada", "Descarte irregular de resíduos", "Desmatamento", "Poluição hídrica",
            "Poluição sonora", "Poluição do ar", "Maus-tratos a animais", "Outros")])
    c.commit()
    c.close()

def novo_codigo():
    """Próximo código único do ano, no formato DEN-AAAA-00001."""
    pre = f"DEN-{date.today().year}-"
    m = q("select max(codigo) m from denuncias where codigo like ?", (pre + "%",), True)["m"]
    return f"{pre}{(int(m[-5:]) + 1 if m else 1):05d}"

def num(v):
    """Converte texto em número aceitando vírgula decimal; devolve None se vazio ou inválido."""
    try:
        return float(v.replace(",", "."))
    except (ValueError, AttributeError):
        return None

def exige(did):
    """Garante que a denúncia existe (senão responde 404)."""
    q("select 1 from denuncias where id=?", (did,), True) or abort(404)

def iso(v):
    """Valida uma data AAAA-MM-DD vinda do formulário (senão responde 400)."""
    try:
        return date.fromisoformat((v or "").strip()).isoformat()
    except ValueError:
        abort(400)

def dados_form(f):
    """Lê, limpa e valida os campos do formulário de denúncia (usado ao cadastrar e ao editar)."""
    g_ = lambda k: f.get(k, "").strip()
    try:
        cat = int(f.get("categoria_id", ""))
    except ValueError:
        abort(400)
    if not g_("descricao") or not g_("logradouro"):
        abort(400)
    lat, lon = num(g_("lat")), num(g_("lon"))
    if (lat is not None and not -90 <= lat <= 90) or (lon is not None and not -180 <= lon <= 180):
        abort(400)
    if (lat is None) != (lon is None):
        lat = lon = None
    anon = 1 if f.get("anonima") else 0
    return {"criada": iso(f.get("criada")), "categoria_id": cat,
            "prioridade": g_("prioridade") if g_("prioridade") in PRIORIDADES else "Normal",
            "descricao": g_("descricao"), "legislacao": g_("legislacao"),
            "reincidente": 1 if f.get("reincidente") == "1" else 0, "anonima": anon,
            "denunciante": "" if anon else g_("denunciante"), "contato": "" if anon else g_("contato"),
            "resp_nome": g_("resp_nome"), "resp_cpf": g_("resp_cpf"), "resp_contato": g_("resp_contato"),
            "logradouro": g_("logradouro"), "numero": g_("numero"), "bairro": g_("bairro"),
            "municipio": g_("municipio"), "referencia": g_("referencia"), "lat": lat, "lon": lon}

def centro():
    """Ponto inicial dos mapas: média das coordenadas já cadastradas ou o CENTRO padrão."""
    r = q("select avg(lat) a, avg(lon) o from enderecos where lat is not null", one=True)
    return (r["a"], r["o"], 12) if r["a"] is not None else CENTRO

def salvar_arquivos(did, aid=None):
    """Grava os arquivos enviados no formulário na pasta de anexos e os vincula à denúncia (e à atualização, se houver)."""
    for f in request.files.getlist("arquivos"):
        if f and f.filename:
            arq = uuid.uuid4().hex[:8] + "_" + (secure_filename(f.filename) or "arquivo")
            f.save(os.path.join(UP, arq))
            ex("insert into anexos(denuncia_id,acomp_id,nome,arquivo) values(?,?,?,?)", (did, aid, f.filename, arq))

# --- Segurança, erros e filtros dos modelos ----------------------------------
@app.before_request
def mesma_origem():
    """Bloqueia envios de formulário vindos de outros sites (proteção contra CSRF)."""
    if request.method == "POST":
        o = request.headers.get("Origin") or request.headers.get("Referer", "")
        if o and urlsplit(o).netloc != request.host:
            abort(403)

@app.after_request
def cabecalhos(r):
    """Cabeçalhos de segurança em todas as respostas."""
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"})
    return r

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(500)
def erro(e):
    """Página de erro amigável."""
    msgs = {400: "Dados inválidos. Volte e confira o formulário.", 403: "Acesso negado.", 404: "Página não encontrada.",
            413: "Arquivo grande demais (limite de 200 MB).", 500: "Erro interno. Tente de novo e, se persistir, avise o responsável."}
    return render_template("erro", cod=e.code, msg=msgs.get(e.code, "Erro.")), e.code

@app.context_processor
def ctx():
    """Variáveis disponíveis em todas as telas (status, tipos, versão, data de hoje e qs para links que mantêm os filtros)."""
    return dict(STATUS=STATUS, TIPOS=TIPOS, DESD=DESD, VERSAO=VERSAO, LEAF=Markup(LEAF), hoje=date.today().isoformat(),
                qs=lambda **kw: urlencode({**request.args.to_dict(), **kw}))

@app.template_filter("st")
def st_tag(v):
    """Filtro st: etiqueta colorida do status."""
    fg, bg = COR.get(v, ("#37474f", "#dde4e8"))
    return Markup(f'<span class=tag style="background:{bg};color:{fg};border:1px solid {fg}">{escape(v)}</span>')

@app.template_filter("cor")
def st_cor(v):
    """Filtro cor: cor principal do status (bordas da lista e do chamado)."""
    return COR.get(v, ("#37474f",))[0]

@app.template_filter("br")
def br(v):
    """Filtro br: converte data AAAA-MM-DD para DD/MM/AAAA."""
    return f"{v[8:10]}/{v[5:7]}/{v[:4]}" if v and len(v) >= 10 else (v or "")

@app.template_filter("fmt")
def fmt(t):
    """Filtro fmt: texto seguro com quebras de linha, **negrito** e *itálico*."""
    t = str(escape(t or ""))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])", r"<i>\1</i>", t)
    return Markup(t.replace("\n", "<br>"))

@app.template_filter("anexo")
def anexo(x):
    """Filtro anexo: miniatura para imagens e link para os demais arquivos."""
    u, n = "/uploads/" + x["arquivo"], escape(x["nome"])
    if x["arquivo"].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return Markup(f'<a href="{u}" target=_blank title="{n}"><img src="{u}" alt="{n}" '
                      f'style="height:80px;border-radius:4px;margin:4px 6px 0 0"></a>')
    return Markup(f'<a href="{u}" target=_blank>{n}</a> ')


# --- Rotas: painel e cadastro --------------------------------------------------
@app.route("/")
def index():
    """Painel principal: totais, filtros (status, categoria, busca) e lista paginada de chamados."""
    st, cat, b = request.args.get("status", ""), request.args.get("cat", ""), request.args.get("q", "").strip()
    filtro, a = "", []
    if st:
        filtro += " and d.status=?"
        a.append(st)
    if cat:
        filtro += " and d.categoria_id=?"
        a.append(cat)
    if b:
        filtro += (" and (d.codigo like ? or d.descricao like ? or e.logradouro like ? or e.bairro like ?"
                   " or d.resp_nome like ? or d.resp_cpf like ?)")
        a += [f"%{b}%"] * 6
    total = q("select count(*) n from denuncias d left join enderecos e on e.id=d.endereco_id where 1=1" + filtro, a, True)["n"]
    paginas = max(1, -(-total // POR_PAGINA))
    pag = min(max(1, request.args.get("page", 1, type=int)), paginas)
    rows = q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro,
      (select min(prevista) from revisitas r where r.denuncia_id=d.id and r.feita is null) prox,
      (select group_concat(distinct tipo) from desdobramentos x where x.denuncia_id=d.id) desd
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where 1=1""" + filtro + " order by d.id desc limit ? offset ?",
      a + [POR_PAGINA, (pag - 1) * POR_PAGINA])
    return render_template("index", rows=rows, total=total, pag=pag, paginas=paginas,
        cats=q("select * from categorias order by nome"),
        abertas=q("select count(*) n from denuncias where status not in ('Encerrada','Arquivada')", one=True)["n"],
        atras=q("select count(*) n from revisitas where feita is null and prevista<?",
                (date.today().isoformat(),), True)["n"])

@app.route("/nova", methods=["GET", "POST"])
def nova():
    """Cadastra uma denúncia (GET: formulário; POST: grava) e gera o código único."""
    if request.method == "POST":
        novo = dados_form(request.form)
        ce, cd = [k for k, _ in ENDS], [k for k, _ in CAMPOS]
        for _ in range(5):  # se dois cadastros simultâneos gerarem o mesmo código, tenta de novo
            try:
                with db() as cx:  # transação única: grava tudo ou nada
                    eid = cx.execute(f"insert into enderecos({','.join(ce)}) values({','.join('?' * len(ce))})",
                                     [novo[k] for k in ce]).lastrowid
                    cols, codigo = ["codigo", "endereco_id", "status"] + cd, novo_codigo()
                    did = cx.execute(f"insert into denuncias({','.join(cols)}) values({','.join('?' * len(cols))})",
                                     [codigo, eid, "Recebida"] + [novo[k] for k in cd]).lastrowid
                    cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,status_novo) values(?,?,?,?,?)",
                               (did, novo["criada"], "Recebimento", "Denúncia recebida.", "Recebida"))
                break
            except sqlite3.IntegrityError:
                continue
        else:
            abort(500)
        salvar_arquivos(did)
        flash(f"Denúncia registrada com o código {codigo}.")
        return redirect(url_for("detalhe", did=did))
    return render_template("nova", cats=q("select * from categorias order by nome"), c=centro())

# --- Rotas: chamado e histórico -------------------------------------------------
@app.route("/d/<int:did>")
def detalhe(did):
    """Tela do chamado: dados, revisitas, desdobramentos, atualização e histórico."""
    return pagina("detalhe", did)

@app.route("/d/<int:did>/imprimir")
def imprimir(did):
    """Ficha compacta do chamado para imprimir ou salvar em PDF."""
    return pagina("ficha", did)

@app.post("/d/<int:did>/legislacao")
def legislacao(did):
    """Salva (ou apaga) o texto da legislação aplicável."""
    exige(did)
    ex("update denuncias set legislacao=? where id=?", (request.form.get("legislacao", "").strip(), did))
    flash("Legislação salva.")
    return redirect(url_for("detalhe", did=did))

def pagina(modelo, did):
    """Reúne os dados de um chamado e os entrega ao modelo (detalhe ou ficha)."""
    d = q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro, e.municipio, e.referencia, e.lat, e.lon
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where d.id=?""", (did,), True) or abort(404)
    an = {}
    for x in q("select * from anexos where denuncia_id=?", (did,)):
        an.setdefault(x["acomp_id"], []).append(x)
    return render_template(modelo, d=d, an=an,
        tl=q("select * from acompanhamentos where denuncia_id=? order by data desc, id desc", (did,)),
        revs=q("select * from revisitas where denuncia_id=? order by prevista", (did,)),
        desd=q("select * from desdobramentos where denuncia_id=? order by data", (did,)),
        outros=q("""select d2.id, d2.codigo, d2.criada from denuncias d2 join enderecos e2 on e2.id=d2.endereco_id
          where d2.id!=? and lower(e2.logradouro)=lower(?) and coalesce(e2.numero,'')=coalesce(?,'')""",
          (did, d["logradouro"], d["numero"])))

@app.post("/d/<int:did>/acompanhar")
def acompanhar(did):
    """Registra uma atualização no histórico (e, se informado, muda o status e anexa arquivos)."""
    exige(did)
    f = request.form
    st = f.get("status") or None
    texto = f.get("texto", "").strip()
    if st not in (None, *STATUS) or not texto:
        abort(400)
    with db() as cx:
        aid = cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor,status_novo) values(?,?,?,?,?,?)",
                         (did, iso(f.get("data")), f.get("tipo") if f.get("tipo") in TIPOS else "Atualização",
                          texto, f.get("autor", "").strip(), st)).lastrowid
        if st:
            cx.execute("update denuncias set status=? where id=?", (st, did))
    salvar_arquivos(did, aid)
    flash("Atualização registrada.")
    return redirect(url_for("detalhe", did=did))

@app.post("/d/<int:did>/revisita")
def agendar(did):
    """Agenda uma revisita para a data informada."""
    exige(did)
    ex("insert into revisitas(denuncia_id,prevista) values(?,?)", (did, iso(request.form.get("prevista"))))
    flash("Revisita agendada.")
    return redirect(url_for("detalhe", did=did))

@app.post("/d/<int:did>/desdobramento")
def desdobrar(did):
    """Registra processo, notificação, embargo ou autuação e lança o fato no histórico."""
    exige(did)
    f = request.form
    tipo = f.get("tipo")
    if tipo not in DESD:
        abort(400)
    numero, obs, data = f.get("numero", "").strip(), f.get("obs", "").strip(), iso(f.get("data"))
    txt = tipo + " registrado(a)" + (" nº " + numero if numero else "") + (": " + obs if obs else "")
    with db() as cx:
        cx.execute("insert into desdobramentos(denuncia_id,tipo,numero,data,obs) values(?,?,?,?,?)", (did, tipo, numero, data, obs))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto) values(?,?,?,?)", (did, data, "Atualização", txt))
    flash(f"{tipo} registrado(a).")
    return redirect(url_for("detalhe", did=did))

@app.post("/revisita/<int:rid>/feita")
def revisita_feita(rid):
    """Conclui uma revisita agendada e lança o que foi constatado no histórico (uma única vez)."""
    r = q("select * from revisitas where id=?", (rid,), True) or abort(404)
    obs, fiscal, h = request.form.get("obs", "").strip(), request.form.get("fiscal", "").strip(), date.today().isoformat()
    if r["feita"] or not obs:  # já concluída (clique duplo) ou sem relato
        return redirect(url_for("detalhe", did=r["denuncia_id"]))
    with db() as cx:
        cx.execute("update revisitas set feita=?, obs=?, fiscal=? where id=?", (h, obs, fiscal, rid))
        cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)",
                   (r["denuncia_id"], h, "Revisita", obs, fiscal))
    flash("Revisita concluída.")
    return redirect(url_for("detalhe", did=r["denuncia_id"]))

# --- Rotas: revisitas, mapa, categorias e relatório -----------------------------
@app.route("/revisitas")
def revisitas():
    """Revisitas pendentes, da mais antiga para a mais nova."""
    return render_template("revisitas", rows=q("""select r.*, d.codigo, e.logradouro, e.numero, e.bairro
      from revisitas r join denuncias d on d.id=r.denuncia_id left join enderecos e on e.id=d.endereco_id
      where r.feita is null order by r.prevista"""))

@app.route("/mapa")
def mapa():
    """Mapa com todas as denúncias que têm coordenadas."""
    pts = [dict(r) for r in q("""select d.id, d.codigo, d.status, c.nome cat, e.lat, e.lon from denuncias d
      join enderecos e on e.id=d.endereco_id left join categorias c on c.id=d.categoria_id where e.lat is not null""")]
    return render_template("mapa", pontos=pts, c=centro())

@app.route("/categorias", methods=["GET", "POST"])
def categorias():
    """Lista as categorias (com o total de denúncias) e permite criar novas."""
    if request.method == "POST":
        n = request.form["nome"].strip()
        if n:
            try:
                ex("insert into categorias(nome) values(?)", (n,))
                flash("Categoria adicionada.")
            except sqlite3.IntegrityError:
                flash("Essa categoria já existe.")
        return redirect(url_for("categorias"))
    return render_template("categorias", rows=q("""select c.*, (select count(*) from denuncias
      where categoria_id=c.id) n from categorias c order by nome"""))

@app.route("/relatorio")
def relatorio():
    """Relatório mensal imprimível: totais, produtividade por fiscal e listas do período."""
    mes = request.args.get("mes", "")
    if not re.fullmatch(r"\d{4}-\d{2}", mes):
        mes = date.today().strftime("%Y-%m")
    fiscal, m = request.args.get("fiscal", "").strip(), mes + "%"
    return render_template("relatorio", mes=mes, fiscal=fiscal,
        den=q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro from denuncias d
          left join categorias c on c.id=d.categoria_id left join enderecos e on e.id=d.endereco_id
          where d.criada like ? order by d.criada""", (m,)),
        reg=q("""select a.*, d.codigo from acompanhamentos a join denuncias d on d.id=a.denuncia_id
          where a.data like ? and a.tipo not in ('Recebimento','Correção') and (?='' or a.autor=?) order by a.data""", (m, fiscal, fiscal)),
        rev=q("""select r.*, d.codigo from revisitas r join denuncias d on d.id=r.denuncia_id
          where r.feita like ? and (?='' or r.fiscal=?) order by r.feita""", (m, fiscal, fiscal)),
        desd=q("""select x.*, d.codigo from desdobramentos x join denuncias d on d.id=x.denuncia_id
          where x.data like ? order by x.data""", (m,)),
        prev=q("select count(*) n from revisitas where prevista like ? and feita is null", (m,), True)["n"],
        porcat=q("""select c.nome, count(*) n from denuncias d left join categorias c on c.id=d.categoria_id
          where d.criada like ? group by c.nome order by n desc""", (m,)),
        porfiscal=q("""select coalesce(nullif(autor,''),'(sem fiscal)') f, count(*) n,
          sum(tipo in ('Vistoria','Revisita')) v from acompanhamentos
          where data like ? and tipo not in ('Recebimento','Correção') group by f order by n desc""", (m,)),
        fiscais=[r["autor"] for r in q("select distinct autor from acompanhamentos where coalesce(autor,'')!='' order by autor")])

# --- Edição de cadastro e backup -------------------------------------------------
# Campos da denúncia e do endereço (coluna, nome exibido no histórico de correções).
CAMPOS = [("criada", "Data de recebimento"), ("categoria_id", "Categoria"), ("prioridade", "Prioridade"),
          ("descricao", "Descrição"), ("legislacao", "Legislação"), ("reincidente", "Situação"), ("anonima", "Anonimato"),
          ("denunciante", "Denunciante"), ("contato", "Contato do denunciante"), ("resp_nome", "Responsável pelo local"),
          ("resp_cpf", "CPF do responsável"), ("resp_contato", "Contato do responsável")]
ENDS = [("logradouro", "Rua"), ("numero", "Número"), ("bairro", "Bairro"), ("municipio", "Município"),
        ("referencia", "Referência"), ("lat", "Latitude"), ("lon", "Longitude")]

def vazio(v):
    """Normaliza vazios (None, texto vazio e 0) para comparar o antes e o depois de uma edição."""
    return "" if v in (None, "", 0) else v

@app.route("/d/<int:did>/editar", methods=["GET", "POST"])
def editar(did):
    """Corrige o cadastro de uma denúncia; o que mudou fica no histórico como "Correção"."""
    d = q("""select d.*, e.logradouro, e.numero, e.bairro, e.municipio, e.referencia, e.lat, e.lon
      from denuncias d left join enderecos e on e.id=d.endereco_id where d.id=?""", (did,), True) or abort(404)
    if request.method == "POST":
        novo = dados_form(request.form)
        mudou = [nome for k, nome in CAMPOS + ENDS if vazio(d[k]) != vazio(novo[k])]
        cd, ce = [k for k, _ in CAMPOS], [k for k, _ in ENDS]
        with db() as cx:  # transação única: grava tudo ou nada
            cx.execute("update denuncias set " + ",".join(k + "=?" for k in cd) + " where id=?", [novo[k] for k in cd] + [did])
            cx.execute("update enderecos set " + ",".join(k + "=?" for k in ce) + " where id=?", [novo[k] for k in ce] + [d["endereco_id"]])
            if novo["criada"] != d["criada"]:
                cx.execute("update acompanhamentos set data=? where denuncia_id=? and tipo='Recebimento'", (novo["criada"], did))
            if mudou:
                cx.execute("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)",
                           (did, date.today().isoformat(), "Correção", "Cadastro corrigido: " + ", ".join(mudou) + ".",
                            request.form.get("autor", "").strip()))
        flash("Correções salvas." if mudou else "Nenhuma alteração feita.")
        return redirect(url_for("detalhe", did=did))
    return render_template("editar", d=d, cats=q("select * from categorias order by nome"), c=centro())

def tamanho(n):
    """Formata bytes como MB."""
    return f"{n / 1048576:.1f} MB".replace(".", ",")

@app.route("/backup", methods=["GET", "POST"])
def backup():
    """Gera o backup (.zip com banco e anexos), guarda as 5 últimas cópias e envia o arquivo para download."""
    os.makedirs(BK, exist_ok=True)
    if request.method == "POST":
        nome = "backup_denuncias_" + datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".zip"
        destino, tmp = os.path.join(BK, nome), os.path.join(BK, uuid.uuid4().hex + ".tmp")
        origem, copia = sqlite3.connect(DB), sqlite3.connect(tmp)
        origem.backup(copia)  # cópia consistente, mesmo com o sistema em uso
        copia.close(); origem.close()
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "denuncias.db")
            for raiz, _, arqs in os.walk(UP):
                for a in arqs:
                    p = os.path.join(raiz, a)
                    z.write(p, os.path.join("uploads", os.path.relpath(p, UP)))
        os.remove(tmp)
        for velho in sorted(x for x in os.listdir(BK) if x.startswith("backup_") and x.endswith(".zip"))[:-5]:
            os.remove(os.path.join(BK, velho))
        flash("Backup gerado.")
        return send_file(destino, as_attachment=True, download_name=nome)
    arqs = sorted((x for x in os.listdir(BK) if x.startswith("backup_") and x.endswith(".zip")), reverse=True)
    return render_template("backup", lista=[(x, tamanho(os.path.getsize(os.path.join(BK, x)))) for x in arqs])

@app.route("/backup/<path:nome>")
def baixar_backup(nome):
    """Baixa um backup guardado anteriormente."""
    return send_from_directory(BK, nome, as_attachment=True)

SEGUROS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf")  # abrem no navegador; o resto é baixado

@app.route("/uploads/<path:nome>")
def uploads(nome):
    """Entrega um anexo. Só imagens e PDF abrem no navegador; os demais tipos são baixados (HTML/SVG enviados nunca são executados)."""
    return send_from_directory(UP, nome, as_attachment=not nome.lower().endswith(SEGUROS))


# --- Visual: CSS e modelos HTML (Jinja) ------------------------------------------
CSS = """:root{--g:#1e6b52;--ln:#cbd6cf;--red:#b3382c;--mut:#5b6b63}*{box-sizing:border-box}
body{margin:0;background:#edf1ee;color:#17261f;font:15px/1.5 "Segoe UI",system-ui,sans-serif}
header{background:#14392c;display:flex;gap:20px;align-items:center;padding:10px 24px;flex-wrap:wrap}
header a{color:#dcebe3;text-decoration:none}.logo{font-weight:700;font-size:17px;color:#fff!important}
header nav{display:flex;gap:16px;flex:1}header .btn{color:#fff}main{max-width:1060px;margin:24px auto;padding:0 16px}
.card{background:#fff;border:1px solid var(--ln);border-radius:6px;padding:16px;margin-bottom:16px}
h1{font-size:22px;margin:0 0 12px}h2{font-size:16px;margin:0 0 10px}a{color:var(--g)}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--ln);vertical-align:top}
th{font-weight:600;color:var(--mut)}label{display:block;font-size:13px;color:var(--mut);margin:8px 0 3px}
input,select,textarea{width:100%;padding:7px 9px;border:1px solid #9fb0a7;border-radius:4px;font:inherit;background:#fff}
.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0 14px}
.btn,button{background:var(--g);color:#fff;border:0;border-radius:4px;padding:8px 14px;font:inherit;cursor:pointer;text-decoration:none;display:inline-block;white-space:nowrap}
.s{background:#fff!important;color:var(--g)!important;border:1px solid var(--g)}
.tag{font-size:12px;padding:2px 8px;border-radius:10px;background:#dfeae3;color:#17261f}.late{color:var(--red);font-weight:600}
.tl{border-left:2px solid var(--ln);margin-left:6px;padding-left:18px}.tl>div{position:relative;margin-bottom:18px}
.tl>div:before{content:"";position:absolute;left:-25px;top:7px;width:10px;height:10px;border-radius:50%;background:var(--g)}
.mut{color:var(--mut);font-size:13px}.big{font-size:26px;font-weight:700}tr.st td:first-child{border-left:4px solid var(--c)}:focus-visible{outline:2px solid #1e6b52;outline-offset:2px}.aviso{background:#e3f1e8;border:1px solid #9cc7ae;color:#14392c;border-radius:6px;padding:10px 14px;margin-bottom:16px}@media print{header,footer,.aviso,.noprint{display:none!important}body{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{border:0;padding:0 0 8px}main{margin:0;max-width:none}}#map{height:320px;border-radius:6px;border:1px solid var(--ln)}"""

TILE = "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(m);"
END = "{% endblock %}"
T = {
"base": """<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{% block t %}Denúncias Ambientais{% endblock %}</title>
<link rel=icon href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🌿%3C/text%3E%3C/svg%3E"><style>""" + CSS + """</style>{% block head %}{% endblock %}
<header><a class=logo href="/">Denúncias Ambientais</a><nav><a href="/">Chamados</a><a href="/revisitas">Revisitas</a>
<a href="/mapa">Mapa</a><a href="/relatorio">Relatório</a><a href="/categorias">Categorias</a><a href="/backup">Backup</a></nav><a class=btn href="/nova">Nova denúncia</a></header>
<main>{% for m in get_flashed_messages() %}<div class=aviso>{{m}}</div>{% endfor %}{% block c %}{% endblock %}</main><footer class=mut style="text-align:center;padding:12px">Versão {{VERSAO}}</footer></html>""",

"index": """{% extends "base" %}{% block c %}<h1>Chamados</h1>
<div class=g><div class=card><div class=mut>Em andamento</div><div class=big>{{abertas}}</div></div>
<div class=card><div class=mut>Revisitas atrasadas</div><div class="big {{'late' if atras}}">{{atras}}</div></div></div>
<form class=card><div class=g><div><label>Busca</label><input name=q value="{{request.args.q}}" placeholder="Código, rua, bairro, texto"></div>
<div><label>Status</label><select name=status><option value="">Todos</option>{% for s in STATUS %}<option {{'selected' if s==request.args.status}}>{{s}}</option>{% endfor %}</select></div>
<div><label>Categoria</label><select name=cat><option value="">Todas</option>{% for c in cats %}<option value={{c.id}} {{'selected' if c.id|string==request.args.cat}}>{{c.nome}}</option>{% endfor %}</select></div></div>
<p><button>Filtrar</button></p><p class=mut>Legenda: {% for s in STATUS %}{{s|st}} {% endfor %}</p></form>
<div class=card style="overflow:auto"><table><tr><th>Código<th>Recebida<th>Categoria<th>Local<th>Status<th>Desdobramento<th>Próxima revisita</tr>
{% for r in rows %}<tr class=st style="--c:{{r.status|cor}}"><td><a href="/d/{{r.id}}">{{r.codigo}}</a><td>{{r.criada}}<td>{{r.cat}}<td>{{r.logradouro}} {{r.numero}}, {{r.bairro}}
<td>{{r.status|st}}{% if r.reincidente %} <span class=tag>Reincidência</span>{% endif %}<td>{{r.desd or '—'}}<td class="{{'late' if r.prox and r.prox<hoje}}">{{r.prox or '—'}}</tr>
{% else %}<tr><td colspan=7>Nenhuma denúncia encontrada. <a href="/nova">Registrar uma denúncia</a></tr>{% endfor %}</table></div>
{% if paginas > 1 %}<p style="display:flex;gap:12px;align-items:center">{% if pag > 1 %}<a class="btn s" href="?{{qs(page=pag-1)}}">Anterior</a>{% endif %}<span class=mut>Página {{pag}} de {{paginas}} · {{total}} chamados</span>{% if pag < paginas %}<a class="btn s" href="?{{qs(page=pag+1)}}">Próxima</a>{% endif %}</p>{% elif total %}<p class=mut>{{total}} chamado(s)</p>{% endif %}""" + END,

"nova": """{% extends "base" %}{% block head %}{{LEAF}}{% endblock %}{% block c %}<h1>Nova denúncia</h1>
<form method=post enctype=multipart/form-data><div class=card><h2>Denúncia</h2><div class=g>
<div><label>Data de recebimento</label><input type=date name=criada value="{{hoje}}" required></div>
<div><label>Categoria</label><select name=categoria_id>{% for c in cats %}<option value={{c.id}}>{{c.nome}}</option>{% endfor %}</select></div>
<div><label>Prioridade</label><select name=prioridade><option>Normal<option>Alta<option>Baixa</select></div></div>
<label>Descrição</label><textarea name=descricao rows=4 required></textarea>
<label>Legislação aplicável (opcional)</label><textarea name=legislacao rows=2 placeholder="Ex.: Lei 9.605/1998, art. 38"></textarea>
<div class=mut>Um item por linha. Use **negrito** ou *itálico* para destacar.</div>
<div class=g><div><label>Situação</label><select name=reincidente><option value=0>Primeira vez<option value=1>Reincidência</select></div>
<div><label>&nbsp;</label><label style="margin:0;color:inherit;font-size:15px"><input type=checkbox name=anonima style="width:auto" onchange="denunciante.disabled=contato.disabled=this.checked"> Denúncia anônima</label></div></div>
<div class=g><div><label>Denunciante (opcional)</label><input name=denunciante id=denunciante></div>
<div><label>Contato (opcional)</label><input name=contato id=contato></div></div></div>
<div class=card><h2>Responsável pelo local</h2><div class=g><div><label>Nome</label><input name=resp_nome></div>
<div><label>CPF</label><input name=resp_cpf inputmode=numeric placeholder="000.000.000-00"></div><div><label>Contato</label><input name=resp_contato></div></div></div>
<div class=card><h2>Local</h2><div class=g><div><label>Rua ou localidade</label><input name=logradouro required></div>
<div><label>Número</label><input name=numero></div><div><label>Bairro ou distrito</label><input name=bairro></div>
<div><label>Município</label><input name=municipio></div></div><label>Ponto de referência</label><input name=referencia>
<div class=g><div><label>Latitude</label><input name=lat id=lat></div><div><label>Longitude</label><input name=lon id=lon></div></div>
<p><button type=button class=s onclick="gps()">Usar minha localização</button> <span class=mut>ou clique no mapa para marcar o ponto</span></p><div id=map></div></div>
<div class=card><h2>Fotos e documentos</h2><input type=file name=arquivos multiple></div><button>Registrar denúncia</button></form>
<script>var m=L.map('map').setView([{{c[0]}},{{c[1]}}],{{c[2]}}),k;""" + TILE + """
function put(a,b,z){lat.value=a.toFixed(6);lon.value=b.toFixed(6);if(k)k.setLatLng([a,b]);else k=L.marker([a,b]).addTo(m);if(z)m.setView([a,b],z)}
m.on('click',function(e){put(e.latlng.lat,e.latlng.lng)});
function gps(){navigator.geolocation.getCurrentPosition(function(p){put(p.coords.latitude,p.coords.longitude,16)},function(){alert('Não foi possível obter a localização.')})}
</script>""" + END,

"detalhe": """{% extends "base" %}{% block t %}{{d.codigo}} · Denúncias{% endblock %}{% block c %}<h1>{{d.codigo}} {{d.status|st}}{% if d.reincidente %} <span class=tag>Reincidência</span>{% endif %}{% if d.anonima %} <span class=tag>Anônima</span>{% endif %}</h1>
<p class=noprint><a class=btn href="/d/{{d.id}}/imprimir" target=_blank>Imprimir / PDF</a> <a class="btn s" href="/d/{{d.id}}/editar">Editar cadastro</a></p>
<div class=card style="border-top:4px solid {{d.status|cor}}"><div class=g><div><div class=mut>Categoria</div>{{d.cat}}</div><div><div class=mut>Recebida em</div>{{d.criada}}</div>
<div><div class=mut>Prioridade</div>{{d.prioridade}}</div></div><p>{{d.descricao}}</p>{% if d.legislacao %}<p><b>Legislação aplicável:</b><br>{{d.legislacao|fmt}}</p>{% endif %}
<p><b>Local:</b> {{d.logradouro}} {{d.numero}}, {{d.bairro}} - {{d.municipio}}{% if d.referencia %} ({{d.referencia}}){% endif %}
{% if d.lat is not none %}<br><span class=mut>{{d.lat}}, {{d.lon}}</span> · <a target=_blank href="https://www.openstreetmap.org/?mlat={{d.lat}}&mlon={{d.lon}}#map=17/{{d.lat}}/{{d.lon}}">Ver no mapa</a>{% endif %}</p>
{% if d.anonima %}<p class=mut>Denúncia anônima</p>{% elif d.denunciante %}<p class=mut>Denunciante: {{d.denunciante}} {{d.contato}}</p>{% endif %}
{% if d.resp_nome or d.resp_cpf or d.resp_contato %}<p><b>Responsável pelo local:</b> {{d.resp_nome}} · CPF {{d.resp_cpf}} · {{d.resp_contato}}</p>{% endif %}
<details class=noprint style="margin:8px 0"><summary>{{'Editar' if d.legislacao else 'Informar'}} legislação aplicável</summary>
<form method=post action="/d/{{d.id}}/legislacao"><textarea name=legislacao rows=3 placeholder="Ex.: Lei 9.605/1998, art. 38; Decreto 6.514/2008, art. 43">{{d.legislacao or ''}}</textarea>
<p><button class=s>Salvar legislação</button></p></form></details>
{% for x in an.get(None, []) %}{{x|anexo}}{% endfor %}</div>
<div class=card><h2>Processo, notificação, embargo ou autuação</h2>
{% for x in desd %}<p><span class=tag>{{x.tipo}}</span> {{x.numero}} · {{x.data}} {{x.obs}}</p>{% else %}<p class=mut>Nada registrado até agora.</p>{% endfor %}
<form method=post action="/d/{{d.id}}/desdobramento" class="g noprint"><div><label>Tipo</label><select name=tipo>{% for t in DESD %}<option>{{t}}{% endfor %}</select></div>
<div><label>Número</label><input name=numero></div><div><label>Data</label><input type=date name=data value="{{hoje}}" required></div>
<div><label>Observação</label><input name=obs></div><div><label>&nbsp;</label><button class=s>Registrar</button></div></form>
{% if outros %}<p class=mut style="margin-top:12px">Outros chamados neste endereço: {% for o in outros %}<a href="/d/{{o.id}}">{{o.codigo}}</a> ({{o.criada}}) {% endfor %}</p>{% endif %}</div>
<div class=card><h2>Revisitas</h2>{% for r in revs %}<div style="margin-bottom:10px">
{% if r.feita %}Realizada em {{r.feita}}: {{r.obs}}{% else %}<span class="{{'late' if r.prevista<hoje}}">Prevista para {{r.prevista}}</span>
<form method=post action="/revisita/{{r.id}}/feita" class=noprint style="display:flex;gap:8px;margin-top:4px"><input name=obs placeholder="O que foi constatado?" required><input name=fiscal placeholder="Fiscal" style="max-width:160px">
<button class=s>Marcar como realizada</button></form>{% endif %}</div>{% else %}<p class=mut>Nenhuma revisita agendada.</p>{% endfor %}
<form method=post action="/d/{{d.id}}/revisita" class=noprint style="display:flex;gap:8px;max-width:360px"><input type=date name=prevista required><button class=s>Agendar revisita</button></form></div>
<div class="card noprint"><h2>Atualizar chamado</h2><form method=post action="/d/{{d.id}}/acompanhar" enctype=multipart/form-data><div class=g>
<div><label>Data</label><input type=date name=data value="{{hoje}}" required></div>
<div><label>Tipo</label><select name=tipo>{% for t in TIPOS %}<option>{{t}}{% endfor %}</select></div>
<div><label>Novo status</label><select name=status><option value="">Manter ({{d.status}})</option>{% for s in STATUS %}<option>{{s}}{% endfor %}</select></div>
<div><label>Registrado por</label><input name=autor></div></div><label>O que aconteceu</label><textarea name=texto rows=3 required></textarea>
<label>Fotos e documentos</label><input type=file name=arquivos multiple><p><button>Registrar atualização</button></p></form></div>
<div class=card><h2>Histórico</h2><div class=tl>{% for a in tl %}<div><b>{{a.data}}</b> · {{a.tipo}}
{% if a.status_novo %}{{a.status_novo|st}}{% endif %}{% if a.autor %} <span class=mut>por {{a.autor}}</span>{% endif %}
<div style="white-space:pre-wrap">{{a.texto}}</div>{% for x in an.get(a.id, []) %}{{x|anexo}}{% endfor %}</div>{% endfor %}</div></div>""" + END,

"revisitas": """{% extends "base" %}{% block c %}<h1>Revisitas pendentes</h1><div class=card><table>
<tr><th>Prevista<th>Chamado<th>Local</tr>{% for r in rows %}<tr><td class="{{'late' if r.prevista<hoje}}">{{r.prevista}}
<td><a href="/d/{{r.denuncia_id}}">{{r.codigo}}</a><td>{{r.logradouro}} {{r.numero}}, {{r.bairro}}</tr>
{% else %}<tr><td colspan=3>Nenhuma revisita pendente.</tr>{% endfor %}</table></div>""" + END,

"mapa": """{% extends "base" %}{% block head %}{{LEAF}}{% endblock %}{% block c %}<h1>Mapa das denúncias</h1>
<div id=map style="height:560px"></div><script>var m=L.map('map').setView([{{c[0]}},{{c[1]}}],{{c[2]}});""" + TILE + """
{{pontos|tojson}}.forEach(function(p){var a=document.createElement('a');a.href='/d/'+p.id;a.textContent=p.codigo;
var b=document.createElement('div');b.append(a,' · '+p.cat+' · '+p.status);L.marker([p.lat,p.lon]).addTo(m).bindPopup(b)});</script>""" + END,

"categorias": """{% extends "base" %}{% block c %}<h1>Categorias</h1><div class=card><table><tr><th>Categoria<th>Denúncias</tr>
{% for r in rows %}<tr><td>{{r.nome}}<td>{{r.n}}</tr>{% endfor %}</table></div>
<form method=post class=card style="display:flex;gap:8px"><input name=nome placeholder="Nova categoria" required><button>Adicionar categoria</button></form>""" + END,
}
T["relatorio"] = """{% extends "base" %}{% block t %}Relatório {{mes}}{% endblock %}{% block c %}<h1>Relatório mensal</h1>
<form class="card noprint" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap"><div><label>Mês</label><input type=month name=mes value="{{mes}}"></div>
<div><label>Fiscal (registros e revisitas)</label><select name=fiscal><option value="">Todos</option>{% for f in fiscais %}<option {{'selected' if f==fiscal}}>{{f}}</option>{% endfor %}</select></div>
<button>Gerar</button><button type=button class=s onclick="print()">Imprimir</button></form>
<div class=card><h2>Resumo de {{mes[5:]}}/{{mes[:4]}}{% if fiscal %} · Fiscal: {{fiscal}}{% endif %}</h2><div class=g>
<div><div class=mut>Denúncias recebidas</div><div class=big>{{den|length}}</div></div><div><div class=mut>Revisitas realizadas</div><div class=big>{{rev|length}}</div></div>
<div><div class=mut>Registros de acompanhamento</div><div class=big>{{reg|length}}</div></div><div><div class=mut>Processos, notificações, embargos e autuações</div><div class=big>{{desd|length}}</div></div></div>
<p class=mut>Revisitas previstas no mês e ainda pendentes: {{prev}}</p><div class=g><table><tr><th>Categoria<th>Denúncias</tr>{% for r in porcat %}<tr><td>{{r.nome}}<td>{{r.n}}</tr>{% endfor %}</table>
<table><tr><th>Fiscal<th>Registros<th>Vistorias e revisitas</tr>{% for r in porfiscal %}<tr><td>{{r.f}}<td>{{r.n}}<td>{{r.v}}</tr>{% endfor %}</table></div></div>
<div class=card><h2>Denúncias recebidas</h2><table><tr><th>Código<th>Data<th>Categoria<th>Local<th>Situação</tr>{% for d in den %}<tr><td>{{d.codigo}}<td>{{d.criada}}<td>{{d.cat}}<td>{{d.logradouro}} {{d.numero}}, {{d.bairro}}<td>{{d.status|st}}{% if d.reincidente %} · reincidência{% endif %}</tr>{% else %}<tr><td colspan=5>Nenhuma.</tr>{% endfor %}</table></div>
<div class=card><h2>Revisitas realizadas</h2><table><tr><th>Data<th>Chamado<th>Fiscal<th>Constatado</tr>{% for r in rev %}<tr><td>{{r.feita}}<td>{{r.codigo}}<td>{{r.fiscal}}<td>{{r.obs}}</tr>{% else %}<tr><td colspan=4>Nenhuma.</tr>{% endfor %}</table></div>
<div class=card><h2>Registros de acompanhamento</h2><table><tr><th>Data<th>Chamado<th>Tipo<th>Fiscal<th>Registro</tr>{% for a in reg %}<tr><td>{{a.data}}<td>{{a.codigo}}<td>{{a.tipo}}<td>{{a.autor}}<td>{{a.texto}}</tr>{% else %}<tr><td colspan=5>Nenhum.</tr>{% endfor %}</table></div>
<div class=card><h2>Processos, notificações, embargos e autuações</h2><table><tr><th>Data<th>Chamado<th>Tipo<th>Número<th>Observação</tr>{% for x in desd %}<tr><td>{{x.data}}<td>{{x.codigo}}<td>{{x.tipo}}<td>{{x.numero}}<td>{{x.obs}}</tr>{% else %}<tr><td colspan=5>Nenhum.</tr>{% endfor %}</table></div>""" + END
T["ficha"] = """{% extends "base" %}{% block t %}Ficha {{d.codigo}}{% endblock %}{% block head %}<style>
.fx{font-size:13px;line-height:1.4}.fx h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#14392c;border-bottom:1px solid #14392c;margin:12px 0 5px;padding-bottom:2px}
.fx table{font-size:12px}.fx td,.fx th{padding:3px 6px}.fx td{border-bottom:1px solid #e1e8e3}.k{color:#5b6b63}
.hd{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;border-bottom:2px solid #14392c;padding-bottom:6px}
.meta{display:flex;flex-wrap:wrap;gap:3px 22px;margin-top:8px}
@media print{@page{margin:12mm}.fx{font-size:11px}.fx h2{break-after:avoid}.fx tr,.fx .it{break-inside:avoid}main{padding:0}}
</style>{% endblock %}{% block c %}
<p class=noprint><button onclick="print()">Imprimir / Salvar como PDF</button> <a class="btn s" href="/d/{{d.id}}">Voltar ao chamado</a></p>
<div class="card fx"><div class=hd><div><b style="font-size:17px">Ficha de denúncia ambiental</b><div class=k>Emitida em {{hoje|br}}</div></div>
<div style="text-align:right"><b style="font-size:17px">{{d.codigo}}</b><br>{{d.status|st}}</div></div>
<div class=meta><span><span class=k>Recebida em</span> <b>{{d.criada|br}}</b></span><span><span class=k>Categoria</span> <b>{{d.cat}}</b></span>
<span><span class=k>Prioridade</span> <b>{{d.prioridade}}</b></span><span><span class=k>Situação</span> <b>{{'Reincidência' if d.reincidente else 'Primeira vez'}}</b></span>
<span><span class=k>Denunciante</span> <b>{% if d.anonima %}Anônima{% else %}{{d.denunciante or 'Não informado'}}{% if d.contato %} · {{d.contato}}{% endif %}{% endif %}</b></span></div>
<h2>Descrição</h2><div style="white-space:pre-wrap">{{d.descricao}}</div>
{% if d.legislacao %}<h2>Legislação aplicável</h2><div>{{d.legislacao|fmt}}</div>{% endif %}
<h2>Local</h2><div>{{d.logradouro}} {{d.numero}}, {{d.bairro}}{% if d.municipio %} - {{d.municipio}}{% endif %}{% if d.referencia %} · Ref.: {{d.referencia}}{% endif %}{% if d.lat is not none %} · <span class=k>Coord.</span> {{d.lat}}, {{d.lon}}{% endif %}</div>
{% if d.resp_nome or d.resp_cpf or d.resp_contato %}<div><span class=k>Responsável pelo local:</span> {{d.resp_nome}}{% if d.resp_cpf %} · CPF {{d.resp_cpf}}{% endif %}{% if d.resp_contato %} · {{d.resp_contato}}{% endif %}</div>{% endif %}
{% if desd %}<h2>Processos, notificações, embargos e autuações</h2><table><tr><th>Tipo<th>Número<th>Data<th>Observação</tr>{% for x in desd %}<tr><td>{{x.tipo}}<td>{{x.numero}}<td>{{x.data|br}}<td>{{x.obs}}</tr>{% endfor %}</table>{% endif %}
{% if revs %}<h2>Revisitas</h2><table><tr><th>Prevista<th>Realizada<th>Fiscal<th>Constatado</tr>{% for r in revs %}<tr><td>{{r.prevista|br}}<td>{{r.feita|br or 'Pendente'}}<td>{{r.fiscal}}<td>{{r.obs}}</tr>{% endfor %}</table>{% endif %}
<h2>Histórico</h2><table><tr><th style="width:78px">Data<th style="width:90px">Tipo<th>Registro</tr>{% for a in tl|reverse %}<tr><td>{{a.data|br}}<td>{{a.tipo}}<td>{% if a.status_novo %}{{a.status_novo|st}} {% endif %}<span style="white-space:pre-wrap">{{a.texto}}</span>{% if a.autor %} <span class=k>({{a.autor}})</span>{% endif %}</tr>{% endfor %}</table>
{% set todos = an.values()|sum(start=[]) %}{% if todos %}<h2>Anexos</h2><div class=it>{% for x in todos %}{{x|anexo}}{% endfor %}</div>{% endif %}
</div>""" + END
T["editar"] = """{% extends "base" %}{% block head %}{{LEAF}}{% endblock %}{% block c %}<h1>Editar {{d.codigo}}</h1>
<form method=post><div class=card><h2>Denúncia</h2><div class=g>
<div><label>Data de recebimento</label><input type=date name=criada value="{{d.criada}}" required></div>
<div><label>Categoria</label><select name=categoria_id>{% for c in cats %}<option value={{c.id}} {{'selected' if c.id==d.categoria_id}}>{{c.nome}}</option>{% endfor %}</select></div>
<div><label>Prioridade</label><select name=prioridade>{% for p in ['Baixa','Normal','Alta'] %}<option {{'selected' if p==d.prioridade}}>{{p}}</option>{% endfor %}</select></div></div>
<label>Descrição</label><textarea name=descricao rows=4 required>{{d.descricao}}</textarea>
<label>Legislação aplicável (opcional)</label><textarea name=legislacao rows=2>{{d.legislacao or ''}}</textarea>
<div class=g><div><label>Situação</label><select name=reincidente><option value=0>Primeira vez<option value=1 {{'selected' if d.reincidente}}>Reincidência</select></div>
<div><label>&nbsp;</label><label style="margin:0;color:inherit;font-size:15px"><input type=checkbox name=anonima style="width:auto" {{'checked' if d.anonima}} onchange="denunciante.disabled=contato.disabled=this.checked"> Denúncia anônima</label></div></div>
<div class=g><div><label>Denunciante</label><input name=denunciante id=denunciante value="{{d.denunciante or ''}}" {{'disabled' if d.anonima}}></div>
<div><label>Contato</label><input name=contato id=contato value="{{d.contato or ''}}" {{'disabled' if d.anonima}}></div></div>
<p class=mut>Marcar como anônima apaga os dados do denunciante.</p></div>
<div class=card><h2>Responsável pelo local</h2><div class=g><div><label>Nome</label><input name=resp_nome value="{{d.resp_nome or ''}}"></div>
<div><label>CPF</label><input name=resp_cpf value="{{d.resp_cpf or ''}}"></div><div><label>Contato</label><input name=resp_contato value="{{d.resp_contato or ''}}"></div></div></div>
<div class=card><h2>Local</h2><div class=g><div><label>Rua ou localidade</label><input name=logradouro value="{{d.logradouro or ''}}" required></div>
<div><label>Número</label><input name=numero value="{{d.numero or ''}}"></div><div><label>Bairro ou distrito</label><input name=bairro value="{{d.bairro or ''}}"></div>
<div><label>Município</label><input name=municipio value="{{d.municipio or ''}}"></div></div><label>Ponto de referência</label><input name=referencia value="{{d.referencia or ''}}">
<div class=g><div><label>Latitude</label><input name=lat id=lat value="{{d.lat if d.lat is not none else ''}}"></div>
<div><label>Longitude</label><input name=lon id=lon value="{{d.lon if d.lon is not none else ''}}"></div></div>
<p><button type=button class=s onclick="gps()">Usar minha localização</button> <span class=mut>ou clique no mapa para mover o ponto</span></p><div id=map></div></div>
<div class=card><label style="margin-top:0">Corrigido por (aparece no histórico)</label><input name=autor style="max-width:260px">
<p><button>Salvar correções</button> <a class="btn s" href="/d/{{d.id}}">Cancelar</a></p></div></form>
<script>var m=L.map('map').setView({% if d.lat is not none %}[{{d.lat}},{{d.lon}}],16{% else %}[{{c[0]}},{{c[1]}}],{{c[2]}}{% endif %}),k;""" + TILE + """
{% if d.lat is not none %}k=L.marker([{{d.lat}},{{d.lon}}]).addTo(m);{% endif %}
function put(a,b,z){lat.value=a.toFixed(6);lon.value=b.toFixed(6);if(k)k.setLatLng([a,b]);else k=L.marker([a,b]).addTo(m);if(z)m.setView([a,b],z)}
m.on('click',function(e){put(e.latlng.lat,e.latlng.lng)});
function gps(){navigator.geolocation.getCurrentPosition(function(p){put(p.coords.latitude,p.coords.longitude,16)},function(){alert('Não foi possível obter a localização.')})}
</script>""" + END
T["backup"] = """{% extends "base" %}{% block c %}<h1>Backup</h1><div class=card>
<p>Gera um arquivo .zip com o banco de dados e todas as fotos e documentos anexados.</p>
<form method=post><button>Gerar e baixar backup agora</button></form>
<p class=mut>Uma cópia também fica na pasta <b>backups</b> do sistema (as 5 mais recentes). Guarde o arquivo baixado também fora deste computador, como em um pendrive ou HD externo.</p></div>
<div class=card><h2>Backups guardados</h2><table><tr><th>Arquivo<th>Tamanho</tr>{% for n, t in lista %}<tr><td><a href="/backup/{{n}}">{{n}}</a><td>{{t}}</tr>{% else %}<tr><td colspan=2>Nenhum ainda.</tr>{% endfor %}</table></div>
<div class=card><h2>Como restaurar</h2><p>Feche o sistema, extraia o .zip, substitua o arquivo <b>denuncias.db</b> e a pasta <b>uploads</b> pelos do backup e abra o sistema novamente.</p></div>""" + END
T["erro"] = """{% extends "base" %}{% block c %}<div class=card><h1>{{cod}}</h1><p>{{msg}}</p><a class=btn href="/">Voltar ao início</a></div>""" + END
app.jinja_env.loader = DictLoader(T)
app.jinja_env.autoescape = True  # textos digitados nunca são interpretados como HTML

init()  # cria/atualiza o banco ao iniciar (também quando rodado por um servidor como o waitress)

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
