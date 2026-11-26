"""Configuração e constantes do sistema: status e cores, tipos, limites de anexos e variáveis de ambiente."""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pasta do projeto (onde fica o app.py)
VERSAO = "2.0"
HOST = os.environ.get("DENUNCIAS_HOST", "127.0.0.1")   # 127.0.0.1 = acessível só neste computador
PORT = int(os.environ.get("DENUNCIAS_PORT", "5000"))
POR_PAGINA = 50                                        # chamados por página na listagem
MAX_REQUISICAO_MB = 200                                # tamanho máximo de um envio inteiro (formulário + arquivos)

# --- Status -----------------------------------------------------------------
STATUS = ["Recebida", "Em análise", "Em fiscalização", "Vistoriada", "Notificada", "Embargada", "Autuada",
          "Aguardando retorno", "Encerrada", "Arquivada"]   # status que o fiscal escolhe ao atualizar
CANCELADA = "Cancelada"                                      # só pelo fluxo "Cancelar chamado" (com justificativa)
STATUS_TODOS = STATUS + [CANCELADA]                          # usado nos filtros e na legenda
COR = {  # status: (cor do texto/borda, cor de fundo)
    "Recebida": ("#1d5fa8", "#dce9f7"), "Em análise": ("#6b3fa0", "#ece3f6"), "Em fiscalização": ("#0b7285", "#d5f0f4"),
    "Vistoriada": ("#2e7d32", "#dff0d8"), "Notificada": ("#8a5a00", "#fcefc7"), "Embargada": ("#b04a0b", "#fde3d0"),
    "Autuada": ("#b3261e", "#fadbd8"), "Aguardando retorno": ("#a1296b", "#f8dceb"),
    "Encerrada": ("#37474f", "#dde4e8"), "Arquivada": ("#6d4c41", "#ede4e0"), "Cancelada": ("#212121", "#e0e0e0")}

# --- Chamados ---------------------------------------------------------------
PREFIXO = {"Denúncia": "DEN", "Fiscalização": "FIS"}  # origem do chamado -> prefixo do código
PRIORIDADES = ["Baixa", "Normal", "Alta"]
TIPOS = ["Atualização", "Vistoria", "Revisita", "Contato", "Encerramento"]  # tipos de registro escolhidos pelo fiscal
DESD = ["Processo", "Notificação", "Embargo", "Autuação"]
# Registros lançados pelo próprio sistema: não contam como produtividade nos relatórios.
TIPOS_SISTEMA = ("Recebimento", "Abertura", "Correção", "Cancelamento", "Reativação", "Anexo")
CENTRO = (-14.2, -51.9, 4)  # centro inicial do mapa (lat, lon, zoom); ajuste para sua região

# --- Anexos -----------------------------------------------------------------
TIPOS_ARQUIVO = {  # extensão -> categoria (define o limite de tamanho)
    **{e: "imagens" for e in (".jpg", ".jpeg", ".png", ".gif", ".webp")},
    **{e: "documentos" for e in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odt", ".ods", ".txt", ".csv")},
    **{e: "vídeos" for e in (".mp4", ".mov", ".webm")}}
LIMITES_MB = {"imagens": 15, "documentos": 25, "vídeos": 100}  # limite por arquivo, por categoria
MAX_ARQUIVOS = 20                                              # arquivos por envio
IMAGENS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
ABRE_NO_NAVEGADOR = IMAGENS + (".pdf",)                        # o resto é baixado (nunca executado)
