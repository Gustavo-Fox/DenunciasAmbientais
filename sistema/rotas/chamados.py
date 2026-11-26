"""Rotas do chamado: tela, ficha de impressão, edição, histórico, legislação, desdobramentos e cancelamento."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from .. import armazenamento, config as cfg, repo
from ..util import dados_form, iso
from .comum import avisar_recusados, bloqueado, chamado, justificativa

bp = Blueprint("chamados", __name__)


def _volta(did):
    return redirect(url_for("chamados.detalhe", did=did))


def _dados(did):
    """Reúne os dados de um chamado para as telas de detalhe e de ficha."""
    d = chamado(did)
    return dict(d=d, an=repo.anexos_por_acomp(did), tl=repo.historico(did), revs=repo.revisitas_do_chamado(did),
                desd=repo.desdobramentos(did), outros=repo.mesmo_endereco(d),
                cancel=repo.ultimo_cancelamento(did) if d["status"] == cfg.CANCELADA else None)


@bp.route("/d/<int:did>")
def detalhe(did):
    """Tela do chamado: dados, revisitas, desdobramentos, atualização e histórico."""
    return render_template("detalhe.html", **_dados(did))


@bp.route("/d/<int:did>/imprimir")
def imprimir(did):
    """Ficha compacta do chamado para imprimir ou salvar em PDF."""
    return render_template("ficha.html", **_dados(did))


@bp.route("/d/<int:did>/editar", methods=["GET", "POST"])
def editar(did):
    """Corrige o cadastro de um chamado; o que mudou fica no histórico como "Correção"."""
    d = chamado(did)
    if (r := bloqueado(d)):
        return r
    if request.method == "POST":
        mudou = repo.atualizar(d, dados_form(request.form), request.form.get("autor", "").strip())
        flash("Correções salvas." if mudou else "Nenhuma alteração feita.")
        return _volta(did)
    return render_template("editar.html", d=d, cats=repo.categorias(), c=repo.centro_mapa())


@bp.post("/d/<int:did>/legislacao")
def legislacao(did):
    """Salva (ou apaga) o texto da legislação aplicável."""
    if (r := bloqueado(chamado(did))):
        return r
    repo.salvar_legislacao(did, request.form.get("legislacao", "").strip())
    flash("Legislação salva.")
    return _volta(did)


@bp.post("/d/<int:did>/acompanhar")
def acompanhar(did):
    """Registra uma atualização no histórico (e, se informado, muda o status e anexa arquivos)."""
    if (r := bloqueado(chamado(did))):
        return r
    f = request.form
    st, texto = f.get("status") or None, f.get("texto", "").strip()
    if st not in (None, *cfg.STATUS) or not texto:
        abort(400)
    aid = repo.registrar(did, iso(f.get("data")), f.get("tipo") if f.get("tipo") in cfg.TIPOS else "Atualização",
                         texto, f.get("autor", "").strip(), st)
    _, recusados = armazenamento.salvar(did, aid, request.files.getlist("arquivos"))
    flash("Atualização registrada.")
    avisar_recusados(recusados)
    return _volta(did)


@bp.post("/d/<int:did>/desdobramento")
def desdobrar(did):
    """Registra processo, notificação, embargo ou autuação e lança o fato no histórico."""
    if (r := bloqueado(chamado(did))):
        return r
    f = request.form
    if f.get("tipo") not in cfg.DESD:
        abort(400)
    repo.registrar_desdobramento(did, f["tipo"], f.get("numero", "").strip(), iso(f.get("data")), f.get("obs", "").strip())
    flash(f"{f['tipo']} registrado(a).")
    return _volta(did)


@bp.post("/d/<int:did>/cancelar")
def cancelar(did):
    """Cancela o chamado com justificativa obrigatória (ele não é apagado)."""
    d = chamado(did)
    if d["status"] != cfg.CANCELADA:
        motivo = justificativa()
        if motivo:
            repo.cancelar(did, motivo, request.form.get("autor", "").strip())
            flash("Chamado cancelado. Ele continua guardado no sistema, com a justificativa no histórico.")
        else:
            flash("Informe a justificativa do cancelamento (mínimo de 10 caracteres).")
    return _volta(did)


@bp.post("/d/<int:did>/reativar")
def reativar(did):
    """Reativa um chamado cancelado, com justificativa obrigatória."""
    d = chamado(did)
    if d["status"] == cfg.CANCELADA:
        motivo = justificativa()
        if motivo:
            repo.reativar(did, motivo, request.form.get("autor", "").strip())
            flash("Chamado reativado.")
        else:
            flash("Informe a justificativa da reativação (mínimo de 10 caracteres).")
    return _volta(did)
