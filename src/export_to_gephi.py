import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import networkx as nx
import networkx.algorithms.community as nx_comm
from collections import Counter

from recommender import construir_grafo, carregar_titulos_jogos

def carregar_metadados(caminho_json):
    """Carrega tags e generos de cada jogo."""
    metadados = {}
    if not os.path.exists(caminho_json):
        return metadados
    with open(caminho_json, mode='r', encoding='utf-8') as f:
        for linha in f:
            dados = json.loads(linha.strip())
            app_id = str(dados.get('app_id', ''))
            metadados[app_id] = {
                'tags': dados.get('tags', []),
                'genres': dados.get('genres', [])
            }
    return metadados

def exportar_para_gephi_hibrido(seed):
    print("=" * 65)
    print(f"EXPORTAÇÃO PARA GEPHI (SISTEMA HÍBRIDO COM LOUVAIN - SEED {seed})")
    print("=" * 65)

    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, '..'))
    ARQUIVO_AMOSTRA = os.path.join(PROJECT_ROOT, 'extracted_data', 'sampled_recommendations.csv')
    ARQUIVO_GAMES = os.path.join(PROJECT_ROOT, 'extracted_data', 'games.csv')
    ARQUIVO_JSON = os.path.join(PROJECT_ROOT, 'extracted_data', 'games_metadata.json')
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Carrega estruturas básicas
    print("\n[1/5] Carregando títulos, metadados e construindo o grafo...")
    dicionario_titulos = carregar_titulos_jogos(ARQUIVO_GAMES)
    dicionario_meta = carregar_metadados(ARQUIVO_JSON)
    G = construir_grafo(ARQUIVO_AMOSTRA)

    if not G:
        print("Erro: Não foi possível construir o grafo.")
        return

    # 2. Executa Louvain com a semente configurada
    print(f"\n[2/5] Executando Algoritmo de Louvain (seed = {seed})...")
    lista_comunidades = nx_comm.louvain_communities(G, weight='weight', seed=seed)
    total_comunidades = len(lista_comunidades)
    print(f" -> Sucesso: {total_comunidades} comunidades (Super Nós) identificadas!")

    # Mapeia cada nó para seu ID de comunidade
    no_para_comunidade = {}
    for id_comunidade, grupo_de_nos in enumerate(lista_comunidades):
        for no in grupo_de_nos:
            no_para_comunidade[no] = id_comunidade

    caminho_cache_json = os.path.join(OUTPUT_DIR, "comunidades_louvain.json")
    with open(caminho_cache_json, 'w', encoding='utf-8') as f_cache:
        json.dump(no_para_comunidade, f_cache)
    print(f" -> Cache de comunidades salvo em '{caminho_cache_json}'.")

    # 3. Injeta atributos ricos em cada nó para visualização e agrupamento no Gephi
    print("\n[3/5] Injetando atributos nos nós (Labels, Comunidade, Tipo e Gêneros)...")
    jogos_por_comunidade = {i: [] for i in range(total_comunidades)}

    for node_id, dados_do_no in G.nodes(data=True):
        comm_id = no_para_comunidade.get(node_id, -1)
        dados_do_no['community'] = int(comm_id)

        if dados_do_no.get('tipo') == 'jogo':
            app_id = dados_do_no.get('nome_original')
            nome_real = dicionario_titulos.get(app_id, f"Jogo {app_id}")
            dados_do_no['label'] = nome_real

            meta = dicionario_meta.get(app_id, {})
            generos = meta.get('genres', [])
            tags = meta.get('tags', [])

            dados_do_no['genres'] = ", ".join(generos) if generos else "Desconhecido"
            dados_do_no['top_tags'] = ", ".join(tags[:5]) if tags else "Nenhuma"
            dados_do_no['categoria_no'] = "Jogo"

            jogos_por_comunidade[comm_id].append((G.degree(node_id, weight='weight'), nome_real, generos))
        else:
            user_id = dados_do_no.get('nome_original')
            dados_do_no['label'] = f"Usuário {user_id}"
            dados_do_no['genres'] = "N/A"
            dados_do_no['top_tags'] = "N/A"
            dados_do_no['categoria_no'] = "Usuario"

    # 4. Exporta o Grafo Completo Híbrido
    arquivo_completo = os.path.join(OUTPUT_DIR, "universo_steam_hibrido.gexf")
    print(f"\n[4/5] Salvando '{arquivo_completo}'...")
    nx.write_gexf(G, arquivo_completo)
    print(f" -> Arquivo '{arquivo_completo}' gerado com sucesso!")

    # 5. Constrói e Exporta o Meta-Grafo de Super Nós (Visão Macro de Alto Nível)
    print("\n[5/5] Construindo o Meta-Grafo dos Super Nós (Visão Macro)...")
    MetaG = nx.Graph()

    for comm_id in range(total_comunidades):
        jogos_comm = jogos_por_comunidade[comm_id]
        jogos_comm.sort(reverse=True, key=lambda x: x[0])  # Ordena pelos mais populares

        exemplos = [j[1] for j in jogos_comm[:4]]
        generos_contagem = Counter([g for j in jogos_comm for g in j[2]])
        genero_dominante = generos_contagem.most_common(1)[0][0] if generos_contagem else "Variado"

        qtd_jogos = len(jogos_comm)
        qtd_total = len(lista_comunidades[comm_id])

        label_super_no = f"Super Nó {comm_id}: {genero_dominante} ({qtd_jogos} jogos)"
        MetaG.add_node(
            f"super_no_{comm_id}",
            label=label_super_no,
            comunidade=int(comm_id),
            genero_principal=genero_dominante,
            qtd_jogos=int(qtd_jogos),
            qtd_total_membros=int(qtd_total),
            exemplos=", ".join(exemplos)
        )

    # Arestas entre super nós: número de conexões cruzadas
    pesos_inter_comunidades = Counter()
    for u, v, dados in G.edges(data=True):
        comm_u = no_para_comunidade.get(u)
        comm_v = no_para_comunidade.get(v)
        if comm_u is not None and comm_v is not None and comm_u != comm_v:
            par = tuple(sorted([comm_u, comm_v]))
            pesos_inter_comunidades[par] += dados.get('weight', 1.0)

    for (c1, c2), peso in pesos_inter_comunidades.items():
        MetaG.add_edge(f"super_no_{c1}", f"super_no_{c2}", weight=float(peso))

    arquivo_super_nos = os.path.join(OUTPUT_DIR, "universo_super_nos.gexf")
    nx.write_gexf(MetaG, arquivo_super_nos)
    print(f" -> Arquivo '{arquivo_super_nos}' gerado com sucesso!")

    print("\n" + "=" * 65)
    print("RESUMO DOS ARQUIVOS GERADOS:")
    print(f"1. '{arquivo_completo}': Grafo completo pronto para colorir por 'community' e agrupar.")
    print(f"2. '{arquivo_super_nos}': Meta-Grafo de Super Nós mostrando a conexão macro entre os 7 clusters.")
    print("=" * 65)

if __name__ == "__main__":
    exportar_para_gephi_hibrido(seed=16)
