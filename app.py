"""Ponto de entrada do sistema de denúncias ambientais.

Rodar:  python app.py   ->  abre http://127.0.0.1:5000 no navegador.
Em servidor (rede interna):  waitress-serve --port=5000 app:app
A organização do código está no README.md (pacote sistema/, templates/, static/).
"""
import os
import socket
import threading
import webbrowser
from sistema import create_app
from sistema.config import HOST, PORT

app = create_app()


def ja_rodando():
    """True se já existe um sistema respondendo na porta (por exemplo, o atalho foi clicado duas vezes)."""
    with socket.socket() as sk:
        sk.settimeout(0.5)
        return sk.connect_ex(("127.0.0.1", PORT)) == 0


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PORT}"
    if ja_rodando():
        print("O sistema já está aberto; abrindo o navegador.")
        webbrowser.open(url)
    else:
        if os.environ.get("DENUNCIAS_ABRIR", "1") == "1":  # DENUNCIAS_ABRIR=0 desliga a abertura automática
            threading.Timer(1.5, webbrowser.open, args=(url,)).start()
        app.run(host=HOST, port=PORT)
