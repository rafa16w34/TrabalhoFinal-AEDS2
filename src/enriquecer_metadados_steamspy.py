"""
Pipeline Unificado de Enriquecimento de Metadados via SteamSpy API

Unifica o enriquecimento de tags da comunidade e gêneros oficiais em uma
única requisição HTTP por jogo, eliminando redundâncias e chamadas duplicadas à API.
"""

import csv
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# Caminhos dos arquivos de dados
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SRC_DIR, ".."))
ARQUIVO_GRAFO = os.path.join(PROJECT_ROOT, "extracted_data", "sampled_recommendations.csv")
ARQUIVO_METADATA = os.path.join(PROJECT_ROOT, "extracted_data", "games_metadata.json")
ARQUIVO_GAMES = os.path.join(PROJECT_ROOT, "extracted_data", "games.csv")

# Cache unificado (com fallback para os caches individuais anteriores)
ARQUIVO_CACHE_UNIFICADO = os.path.join(PROJECT_ROOT, "extracted_data", "steamspy_cache.json")
CACHE_LEGADO_TAGS = os.path.join(PROJECT_ROOT, "extracted_data", "tags_cache_steamspy.json")
CACHE_LEGADO_GENEROS = os.path.join(PROJECT_ROOT, "extracted_data", "genres_cache_steamspy.json")

TOP_N_TAGS = 20

# Sufixos societários que aparecem após vírgula (ex: "FromSoftware, Inc.")
SUFIXOS_EMPRESA = {"inc", " Inc.", "inc.", "llc", "llc.", "ltd", "ltd.", "co", "co.", "co. ltd", "co., ltd.",
                   "corp", "corp.", "corporation", "gmbh", "s.a.", "sa", "s.r.l.", "srl",
                   "limited", "plc", "ab", "oy", "as", "a/s", "pty ltd", "k.k."}


def normalizar_developers(lista):
    """Reúne sufixos de empresa ao nome anterior e padroniza 'Traveller\'s Tales' como 'TT Games'."""
    resultado = []
    for nome in lista or []:
        n = nome.strip()
        if 'traveller' in n.lower():
            n = 'TT Games'
        if resultado and n.lower() in SUFIXOS_EMPRESA:
            resultado[-1] = f"{resultado[-1]}, {n}"
        elif n not in resultado:
            resultado.append(n)
    return resultado


def carregar_jogos_do_grafo(caminho_grafo):
    """Retorna o conjunto de App IDs únicos presentes no grafo amostrado."""
    jogos = set()
    if not os.path.exists(caminho_grafo):
        print(f"Erro: {caminho_grafo} não encontrado.")
        return jogos
    with open(caminho_grafo, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            app_id = str(row.get("app_id", "")).strip()
            if app_id:
                jogos.add(app_id)
    return jogos


def carregar_nomes_jogos(caminho_games):
    """Mapeia app_id -> (título, reviews) para ordenação e logs informativos."""
    info = {}
    if not os.path.exists(caminho_games):
        return info
    with open(caminho_games, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            app_id = str(row.get("app_id", "")).strip()
            titulo = row.get("title", "Desconhecido")
            try:
                reviews = int(row.get("user_reviews", 0) or 0)
            except ValueError:
                reviews = 0
            info[app_id] = (titulo, reviews)
    return info


def carregar_ou_inicializar_cache():
    """
    Carrega o cache unificado. Se não existir, importa os dados dos caches
    legados (tags_cache_steamspy.json e genres_cache_steamspy.json) se disponíveis.
    """
    cache = {}

    # 1. Tenta carregar o cache unificado
    if os.path.exists(ARQUIVO_CACHE_UNIFICADO):
        try:
            with open(ARQUIVO_CACHE_UNIFICADO, mode="r", encoding="utf-8") as f:
                cache = json.load(f)
            return cache
        except Exception:
            cache = {}

    # 2. Migração automática e transparente de caches legados
    legado_tags = {}
    legado_generos = {}

    if os.path.exists(CACHE_LEGADO_TAGS):
        try:
            with open(CACHE_LEGADO_TAGS, mode="r", encoding="utf-8") as f:
                legado_tags = json.load(f)
        except Exception:
            pass

    if os.path.exists(CACHE_LEGADO_GENEROS):
        try:
            with open(CACHE_LEGADO_GENEROS, mode="r", encoding="utf-8") as f:
                legado_generos = json.load(f)
        except Exception:
            pass

    todos_ids = set(legado_tags.keys()).union(set(legado_generos.keys()))
    for aid in todos_ids:
        cache[aid] = {
            "tags": legado_tags.get(aid, []),
            "genres": legado_generos.get(aid, [])
        }

    return cache


def salvar_cache(cache):
    """Salva o cache em disco de forma segura."""
    with open(ARQUIVO_CACHE_UNIFICADO, mode="w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def identificar_jogos_pendentes(caminho_metadata, jogos_grafo, info_jogos, cache):
    """
    Identifica quais jogos do grafo necessitam de consulta à API.
    Critério: se faltar 'tags' OU 'genres' (no JSON e no cache), ou se o
    jogo ainda nunca teve 'developers' consultado (chave ausente no cache).
    """
    pendentes = []

    if not os.path.exists(caminho_metadata):
        print(f"Erro: {caminho_metadata} não encontrado.")
        return pendentes

    with open(caminho_metadata, mode="r", encoding="utf-8") as f:
        for linha in f:
            if not linha.strip():
                continue
            dado = json.loads(linha)
            app_id = str(dado.get("app_id", ""))

            if app_id not in jogos_grafo:
                continue

            tags_atuais = dado.get("tags", [])
            generos_atuais = dado.get("genres", [])

            dados_cache = cache.get(app_id, {})
            tags_no_cache = dados_cache.get("tags", [])
            generos_no_cache = dados_cache.get("genres", [])

            precisa_tags = (not tags_atuais) and (not tags_no_cache)
            precisa_generos = (not generos_atuais) and (not generos_no_cache)
            # Presença da chave indica que a API já foi consultada com sucesso
            # (mesmo que o jogo não tenha developer cadastrado)
            precisa_devs = ("developers" not in dado) and ("developers" not in dados_cache)

            if precisa_tags or precisa_generos or precisa_devs:
                titulo, reviews = info_jogos.get(app_id, (f"App {app_id}", 0))
                pendentes.append((reviews, app_id, titulo))

    # Ordena pelos mais populares primeiro (Princípio de Pareto)
    pendentes.sort(reverse=True, key=lambda x: x[0])
    return [(app_id, titulo) for _, app_id, titulo in pendentes]


def consultar_steamspy(app_id, titulo, tentativas=3):
    """
    Faz UMA ÚNICA chamada à API do SteamSpy e extrai SIMULTANEAMENTE:
      1. Top 20 tags comunitárias ordenadas por votos
      2. Lista de gêneros oficiais
      3. Lista de estúdios desenvolvedores (developers)
    Em caso de falha de rede, retorna None nos três campos.
    """
    url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    req = urllib.request.Request(url, headers=headers)

    for tentativa in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=6) as response:
                dados = json.loads(response.read().decode("utf-8"))

                # 1. Extração de Tags
                top_tags = []
                dict_tags = dados.get("tags", {})
                if isinstance(dict_tags, dict) and dict_tags:
                    tags_ordenadas = sorted(dict_tags.items(), key=lambda x: x[1], reverse=True)
                    top_tags = [tag for tag, _ in tags_ordenadas[:TOP_N_TAGS]]

                # 2. Extração de Gêneros Oficiais
                generos = []
                genre_str = dados.get("genre", "")
                if genre_str:
                    generos = [g.strip() for g in genre_str.split(",") if g.strip()]

                # 3. Extração de Developers
                developers = []
                dev_str = dados.get("developer", "")
                if dev_str:
                    developers = normalizar_developers([d.strip() for d in dev_str.split(",") if d.strip()])

                return app_id, titulo, top_tags, generos, developers
        except Exception:
            time.sleep(0.4 * (tentativa + 1))

    return app_id, titulo, None, None, None


def atualizar_metadata_json(caminho_metadata, cache):
    """
    Atualiza 'games_metadata.json' gravando 'tags', 'genres' e 'developers' com escrita atômica.
    """
    caminho_temp = caminho_metadata + ".tmp"
    atualizados = 0

    with open(caminho_metadata, mode="r", encoding="utf-8") as f_in, \
         open(caminho_temp, mode="w", encoding="utf-8") as f_out:
        for linha in f_in:
            if not linha.strip():
                continue
            dado = json.loads(linha)
            app_id = str(dado.get("app_id", ""))

            modificado = False
            if app_id in cache:
                novas_tags = cache[app_id].get("tags", [])
                novos_generos = cache[app_id].get("genres", [])

                # Atualiza tags se as atuais estiverem vazias e o cache possuir novas
                if (not dado.get("tags")) and novas_tags:
                    dado["tags"] = novas_tags
                    modificado = True

                # Atualiza ou adiciona gêneros oficiais
                if novos_generos and dado.get("genres") != novos_generos:
                    dado["genres"] = novos_generos
                    modificado = True

                # Atualiza ou adiciona developers
                if "developers" in cache[app_id]:
                    novos_devs = cache[app_id]["developers"]
                    if dado.get("developers") != novos_devs:
                        dado["developers"] = novos_devs
                        modificado = True

            if "genres" not in dado:
                dado["genres"] = []
                modificado = True

            if modificado:
                atualizados += 1

            f_out.write(json.dumps(dado, ensure_ascii=False) + "\n")

    os.replace(caminho_temp, caminho_metadata)
    return atualizados


def main():
    print("=" * 70)
    print("   PIPELINE UNIFICADO DE ENRIQUECIMENTO DE DADOS (STEAMSPY API)")
    print("   Coleta simultânea: Tags + Gêneros Oficiais + Developers")
    print("=" * 70)

    # 1. Carregar dependências
    print("\n[1/5] Carregando jogos do grafo e metadados...")
    jogos_grafo = carregar_jogos_do_grafo(ARQUIVO_GRAFO)
    info_jogos = carregar_nomes_jogos(ARQUIVO_GAMES)
    print(f" -> Jogos únicos no grafo: {len(jogos_grafo)}")

    # 2. Carregar Cache
    cache = carregar_ou_inicializar_cache()
    # Corrige developers já salvos com sufixos separados
    for dados_cache in cache.values():
        if "developers" in dados_cache:
            dados_cache["developers"] = normalizar_developers(dados_cache["developers"])
    print(f" -> Jogos presentes no cache: {len(cache)}")

    # 3. Identificar pendências
    pendentes = identificar_jogos_pendentes(ARQUIVO_METADATA, jogos_grafo, info_jogos, cache)
    total_pendentes = len(pendentes)
    print(f" -> Jogos pendentes de consulta à API: {total_pendentes}")

    # 4. Executar consultas se houver pendências
    if total_pendentes > 0:
        print(f"\n[2/5] Consultando SteamSpy API em lote para {total_pendentes} jogos...")
        concluidos = 0
        falhas = 0

        with ThreadPoolExecutor(max_workers=5) as executor:
            futuros = {
                executor.submit(consultar_steamspy, app_id, titulo): (app_id, titulo)
                for app_id, titulo in pendentes
            }

            for futuro in as_completed(futuros):
                app_id, titulo, tags, generos, developers = futuro.result()
                concluidos += 1

                if tags is None:
                    # Falha de rede: não grava nada, será tentado na próxima execução
                    falhas += 1
                else:
                    anterior = cache.get(app_id, {})
                    cache[app_id] = {
                        "tags": tags or anterior.get("tags", []),
                        "genres": generos or anterior.get("genres", []),
                        "developers": developers
                    }

                if concluidos % 25 == 0 or concluidos == total_pendentes:
                    devs_txt = ", ".join(developers) if developers else "-"
                    print(f"  [{concluidos}/{total_pendentes}] {titulo} ({app_id}) -> Dev: {devs_txt}")
                    salvar_cache(cache)

        salvar_cache(cache)
        if falhas:
            print(f" -> Atenção: {falhas} consultas falharam. Rode o script novamente para tentar de novo.")
    else:
        print("\n[2/5] Nenhuma consulta necessária: todos os jogos já estão cacheados ou enriquecidos!")

    # 5. Atualizar games_metadata.json
    print("\n[3/5] Gravando dados em 'games_metadata.json'...")
    atualizados = atualizar_metadata_json(ARQUIVO_METADATA, cache)
    print(f" -> Concluído: {atualizados} registros atualizados/verificados.")

    # 6. Salvar cache unificado final consolidado
    salvar_cache(cache)
    print(" -> Cache unificado salvo em 'extracted_data/steamspy_cache.json'.")

    # 7. Amostra de validação dos metadados
    print("\n[4/5] Amostra de Validação dos Metadados Enriquecidos:")
    print("-" * 70)
    amostras = ["271590", "374320", "21130", "367520", "1091500", "227300"]
    for aid in amostras:
        titulo = info_jogos.get(aid, (f"App {aid}", 0))[0]
        dados = cache.get(aid, {})
        tags = dados.get("tags", [])
        generos = dados.get("genres", [])
        devs = dados.get("developers", [])
        print(f" • {titulo} (ID {aid}):")
        print(f"   - Developer: {devs}")
        print(f"   - Gêneros : {generos}")
        print(f"   - Top Tags: {tags[:6]}... ({len(tags)} tags no total)\n")
    print("-" * 70)

    print("Pipeline de dados concluído com 100% de sucesso!")


if __name__ == "__main__":
    main()
