"""Sistema de denúncias ambientais (chamados de fiscalização): fábrica do aplicativo Flask.

Camadas: rotas/ (blueprints, só recebem e respondem) -> repo.py (todo o SQL) -> db.py (conexão e esquema);
armazenamento.py cuida dos arquivos anexados; templates/ e static/ ficam na pasta do projeto.
"""
import os
from urllib.parse import urlencode, urlsplit
from flask import Flask, abort, render_template, request
from . import config as cfg, db, filters
from .rotas import anexos, backup, chamados, painel, relatorios, revisitas


def create_app(dados=None):
    """Cria o aplicativo. `dados` = pasta do banco, anexos e backups (padrão: DENUNCIAS_DIR ou a pasta do projeto)."""
    app = Flask(__name__, template_folder=os.path.join(cfg.RAIZ, "templates"), static_folder=os.path.join(cfg.RAIZ, "static"))
    dados = dados or os.environ.get("DENUNCIAS_DIR", cfg.RAIZ)
    app.config.update(DADOS=dados, DB=os.path.join(dados, "denuncias.db"), UP=os.path.join(dados, "uploads"),
                      BK=os.path.join(dados, "backups"), MAX_CONTENT_LENGTH=cfg.MAX_REQUISICAO_MB * 1024 * 1024,
                      SECRET_KEY=os.urandom(24))  # a chave só serve às mensagens de aviso (flash); muda a cada reinício
    os.makedirs(app.config["UP"], exist_ok=True)
    db.iniciar(app.config["DB"])
    app.teardown_appcontext(db.fechar)
    filters.registrar(app)
    _seguranca(app)
    _erros(app)
    _contexto(app)
    for modulo in (painel, chamados, revisitas, anexos, relatorios, backup):
        app.register_blueprint(modulo.bp)
    return app


def _seguranca(app):
    """Bloqueio de envios vindos de outros sites (CSRF) e cabeçalhos de segurança."""

    @app.before_request
    def mesma_origem():
        if request.method == "POST":
            o = request.headers.get("Origin") or request.headers.get("Referer", "")
            if o and urlsplit(o).netloc != request.host:
                abort(403)

    @app.after_request
    def cabecalhos(r):
        # O Referrer-Policy precisa permitir enviar a origem a outros sites: o OpenStreetMap bloqueia o mapa sem ela.
        r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                          "Referrer-Policy": "strict-origin-when-cross-origin"})
        return r


def _erros(app):
    """Páginas de erro amigáveis."""
    msgs = {400: "Dados inválidos. Volte e confira o formulário.", 403: "Acesso negado.", 404: "Página não encontrada.",
            413: "Envio grande demais (limite de %d MB no total)." % cfg.MAX_REQUISICAO_MB,
            500: "Erro interno. Tente de novo e, se persistir, avise o responsável."}

    def erro(e):
        return render_template("erro.html", cod=e.code, msg=msgs.get(e.code, "Erro.")), e.code

    for codigo in msgs:
        app.register_error_handler(codigo, erro)


def _contexto(app):
    """Variáveis disponíveis em todas as telas."""
    lim = cfg.LIMITES_MB
    exts = sorted(cfg.TIPOS_ARQUIVO)
    dica = (f"Imagens até {lim['imagens']} MB, documentos até {lim['documentos']} MB, vídeos até {lim['vídeos']} MB; "
            f"até {cfg.MAX_ARQUIVOS} arquivos por envio. Tipos aceitos: " + ", ".join(e[1:] for e in exts) + ".")

    @app.context_processor
    def ctx():
        from .repo import hoje
        return dict(STATUS=cfg.STATUS, STATUS_TODOS=cfg.STATUS_TODOS, TIPOS=cfg.TIPOS, DESD=cfg.DESD, VERSAO=cfg.VERSAO,
                    ANEXO_ACCEPT=",".join(exts), ANEXO_DICA=dica, hoje=hoje(),
                    qs=lambda **kw: urlencode({**request.args.to_dict(), **kw}))
