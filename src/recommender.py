import networkx as nx
import csv
import math
import os
import json
import re
import unicodedata

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

IDF_TABLE = {}
TOTAL_DOCS = 0

TAGS_MATURE = {'mature', 'crime', 'violent', 'violence', 'gore', 'sexual content', 'nudity', 'nsfw', 'hentai', 'blood'}
TAGS_FAMILIA = {'family friendly', 'kids'}

SUFIXOS_DEV = r'\b(inc|llc|ltd|limited|co|corp|corporation|gmbh|s\.?a|s\.?r\.?l|plc|k\.?k|games|game|studios|studio|software|softworks|entertainment|interactive|productions|development|digital|media|north|south|west|east|montreal|toronto|kiev|shanghai|paris|annecy|sofia|bucharest|quebec|usa|japan|uk|online|works)\b\.?'
PREFIXOS_DEV = r'^(and|in collaboration with|a)\s+'

def chave_developer(nome):
    """
    Normaliza o nome do estúdio de forma puramente algorítmica:
    - Descarta ports técnicos de Mac/Linux que geram afinidades falsas.
    - Poda em laço termos societários, filiais e termos genéricos de estúdio.
    """
    if re.search(r'\((mac|linux|pc|remastered)', nome, re.I):
        return ""
    nome = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode()
    nome = nome.lower().replace(',', ' ')
    nome = re.sub(r'[^\w\s]', ' ', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    nome = re.sub(PREFIXOS_DEV, '', nome).strip()

    while True:
        novo = re.sub(r'\s+' + SUFIXOS_DEV + r'$', '', nome).strip()
        if novo and novo != nome:
            nome = novo
        else:
            break
    return nome

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def carregar_tags_jogos(caminho_json, caminho_games=None):
    """
    Lê o arquivo JSON do banco de dados, mapeia tags/gêneros e pré-calcula a tabela TF-IDF.
    Opcionalmente recebe caminho_games (games.csv) para acoplar a taxa de avaliações positivas (positive_ratio).
    """
    global IDF_TABLE, TOTAL_DOCS
    metadados = {}
    if not os.path.exists(caminho_json):
        return metadados

    doc_frequencies = {}
    TOTAL_DOCS = 0

    with open(caminho_json, mode='r', encoding='utf-8') as f:
        for linha in f:
            linha_str = linha.strip()
            if not linha_str:
                continue
            dados = json.loads(linha_str)
            app_id = str(dados.get('app_id', ''))
            
            tags_lista = [t.strip() for t in dados.get('tags', []) if t.strip()]
            genres = set(dados.get('genres', []))
            
            # Normalização de estúdios
            raw_devs = dados.get('developers', [])
            devs_normalizados = set()
            for d in raw_devs:
                norm = chave_developer(d)
                if norm:
                    devs_normalizados.add(norm)

            metadados[app_id] = {
                'tags': tags_lista,
                'genres': genres,
                'developers': devs_normalizados,
                'positive_ratio': 80.0  # Valor padrão equilibrado
            }

            # Acumula frequências para o IDF
            for t in tags_lista:
                k = f"tag_{t.strip().lower()}"
                doc_frequencies[k] = doc_frequencies.get(k, 0) + 1
            for g in genres:
                k = f"gen_{g.strip().lower()}"
                doc_frequencies[k] = doc_frequencies.get(k, 0) + 1
            
            TOTAL_DOCS += 1

    # Pré-computa e armazena os valores de IDF globalmente
    for termo, freq in doc_frequencies.items():
        IDF_TABLE[termo] = math.log((1 + TOTAL_DOCS) / (1 + freq)) + 1.0

    # Pré-computa os vetores de pesos ponderados por consenso comunitário (SteamSpy)
    for app_id, meta in metadados.items():
        tags_l = meta['tags']
        n_tags = len(tags_l)
        pesos_tags = {}
        for r, t in enumerate(tags_l):
            tok = f"tag_{t.strip().lower()}"
            # Fator de consenso decrescente: 1.0 no topo (1º lugar) atenuando até 0.30 na 20ª tag
            c = 1.0 - 0.70 * (r / max(1, n_tags - 1))
            pesos_tags[tok] = ((IDF_TABLE.get(tok, 1.0)) ** 2) * c
        meta['pesos_tags'] = pesos_tags
        meta['soma_pesos'] = sum(pesos_tags.values())

    # Carrega taxas reais de aprovação de games.csv se fornecido
    if caminho_games and os.path.exists(caminho_games):
        with open(caminho_games, mode='r', encoding='utf-8') as f_games:
            reader = csv.DictReader(f_games)
            for row in reader:
                aid = str(row.get('app_id', ''))
                if aid in metadados:
                    try:
                        metadados[aid]['positive_ratio'] = float(row.get('positive_ratio', 80.0))
                    except (ValueError, TypeError):
                        metadados[aid]['positive_ratio'] = 80.0

    return metadados

def verificar_dissonancia_tom(meta_a, meta_b):
    """
    Identifica conflitos temáticos/demográficos extremos entre dois jogos.
    Ex: Evita que um jogo explicitamente violento/adulto (GTA V) recomende um jogo exclusivamente infantil (LEGO).
    """
    tags_a = {t.lower() for t in meta_a.get('tags', set())}
    tags_b = {t.lower() for t in meta_b.get('tags', set())}

    has_mature_a = bool(tags_a & TAGS_MATURE)
    has_family_a = bool(tags_a & TAGS_FAMILIA)

    has_mature_b = bool(tags_b & TAGS_MATURE)
    has_family_b = bool(tags_b & TAGS_FAMILIA)

    # Conflito se um tem tom maduro estrito e o outro tem tom familiar estrito
    if has_mature_a and not has_family_a and has_family_b and not has_mature_b:
        return True
    if has_family_a and not has_mature_a and has_mature_b and not has_family_b:
        return True
    return False

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def jaccard(meta_a, meta_b):
    """
    Cálculo de similaridade de conteúdo:
    - Jaccard Generalizado (Índice de Ruzicka) ponderado pelo quadrado do IDF
      e atenuado pelo posto de consenso comunitário das tags (SteamSpy).
    - Gênero oficial atua como multiplicador suave de congruência e desempate.
    Retorna: (fator_tags, bonus_genero)
    """
    w_a = meta_a.get('pesos_tags', {})
    w_b = meta_b.get('pesos_tags', {})

    if not w_a or not w_b:
        return 0.0, 1.0

    intersecao = set(w_a.keys()) & set(w_b.keys())
    if not intersecao:
        return 0.0, 1.0

    # Jaccard Generalizado (Min-Max Ruzicka): sum(min) / sum(max)
    # Identidade matemática: sum(max) = sum(w_a) + sum(w_b) - sum(min)
    soma_min = sum(min(w_a[t], w_b[t]) for t in intersecao)
    soma_max = meta_a.get('soma_pesos', 0.0) + meta_b.get('soma_pesos', 0.0) - soma_min

    fator_tags = (soma_min / soma_max) if soma_max > 0 else 0.0

    # Multiplicador suave de gênero
    gen_a = meta_a.get('genres', set())
    gen_b = meta_b.get('genres', set())

    if gen_a and gen_b:
        if gen_a.intersection(gen_b):
            bonus_genero = 1.15  # Bônus de afinidade macro (+15%)
        else:
            bonus_genero = 0.65  # Penalidade de incompatibilidade (-35%)
    else:
        bonus_genero = 1.0

    return fator_tags, bonus_genero

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def construir_grafo(caminho_csv, caminho_games=None, min_positive_ratio=65.0, peso_helpful=0.20):
    """Constrói o grafo bipartido de Usuários e Jogos a partir do CSV filtrado,
    aplicando Poda Prévia de Qualidade (descarta jogos com positive_ratio < min_positive_ratio)
    e ponderando arestas pelo tempo de jogo amortecido e pela validação social de 'helpful'"""
    if not os.path.exists(caminho_csv):
        print(f"ERRO: O arquivo {caminho_csv} não existe.")
        return None

    # Carrega taxas de aprovação para a poda prévia de qualidade
    ratings = {}
    if caminho_games and os.path.exists(caminho_games) and min_positive_ratio > 0:
        print(f"Carregando taxas de aprovação de {os.path.basename(caminho_games)} para poda de qualidade (< {min_positive_ratio}%)...")
        with open(caminho_games, mode='r', encoding='utf-8') as f_games:
            reader_games = csv.DictReader(f_games)
            for row in reader_games:
                aid = row.get('app_id', '').strip()
                pr_str = row.get('positive_ratio', '')
                try:
                    pr = float(pr_str) if pr_str else 80.0
                except ValueError:
                    pr = 80.0
                ratings[aid] = pr

    G = nx.Graph()
    print("Carregando grafo bipartido a partir do CSV...")

    linhas_lidas = 0
    descartados_qualidade = 0
    with open(caminho_csv, mode='r', encoding='utf-8') as f:
        _ = f.readline()
        for linha in f:
            linhas_lidas += 1
            if linhas_lidas % 1000000 == 0:
                print(f"   -> Adicionando ao grafo: {linhas_lidas} conexões processadas...")
                
            parts = linha.strip().split(',')
            if len(parts) >= 7:
                app_id = parts[0]
                helpful_str = parts[1]
                hours_str = parts[5]
                user_id = parts[6]
                try:
                    hours = float(hours_str) if hours_str else 0.0
                    helpful = float(helpful_str) if helpful_str else 0.0
                except ValueError:
                    continue

                if not app_id or not user_id:
                    continue

                # Poda Prévia Baseada em Qualidade: ignora títulos universalmente rejeitados pela comunidade
                if ratings and ratings.get(app_id, 80.0) < min_positive_ratio:
                    descartados_qualidade += 1
                    continue

                node_jogo = f"game_{app_id}"
                node_user = f"user_{user_id}"
                # Ponderação híbrida: engajamento temporal + credibilidade social (helpful reviews)
                peso = math.log1p(hours) * (1.0 + peso_helpful * math.log1p(helpful))

                G.add_node(node_jogo, tipo='jogo', nome_original=app_id)
                G.add_node(node_user, tipo='usuario', nome_original=user_id)
                G.add_edge(node_jogo, node_user, weight=peso)

    if descartados_qualidade > 0:
        print(f"   -> Poda Prévia de Qualidade: {descartados_qualidade} conexões de jogos com aprovação < {min_positive_ratio}% foram excluídas do grafo.")
    print(f"Grafo construído! Vértices: {G.number_of_nodes()} | Arestas: {G.number_of_edges()}")
    return G

#------------------------------------------------------------------------------------------------------------------------------------------------------------------

def recomendar_jogos(G, jogo_alvo_id, comunidades, dicionario_tags, 
                     top_k_users=1000, top_n_jogos=10, bonus_dev=0.1,
                     limiar_jaccard=0.20, peso_louvain=3.0, expoente_grau=0.35,
                     min_positive_ratio=65.0, fator_dissonancia_tom=0.0,
                     silencioso=False):
    """
    Busca em Largura (BFS) em 2 Níveis com:
    - Poda de auto-recomendação em O(1)
    - Poda por aprovação mínima da comunidade (min_positive_ratio)
    - Filtro de compatibilidade temática/demográfica (mature vs family friendly)
    - Memoização local de Jaccard e modulação de qualidade bayesiana
    Retorna: (recomendações_ranqueadas, top_usuarios)
    """
    node_alvo = f"game_{jogo_alvo_id}"
    if node_alvo not in G:
        if not silencioso:
            pr = dicionario_tags.get(str(jogo_alvo_id), {}).get('positive_ratio')
            if pr is not None and pr < min_positive_ratio:
                print(f"[AVISO] O jogo {jogo_alvo_id} foi excluído previamente do Grafo devido à baixa taxa de aprovação da comunidade ({pr}% positivas, corte mínimo: {min_positive_ratio}%).")
            else:
                print(f"O jogo {jogo_alvo_id} não foi encontrado no Grafo (filtrado na amostragem K-Core ou sem tags).")
        return [], []

    if not silencioso:
        print(f"\nIniciando Busca em Largura (BFS) em 2 níveis para o alvo: {jogo_alvo_id}...")

    # NÍVEL 1: Encontrar os Top Usuários com maior engajamento comprovado
    usuarios_vizinhos = G[node_alvo]
    usuarios_ordenados = sorted(
        usuarios_vizinhos.items(), 
        key=lambda x: x[1]['weight'], 
        reverse=True
    )
    top_usuarios = usuarios_ordenados[:top_k_users]

    pontuacao_jogos = {}
    cache_jaccard = {}  # Memoização local: evita recalcular Jaccard dezenas de vezes para o mesmo jogo
    meta_alvo = dicionario_tags.get(jogo_alvo_id, {})

    # NÍVEL 2: Expandir para os Jogos recomendados pelos Top Usuários
    for node_user, dados_aresta_origem in top_usuarios:
        peso_usuario = dados_aresta_origem['weight']
        jogos_do_usuario = G[node_user]
        
        for node_jogo, dados_aresta_destino in jogos_do_usuario.items():
            # Poda direta em O(1): não recomenda o próprio jogo de entrada
            if node_jogo == node_alvo:
                continue

            id_limpo = node_jogo.replace("game_", "")
            meta_recomendado = dicionario_tags.get(id_limpo, {})

            # 1. Filtro de qualidade mínima da comunidade (descarta jogos universalmente rejeitados)
            pr = meta_recomendado.get('positive_ratio', 80.0)
            if pr < min_positive_ratio:
                continue

            score_colaborativo = peso_usuario * dados_aresta_destino['weight']

            # 2. Filtro de Dissonância Temática / Demográfica (evita colisões Mature vs Family Friendly)
            if verificar_dissonancia_tom(meta_alvo, meta_recomendado):
                if fator_dissonancia_tom <= 0.0:
                    continue
                score_colaborativo *= fator_dissonancia_tom

            # Modulador Comunitário (Louvain)
            bonus_comm = peso_louvain if comunidades.get(node_alvo) == comunidades.get(node_jogo) else 1.0

            # 3. Similaridade Semântica com Cache
            if id_limpo in cache_jaccard:
                fator_jaccard, bonus_genero = cache_jaccard[id_limpo]
            else:
                fator_jaccard, bonus_genero = jaccard(meta_alvo, meta_recomendado)
                cache_jaccard[id_limpo] = (fator_jaccard, bonus_genero)

            # Corte de relevância semântica intrínseca (conteúdo real das tags)
            # Evita que estúdios com múltiplos gêneros (ex: Capcom) resgatem jogos incompatíveis (ex: DMC5 em RE2)
            if fator_jaccard < limiar_jaccard:
                continue

            # Bônus de estúdio: concedido apenas a títulos que já atendem ao corte semântico
            bonus_estudio = 0.0
            if meta_alvo.get('developers') and meta_recomendado.get('developers'):
                if meta_alvo['developers'] & meta_recomendado['developers']:
                    bonus_estudio = bonus_dev

            # 4. Modulador suave de qualidade do item (prior de aprovação dos usuários)
            fator_qualidade = (pr / 100.0)

            # Score composto do par
            score_final = score_colaborativo * bonus_comm * bonus_genero * (fator_jaccard + bonus_estudio + 0.1) * fator_qualidade

            # Acumulação aditiva de score
            if node_jogo not in pontuacao_jogos:
                pontuacao_jogos[node_jogo] = 0.0
            pontuacao_jogos[node_jogo] += score_final

    # Amortecimento de Grau para mitigar viés de super-hubs
    if expoente_grau > 0:
        for node_jogo in pontuacao_jogos:
            grau = G.degree(node_jogo)
            if grau > 0:
                pontuacao_jogos[node_jogo] /= (grau ** expoente_grau)

    # Ordenação final decrescente
    recomendacoes_ordenadas = sorted(
        pontuacao_jogos.items(), 
        key=lambda item: item[1], 
        reverse=True
    )

    return recomendacoes_ordenadas[:top_n_jogos], top_usuarios
