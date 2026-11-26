"""Rotas de revisitas: lista de pendentes, agendamento e conclusão."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from .. import repo
from ..util import iso
from .comum import bloqueado, chamado

bp = Blueprint("revisitas", __name__)


@bp.route("/revisitas")
def pendentes():
    """Revisitas pendentes, da mais antiga para a mais nova."""
    return render_template("revisitas.html", rows=repo.revisitas_pendentes())


@bp.post("/d/<int:did>/revisita")
def agendar(did):
    """Agenda uma revisita para a data informada."""
    if (r := bloqueado(chamado(did))):
        return r
    repo.agendar_revisita(did, iso(request.form.get("prevista")))
    flash("Revisita agendada.")
    return redirect(url_for("chamados.detalhe", did=did))


@bp.post("/revisita/<int:rid>/feita")
def feita(rid):
    """Conclui uma revisita agendada e lança o que foi constatado no histórico (uma única vez)."""
    rev = repo.revisita(rid) or abort(404)
    if (r := bloqueado(chamado(rev["denuncia_id"]))):
        return r
    obs, fiscal = request.form.get("obs", "").strip(), request.form.get("fiscal", "").strip()
    if not rev["feita"] and obs:  # já concluída (clique duplo) ou sem relato: não repete
        repo.concluir_revisita(rev, obs, fiscal)
        flash("Revisita concluída.")
    return redirect(url_for("chamados.detalhe", did=rev["denuncia_id"]))
