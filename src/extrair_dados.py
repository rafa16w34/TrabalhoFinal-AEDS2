import os
import sys
import json
import statistics
import time
from collections import defaultdict, Counter

def carregar_jogos_validos_com_tags(caminho_json):
    """
    Carrega apenas os IDs de jogos que possuem tags semânticas cadastradas no JSON.
    Garante que nenhum jogo sem metadados entre no grafo.
    """
    if not os.path.exists(caminho_json):
        print(f"Aviso: {caminho_json} não encontrado. Não haverá pré-filtragem por tags.")
        return None

    jogos_validos = set()
    with open(caminho_json, mode='r', encoding='utf-8') as f:
        for linha in f:
            linha_str = linha.strip()
            if not linha_str:
                continue
            try:
                dados = json.loads(linha_str)
                app_id = str(dados.get('app_id', '')).strip()
                tags = dados.get('tags', [])
                if app_id and tags and len(tags) > 0:
                    jogos_validos.add(app_id)
            except json.JSONDecodeError:
                continue

    print(f"Metadados: {len(jogos_validos)} jogos com tags válidas identificados.")
    return jogos_validos

def extrair(input_path, output_path, json_path=None, 
            min_hours_piso=5.0, min_hours_teto=50.0, 
            min_jogos_por_usuario=10, min_avaliacoes_por_jogo=50):
    """
    Algoritmo de K-Core Iterativo Real com Poda Adaptativa por Mediana e Pré-filtro de Tags:
    - Pré-passo: Descarta jogos sem tags válidas (evita nós órfãos de metadados).
    - Passo 1: Calcula a mediana adaptativa de horas por jogo (travada entre piso e teto).
    - Passo 2: Coleta todas as arestas candidatas com engajamento acima do limiar.
    - Passo 3: Executa K-Core iterativo até convergência matemática estrita (while True).
    - Passo 4: Grava o dataset reduzido final com 100% de consistência estrutural.
    """
    if not os.path.exists(input_path):
        print(f"ERRO: Arquivo {input_path} não encontrado.")
        return

    tempo_inicio = time.time()
    print("=" * 65)
    print("INICIANDO FILTRAGEM COM K-CORE ITERATIVO FORMAL")
    print(f"Parâmetros: Piso Horas={min_hours_piso}h | Teto Horas={min_hours_teto}h")
    print(f"Critérios K-Core: Mínimo Jogos/User={min_jogos_por_usuario} | Mínimo Avaliações/Jogo={min_avaliacoes_por_jogo}")
    print("=" * 65)

    # 1. Carregar jogos com tags válidas
    jogos_validos = None
    if json_path:
        jogos_validos = carregar_jogos_validos_com_tags(json_path)

    # 2. Passo 1: Calcular medianas de horas por jogo (apenas avaliações positivas)
    print("\n[PASSO 1/4] Analisando histórico de horas e calculando medianas adaptativas...")
    horas_por_jogo = defaultdict(list)
    linhas_lidas = 0

    with open(input_path, mode='r', encoding='utf-8') as f_in:
        _ = f_in.readline()  # Pula cabeçalho
        for linha in f_in:
            linhas_lidas += 1
            if linhas_lidas % 10000000 == 0:
                print(f"   -> {linhas_lidas // 1000000}M linhas processadas...")

            parts = linha.strip().split(',')
            if len(parts) >= 7:
                app_id, _, _, _, is_recommended, hours_str, user_id = parts[:7]
                if is_recommended.lower() in ('true', '1'):
                    if jogos_validos is None or app_id in jogos_validos:
                        try:
                            h = float(hours_str)
                            if h > 0:
                                horas_por_jogo[app_id].append(h)
                        except ValueError:
                            continue

    print(f" -> Avaliações positivas coletadas para {len(horas_por_jogo)} jogos.")

    # Cálculo dos limiares individuais por jogo
    limiares_jogo = {}
    for app_id, lista_h in horas_por_jogo.items():
        mediana = statistics.median(lista_h)
        limiar = min(min_hours_teto, max(min_hours_piso, mediana))
        limiares_jogo[app_id] = limiar

    del horas_por_jogo  # Libera memória imediatamente

    # 3. Passo 2: Coletar arestas candidatas que superam o limiar adaptativo
    print("\n[PASSO 2/4] Coletando arestas candidatas que atendem ao limiar adaptativo...")
    arestas_candidatas = []
    linhas_lidas = 0

    with open(input_path, mode='r', encoding='utf-8') as f_in:
        _ = f_in.readline()
        for linha in f_in:
            linhas_lidas += 1
            if linhas_lidas % 10000000 == 0:
                print(f"   -> {linhas_lidas // 1000000}M linhas verificadas...")

            parts = linha.strip().split(',')
            if len(parts) >= 7:
                app_id, _, _, _, is_recommended, hours_str, user_id = parts[:7]
                if is_recommended.lower() in ('true', '1') and user_id:
                    limiar = limiares_jogo.get(app_id)
                    if limiar is not None:
                        try:
                            h = float(hours_str)
                            if h >= limiar:
                                arestas_candidatas.append((user_id, app_id))
                        except ValueError:
                            continue

    print(f" -> Total de arestas candidatas pré-K-Core: {len(arestas_candidatas)}")

    # 4. Passo 3: K-Core Iterativo até Convergência
    print("\n[PASSO 3/4] Executando K-Core Iterativo até estabilização total...")
    pares = arestas_candidatas
    iteracao = 0

    while True:
        iteracao += 1
        contagem_u = Counter(u for u, _ in pares)
        contagem_j = Counter(j for _, j in pares)

        removidos_u = {u for u, c in contagem_u.items() if c < min_jogos_por_usuario}
        removidos_j = {j for j, c in contagem_j.items() if c < min_avaliacoes_por_jogo}

        if not removidos_u and not removidos_j:
            print(f" -> CONVERGÊNCIA PLENA ALCANÇADA na Iteração {iteracao}!")
            break

        pares = [p for p in pares if p[0] not in removidos_u and p[1] not in removidos_j]
        print(f"   Iteração {iteracao}: podados {len(removidos_u)} usuários e {len(removidos_j)} jogos. Arestas restantes: {len(pares)}")

    pares_finais_set = set(pares)
    total_users_finais = len(set(u for u, _ in pares))
    total_jogos_finais = len(set(j for _, j in pares))
    del pares
    del arestas_candidatas

    print(f"\nResumo da Topologia Final:")
    print(f" * Usuários válidos (grau >= {min_jogos_por_usuario}): {total_users_finais}")
    print(f" * Jogos válidos (grau >= {min_avaliacoes_por_jogo}): {total_jogos_finais}")
    print(f" * Arestas convergidas: {len(pares_finais_set)}")

    # 5. Passo 4: Gravar o novo arquivo CSV filtrado
    print(f"\n[PASSO 4/4] Gravando dataset refinado em: {output_path}...")
    linhas_salvas = 0

    with open(input_path, mode='r', encoding='utf-8') as f_in, \
         open(output_path, mode='w', encoding='utf-8', newline='') as f_out:
        
        header = f_in.readline()
        f_out.write(header)

        for linha in f_in:
            parts = linha.strip().split(',')
            if len(parts) >= 7:
                app_id, _, _, _, is_recommended, hours_str, user_id = parts[:7]
                if (user_id, app_id) in pares_finais_set:
                    f_out.write(linha)
                    linhas_salvas += 1

    tempo_total = time.time() - tempo_inicio
    print("=" * 65)
    print("EXTRAÇÃO E K-CORE ITERATIVO FINALIZADOS COM SUCESSO!")
    print(f"Total de arestas salvas: {linhas_salvas}")
    print(f"Tempo total de execução: {tempo_total:.2f} segundos ({tempo_total / 60:.2f} minutos)")
    print(f"Arquivo gerado: {output_path}")
    print("=" * 65)

if __name__ == "__main__":
    SRC_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, '..'))
    INPUT_FILE = os.path.join(PROJECT_ROOT, 'extracted_data', 'recommendations.csv')
    OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'extracted_data', 'sampled_recommendations.csv')
    JSON_FILE = os.path.join(PROJECT_ROOT, 'extracted_data', 'games_metadata.json')

    extrair(
        input_path=INPUT_FILE, 
        output_path=OUTPUT_FILE, 
        json_path=JSON_FILE,
        min_hours_piso=5.0,
        min_hours_teto=50.0,
        min_jogos_por_usuario=10,
        min_avaliacoes_por_jogo=50
    )
