"""Rotas de backup: gera um .zip com o banco e os anexos, guarda as 5 últimas cópias e permite baixá-las."""
import os
import sqlite3
import uuid
import zipfile
from datetime import datetime
from flask import Blueprint, current_app, flash, render_template, request, send_file, send_from_directory
from ..util import tamanho_legivel

bp = Blueprint("backup", __name__)


def _copias(bk):
    """Nomes dos backups guardados, do mais novo para o mais antigo."""
    return sorted((x for x in os.listdir(bk) if x.startswith("backup_") and x.endswith(".zip")), reverse=True)


def gerar_zip(db, up, bk):
    """Cria o .zip (banco + anexos, sem as miniaturas), mantém só as 5 últimas cópias e devolve (caminho, nome)."""
    nome = "backup_denuncias_" + datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".zip"
    destino, tmp = os.path.join(bk, nome), os.path.join(bk, uuid.uuid4().hex + ".tmp")
    origem, copia = sqlite3.connect(db), sqlite3.connect(tmp)
    origem.backup(copia)  # cópia consistente, mesmo com o sistema em uso
    copia.close()
    origem.close()
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "denuncias.db")
        for raiz, dirs, arqs in os.walk(up):
            dirs[:] = [d for d in dirs if d != "_mini"]  # miniaturas são recriadas sozinhas
            for a in arqs:
                p = os.path.join(raiz, a)
                z.write(p, os.path.join("uploads", os.path.relpath(p, up)))
    os.remove(tmp)
    for velho in sorted(_copias(bk))[:-5]:
        os.remove(os.path.join(bk, velho))
    return destino, nome


@bp.route("/backup", methods=["GET", "POST"])
def backup():
    """Gera o backup (POST) e envia o arquivo para download; no GET, lista as cópias guardadas."""
    c = current_app.config
    os.makedirs(c["BK"], exist_ok=True)
    if request.method == "POST":
        destino, nome = gerar_zip(c["DB"], c["UP"], c["BK"])
        flash("Backup gerado.")
        return send_file(destino, as_attachment=True, download_name=nome)
    return render_template("backup.html", lista=[(x, tamanho_legivel(os.path.getsize(os.path.join(c["BK"], x)))) for x in _copias(c["BK"])])


@bp.route("/backup/<path:nome>")
def baixar(nome):
    """Baixa um backup guardado anteriormente."""
    return send_from_directory(current_app.config["BK"], nome, as_attachment=True)
