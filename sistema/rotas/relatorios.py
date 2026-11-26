"""Rota do relatório mensal imprimível."""
import re
from datetime import date
from flask import Blueprint, render_template, request
from .. import repo

bp = Blueprint("relatorios", __name__)


@bp.route("/relatorio")
def relatorio():
    """Relatório mensal: totais, produtividade por fiscal e listas do período (mês inválido vira o mês atual)."""
    mes = request.args.get("mes", "")
    if not re.fullmatch(r"\d{4}-\d{2}", mes):
        mes = date.today().strftime("%Y-%m")
    fiscal = request.args.get("fiscal", "").strip()
    return render_template("relatorio.html", mes=mes, fiscal=fiscal, **repo.relatorio(mes, fiscal))
