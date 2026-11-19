"""Sistema local de denúncias ambientais. Rodar: python app.py  ->  http://127.0.0.1:5000"""
import os, sqlite3, uuid
from datetime import date
from flask import Flask, g, request, redirect, url_for, render_template, send_from_directory, abort
from jinja2 import DictLoader
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB, UP = os.path.join(BASE, "denuncias.db"), os.path.join(BASE, "uploads")
os.makedirs(UP, exist_ok=True)
STATUS = ["Aberta", "Em análise", "Vistoriada", "Aguardando retorno", "Encerrada"]
TIPOS = ["Atualização", "Vistoria", "Revisita", "Contato", "Encerramento"]
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
create table if not exists anexos(id integer primary key, denuncia_id integer not null
  references denuncias(id) on delete cascade, acomp_id integer, nome text, arquivo text);
"""

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
    return dict(STATUS=STATUS, TIPOS=TIPOS, LEAF=Markup(LEAF), hoje=date.today().isoformat())

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
      (select min(prevista) from revisitas r where r.denuncia_id=d.id and r.feita is null) prox
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where 1=1"""
    a = []
    if st:
        sql += " and d.status=?"; a.append(st)
    if cat:
        sql += " and d.categoria_id=?"; a.append(cat)
    if b:
        sql += " and (d.codigo like ? or d.descricao like ? or e.logradouro like ? or e.bairro like ?)"
        a += [f"%{b}%"] * 4
    return render_template("index", rows=q(sql + " order by d.id desc", a),
        cats=q("select * from categorias order by nome"),
        abertas=q("select count(*) n from denuncias where status!='Encerrada'", one=True)["n"],
        atras=q("select count(*) n from revisitas where feita is null and prevista<?",
                (date.today().isoformat(),), True)["n"])

@app.route("/nova", methods=["GET", "POST"])
def nova():
    if request.method == "POST":
        f = request.form
        eid = ex("insert into enderecos(logradouro,numero,bairro,municipio,referencia,lat,lon) values(?,?,?,?,?,?,?)",
                 (f["logradouro"], f["numero"], f["bairro"], f["municipio"], f["referencia"], num(f["lat"]), num(f["lon"])))
        did = ex("insert into denuncias(codigo,criada,categoria_id,endereco_id,descricao,denunciante,contato,prioridade)"
                 " values(?,?,?,?,?,?,?,?)", (novo_codigo(), f["criada"], f["categoria_id"], eid, f["descricao"],
                 f["denunciante"], f["contato"], f["prioridade"]))
        ex("insert into acompanhamentos(denuncia_id,data,tipo,texto,status_novo) values(?,?,?,?,?)",
           (did, f["criada"], "Recebimento", "Denúncia recebida.", "Aberta"))
        salvar_arquivos(did)
        return redirect(url_for("detalhe", did=did))
    return render_template("nova", cats=q("select * from categorias order by nome"), c=centro())

@app.route("/d/<int:did>")
def detalhe(did):
    d = q("""select d.*, c.nome cat, e.logradouro, e.numero, e.bairro, e.municipio, e.referencia, e.lat, e.lon
      from denuncias d left join categorias c on c.id=d.categoria_id
      left join enderecos e on e.id=d.endereco_id where d.id=?""", (did,), True) or abort(404)
    an = {}
    for x in q("select * from anexos where denuncia_id=?", (did,)):
        an.setdefault(x["acomp_id"], []).append(x)
    return render_template("detalhe", d=d, an=an,
        tl=q("select * from acompanhamentos where denuncia_id=? order by data desc, id desc", (did,)),
        revs=q("select * from revisitas where denuncia_id=? order by prevista", (did,)))

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

@app.post("/revisita/<int:rid>/feita")
def revisita_feita(rid):
    r = q("select * from revisitas where id=?", (rid,), True) or abort(404)
    h, obs = date.today().isoformat(), request.form["obs"]
    ex("update revisitas set feita=?, obs=? where id=?", (h, obs, rid))
    ex("insert into acompanhamentos(denuncia_id,data,tipo,texto) values(?,?,?,?)", (r["denuncia_id"], h, "Revisita", obs))
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
.mut{color:var(--mut);font-size:13px}.big{font-size:26px;font-weight:700}#map{height:320px;border-radius:6px;border:1px solid var(--ln)}"""

TILE = "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(m);"
END = "{% endblock %}"
T = {
"base": """<!doctype html><html lang=pt-BR><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Denúncias Ambientais</title><style>""" + CSS + """</style>{% block head %}{% endblock %}
<header><a class=logo href="/">Denúncias Ambientais</a><nav><a href="/">Chamados</a><a href="/revisitas">Revisitas</a>
<a href="/mapa">Mapa</a><a href="/categorias">Categorias</a></nav><a class=btn href="/nova">Nova denúncia</a></header>
<main>{% block c %}{% endblock %}</main></html>""",

"index": """{% extends "base" %}{% block c %}<h1>Chamados</h1>
<div class=g><div class=card><div class=mut>Em andamento</div><div class=big>{{abertas}}</div></div>
<div class=card><div class=mut>Revisitas atrasadas</div><div class="big {{'late' if atras}}">{{atras}}</div></div></div>
<form class=card><div class=g><div><label>Busca</label><input name=q value="{{request.args.q}}" placeholder="Código, rua, bairro, texto"></div>
<div><label>Status</label><select name=status><option value="">Todos</option>{% for s in STATUS %}<option {{'selected' if s==request.args.status}}>{{s}}</option>{% endfor %}</select></div>
<div><label>Categoria</label><select name=cat><option value="">Todas</option>{% for c in cats %}<option value={{c.id}} {{'selected' if c.id|string==request.args.cat}}>{{c.nome}}</option>{% endfor %}</select></div></div>
<p><button>Filtrar</button></p></form>
<div class=card style="overflow:auto"><table><tr><th>Código<th>Recebida<th>Categoria<th>Local<th>Status<th>Próxima revisita</tr>
{% for r in rows %}<tr><td><a href="/d/{{r.id}}">{{r.codigo}}</a><td>{{r.criada}}<td>{{r.cat}}<td>{{r.logradouro}} {{r.numero}}, {{r.bairro}}
<td><span class=tag>{{r.status}}</span><td class="{{'late' if r.prox and r.prox<hoje}}">{{r.prox or '—'}}</tr>
{% else %}<tr><td colspan=6>Nenhuma denúncia encontrada. <a href="/nova">Registrar uma denúncia</a></tr>{% endfor %}</table></div>""" + END,

"nova": """{% extends "base" %}{% block head %}{{LEAF}}{% endblock %}{% block c %}<h1>Nova denúncia</h1>
<form method=post enctype=multipart/form-data><div class=card><h2>Denúncia</h2><div class=g>
<div><label>Data de recebimento</label><input type=date name=criada value="{{hoje}}" required></div>
<div><label>Categoria</label><select name=categoria_id>{% for c in cats %}<option value={{c.id}}>{{c.nome}}</option>{% endfor %}</select></div>
<div><label>Prioridade</label><select name=prioridade><option>Normal<option>Alta<option>Baixa</select></div></div>
<label>Descrição</label><textarea name=descricao rows=4 required></textarea>
<div class=g><div><label>Denunciante (opcional)</label><input name=denunciante></div>
<div><label>Contato (opcional)</label><input name=contato></div></div></div>
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

"detalhe": """{% extends "base" %}{% block c %}<h1>{{d.codigo}} <span class=tag>{{d.status}}</span></h1>
<div class=card><div class=g><div><div class=mut>Categoria</div>{{d.cat}}</div><div><div class=mut>Recebida em</div>{{d.criada}}</div>
<div><div class=mut>Prioridade</div>{{d.prioridade}}</div></div><p>{{d.descricao}}</p>
<p><b>Local:</b> {{d.logradouro}} {{d.numero}}, {{d.bairro}} - {{d.municipio}}{% if d.referencia %} ({{d.referencia}}){% endif %}
{% if d.lat is not none %}<br><span class=mut>{{d.lat}}, {{d.lon}}</span> · <a target=_blank href="https://www.openstreetmap.org/?mlat={{d.lat}}&mlon={{d.lon}}#map=17/{{d.lat}}/{{d.lon}}">Ver no mapa</a>{% endif %}</p>
{% if d.denunciante %}<p class=mut>Denunciante: {{d.denunciante}} {{d.contato}}</p>{% endif %}
{% for x in an.get(None, []) %}{{x|anexo}}{% endfor %}</div>
<div class=card><h2>Revisitas</h2>{% for r in revs %}<div style="margin-bottom:10px">
{% if r.feita %}Realizada em {{r.feita}}: {{r.obs}}{% else %}<span class="{{'late' if r.prevista<hoje}}">Prevista para {{r.prevista}}</span>
<form method=post action="/revisita/{{r.id}}/feita" style="display:flex;gap:8px;margin-top:4px"><input name=obs placeholder="O que foi constatado?" required>
<button class=s>Marcar como realizada</button></form>{% endif %}</div>{% else %}<p class=mut>Nenhuma revisita agendada.</p>{% endfor %}
<form method=post action="/d/{{d.id}}/revisita" style="display:flex;gap:8px;max-width:360px"><input type=date name=prevista required><button class=s>Agendar revisita</button></form></div>
<div class=card><h2>Atualizar chamado</h2><form method=post action="/d/{{d.id}}/acompanhar" enctype=multipart/form-data><div class=g>
<div><label>Data</label><input type=date name=data value="{{hoje}}" required></div>
<div><label>Tipo</label><select name=tipo>{% for t in TIPOS %}<option>{{t}}{% endfor %}</select></div>
<div><label>Novo status</label><select name=status><option value="">Manter ({{d.status}})</option>{% for s in STATUS %}<option>{{s}}{% endfor %}</select></div>
<div><label>Registrado por</label><input name=autor></div></div><label>O que aconteceu</label><textarea name=texto rows=3 required></textarea>
<label>Fotos e documentos</label><input type=file name=arquivos multiple><p><button>Registrar atualização</button></p></form></div>
<div class=card><h2>Histórico</h2><div class=tl>{% for a in tl %}<div><b>{{a.data}}</b> · {{a.tipo}}
{% if a.status_novo %}<span class=tag>{{a.status_novo}}</span>{% endif %}{% if a.autor %} <span class=mut>por {{a.autor}}</span>{% endif %}
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
app.jinja_env.loader = DictLoader(T)

if __name__ == "__main__":
    init()
    app.run(host="127.0.0.1", port=5000)
