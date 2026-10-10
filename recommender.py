import networkx as nx
import csv
import math
import os
import hashlib

import json
import networkx.algorithms.community as nx_comm

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

class BloomFilter:
    """
    Filtro de Bloom para gerenciar nós visitados na BFS de forma otimizada.
    """
    def __init__(self, estimativa_elementos, probabilidade_falso_positivo=0.01):
        numerador = -(estimativa_elementos * math.log(probabilidade_falso_positivo))
        denominador = (math.log(2) ** 2)
        self.tamanho_bit_array = int(numerador / denominador)
        self.qtd_hashes = int((self.tamanho_bit_array / estimativa_elementos) * math.log(2))
        self.bit_array = [False] * self.tamanho_bit_array
        print(f"[Bloom Filter] Criado com {self.tamanho_bit_array} bits e {self.qtd_hashes} hashes.")

    def _gerar_hashes(self, item):
        posicoes = []
        hash_base = int(hashlib.md5(item.encode('utf-8')).hexdigest(), 16)
        for i in range(self.qtd_hashes):
            pos = (hash_base + (i * 987654321)) % self.tamanho_bit_array
            posicoes.append(pos)
        return posicoes

    def adicionar(self, item):
        for posicao in self._gerar_hashes(item):
            self.bit_array[posicao] = True

    def possivelmente_contem(self, item):
        for posicao in self._gerar_hashes(item):
            if not self.bit_array[posicao]:
                return False
        return True

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def carregar_titulos_jogos(caminho_csv):
    """
    Lê o arquivo games.csv e retorna um dicionário mapeando ID -> Título.
    """
    titulos = {}
    if not os.path.exists(caminho_csv):
        print(f"Aviso: {caminho_csv} não encontrado. Nomes dos jogos não serão exibidos.")
        return titulos

    with open(caminho_csv, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            titulos[row.get('app_id', '')] = row.get('title', 'Desconhecido')
            
    return titulos

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def carregar_tags_jogos(caminho_json):
    """
    Lê o arquivo JSON do banco de dados e mapeia:
    app(id) -> conjunto de tags
    """

    tags_jogo = {}
    if not os.path.exists(caminho_json):
        return tags_jogo

    with open(caminho_json, mode='r', encoding='utf-8') as f:

        for linha in f:
            dados = json.loads(linha.strip())
            app_id = str(dados.get('app_id',''))

            lista_tags = dados.get('tags', [])
            tags_jogo[app_id] = set(lista_tags)

    return tags_jogo

def jaccard(tags_jogo_a,tags_jogos_b):
    """
    Calculo simples de similaridade de Jaccard (0.00 ou 1.00)
    """

    if not  tags_jogo_a or not tags_jogos_b: #Se não houverem tags cadastradas, devo avaliar o banco de dados para confirmar se existe essa possibilidade
        return 0.1

    intercessao = len(tags_jogo_a.intersection(tags_jogos_b))
    uniao = len(tags_jogo_a.union(tags_jogos_b))

    return (intercessao/uniao)

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def construir_grafo(caminho_csv):
    """Constrói o grafo bipartido de Usuários e Jogos a partir do CSV"""
    if not os.path.exists(caminho_csv):
        print(f"ERRO: O arquivo {caminho_csv} não existe.")
        return None

    G = nx.Graph()
    print("Carregando o K-Core do CSV para a memória... Isso pode levar um instante.")

    linhas_lidas = 0
    with open(caminho_csv, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            linhas_lidas += 1
            if linhas_lidas % 1000000 == 0:
                print(f"   -> Adicionando ao grafo: {linhas_lidas} conexões processadas...")
                
            app_id = row.get('app_id')
            user_id = row.get('user_id')
            hours_str = row.get('hours', '0')
            
            try:
                hours = float(hours_str) if hours_str else 0.0
            except ValueError:
                continue

            if not app_id or not user_id:
                continue

            node_jogo = f"game_{app_id}"
            node_user = f"user_{user_id}"
            peso = math.log(1 + hours)

            # Salvando o app_id como atributo do nó para facilitar no graphviz
            G.add_node(node_jogo, tipo='jogo', nome_original=app_id)
            G.add_node(node_user, tipo='usuario', nome_original=user_id)
            G.add_edge(node_jogo, node_user, weight=peso)

    print(f"Grafo construído! Vértices: {G.number_of_nodes()} | Arestas: {G.number_of_edges()}")
    return G

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def recomendar_jogos(G, jogo_alvo_id, comunidades, dicionario_tags, top_k_users=50, top_n_jogos=10):
    """
    Busca em Largura (BFS) utilizando Filtro de Bloom para gerenciar os visitados.
    Retorna também os top_usuarios para podermos desenhar o Graphviz.
    """
    node_alvo = f"game_{jogo_alvo_id}"
    if node_alvo not in G:
        print(f"O jogo {jogo_alvo_id} não foi encontrado no Grafo.")
        return [], []

    print(f"\nIniciando Busca em Largura (BFS) para o alvo: {jogo_alvo_id}...")

    visitados = BloomFilter(estimativa_elementos=100000, probabilidade_falso_positivo=0.01)
    visitados.adicionar(node_alvo)

    # NÍVEL 1: Encontrar os Top Usuários
    usuarios_vizinhos = G[node_alvo]
    usuarios_ordenados = sorted(
        usuarios_vizinhos.items(), 
        key=lambda x: x[1]['weight'], 
        reverse=True
    )
    top_usuarios = usuarios_ordenados[:top_k_users]

    pontuacao_jogos = {}

    # NÍVEL 2: Expandir para os Jogos recomendados
    for node_user, dados_aresta_origem in top_usuarios:
        peso_usuario = dados_aresta_origem['weight']
        jogos_do_usuario = G[node_user]
        
        for node_jogo, dados_aresta_destino in jogos_do_usuario.items():
            
            if visitados.possivelmente_contem(node_jogo):
                continue
            
#------------------------------------------------------------------------------------------------------------------------------------------------------------------

            score_colaborativo = peso_usuario * dados_aresta_destino['weight']

            id_limpo = node_jogo.replace("game_","")

            bonus_louvain = 1.0
            if comunidades.get(node_alvo) == comunidades.get(node_jogo):
                bonus_louvain = 3.0


            tags_alvo = dicionario_tags.get(jogo_alvo_id, set())
            tags_recomendado = dicionario_tags.get(id_limpo,set())

            fator_jaccard = jaccard(tags_alvo, tags_recomendado)

            if fator_jaccard < 0.2: continue

            score_final = score_colaborativo * bonus_louvain * (fator_jaccard + 0.1)

            if node_jogo not in pontuacao_jogos:
                pontuacao_jogos[node_jogo] = 0
            pontuacao_jogos[node_jogo] += score_final

#------------------------------------------------------------------------------------------------------------------------------------------------------------------
            
            visitados.adicionar(node_jogo)

    recomendacoes_ordenadas = sorted(
        pontuacao_jogos.items(), 
        key=lambda item: item[1], 
        reverse=True
    )

    return recomendacoes_ordenadas[:top_n_jogos], top_usuarios

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ARQUIVO_AMOSTRA = os.path.join(BASE_DIR, 'extracted_data', 'sampled_recommendations.csv')
    ARQUIVO_GAMES = os.path.join(BASE_DIR, 'extracted_data', 'games.csv')
    ARQUIVO_JSON = os.path.join(BASE_DIR, 'extracted_data', 'games_metadata.json')

    # Carrega os títulos dos jogos antes de rodar o grafo
    dicionario_titulos = carregar_titulos_jogos(ARQUIVO_GAMES)

    # Constrói a estrutura
    grafo = construir_grafo(ARQUIVO_AMOSTRA)

    dicionario_tags = carregar_tags_jogos(ARQUIVO_JSON)

    print("\nExecutando Algoritmo de Louvain...")
    lista_comunidades = nx_comm.louvain_communities(grafo, weight='weight')
    
    # Transforma a lista de grupos em um dicionário rápido (nó -> ID da comunidade)
    dicionario_comunidades = {}
    for id_comunidade, grupo_de_nos in enumerate(lista_comunidades):
        for no in grupo_de_nos:
            dicionario_comunidades[no] = id_comunidade
    print(f"Louvain finalizado! Foram encontradas {len(lista_comunidades)} comunidades (Super Nós).")

    if grafo:
        #JOGO_PESQUISA = "271590" # GTA V
        JOGO_PESQUISA = "304240" # Resident Evil HD Remaster
        titulo_pesquisa = dicionario_titulos.get(JOGO_PESQUISA, JOGO_PESQUISA)
        print(f"\nAlvo da Pesquisa: {titulo_pesquisa}")
        
        # Agora a função retorna as recomendações E a lista de usuários top (para podermos desenhar)
        resultado, top_users = recomendar_jogos(grafo, JOGO_PESQUISA, dicionario_comunidades, dicionario_tags , top_k_users=50, top_n_jogos=10)
        
        print(f"\n--- TOP 10 RECOMENDAÇÕES (Otimizadas com Bloom Filter) ---")
        for i, (jogo_id, score) in enumerate(resultado):
            id_limpo = jogo_id.replace("game_", "")
            titulo = dicionario_titulos.get(id_limpo, "Nome Desconhecido")
            print(f"{i+1}º Lugar - {titulo} | Score: {score:.2f}")
