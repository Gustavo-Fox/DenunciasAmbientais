"""Armazenamento de anexos: validação (tipo, tamanho e assinatura), gravação, miniaturas e remoção sem apagar de vez."""
import os
import shutil
import uuid
from flask import current_app
from . import config as cfg, repo

try:
    from PIL import Image, ImageOps
except ImportError:  # sem Pillow o sistema funciona; só não gera miniaturas
    Image = None

# Primeiros bytes de cada formato, para conferir que o conteúdo bate com a extensão.
ASSINATURAS = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
               ".gif": (b"GIF87a", b"GIF89a"), ".pdf": (b"%PDF",)}


def _pasta(sub=""):
    """Pasta de anexos (ou subpasta: _mini = miniaturas, _removidos = anexos removidos), criada se não existir."""
    p = os.path.join(current_app.config["UP"], sub)
    os.makedirs(p, exist_ok=True)
    return p


def caminho(a):
    """Caminho do arquivo de um anexo no disco."""
    return os.path.join(current_app.config["UP"], a["arquivo"])


def validar(f):
    """Confere tipo, tamanho, assinatura e (com Pillow) se a imagem abre. Devolve (extensão, tamanho) ou levanta ValueError."""
    ext = os.path.splitext(f.filename)[1].lower()
    cat = cfg.TIPOS_ARQUIVO.get(ext)
    if not cat:
        raise ValueError("tipo de arquivo não permitido")
    f.stream.seek(0, os.SEEK_END)
    tam = f.stream.tell()
    f.stream.seek(0)
    if tam == 0:
        raise ValueError("arquivo vazio")
    if tam > cfg.LIMITES_MB[cat] * 1048576:
        raise ValueError(f"maior que {cfg.LIMITES_MB[cat]} MB (limite para {cat})")
    cab = f.stream.read(12)
    f.stream.seek(0)
    ok = (cab[:4] == b"RIFF" and cab[8:12] == b"WEBP") if ext == ".webp" else (ext not in ASSINATURAS or cab.startswith(ASSINATURAS[ext]))
    if not ok:
        raise ValueError("o conteúdo não corresponde ao tipo do arquivo")
    if Image is not None and ext in cfg.IMAGENS:
        try:
            Image.open(f.stream).verify()
        except Exception:
            raise ValueError("imagem inválida ou corrompida")
        finally:
            f.stream.seek(0)
    return ext, tam


def gravar(did, acomp_id, f):
    """Valida e grava um arquivo no disco e no banco; devolve o id do anexo (ValueError se for recusado)."""
    ext, tam = validar(f)
    arq = uuid.uuid4().hex[:12] + ext  # o nome original fica só no banco (para exibir e baixar)
    destino = os.path.join(_pasta(), arq)
    f.save(destino)
    try:
        aid = repo.inserir_anexo(did, acomp_id, f.filename, arq, tam)
    except Exception:
        os.remove(destino)
        raise
    miniatura(repo.anexo(aid))
    return aid


def salvar(did, acomp_id, arquivos):
    """Grava os arquivos válidos de um envio; devolve (quantos foram salvos, lista de (nome, motivo) dos recusados)."""
    arquivos = [f for f in arquivos if f and f.filename]
    recusados = [(f.filename, f"limite de {cfg.MAX_ARQUIVOS} arquivos por envio") for f in arquivos[cfg.MAX_ARQUIVOS:]]
    n = 0
    for f in arquivos[:cfg.MAX_ARQUIVOS]:
        try:
            gravar(did, acomp_id, f)
            n += 1
        except ValueError as e:
            recusados.append((f.filename, str(e)))
    return n, recusados


def miniatura(a):
    """Caminho da miniatura (JPEG de até 360 px) de um anexo de imagem, criada na primeira vez; None se não for possível."""
    origem = caminho(a)
    if Image is None or not a["arquivo"].lower().endswith(cfg.IMAGENS) or not os.path.exists(origem):
        return None
    mini = os.path.join(_pasta("_mini"), a["arquivo"] + ".jpg")
    if not os.path.exists(mini):
        try:
            with Image.open(origem) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((360, 360))
                im.convert("RGB").save(mini, "JPEG", quality=80)
        except Exception:
            return None
    return mini


def _guardar(a):
    """Tira o arquivo de uso: vai para uploads/_removidos (não é apagado) e a miniatura é descartada."""
    if os.path.exists(caminho(a)):
        shutil.move(caminho(a), os.path.join(_pasta("_removidos"), a["arquivo"]))
    mini = os.path.join(_pasta("_mini"), a["arquivo"] + ".jpg")
    if os.path.exists(mini):
        os.remove(mini)


def remover(a, motivo, autor):
    """Remove o anexo da tela, registrando motivo e autor; o arquivo fica guardado em uploads/_removidos."""
    _guardar(a)
    repo.marcar_anexo_removido(a, motivo, autor)


def substituir(a, f, motivo, autor):
    """Troca o anexo por outro arquivo (no mesmo lugar do histórico); o antigo fica guardado. ValueError se o novo for recusado."""
    gravar(a["denuncia_id"], a["acomp_id"], f)  # se o novo for recusado, o antigo continua intacto
    _guardar(a)
    repo.marcar_anexo_removido(a, f"Substituído por {f.filename}. {motivo}", autor, no_historico=False)
    repo.registrar(a["denuncia_id"], repo.hoje(), "Anexo", f"Anexo substituído: {a['nome']} → {f.filename}. Motivo: {motivo}", autor)
