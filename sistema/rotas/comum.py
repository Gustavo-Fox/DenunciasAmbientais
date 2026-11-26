"""Utilitários compartilhados pelas rotas."""
from flask import abort, flash, redirect, request, url_for
from .. import config as cfg, repo


def chamado(did):
    """Devolve o chamado ou responde 404."""
    return repo.obter(did) or abort(404)


def bloqueado(d):
    """Se o chamado está cancelado, avisa e devolve o redirecionamento para a tela dele (senão None)."""
    if d["status"] == cfg.CANCELADA:
        flash("Chamado cancelado: reative-o para fazer alterações.")
        return redirect(url_for("chamados.detalhe", did=d["id"]))


def avisar_recusados(recusados):
    """Mostra, em uma mensagem, os arquivos recusados no envio e o motivo de cada um."""
    if recusados:
        flash("Arquivos recusados: " + "; ".join(f"{n} ({m})" for n, m in recusados) + ".")


def justificativa():
    """Justificativa digitada no formulário (mínimo de 10 caracteres); None se for curta demais."""
    t = request.form.get("motivo", "").strip()
    return t if len(t) >= 10 else None
