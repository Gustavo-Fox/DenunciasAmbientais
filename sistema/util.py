"""Funções de apoio: leitura e validação de formulários, datas, números e formatação."""
from datetime import date
from flask import abort
from . import config as cfg


def num(v):
    """Converte texto em número aceitando vírgula decimal; devolve None se vazio ou inválido."""
    try:
        return float(v.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def iso(v):
    """Valida uma data AAAA-MM-DD vinda do formulário (senão responde 400)."""
    try:
        return date.fromisoformat((v or "").strip()).isoformat()
    except ValueError:
        abort(400)


def dados_form(f):
    """Lê, limpa e valida os campos do formulário de denúncia/fiscalização (usado ao cadastrar e ao editar)."""
    g_ = lambda k: f.get(k, "").strip()
    try:
        cat = int(f.get("categoria_id", ""))
    except ValueError:
        abort(400)
    if not g_("descricao") or not g_("logradouro"):
        abort(400)
    lat, lon = num(g_("lat")), num(g_("lon"))
    if (lat is not None and not -90 <= lat <= 90) or (lon is not None and not -180 <= lon <= 180):
        abort(400)
    if (lat is None) != (lon is None):
        lat = lon = None
    anon = 1 if f.get("anonima") else 0
    return {"criada": iso(f.get("criada")), "categoria_id": cat,
            "prioridade": g_("prioridade") if g_("prioridade") in cfg.PRIORIDADES else "Normal",
            "descricao": g_("descricao"), "legislacao": g_("legislacao"),
            "reincidente": 1 if f.get("reincidente") == "1" else 0, "anonima": anon,
            "denunciante": "" if anon else g_("denunciante"), "contato": "" if anon else g_("contato"),
            "resp_nome": g_("resp_nome"), "resp_cpf": g_("resp_cpf"), "resp_contato": g_("resp_contato"),
            "logradouro": g_("logradouro"), "numero": g_("numero"), "bairro": g_("bairro"),
            "municipio": g_("municipio"), "referencia": g_("referencia"), "lat": lat, "lon": lon,
            "fiscal": g_("fiscal")}


def tamanho_legivel(n):
    """Formata bytes como KB ou MB."""
    n = n or 0
    return f"{n / 1048576:.1f} MB".replace(".", ",") if n >= 1048576 else f"{max(1, round(n / 1024))} KB"
