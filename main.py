#!/usr/bin/env python3
"""
Ponto de entrada principal do projeto na raiz do repositório.
Redireciona a execução diretamente para o módulo principal em src/main.py.
"""

import os
import sys

if __name__ == "__main__":
    caminho_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if caminho_src not in sys.path:
        sys.path.insert(0, caminho_src)
    
    from main import main
    main()
