import sys, os, time, statistics, random
from collections import defaultdict
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)
import main, recommender, avaliar_recomendador

def main_experiment():
    print("=== INICIALIZANDO GRAFO E ESTRUTURAS ===")
    grafo, titulos, metadados, comunidades = main.inicializacao()
    
    # 1. Obter os Top-10 jogos de Popularidade Global por Grau
    todos_jogos = [n for n in grafo.nodes() if str(n).startswith('game_')]
    jogos_ordenados_grau = sorted(todos_jogos, key=lambda n: grafo.degree(n), reverse=True)
    pop_global_top10 = [n.replace('game_', '') for n in jogos_ordenados_grau[:10]]
    print(f"Popularidade Global Top-10: {[titulos.get(g, g) for g in pop_global_top10]}")
    
    # Mediana do grau do catálogo para estratificação
    graus_catalogo = [grafo.degree(n) for n in todos_jogos]
    mediana_grau_catalogo = statistics.median(graus_catalogo)
    print(f"Total jogos no catálogo: {len(todos_jogos)} | Mediana de Grau: {mediana_grau_catalogo:.1f}")

    # 2. Gerar pares de teste Leave-One-Out (Seed 42, N=300)
    pares = avaliar_recomendador.preparar_amostra_leave_one_out(grafo, qtd_usuarios=300, seed=42)
    print(f"Pares LOO gerados: {len(pares)}")

    # Função de Co-ocorrência simples (CF Item-Item sem semântica, sem Louvain, sem tom, sem amortecimento)
    def recomendar_coocorrencia(jalvo, top_k=1000):
        node_alvo = f"game_{jalvo}"
        if node_alvo not in grafo:
            return []
        vizinhos = sorted(grafo[node_alvo].items(), key=lambda x: x[1].get('weight', 1.0), reverse=True)[:top_k]
        scores = defaultdict(float)
        for u, d_u in vizinhos:
            w_u = d_u.get('weight', 1.0)
            for v, d_v in grafo[u].items():
                if v == node_alvo:
                    continue
                w_v = d_v.get('weight', 1.0)
                scores[v] += w_u * w_v
        top_cands = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        return [c[0].replace('game_', '') for c in top_cands]

    # Modelos a avaliar
    modelos = ["Popularidade Global", "Co-ocorrência Pura (CF)", "Método sem Amortecimento (a=0)", "Método Proposto (a=0.35)"]
    
    # Estruturas de métricas
    metricas = {m: {
        'hits': 0,
        'ndcg': [],
        'hits_sub_mediana': 0,
        'total_sub_mediana': 0,
        'hits_sup_mediana': 0,
        'total_sup_mediana': 0,
        'comm_overlap': [],
        'genre_jaccard': [],
        'tag_jaccard': [],
        'unique_items': set(),
        'intra_list_div': []
    } for m in modelos}

    print("\n=== EXECUTANDO AVALIAÇÃO COMPARATIVA NAS 300 CONSULTAS ===")
    t_start = time.time()

    for idx, (usuario, jalvo, joculto) in enumerate(pares):
        if (idx + 1) % 50 == 0:
            print(f"Progresso: {idx+1}/300 consultas avaliadas ({time.time()-t_start:.1f}s)...")

        # Dados do jogo alvo e oculto
        grau_oculto = grafo.degree(f"game_{joculto}") if f"game_{joculto}" in grafo else 0
        is_sub_mediana = (grau_oculto < mediana_grau_catalogo)
        
        c_alvo = comunidades.get(f"game_{jalvo}")
        g_alvo = metadados.get(jalvo, {}).get('genres', set())
        t_alvo = set(metadados.get(jalvo, {}).get('tags', []))

        # Mascaramento temporário da aresta de teste para LOO
        peso_oculto = None
        user_node = usuario if str(usuario).startswith("user_") else f"user_{usuario}"
        oculto_node = f"game_{joculto}"
        if grafo.has_edge(user_node, oculto_node):
            peso_oculto = grafo[user_node][oculto_node].get('weight', 1.0)
            grafo.remove_edge(user_node, oculto_node)

        # 1. Popularidade Global
        recs_pop = list(pop_global_top10)
        
        # 2. Co-ocorrência Pura
        recs_cooc = recomendar_coocorrencia(jalvo, top_k=1000)
        
        # 3. Método a=0.00
        res_a0, _ = recommender.recomendar_jogos(grafo, jalvo, comunidades, metadados, top_k_users=1000, expoente_grau=0.0, silencioso=True)
        recs_a0 = [c[0].replace('game_', '') for c in res_a0]

        # 4. Método a=0.35
        res_a35, _ = recommender.recomendar_jogos(grafo, jalvo, comunidades, metadados, top_k_users=1000, expoente_grau=0.35, silencioso=True)
        recs_a35 = [c[0].replace('game_', '') for c in res_a35]

        # Restaurar aresta de teste imediatamente
        if peso_oculto is not None:
            grafo.add_edge(user_node, oculto_node, weight=peso_oculto)

        listas_recs = {
            "Popularidade Global": recs_pop,
            "Co-ocorrência Pura (CF)": recs_cooc,
            "Método sem Amortecimento (a=0)": recs_a0,
            "Método Proposto (a=0.35)": recs_a35
        }

        import math
        for m_nome, recs in listas_recs.items():
            st = metricas[m_nome]
            
            # Hits e NDCG
            hit = 1 if joculto in recs else 0
            st['hits'] += hit
            if hit:
                rk = recs.index(joculto) + 1
                st['ndcg'].append(1.0 / math.log2(rk + 1))
            else:
                st['ndcg'].append(0.0)

            # Estratificação por popularidade do item oculto
            if is_sub_mediana:
                st['total_sub_mediana'] += 1
                if hit:
                    st['hits_sub_mediana'] += 1
            else:
                st['total_sup_mediana'] += 1
                if hit:
                    st['hits_sup_mediana'] += 1

            # Itens únicos
            for r in recs:
                st['unique_items'].add(r)

            # Similaridade com o jogo-alvo
            c_matches = []
            g_jaccards = []
            t_jaccards = []
            for r in recs:
                # Comunidade
                c_r = comunidades.get(f"game_{r}")
                c_matches.append(1.0 if (c_alvo is not None and c_alvo == c_r) else 0.0)
                
                # Gêneros oficiais (não circular)
                g_r = metadados.get(r, {}).get('genres', set())
                if g_alvo and g_r and (g_alvo | g_r):
                    g_jaccards.append(len(g_alvo & g_r) / len(g_alvo | g_r))
                else:
                    g_jaccards.append(0.0)

                # Tags comunitárias
                t_r = set(metadados.get(r, {}).get('tags', []))
                if t_alvo and t_r and (t_alvo | t_r):
                    t_jaccards.append(len(t_alvo & t_r) / len(t_alvo | t_r))
                else:
                    t_jaccards.append(0.0)

            st['comm_overlap'].append(statistics.mean(c_matches) if c_matches else 0.0)
            st['genre_jaccard'].append(statistics.mean(g_jaccards) if g_jaccards else 0.0)
            st['tag_jaccard'].append(statistics.mean(t_jaccards) if t_jaccards else 0.0)

            # Diversidade intra-lista (1 - Jaccard médio de gênero entre pares da lista)
            if len(recs) >= 2:
                pair_sims = []
                for i in range(len(recs)):
                    gi = metadados.get(recs[i], {}).get('genres', set())
                    for j in range(i + 1, len(recs)):
                        gj = metadados.get(recs[j], {}).get('genres', set())
                        if gi and gj and (gi | gj):
                            pair_sims.append(len(gi & gj) / len(gi | gj))
                        else:
                            pair_sims.append(0.0)
                st['intra_list_div'].append(1.0 - statistics.mean(pair_sims) if pair_sims else 1.0)
            else:
                st['intra_list_div'].append(0.0)

    # Imprimir Relatório Consolidado
    print("\n" + "="*80)
    print("RESULTADOS CONSOLIDADOS: MÉTRICAS COMPARATIVAS (N=300, Seed 42, K=1000)")
    print("="*80)
    header = f"{'Modelo':<30} | {'HR@10':<7} | {'NDCG@10':<7} | {'Sub-Med HR':<10} | {'Sup-Med HR':<10} | {'Com. Match':<10} | {'Gên. Jacc.':<10} | {'Tag Jacc.':<10} | {'Cat. Cov.':<10} | {'Intra-Div':<9}"
    print(header)
    print("-" * len(header))

    res_json = {}
    for m in modelos:
        st = metricas[m]
        hr = (st['hits'] / 300.0) * 100.0
        ndcg = statistics.mean(st['ndcg'])
        hr_sub = (st['hits_sub_mediana'] / st['total_sub_mediana'] * 100.0) if st['total_sub_mediana'] else 0.0
        hr_sup = (st['hits_sup_mediana'] / st['total_sup_mediana'] * 100.0) if st['total_sup_mediana'] else 0.0
        c_match = statistics.mean(st['comm_overlap']) * 100.0
        g_jacc = statistics.mean(st['genre_jaccard']) * 100.0
        t_jacc = statistics.mean(st['tag_jaccard']) * 100.0
        cov_pct = (len(st['unique_items']) / len(todos_jogos)) * 100.0
        cov_str = f"{len(st['unique_items'])} ({cov_pct:.1f}%)"
        ild = statistics.mean(st['intra_list_div']) * 100.0

        res_json[m] = {
            'hr10': hr,
            'ndcg10': ndcg,
            'hr_sub_mediana': hr_sub,
            'hr_sup_mediana': hr_sup,
            'community_match_pct': c_match,
            'genre_jaccard_pct': g_jacc,
            'tag_jaccard_pct': t_jacc,
            'catalog_coverage_count': len(st['unique_items']),
            'catalog_coverage_pct': cov_pct,
            'intra_list_diversity_pct': ild
        }

        print(f"{m:<30} | {hr:6.2f}% | {ndcg:7.4f} | {hr_sub:6.2f}% ({st['hits_sub_mediana']}/{st['total_sub_mediana']}) | {hr_sup:6.2f}% ({st['hits_sup_mediana']}/{st['total_sup_mediana']}) | {c_match:9.1f}% | {g_jacc:9.1f}% | {t_jacc:9.1f}% | {cov_str:<10} | {ild:8.1f}%")

    import json
    out_path = os.path.join(os.path.dirname(base_dir), 'output', 'metricas_multidimensionais.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(res_json, f, indent=2)
    print(f"\nResultados salvos com sucesso em {out_path}!")

if __name__ == '__main__':
    main_experiment()
