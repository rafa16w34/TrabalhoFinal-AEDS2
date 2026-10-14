import networkx as nx
import csv
import math
import os
import hashlib

import json

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

# Adicione estas variáveis globais logo antes da função carregar_tags_jogos
IDF_TABLE = {}
TOTAL_DOCS = 0

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def carregar_tags_jogos(caminho_json):
    """
    Lê o arquivo JSON do banco de dados, mapeia tags/gêneros e pré-calcula a tabela TF-IDF.
    """
    global IDF_TABLE, TOTAL_DOCS
    metadados = {}
    if not os.path.exists(caminho_json):
        return metadados

    doc_frequencies = {}
    TOTAL_DOCS = 0

    with open(caminho_json, mode='r', encoding='utf-8') as f:
        for linha in f:
            dados = json.loads(linha.strip())
            app_id = str(dados.get('app_id',''))
            
            tags = set(dados.get('tags',[]))
            genres = set(dados.get('genres',[]))
            metadados[app_id] = {'tags': tags, 'genres': genres}
            
            # Contabiliza frequências para o cálculo IDF
            for t in tags:
                k = f"tag_{t.strip().lower()}"
                doc_frequencies[k] = doc_frequencies.get(k, 0) + 1
            for g in genres:
                k = f"gen_{g.strip().lower()}"
                doc_frequencies[k] = doc_frequencies.get(k, 0) + 1
            
            TOTAL_DOCS += 1

    # Pré-computa e armazena os valores de IDF globalmente
    for termo, freq in doc_frequencies.items():
        IDF_TABLE[termo] = math.log((1 + TOTAL_DOCS) / (1 + freq)) + 1.0

    return metadados

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def jaccard(meta_a, meta_b, peso_genre = 1.5, peso_tag = 1.0):
    """
    Cálculo de similaridade Weighted Jaccard com TF-IDF usando a tabela global.
    """
    global IDF_TABLE

    tags_a = {f"tag_{t.strip().lower()}" for t in meta_a.get('tags', set()) if t}
    tags_b = {f"tag_{t.strip().lower()}" for t in meta_b.get('tags', set()) if t}
    gen_a = {f"gen_{g.strip().lower()}" for g in meta_a.get('genres', set()) if g}
    gen_b = {f"gen_{g.strip().lower()}" for g in meta_b.get('genres', set()) if g}

    tokens_a = tags_a | gen_a
    tokens_b = tags_b | gen_b

    if not tokens_a or not tokens_b:
        return 0.0

    intersecao = tokens_a.intersection(tokens_b)
    uniao = tokens_a.union(tokens_b)

    if not intersecao:
        return 0.0

    soma_intersecao = 0.0
    soma_uniao = 0.0

    for token in uniao:
        # Multiplicador estrutural de prioridade
        multiplicador = peso_genre if token.startswith("gen_") else peso_tag
        peso_final = multiplicador * IDF_TABLE.get(token, 1.0)

        soma_uniao += peso_final
        if token in intersecao:
            soma_intersecao += peso_final

    return soma_intersecao / soma_uniao if soma_uniao > 0 else 0.0
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

             # O Filtro de Bloom barra o próprio jogo alvo, para não recomendar ele mesmo
            if visitados.possivelmente_contem(node_jogo):
                continue
            
#------------------------------------------------------------------------------------------------------------------------------------------------------------------

            score_colaborativo = peso_usuario * dados_aresta_destino['weight']

            id_limpo = node_jogo.replace("game_","")

            bonus_louvain = 1.0
            if comunidades.get(node_alvo) == comunidades.get(node_jogo):
                bonus_louvain = 3.0


            meta_alvo = dicionario_tags.get(jogo_alvo_id, {})
            meta_recomendado = dicionario_tags.get(id_limpo, {})

            fator_jaccard = jaccard(meta_alvo, meta_recomendado)

            if fator_jaccard < 0.2: 
                continue

            score_final = score_colaborativo * bonus_louvain * (fator_jaccard + 0.1)

            #Acumula pontuação para cada user que recomenda o jogo
            if node_jogo not in pontuacao_jogos:
                pontuacao_jogos[node_jogo] = 0
            pontuacao_jogos[node_jogo] += score_final

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

    recomendacoes_ordenadas = sorted(
        pontuacao_jogos.items(), 
        key=lambda item: item[1], 
        reverse=True
    )

    return recomendacoes_ordenadas[:top_n_jogos], top_usuarios

#------------------------------------------------------------------------------------------------------------------------------------------------------------------