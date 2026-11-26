"""Filtros dos modelos (Jinja): etiqueta de status, datas, texto formatado e tamanho de arquivo."""
import re
from markupsafe import Markup, escape
from . import config as cfg
from .util import tamanho_legivel


def registrar(app):
    """Registra os filtros no aplicativo."""

    @app.template_filter("st")
    def st_tag(v):
        """Filtro st: etiqueta colorida do status."""
        fg, bg = cfg.COR.get(v, ("#37474f", "#dde4e8"))
        return Markup(f'<span class=tag style="background:{bg};color:{fg};border:1px solid {fg}">{escape(v)}</span>')

    @app.template_filter("cor")
    def st_cor(v):
        """Filtro cor: cor principal do status (bordas da lista e do chamado)."""
        return cfg.COR.get(v, ("#37474f",))[0]

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

    app.add_template_filter(tamanho_legivel, "tam")
