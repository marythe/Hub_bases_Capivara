#!/usr/bin/env python3
"""Baixa os dados sem abrir a tela (útil para agendar).

    python baixar.py                 # todos os sites
    python baixar.py ibge_sidra      # só um site
    python baixar.py bcb selic       # só um conjunto de um site
"""

import sys
from pathlib import Path

from plataforma.armazenamento import Armazenamento
from plataforma.conectores import ErroConfig


def main(args):
    if len(args) > 2 or (args and args[0] in ("-h", "--help")):
        print(__doc__)
        return 2
    arm = Armazenamento(Path(__file__).parent)
    try:
        resultados = arm.baixar_tudo(*args)
    except ErroConfig as e:
        print(f"Erro: {e}")
        return 2
    for r in resultados:
        detalhe = (f"{r['linhas']} linhas" if r["status"] == "ok"
                   else f"ERRO: {r['mensagem']}")
        print(f"{r['fonte']}/{r['endpoint']}: {detalhe}")
    erros = sum(r["status"] == "erro" for r in resultados)
    print(f"\n{len(resultados) - erros} baixado(s), {erros} com erro.")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
