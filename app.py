"""Sistema local de denúncias ambientais. Rodar: python app.py  ->  http://127.0.0.1:5000"""
import os, re, sqlite3, uuid
from datetime import date
from flask import Flask, g, request, redirect, url_for, render_template, send_from_directory, abort
from jinja2 import DictLoader
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB, UP = os.path.join(BASE, "denuncias.db"), os.path.join(BASE, "uploads")
os.makedirs(UP, exist_ok=True)
STATUS = ["Recebida", "Em análise", "Em fiscalização", "Vistoriada", "Notificada", "Embargada", "Autuada",
          "Aguardando retorno", "Encerrada", "Arquivada"]
COR = {  # status: (cor do texto/borda, cor de fundo)
    "Recebida": ("#1d5fa8", "#dce9f7"), "Em análise": ("#6b3fa0", "#ece3f6"), "Em fiscalização": ("#0b7285", "#d5f0f4"),
    "Vistoriada": ("#2e7d32", "#dff0d8"), "Notificada": ("#8a5a00", "#fcefc7"), "Embargada": ("#b04a0b", "#fde3d0"),
    "Autuada": ("#b3261e", "#fadbd8"), "Aguardando retorno": ("#a1296b", "#f8dceb"),
    "Encerrada": ("#37474f", "#dde4e8"), "Arquivada": ("#6d4c41", "#ede4e0")}
TIPOS = ["Atualização", "Vistoria", "Revisita", "Contato", "Encerramento"]
VERSAO = "1.2"
DESD = ["Processo", "Notificação", "Embargo", "Autuação"]
CENTRO = (-14.2, -51.9, 4)  # centro inicial do mapa (lat, lon, zoom); ajuste para sua região
LEAF = ('<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">'
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')

SCHEMA = """
create table if not exists categorias(id integer primary key, nome text unique not null);
create table if not exists enderecos(id integer primary key, logradouro text, numero text, bairro text,
  municipio text, referencia text, lat real, lon real);
create table if not exists denuncias(id integer primary key, codigo text unique not null, criada text not null,
  categoria_id integer references categorias(id), endereco_id integer references enderecos(id), descricao text,
  denunciante text, contato text, prioridade text default 'Normal', status text default 'Aberta');
create table if not exists acompanhamentos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, data text not null, tipo text, texto text, autor text, status_novo text);
create table if not exists revisitas(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, prevista text not null, feita text, obs text);
create table if not exists desdobramentos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, tipo text, numero text, data text, obs text);
create table if not exists anexos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, acomp_id integer, nome text, arquivo text);
"""

NOVAS = {"denuncias": [("anonima", "integer default 0"), ("reincidente", "integer default 0"),
    ("resp_nome", "text"), ("resp_cpf", "text"), ("resp_contato", "text"), ("legislacao", "text")], "revisitas": [("fiscal", "text")]}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys=on")
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d:
        d.close()

def q(sql, a=(), one=False):
    r = db().execute(sql, a).fetchall()
    return (r[0] if r else None) if one else r

def ex(sql, a=()):
    c = db().execute(sql, a)
    db().commit()
    return c.lastrowid

def init():
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
    pre = f"DEN-{date.today().year}-"
    m = q("select max(codigo) m from denuncias where codigo like ?", (pre + "%",), True)["m"]
    return f"{pre}{(int(m[-5:]) + 1 if m else 1):05d}"

def num(v):
    try:
        return float(v.replace(",", "."))
    except (ValueError, AttributeError):
        return None

def centro():
    r = q("select avg(lat) a, avg(lon) o from enderecos where lat is not null", one=True)
    return (r["a"], r["o"], 12) if r["a"] is not None else CENTRO

def salvar_arquivos(did, aid=None):
    for f in request.files.getlist("arquivos"):
        if f and f.filename:
            arq = uuid.uuid4().hex[:8] + "_" + (secure_filename(f.filename) or "arquivo")
            f.save(os.path.join(UP, arq))
            ex("insert into anexos(denuncia_id,acomp_id,nome,arquivo) values(?,?,?,?)", (did, aid, f.filename, arq))

@app.context_processor
def ctx():
    return dict(STATUS=STATUS, TIPOS=TIPOS, DESD=DESD, VERSAO=VERSAO, LEAF=Markup(LEAF), hoje=date.today().isoformat())

@app.template_filter("st")
def st_tag(v):
    fg, bg = COR.get(v, ("#37474f", "#dde4e8"))
    return Markup(f'<span class=tag style="background:{bg};color:{fg};border:1px solid {fg}">{escape(v)}</span>')

@app.template_filter("cor")
def st_cor(v):
    return COR.get(v, ("#37474f",))[0]

@app.template_filter("br")
def br(v):
    return f"{v[8:10]}/{v[5:7]}/{v[:4]}" if v and len(v) >= 10 else (v or "")

@app.template_filter("fmt")
def fmt(t):
    t = str(escape(t or ""))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?![*\w])", r"<i>\1</i>", t)
    return Markup(t.replace("\n", "<br>"))

@app.template_filter("anexo")
def anexo(x):
    u, n = "/uploads/" + x["arquivo"], escape(x["nome"])
    if x["arquivo"].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return Markup(f'<a href="{u}" target=_blank title="{n}"><img src="{u}" alt="{n}" '
                      f'style="height:80px;border-radius:4px;margin:4px 6px 0 0"></a>')
    return Markup(f'<a href="{u}" target=_blank>{n}</a> ')


@app.route("/")
def index():
    st, cat, b = request.args.get("status", ""), request.args.get("cat", ""), request.args.get("q", "").strip()
    sql = """select d.*, c.nome cat, e.logradouro, e.numero, e.bairro,
      (select min(prevista) from revisitas r where r.denuncia_id=d.id and r.feita is null) prox,
      (select group_concat(distinct tipo) from desdobramentos x where x.denuncia_id=d.id) desd
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where 1=1"""
    a = []
    if st:
        sql += " and d.status=?"; a.append(st)
    if cat:
        sql += " and d.categoria_id=?"; a.append(cat)
    if b:
        sql += " and (d.codigo like ? or d.descricao like ? or e.logradouro like ? or e.bairro like ? or d.resp_nome like ? or d.resp_cpf like ?)"
        a += [f"%{b}%"] * 6
    return render_template("index", rows=q(sql + " order by d.id desc", a),
        cats=q("select * from categorias order by nome"),
        abertas=q("select count(*) n from denuncias where status not in ('Encerrada','Arquivada')", one=True)["n"],
        atras=q("select count(*) n from revisitas where feita is null and prevista<?",
                (date.today().isoformat(),), True)["n"])

@app.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        f = request.form
        eid = ex("insert into enderecos(logradouro,numero,bairro,municipio,referencia,lat,lon) values(?,?,?,?,?,?,?)",
                 (f["logradouro"], f["numero"], f["bairro"], f["municipio"], f["referencia"], num(f["lat"]), num(f["lon"])))
        anon = 1 if f.get("anonima") else 0
        did = ex("insert into denuncias(codigo,criada,categoria_id,endereco_id,descricao,denunciante,contato,prioridade,"
                 "anonima,reincidente,resp_nome,resp_cpf,resp_contato,legislacao,status) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (novo_codigo(), f["criada"], f["categoria_id"], eid, f["descricao"],
                  "" if anon else f["denunciante"], "" if anon else f["contato"], f["prioridade"], anon,
                  1 if f.get("reincidente") == "1" else 0, f["resp_nome"], f["resp_cpf"], f["resp_contato"],
                  f["legislacao"].strip(), "Recebida"))
        ex("insert into acompanhamentos(denuncia_id,data,tipo,texto,status_novo) values(?,?,?,?,?)",
           (did, f["criada"], "Recebimento", "Denúncia recebida.", "Recebida"))
        salvar_arquivos(did)
        return redirect(url_for("detalhe", did=did))
    return render_template("nova", cats=q("select * from categorias order by nome"), c=centro())

@app.route("/d/<int:did>")
def detalhe(did):
    return pagina("detalhe", did)

@app.route("/d/<int:did>/imprimir")
def imprimir(did):
    return pagina("ficha", did)

@app.post("/d/<int:did>/legislacao")
def legislacao(did):
    ex("update denuncias set legislacao=? where id=?", (request.form["legislacao"].strip(), did))
    return redirect(url_for("detalhe", did=did))

def pagina(modelo, did):
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
    f = request.form
    st = f.get("status") or None
    aid = ex("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor,status_novo) values(?,?,?,?,?,?)",
             (did, f["data"], f["tipo"], f["texto"], f["autor"], st))
    if st:
        ex("update denuncias set status=? where id=?", (st, did))
    salvar_arquivos(did, aid)
    return redirect(url_for("detalhe", did=did))

@app.post("/d/<int:did>/revisita")
def agendar(did):
    ex("insert into revisitas(denuncia_id,prevista) values(?,?)", (did, request.form["prevista"]))
    return redirect(url_for("detalhe", did=did))

@app.post("/d/<int:did>/desdobramento")
def desdobrar(did):
    f = request.form
    ex("insert into desdobramentos(denuncia_id,tipo,numero,data,obs) values(?,?,?,?,?)",
       (did, f["tipo"], f["numero"], f["data"], f["obs"]))
    txt = f["tipo"] + " registrado(a)"
    if f["numero"]:
        txt += " nº " + f["numero"]
    if f["obs"]:
        txt += ": " + f["obs"]
    ex("insert into acompanhamentos(denuncia_id,data,tipo,texto) values(?,?,?,?)", (did, f["data"], "Atualização", txt))
    return redirect(url_for("detalhe", did=did))

@app.post("/revisita/<int:rid>/feita")
def revisita_feita(rid):
    r = q("select * from revisitas where id=?", (rid,), True) or abort(404)
    h, obs = date.today().isoformat(), request.form["obs"]
    fiscal = request.form.get("fiscal", "")
    ex("update revisitas set feita=?, obs=?, fiscal=? where id=?", (h, obs, fiscal, rid))
    ex("insert into acompanhamentos(denuncia_id,data,tipo,texto,autor) values(?,?,?,?,?)", (r["denuncia_id"], h, "Revisita", obs, fiscal))
    return redirect(url_for("detalhe", did=r["denuncia_id"]))

@app.route("/revisitas")
def revisitas():
    return render_template("revisitas", rows=q("""select r.*, d.codigo, e.logradouro, e.numero, e.bairro
      from revisitas r join denuncias d on d.id=r.denuncia_id left join enderecos e on e.id=d.endereco_id
      where r.feita is null order by r.prevista"""))

@app.route("/mapa")
def mapa():
    pts = [dict(r) for r in q("""select d.id, d.codigo, d.status, c.nome cat, e.lat, e.lon from denuncias d
      join enderecos e on e.id=d.endereco_id left join categorias c on c.id=d.categoria_id where e.lat is not null""")]
    return render_template("mapa", pontos=pts, c=centro())

@app.route("/categorias", methods=["GET", "POST"])
def categorias():
    if request.method == "POST":
        n = request.form["nome"].strip()
        if n:
            try:
                ex("insert into categorias(nome) values(?)", (n,))
            except sqlite3.IntegrityError:
                pass
        return redirect(url_for("categorias"))
    return render_template("categorias", rows=q("""select c.*, (select count(*) from denuncias
      where categoria_id=c.id) n from categorias c order by nome"""))

@app.route("/relatorio")
def relatorio():
    mes = request.args.get("mes") or date.today().strftime("%Y-%m")
    fiscal, m = request.args.get("fiscal", "").strip(), mes + "%"
    return render_template("relatorio", mes=mes, fiscal=fiscal,
        den=q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro from denuncias d
          left join categorias c on c.id=d.categoria_id left join enderecos e on e.id=d.endereco_id
          where d.criada like ? order by d.criada""", (m,)),
        reg=q("""select a.*, d.codigo from acompanhamentos a join denuncias d on d.id=a.denuncia_id
          where a.data like ? and a.tipo!='Recebimento' and (?='' or a.autor=?) order by a.data""", (m, fiscal, fiscal)),
        rev=q("""select r.*, d.codigo from revisitas r join denuncias d on d.id=r.denuncia_id
          where r.feita like ? and (?='' or r.fiscal=?) order by r.feita""", (m, fiscal, fiscal)),
        desd=q("""select x.*, d.codigo from desdobramentos x join denuncias d on d.id=x.denuncia_id
          where x.data like ? order by x.data""", (m,)),
        prev=q("select count(*) n from revisitas where prevista like ? and feita is null", (m,), True)["n"],
        porcat=q("""select c.nome, count(*) n from denuncias d left join categorias c on c.id=d.categoria_id
          where d.criada like ? group by c.nome order by n desc""", (m,)),
        porfiscal=q("""select coalesce(nullif(autor,''),'(sem fiscal)') f, count(*) n,
          sum(tipo in ('Vistoria','Revisita')) v from acompanhamentos
          where data like ? and tipo!='Recebimento' group by f order by n desc""", (m,)),
        fiscais=[r["autor"] for r in q("select distinct autor from acompanhamentos where coalesce(autor,'')!='' order by autor")])

@app.route("/uploads/<path:nome>")
def uploads(nome):
    return send_from_directory(UP, nome)


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
.mut{color:var(--mut);font-size:13px}.big{font-size:26px;font-weight:700}tr.st td:first-child{border-left:4px solid var(--c)}@media print{header,footer,.noprint{display:none!important}body{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}.card{border:0;padding:0 0 8px}main{margin:0;max-width:none}}#map{height:320px;border-radius:6px;border:1px solid var(--ln)}"""

TILE = "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(m);"
END = "{% endblock %}"
T = {
"base": """<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Denúncias Ambientais</title><style>""" + CSS + """</style>{% block head %}{% endblock %}
<header><a class=logo href="/">Denúncias Ambientais</a><nav><a href="/">Chamados</a><a href="/revisitas">Revisitas</a>
<a href="/mapa">Mapa</a><a href="/relatorio">Relatório</a><a href="/categorias">Categorias</a></nav><a class=btn href="/nova">Nova denúncia</a></header>
<main>{% block c %}{% endblock %}</main><footer class=mut style="text-align:center;padding:12px">Versão {{VERSAO}}</footer></html>""",

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
{% else %}<tr><td colspan=7>Nenhuma denúncia encontrada. <a href="/nova">Registrar uma denúncia</a></tr>{% endfor %}</table></div>""" + END,

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

"detalhe": """{% extends "base" %}{% block c %}<h1>{{d.codigo}} {{d.status|st}}{% if d.reincidente %} <span class=tag>Reincidência</span>{% endif %}{% if d.anonima %} <span class=tag>Anônima</span>{% endif %}</h1>
<p class=noprint><a class=btn href="/d/{{d.id}}/imprimir" target=_blank>Imprimir / PDF</a></p>
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
T["relatorio"] = """{% extends "base" %}{% block c %}<h1>Relatório mensal</h1>
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
T["ficha"] = """{% extends "base" %}{% block head %}<style>
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
app.jinja_env.loader = DictLoader(T)

if __name__ == "__main__":
    init()
    app.run(host="127.0.0.1", port=5000)
