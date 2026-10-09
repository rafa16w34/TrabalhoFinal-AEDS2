import networkx as nx
import csv
import math
import os
import hashlib
from networkx.drawing.nx_pydot import write_dot

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


def recomendar_jogos(G, jogo_alvo_id, top_k_users=50, top_n_jogos=10):
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
            
            peso_jogo = dados_aresta_destino['weight']
            score = peso_usuario * peso_jogo
            
            if node_jogo not in pontuacao_jogos:
                pontuacao_jogos[node_jogo] = 0
            pontuacao_jogos[node_jogo] += score
            
            visitados.adicionar(node_jogo)

    recomendacoes_ordenadas = sorted(
        pontuacao_jogos.items(), 
        key=lambda item: item[1], 
        reverse=True
    )

    return recomendacoes_ordenadas[:top_n_jogos], top_usuarios


def gerar_arquivo_dot(G, jogo_alvo_id, top_usuarios, recomendacoes, dicionario_titulos):#Apenas da recomendação
    """
    Gera um Subgrafo contendo apenas a pesquisa atual e exporta para o Graphviz (.dot).
    """
    print("\nGerando arquivo .dot para o Graphviz...")
    subgrafo = nx.Graph()
    
    node_alvo = f"game_{jogo_alvo_id}"
    titulo_alvo = dicionario_titulos.get(jogo_alvo_id, f"ID: {jogo_alvo_id}")
    
    # 1. Adiciona o Jogo Pesquisado (Centro)
    subgrafo.add_node(node_alvo, label=f'"{titulo_alvo}"', color="red", style="filled", shape="box")
    
    # 2. Adiciona os Usuários Fortes e liga eles ao jogo alvo
    for node_user, _ in top_usuarios:
        subgrafo.add_node(node_user, label="Usuário", color="lightblue", style="filled", shape="circle")
        subgrafo.add_edge(node_alvo, node_user)
        
    # 3. Adiciona os Jogos Recomendados e liga os usuários a eles
    for jogo_id, _ in recomendacoes:
        id_limpo = jogo_id.replace("game_", "")
        titulo = dicionario_titulos.get(id_limpo, f"ID: {id_limpo}")
        subgrafo.add_node(jogo_id, label=f'"{titulo}"', color="lightgreen", style="filled", shape="box")
        
        # Procura quais dos Top Users jogaram o jogo recomendado
        for node_user, _ in top_usuarios:
            if G.has_edge(node_user, jogo_id):
                subgrafo.add_edge(node_user, jogo_id)

    # 4. Salva no disco
    write_dot(subgrafo, "recomendacoes_graphviz.dot")
    print("Arquivo 'recomendacoes_graphviz.dot' gerado com sucesso na raiz do projeto!")


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ARQUIVO_AMOSTRA = os.path.join(BASE_DIR, 'extracted_data', 'sampled_recommendations.csv')
    ARQUIVO_GAMES = os.path.join(BASE_DIR, 'extracted_data', 'games.csv')

    # Carrega os títulos dos jogos antes de rodar o grafo
    dicionario_titulos = carregar_titulos_jogos(ARQUIVO_GAMES)

    # Constrói a estrutura
    grafo = construir_grafo(ARQUIVO_AMOSTRA)

    if grafo:
        JOGO_PESQUISA = "271590" # GTA V
        titulo_pesquisa = dicionario_titulos.get(JOGO_PESQUISA, JOGO_PESQUISA)
        print(f"\nAlvo da Pesquisa: {titulo_pesquisa}")
        
        # Agora a função retorna as recomendações E a lista de usuários top (para podermos desenhar)
        resultado, top_users = recomendar_jogos(grafo, JOGO_PESQUISA, top_k_users=50, top_n_jogos=10)
        
        print(f"\n--- TOP 10 RECOMENDAÇÕES (Otimizadas com Bloom Filter) ---")
        for i, (jogo_id, score) in enumerate(resultado):
            id_limpo = jogo_id.replace("game_", "")
            titulo = dicionario_titulos.get(id_limpo, "Nome Desconhecido")
            print(f"{i+1}º Lugar - {titulo} | Score: {score:.2f}")

        # Chama a função para exportar o grafo para o Graphviz
        gerar_arquivo_dot(grafo, JOGO_PESQUISA, top_users, resultado, dicionario_titulos)