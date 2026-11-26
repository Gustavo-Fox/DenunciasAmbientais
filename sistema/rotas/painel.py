"""Rotas do painel: lista de chamados, cadastro (denúncia ou fiscalização de ofício), mapa geral e categorias."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from .. import armazenamento, repo
from ..util import dados_form
from .comum import avisar_recusados

bp = Blueprint("painel", __name__)


@bp.route("/")
def index():
    """Painel principal: totais, filtros (status, categoria, origem, busca) e lista paginada de chamados."""
    a = request.args
    lista = repo.listar(a.get("status", ""), a.get("cat", ""), a.get("origem", ""), a.get("q", "").strip(),
                        a.get("page", 1, type=int))
    abertas, atras = repo.contagens()
    return render_template("index.html", cats=repo.categorias(), abertas=abertas, atras=atras, **lista)


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    """Cadastra uma denúncia ou, com tipo=fiscalizacao, uma fiscalização de ofício (GET: formulário; POST: grava)."""
    if request.method == "POST":
        fisc = request.form.get("tipo") == "fiscalizacao"
        did, codigo = repo.criar(dados_form(request.form), "Fiscalização" if fisc else "Denúncia")
        _, recusados = armazenamento.salvar(did, None, request.files.getlist("arquivos"))
        flash(f"{'Fiscalização registrada' if fisc else 'Denúncia registrada'} com o código {codigo}.")
        avisar_recusados(recusados)
        return redirect(url_for("chamados.detalhe", did=did))
    return render_template("nova.html", cats=repo.categorias(), c=repo.centro_mapa(),
                           fisc=request.args.get("tipo") == "fiscalizacao")


@bp.route("/mapa")
def mapa():
    """Mapa com todos os chamados que têm coordenadas."""
    return render_template("mapa.html", pontos=repo.pontos_mapa(), c=repo.centro_mapa())


@bp.route("/categorias", methods=["GET", "POST"])
def categorias():
    """Lista as categorias (com o total de chamados) e permite criar novas."""
    if request.method == "POST":
        n = request.form.get("nome", "").strip()
        if n:
            flash("Categoria adicionada." if repo.criar_categoria(n) else "Essa categoria já existe.")
        return redirect(url_for("painel.categorias"))
    return render_template("categorias.html", rows=repo.categorias_com_total())
