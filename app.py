#!/usr/bin/env python3
"""Plataforma de dados: abre a tela no navegador.

    python app.py                # abre em http://127.0.0.1:8000
    python app.py --porta 9000
"""

import argparse
import threading
import webbrowser
from pathlib import Path

from plataforma.servidor import criar_servidor


def main():
    p = argparse.ArgumentParser(description="Plataforma de conexão com APIs")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--sem-navegador", action="store_true",
                   help="não abre o navegador automaticamente")
    p.add_argument("--qualquer-host", action="store_true",
                   help="aceita acesso por um endereço diferente de "
                        "127.0.0.1 (ex.: atrás de um proxy)")
    args = p.parse_args()

    servidor = criar_servidor(Path(__file__).parent, args.porta,
                              args.qualquer_host)
    url = f"http://127.0.0.1:{args.porta}"
    print(f"Plataforma no ar em {url}  (Ctrl+C para encerrar)")
    if not args.sem_navegador:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
