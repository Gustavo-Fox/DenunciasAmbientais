"""Rotas de anexos: abrir o arquivo, miniatura, e gerenciar (substituir ou remover) com motivo."""
from flask import Blueprint, abort, current_app, flash, redirect, request, send_file, send_from_directory, url_for
from .. import armazenamento, config as cfg, repo
from .comum import bloqueado, chamado

bp = Blueprint("anexos", __name__)


def _ativo(aid):
    """Anexo existente e não removido (senão 404)."""
    a = repo.anexo(aid)
    if not a or a["removido_em"]:
        abort(404)
    return a


@bp.route("/anexos/<int:aid>/arquivo")
def arquivo(aid):
    """Entrega o anexo. Só imagens e PDF abrem no navegador; os demais tipos são baixados (nunca executados)."""
    a = _ativo(aid)
    return send_from_directory(current_app.config["UP"], a["arquivo"], download_name=a["nome"],
                               as_attachment=not a["arquivo"].lower().endswith(cfg.ABRE_NO_NAVEGADOR))


@bp.route("/anexos/<int:aid>/mini")
def mini(aid):
    """Miniatura da imagem; sem Pillow (ou se a imagem não abrir), entrega a original."""
    p = armazenamento.miniatura(_ativo(aid))
    return send_file(p, mimetype="image/jpeg", max_age=86400) if p else arquivo(aid)


@bp.post("/anexos/<int:aid>/gerir")
def gerir(aid):
    """Substitui ou remove um anexo (motivo obrigatório). O arquivo antigo não é apagado: vai para uploads/_removidos."""
    a = _ativo(aid)
    volta = redirect(url_for("chamados.detalhe", did=a["denuncia_id"]))
    if (r := bloqueado(chamado(a["denuncia_id"]))):
        return r
    f, motivo, autor = request.form, request.form.get("motivo", "").strip(), request.form.get("autor", "").strip()
    if len(motivo) < 3:
        flash("Informe o motivo.")
    elif f.get("acao") == "remover":
        armazenamento.remover(a, motivo, autor)
        flash("Anexo removido. O arquivo fica guardado em uploads/_removidos.")
    elif f.get("acao") == "substituir":
        novo = request.files.get("arquivo")
        if not novo or not novo.filename:
            flash("Escolha o arquivo novo.")
        else:
            try:
                armazenamento.substituir(a, novo, motivo, autor)
                flash("Anexo substituído.")
            except ValueError as e:
                flash(f"Arquivo recusado: {e}.")
    return volta
