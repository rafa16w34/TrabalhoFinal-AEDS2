"""
Ponto de entrada para o Hugging Face Spaces / Nuvem
Sistema de Recomendação de Jogos da Steam (Trabalho Final AEDS 2 - CEFET-MG / UFC-IMG)
Autores: Rafael Alves Faria e Gabriel Alves Faria
"""
import os
import sys

# Garante acesso aos módulos em src/
root_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(root_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import main
import servidor_web

if __name__ == "__main__":
    # 1. Garante que os dados do Zenodo existam (baixa automaticamente se necessário)
    main.garantir_dados_zenodo()
    
    # 2. Obtém a porta (Hugging Face injeta PORT=7860; padrão local = 7860 ou 5000)
    porta_str = os.environ.get("PORT", "7860")
    porta = int(porta_str) if porta_str.isdigit() else 7860
    
    # 3. Inicia o servidor web nativo (sem abrir navegador automaticamente na nuvem)
    print(f"🚀 Iniciando Steam Finder na porta {porta}...")
    servidor_web.iniciar_servidor(porta=porta, abrir_navegador=False)
