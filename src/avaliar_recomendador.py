import os
import sys
import random
import math
import time
from collections import defaultdict

# Garante acesso aos módulos em src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main
import recommender

def carregar_dados_avaliacao():
    """Carrega as estruturas com Louvain em cache"""
    print("=" * 65)
    print("INICIALIZANDO ESTRUTURAS PARA AVALIAÇÃO QUANTITATIVA")
    print("=" * 65)
    grafo, titulos, metadados, comunidades = main.inicializacao()
    return grafo, titulos, metadados, comunidades

def preparar_amostra_leave_one_out(grafo, qtd_usuarios=400, seed=42):
    """
    Seleciona uma amostra reprodutível de usuários para o protocolo Leave-One-Out.
    Para cada usuário, separa:
    - jogo_alvo (maior engajamento)
    - jogo_oculto (item de teste retirado temporariamente do grafo)
    """
    random.seed(seed)
    todos_usuarios = [n for n, d in grafo.nodes(data=True) if d.get('tipo') == 'usuario']
    
    # Filtra usuários com grau suficiente para ter jogo alvo e jogo oculto
    usuarios_candidatos = [u for u in todos_usuarios if grafo.degree(u) >= 10]
    amostra_usuarios = random.sample(usuarios_candidatos, min(qtd_usuarios, len(usuarios_candidatos)))
    
    pares_teste = []
    for node_u in amostra_usuarios:
        vizinhos = grafo[node_u]
        # Ordena jogos do usuário por peso de engajamento
        jogos_ordenados = sorted(
            [(j.replace("game_", ""), d['weight']) for j, d in vizinhos.items()],
            key=lambda x: x[1],
            reverse=True
        )
        
        jogo_alvo = jogos_ordenados[0][0]
        # Escolhe um jogo oculto entre os demais jogos bem avaliados do usuário
        candidatos_ocultos = [j for j, _ in jogos_ordenados[1:]]
        jogo_oculto = random.choice(candidatos_ocultos)
        
        pares_teste.append((node_u, jogo_alvo, jogo_oculto))

    print(f" -> {len(pares_teste)} pares de teste Leave-One-Out gerados com sucesso (seed={seed}).")
    return pares_teste

def avaliar_configuracao(grafo, pares_teste, comunidades, metadados, 
                         limiar_jaccard=0.20, expoente_grau=0.35, peso_louvain=3.0, 
                         min_positive_ratio=65.0, fator_dissonancia_tom=0.0, top_n=10):
    """
    Executa o protocolo Leave-One-Out para uma configuração específica de hiperparâmetros
    e calcula Hit Rate@K e NDCG@K.
    """
    hits = 0
    soma_ndcg = 0.0
    total = len(pares_teste)

    for node_u, jogo_alvo, jogo_oculto in pares_teste:
        node_oculto = f"game_{jogo_oculto}"
        peso_original = None

        # Oculta a aresta temporariamente para não vazar informação de teste
        if grafo.has_edge(node_u, node_oculto):
            peso_original = grafo[node_u][node_oculto]['weight']
            grafo.remove_edge(node_u, node_oculto)

        # Gera recomendações a partir do jogo-alvo
        recs, _ = recommender.recomendar_jogos(
            grafo, 
            jogo_alvo, 
            comunidades, 
            metadados, 
            top_k_users=50, 
            top_n_jogos=top_n,
            limiar_jaccard=limiar_jaccard,
            peso_louvain=peso_louvain,
            expoente_grau=expoente_grau,
            min_positive_ratio=min_positive_ratio,
            fator_dissonancia_tom=fator_dissonancia_tom,
            silencioso=True
        )

        # Restaura a aresta no grafo
        if peso_original is not None:
            grafo.add_edge(node_u, node_oculto, weight=peso_original)

        # Extrai IDs recomendados
        ids_recomendados = [j.replace("game_", "") for j, _ in recs]

        # Verifica se o jogo oculto foi recomendado
        if jogo_oculto in ids_recomendados:
            rank = ids_recomendados.index(jogo_oculto) + 1  # 1-indexed
            hits += 1
            soma_ndcg += 1.0 / math.log2(rank + 1)

    hit_rate = (hits / total) * 100.0
    ndcg = (soma_ndcg / total)
    return hit_rate, ndcg

def executar_analise_sensibilidade():
    grafo, titulos, metadados, comunidades = carregar_dados_avaliacao()
    pares_teste = preparar_amostra_leave_one_out(grafo, qtd_usuarios=300, seed=42)

    print("\n" + "=" * 65)
    print("1. ANÁLISE DE SENSIBILIDADE: CORTE DE JACCARD")
    print("   (Fixando: Expoente de Grau = 0.35, Bônus Louvain = 3.0)")
    print("=" * 65)
    print(f"{'Corte Jaccard':<15} | {'Hit Rate@10 (%)':<18} | {'NDCG@10':<12}")
    print("-" * 52)

    cortes = [0.10, 0.15, 0.20, 0.25]
    resultados_jaccard = []
    for c in cortes:
        hr, ndcg = avaliar_configuracao(
            grafo, pares_teste, comunidades, metadados,
            limiar_jaccard=c, expoente_grau=0.35, peso_louvain=3.0
        )
        resultados_jaccard.append((c, hr, ndcg))
        print(f"{c:<15.2f} | {hr:<18.2f} | {ndcg:<12.4f}")

    print("\n" + "=" * 65)
    print("2. ANÁLISE DE SENSIBILIDADE: AMORTECIMENTO DE GRAU (POPULARIDADE)")
    print("   (Fixando: Corte Jaccard = 0.20, Bônus Louvain = 3.0)")
    print("=" * 65)
    print(f"{'Expoente Grau':<15} | {'Hit Rate@10 (%)':<18} | {'NDCG@10':<12}")
    print("-" * 52)

    expoentes = [0.00, 0.20, 0.35, 0.50]
    resultados_grau = []
    for exp in expoentes:
        hr, ndcg = avaliar_configuracao(
            grafo, pares_teste, comunidades, metadados,
            limiar_jaccard=0.20, expoente_grau=exp, peso_louvain=3.0
        )
        resultados_grau.append((exp, hr, ndcg))
        print(f"{exp:<15.2f} | {hr:<18.2f} | {ndcg:<12.4f}")

    print("\n" + "=" * 65)
    print("3. ANÁLISE DE SENSIBILIDADE: BÔNUS DE COMUNIDADE (LOUVAIN)")
    print("   (Fixando: Corte Jaccard = 0.20, Expoente Grau = 0.35)")
    print("=" * 65)
    print(f"{'Bônus Louvain':<15} | {'Hit Rate@10 (%)':<18} | {'NDCG@10':<12}")
    print("-" * 52)

    bonus_list = [1.00, 2.00, 3.00, 5.00]
    resultados_louvain = []
    for b in bonus_list:
        hr, ndcg = avaliar_configuracao(
            grafo, pares_teste, comunidades, metadados,
            limiar_jaccard=0.20, expoente_grau=0.35, peso_louvain=b
        )
        resultados_louvain.append((b, hr, ndcg))
        print(f"{b:<15.2f} | {hr:<18.2f} | {ndcg:<12.4f}")

    print("\n" + "=" * 65)
    print("4. ANÁLISE DE SENSIBILIDADE: FILTRO DE QUALIDADE MÍNIMA (POSITIVE RATIO)")
    print("   (Fixando: Corte Jaccard = 0.20, Expoente Grau = 0.35, Louvain = 3.0)")
    print("=" * 65)
    print(f"{'Min Pos Ratio %':<15} | {'Hit Rate@10 (%)':<18} | {'NDCG@10':<12}")
    print("-" * 52)

    qualidades = [0.0, 50.0, 60.0, 65.0, 70.0]
    for q in qualidades:
        hr, ndcg = avaliar_configuracao(
            grafo, pares_teste, comunidades, metadados,
            limiar_jaccard=0.20, expoente_grau=0.35, peso_louvain=3.0,
            min_positive_ratio=q
        )
        print(f"{q:<15.1f} | {hr:<18.2f} | {ndcg:<12.4f}")

    print("\n" + "=" * 65)
    print("EXPERIMENTO QUANTITATIVO FINALIZADO COM SUCESSO!")
    print("=" * 65)

if __name__ == "__main__":
    executar_analise_sensibilidade()
