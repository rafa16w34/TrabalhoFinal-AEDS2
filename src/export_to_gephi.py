"""
Módulo de Exportação para o Gephi
Trabalho Final AEDS 2 - CEFET-MG / UFC-IMG
Autores: Rafael Alves Faria e Gabriel Alves Faria

Gera visualizações em rede estruturadas e elegantes inspiradas na Figura 2 do artigo
clássico do Algoritmo de Louvain:
"Fast unfolding of communities in large networks" (Blondel et al., 2008, pág. 9).

Arquivos gerados:
1. 'output/universo_super_nos.gexf':
   Rede de comunidades e sub-comunidades (análogo direto à Figura 2 do artigo).
   Nós representam sub-comunidades, com tamanho proporcional ao volume de membros
   e cores mapeadas para os 7 Super-Nós.
2. 'output/universo_steam_hibrido.gexf':
   Universo organizado dos jogos (projeção monopartite de alta coesão sem ruído de 152k usuários),
   com nós de jogos estilizados e pré-agrupados por comunidade no espaço 2D.
"""

import os
import sys
import json
import math
import random
from collections import Counter, defaultdict

# Garante acesso aos módulos em src/
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(src_dir, '..'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import networkx as nx
import networkx.algorithms.community as nx_comm
import main

# Paleta cromática oficial inspirada no artigo de Louvain (Blondel et al., Figura 2)
# Destaque para o contraste Vermelho (JRPG/Ação) vs Verde (Indies) e nós intermediários
CORES_SUPER_NOS = {
    0: {"r": 46,  "g": 213, "b": 115, "hex": "#2ed573", "nome": "Indie & Roguelike 2D"},            # Verde Esmeralda
    1: {"r": 30,  "g": 144, "b": 255, "hex": "#1e90ff", "nome": "Aventura Narrativa & Puzzle"},      # Azul Real
    2: {"r": 155, "g": 89,  "b": 182, "hex": "#9b59b6", "nome": "Estratégia & Simulação Tática"},    # Roxo Ametista
    3: {"r": 255, "g": 165, "b": 2,   "hex": "#ffa502", "nome": "FPS Clássico & Ação Retrô"},         # Âmbar / Laranja
    4: {"r": 255, "g": 71,  "b": 87,  "hex": "#ff4757", "nome": "JRPG & RPG Narrativo / Anime"},     # Vermelho Carmesim
    5: {"r": 241, "g": 196, "b": 15,  "hex": "#f1c40f", "nome": "Simulação, Direção & Mundo Aberto"}, # Ouro / Amarelo
    6: {"r": 26,  "g": 188, "b": 156, "hex": "#1abc9c", "nome": "Expansões & Comunidades Emergentes"} # Turquesa
}

def exportar_para_gephi_hibrido(seed=16, grafo=None, titulos=None, metadados=None, comunidades=None):
    """
    Gera os arquivos GEXF estruturados e visualmente limpos para o Gephi.
    """
    print("=" * 68)
    print(" EXPORTAÇÃO GEPHI: REDES ESTRUTURADAS DE COMUNIDADES (BLONDEL ET AL.)")
    print("=" * 68)

    output_dir = os.path.join(project_root, 'output')
    os.makedirs(output_dir, exist_ok=True)

    # 1. Carrega estruturas caso não tenham sido passadas em memória
    if grafo is None or titulos is None or metadados is None or comunidades is None:
        print("\n[1/4] Inicializando grafo limpo e metadados...")
        grafo, titulos, metadados, comunidades = main.inicializacao()
    else:
        print("\n[1/4] Utilizando grafo e comunidades já carregados em memória.")

    jogos_nos = [n for n in grafo.nodes() if n.startswith("game_")]
    print(f" -> Catálogo disponível no grafo limpo: {len(jogos_nos)} jogos.")

    # 2. Constrói projeção co-play entre os jogos (eliminando o ruído de 152k usuários)
    print("\n[2/4] Calculando Projeção Co-Play com Validação Social entre jogos...")
    # Pega top 30 usuários mais engajados de cada jogo para filtrar ruído
    jogo_top_u = {}
    for g in jogos_nos:
        viz = grafo[g]
        top_u = sorted(viz.items(), key=lambda x: x[1]['weight'], reverse=True)[:30]
        jogo_top_u[g] = {u: d['weight'] for u, d in top_u}

    G_jogos = nx.Graph()
    for g in jogos_nos:
        aid = g.replace("game_", "")
        cid = comunidades.get(g, -1)
        meta = metadados.get(aid, {})
        grau_bipartido = grafo.degree(g)
        G_jogos.add_node(
            g,
            app_id=aid,
            label=titulos.get(aid, f"Jogo {aid}"),
            community=int(cid),
            community_name=CORES_SUPER_NOS.get(cid, {}).get("nome", f"Comunidade {cid}"),
            genres=", ".join(meta.get('genres', [])) if meta.get('genres') else "Variado",
            positive_ratio=float(meta.get('positive_ratio', 80.0)),
            grau_popularidade=int(grau_bipartido)
        )

    # Agrega arestas de co-play com pesos
    arestas_brutas = Counter()
    for g, u_dict in jogo_top_u.items():
        for u, w_ug in u_dict.items():
            for outro_g, d in grafo[u].items():
                if outro_g != g and outro_g.startswith("game_"):
                    par = tuple(sorted([g, outro_g]))
                    arestas_brutas[par] += w_ug * d['weight']

    # Filtra arestas para manter apenas a espinha dorsal (Backbone) limpa
    # Cada jogo mantém suas conexões mais expressivas (k=8), evitando o "hairball" preto
    conexoes_por_jogo = defaultdict(list)
    for (g1, g2), peso in arestas_brutas.items():
        conexoes_por_jogo[g1].append((g2, peso))
        conexoes_por_jogo[g2].append((g1, peso))

    arestas_backbone = set()
    for g, lista in conexoes_por_jogo.items():
        lista.sort(key=lambda x: x[1], reverse=True)
        for outro_g, peso in lista[:8]: # Mantém os 8 parceiros mais fortes
            par = tuple(sorted([g, outro_g]))
            arestas_backbone.add((par[0], par[1], peso))

    for g1, g2, peso in arestas_backbone:
        G_jogos.add_edge(g1, g2, weight=round(float(peso), 2))

    print(f" -> Grafo de Jogos limpo: {G_jogos.number_of_nodes()} nós e {G_jogos.number_of_edges()} arestas (Backbone Coeso).")

    # 3. Detecta Sub-Comunidades dentro de cada Super-Nó para montar a Figura 2 de Blondel et al.
    print("\n[3/4] Construindo Rede de Comunidades e Sub-Comunidades (Figura 2 do Artigo)...")
    MetaG = nx.Graph()
    random.seed(seed)

    # Centros orbitais das 7 macro-comunidades em coordenadas 2D (escala Gephi)
    raio_macro = 3200.0
    centros_comunidades = {}
    for cid in range(7):
        angulo = (2.0 * math.pi * cid) / 7.0
        centros_comunidades[cid] = (raio_macro * math.cos(angulo), raio_macro * math.sin(angulo))

    sub_comunidades_lista = []
    sub_id_counter = 0

    for cid in range(7):
        nos_cid = [n for n in jogos_nos if comunidades.get(n) == cid]
        if not nos_cid:
            continue

        subg = G_jogos.subgraph(nos_cid)
        # Executa Louvain interno dentro de cada Super-Nó
        try:
            comms_internas = nx_comm.louvain_communities(subg, weight='weight', seed=seed)
        except Exception:
            comms_internas = [set(nos_cid)]

        # Agrupa os nós pequenos em sub-comunidades significativas (>= 3 jogos)
        for grupo in comms_internas:
            if len(grupo) >= 3:
                sub_id = f"subcomm_{sub_id_counter}"
                sub_id_counter += 1
                sub_comunidades_lista.append({
                    "id": sub_id,
                    "macro_cid": cid,
                    "jogos": list(grupo)
                })

    # Mapeia cada jogo para a sua sub-comunidade
    jogo_para_subcomm = {}
    for sub in sub_comunidades_lista:
        for g in sub["jogos"]:
            jogo_para_subcomm[g] = sub["id"]

    # Adiciona nós das Sub-Comunidades no Meta-Grafo
    for sub in sub_comunidades_lista:
        sub_id = sub["id"]
        cid = sub["macro_cid"]
        jogos = sub["jogos"]
        cor = CORES_SUPER_NOS.get(cid, {"r": 200, "g": 200, "b": 200})

        # Identifica os jogos mais populares desta sub-comunidade
        jogos_ordenados = sorted(jogos, key=lambda g: grafo.degree(g), reverse=True)
        top_nomes = [titulos.get(g.replace("game_", "")) for g in jogos_ordenados[:2] if titulos.get(g.replace("game_", ""))]
        exemplos_str = " & ".join(top_nomes) if top_nomes else f"Cluster {sub_id}"

        # Gênero mais frequente
        generos_cluster = Counter()
        volume_total = 0
        for g in jogos:
            aid = g.replace("game_", "")
            volume_total += grafo.degree(g)
            for gen in metadados.get(aid, {}).get("genres", []):
                generos_cluster[gen] += 1
        gen_dominante = generos_cluster.most_common(1)[0][0] if generos_cluster else "Indie/Ação"

        label_sub = f"{gen_dominante}: {exemplos_str}"

        # Posição pré-calculada orbitando o centro da sua macro-comunidade
        cx, cy = centros_comunidades[cid]
        r_dist = random.uniform(80.0, 750.0)
        phi = random.uniform(0.0, 2.0 * math.pi)
        pos_x = cx + r_dist * math.cos(phi)
        pos_y = cy + r_dist * math.sin(phi)

        # Tamanho proporcional ao volume de jogadores (análogo à Figura 2)
        tam = max(18.0, min(85.0, math.sqrt(len(jogos)) * 7.5))

        MetaG.add_node(
            sub_id,
            label=label_sub,
            macro_comunidade=int(cid),
            super_no_nome=CORES_SUPER_NOS.get(cid, {}).get("nome", ""),
            genero_dominante=gen_dominante,
            qtd_jogos=int(len(jogos)),
            volume_avaliacoes=int(volume_total),
            exemplos=exemplos_str,
            viz={
                "color": {"r": cor["r"], "g": cor["g"], "b": cor["b"], "a": 1.0},
                "size": float(tam),
                "position": {"x": round(pos_x, 2), "y": round(pos_y, 2), "z": 0.0}
            }
        )

    # Conecta as sub-comunidades somando os pesos das arestas de jogos entre elas
    pesos_entre_subcomms = Counter()
    for g1, g2, d in G_jogos.edges(data=True):
        s1 = jogo_para_subcomm.get(g1)
        s2 = jogo_para_subcomm.get(g2)
        if s1 and s2 and s1 != s2:
            par = tuple(sorted([s1, s2]))
            pesos_entre_subcomms[par] += d.get('weight', 1.0)

    # Filtra arestas fracas para deixar o layout tão limpo quanto a Figura 2
    if pesos_entre_subcomms:
        corte_peso = max(1.0, sorted(pesos_entre_subcomms.values(), reverse=True)[min(len(pesos_entre_subcomms)-1, 350)])
        for (s1, s2), peso in pesos_entre_subcomms.items():
            if peso >= corte_peso:
                MetaG.add_edge(s1, s2, weight=round(float(peso), 2))

    # 4. Prepara Atributos Visuais no Grafo dos Jogos (universo_steam_hibrido.gexf)
    print("\n[4/4] Injetando coordenadas pré-calculadas e paleta visual nos jogos...")
    for n, d in G_jogos.nodes(data=True):
        cid = d.get('community', 0)
        cor = CORES_SUPER_NOS.get(cid, {"r": 180, "g": 180, "b": 180})
        grau = d.get('grau_popularidade', 50)

        # Tamanho logarítmico calibrado
        tam_no = max(12.0, min(75.0, math.log10(max(10, grau)) * 16.0))

        # Posição 2D pré-agrupada em torno da comunidade
        cx, cy = centros_comunidades.get(cid, (0.0, 0.0))
        r_dist = random.uniform(60.0, 950.0)
        phi = random.uniform(0.0, 2.0 * math.pi)
        px = cx + r_dist * math.cos(phi)
        py = cy + r_dist * math.sin(phi)

        d['viz'] = {
            "color": {"r": cor["r"], "g": cor["g"], "b": cor["b"], "a": 1.0},
            "size": float(tam_no),
            "position": {"x": round(px, 2), "y": round(py, 2), "z": 0.0}
        }

    # Salva os dois arquivos GEXF limpos
    caminho_super_nos = os.path.join(output_dir, "universo_super_nos.gexf")
    caminho_jogos = os.path.join(output_dir, "universo_steam_hibrido.gexf")

    print(f"\n -> Gravando '{os.path.basename(caminho_super_nos)}'...")
    nx.write_gexf(MetaG, caminho_super_nos)

    print(f" -> Gravando '{os.path.basename(caminho_jogos)}'...")
    nx.write_gexf(G_jogos, caminho_jogos)

    print("\n" + "=" * 68)
    print(" EXPORTAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 68)
    print(f"1. '{caminho_super_nos}':")
    print(f"   -> {MetaG.number_of_nodes()} sub-comunidades e {MetaG.number_of_edges()} arestas.")
    print("   -> Idêntico à Figura 2 do artigo de Louvain (Blondel et al., 2008).")
    print(f"2. '{caminho_jogos}':")
    print(f"   -> {G_jogos.number_of_nodes()} jogos e {G_jogos.number_of_edges()} arestas (Backbone organizado).")
    print("   -> Cores RGB e coordenadas espaciais já injetadas no arquivo XML.")
    print("=" * 68)

if __name__ == "__main__":
    exportar_para_gephi_hibrido()
