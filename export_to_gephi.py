import os
import networkx as nx

# Importamos as funções que já criamos no recommender.py para não reinventar a roda
from recommender import construir_grafo, carregar_titulos_jogos

def exportar_para_gephi():
    print("="*50)
    print("INICIANDO EXPORTAÇÃO PARA GEPHI (Baseline)")
    print("="*50)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ARQUIVO_AMOSTRA = os.path.join(BASE_DIR, 'extracted_data', 'sampled_recommendations.csv')
    ARQUIVO_GAMES = os.path.join(BASE_DIR, 'extracted_data', 'games.csv')

    # 1. Carrega os títulos e o K-Core
    dicionario_titulos = carregar_titulos_jogos(ARQUIVO_GAMES)
    G = construir_grafo(ARQUIVO_AMOSTRA)

    if not G:
        return

    print("\nPreparando os Rótulos (Labels) para o Gephi...")
    
    # 2. O Gephi exige que os nós tenham o atributo "label" para mostrar o nome na tela.
    # O nosso grafo original não tem isso para economizar memória durante a BFS. 
    # Aqui nós iteramos sobre todos os vértices e injetamos o nome.
    for node_id, dados_do_no in G.nodes(data=True):
        if dados_do_no.get('tipo') == 'jogo':
            app_id = dados_do_no.get('nome_original')
            # Busca no dicionário de títulos; se não achar, coloca "Jogo ID"
            nome_real = dicionario_titulos.get(app_id, f"Jogo {app_id}")
            dados_do_no['label'] = nome_real
        else:
            # Para usuários, colocamos apenas "Usuário XYZ"
            user_id = dados_do_no.get('nome_original')
            dados_do_no['label'] = f"Usuário {user_id}"

    # 3. Exporta para o formato GEXF (Graph Exchange XML Format) padrão do Gephi
    arquivo_saida = "universo_steam_baseline.gexf"
    print(f"\nEscrevendo arquivo {arquivo_saida} (Isso pode demorar dependendo do tamanho)...")
    
    nx.write_gexf(G, arquivo_saida)
    
    print("="*50)
    print(f"EXPORTAÇÃO CONCLUÍDA! Você já pode abrir o {arquivo_saida} no Gephi.")
    print("="*50)

if __name__ == "__main__":
    exportar_para_gephi()
