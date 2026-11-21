"""
Script para Geração de Cache Pré-Calculado de Recomendações
Trabalho Final AEDS 2 - CEFET-MG / UFC-IMG
Autores: Rafael Alves Faria e Gabriel Alves Faria

Objetivo:
Pré-calcular as Top-10 recomendações e o diagnóstico completo de explicabilidade (XAI)
para todos os jogos do Grafo. O arquivo resultante (web/cache_recomendacoes.json) consome
apenas ~40 MB de RAM ao ser carregado pelo servidor web, permitindo hospedagem 100% gratuita
e instantânea no Render (ou qualquer nuvem com limite de 512 MB de RAM).
"""

import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Garante acesso aos módulos em src/
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(src_dir, '..'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import main
import recommender
import servidor_web

def formatar_diagnostico_jogo(app_id, grafo, comunidades, metadados, titulos):
    """Calcula e formata os dados exatos de recomendação e explicabilidade para 1 jogo."""
    node_alvo = f"game_{app_id}"
    meta_alvo = metadados.get(app_id, {})
    comm_alvo_id = comunidades.get(node_alvo, -1)
    comm_alvo_info = servidor_web.ROTULOS_FIXOS.get(comm_alvo_id, {"nome": f"Comunidade {comm_alvo_id}", "subtitulo": ""})

    # Executa algoritmo de recomendação do AEDS 2
    resultados, top_usuarios = recommender.recomendar_jogos(
        grafo,
        app_id,
        comunidades,
        metadados,
        top_n_jogos=10,
        silencioso=True
    )

    alvo_dto = {
        "id": app_id,
        "titulo": titulos.get(app_id, f"Jogo {app_id}"),
        "imagem": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
        "imagem_capsule": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_616x353.jpg",
        "generos": list(meta_alvo.get('genres', [])),
        "tags": list(meta_alvo.get('tags', []))[:8],
        "developers": list(meta_alvo.get('developers', [])),
        "positive_ratio": meta_alvo.get('positive_ratio', 80.0),
        "comunidade_id": comm_alvo_id,
        "comunidade_nome": comm_alvo_info["nome"],
        "comunidade_subtitulo": comm_alvo_info["subtitulo"]
    }

    recs_dto = []
    max_score = resultados[0][1] if resultados else 1.0
    tags_alvo_set = set(t.lower() for t in meta_alvo.get('tags', []))
    user_nodes = [u[0] if isinstance(u, tuple) else u for u in top_usuarios]

    for pos, (node_rec, score) in enumerate(resultados, 1):
        rec_id = node_rec.replace("game_", "")
        meta_rec = metadados.get(rec_id, {})
        comm_rec_id = comunidades.get(node_rec, -1)
        comm_rec_info = servidor_web.ROTULOS_FIXOS.get(comm_rec_id, {"nome": f"Comunidade {comm_rec_id}", "subtitulo": ""})
        
        tags_rec_list = meta_rec.get('tags', [])
        tags_todas_comuns = [t for t in tags_rec_list if t.lower() in tags_alvo_set]
        tags_comuns_topo = tags_todas_comuns[:4]

        fator_jaccard, bonus_genero = recommender.jaccard(meta_alvo, meta_rec)
        mesma_comm = (comm_rec_id == comm_alvo_id)
        bonus_comm = 3.0 if mesma_comm else 1.0

        devs_alvo = meta_alvo.get('developers', set())
        devs_rec = meta_rec.get('developers', set())
        devs_em_comum = list(devs_alvo & devs_rec) if devs_alvo and devs_rec else []
        bonus_dev = 0.10 if devs_em_comum else 0.0

        vizinhos_rec = set(grafo.neighbors(node_rec)) if node_rec in grafo else set()
        usuarios_ponte = len([u for u in user_nodes if u in vizinhos_rec])

        pr = meta_rec.get('positive_ratio', 80.0)
        fator_qualidade = round(pr / 100.0, 2)

        grau = grafo.degree(node_rec) if node_rec in grafo else 0
        amortecimento_grau = round(1.0 / (grau ** 0.35), 4) if grau > 0 else 1.0
        afinidade = round((score / max_score) * 100, 1)

        diagnostico = {
            "jaccard_pct": round(fator_jaccard * 100, 1),
            "jaccard_cor": "#2ed573" if fator_jaccard >= 0.28 else ("#ffa502" if fator_jaccard >= 0.20 else "#ff4757"),
            "tags_comuns": tags_todas_comuns,
            "tags_total": len(tags_todas_comuns),
            "bonus_comunidade": bonus_comm,
            "mesma_comunidade": mesma_comm,
            "comunidade_cor": "#2ed573" if mesma_comm else "#ffa502",
            "bonus_genero": round(bonus_genero, 2),
            "genero_cor": "#2ed573" if bonus_genero > 1.0 else ("#ffa502" if bonus_genero == 1.0 else "#ff4757"),
            "bonus_estudio": bonus_dev,
            "mesmo_estudio": bool(devs_em_comum),
            "estudios_comuns": devs_em_comum,
            "estudio_cor": "#2ed573" if devs_em_comum else "#8fa3b8",
            "usuarios_ponte": usuarios_ponte,
            "usuarios_ponte_total": len(user_nodes),
            "ponte_cor": "#2ed573" if usuarios_ponte >= 8 else ("#ffa502" if usuarios_ponte >= 3 else "#ff4757"),
            "positive_ratio": pr,
            "qualidade_cor": "#2ed573" if pr >= 80 else ("#ffa502" if pr >= 70 else "#ff4757"),
            "grau_popularidade": grau,
            "amortecimento_grau": amortecimento_grau
        }

        recs_dto.append({
            "posicao": pos,
            "id": rec_id,
            "titulo": titulos.get(rec_id, f"Jogo {rec_id}"),
            "imagem": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{rec_id}/header.jpg",
            "imagem_capsule": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{rec_id}/capsule_616x353.jpg",
            "url_steam": f"https://store.steampowered.com/app/{rec_id}",
            "score": round(score, 2),
            "afinidade": afinidade,
            "afinidade_pct": afinidade,
            "mesma_comunidade": mesma_comm,
            "comunidade_id": comm_rec_id,
            "comunidade_nome": comm_rec_info["nome"],
            "comunidade_subtitulo": comm_rec_info["subtitulo"],
            "generos": list(meta_rec.get('genres', [])),
            "tags_comuns": tags_comuns_topo,
            "tags_topo": tags_comuns_topo,
            "developers": list(meta_rec.get('developers', [])),
            "positive_ratio": pr,
            "diagnostico": diagnostico
        })

    return {
        "status": "ok",
        "tempo_ms": 1.0,
        "alvo": alvo_dto,
        "jogo_alvo": alvo_dto,
        "recomendacoes": recs_dto
    }

def gerar_cache_completo(limite_jogos=None):
    """Gera o arquivo web/cache_recomendacoes.json para todos os jogos."""
    print("=" * 65)
    print("GERADOR DE CACHE DE RECOMENDAÇÕES PARA NUVEM (RENDER)")
    print("=" * 65)

    # 1. Constrói o grafo em memória
    grafo, titulos, metadados, comunidades = main.inicializacao()

    # 2. Prepara lista de jogos para busca e identificação dos nós
    jogos_nos = [n for n in grafo.nodes() if n.startswith("game_")]
    jogos_ids = [n.replace("game_", "") for n in jogos_nos]

    if limite_jogos:
        jogos_ids = jogos_ids[:limite_jogos]
        print(f"[TESTE] Limitando geração para os primeiros {limite_jogos} jogos.")

    total_jogos = len(jogos_ids)
    print(f"Total de jogos a processar: {total_jogos}")

    # 3. Lista para o autocomplete no frontend
    jogos_busca = []
    for app_id in jogos_ids:
        node_id = f"game_{app_id}"
        cid = comunidades.get(node_id, -1)
        pr = metadados.get(app_id, {}).get('positive_ratio', 80.0)
        genres = list(metadados.get(app_id, {}).get('genres', []))
        jogos_busca.append({
            "id": str(app_id),
            "nome": titulos.get(app_id, f"Jogo {app_id}"),
            "comm_id": cid,
            "positive_ratio": pr,
            "genres": genres
        })
    jogos_busca.sort(key=lambda x: x["nome"].lower())

    # 4. Pré-calcula jogos excluídos por baixa qualidade (< 65%)
    # para exibir o modal de aviso informativo caso sejam buscados
    print("Indexando jogos excluídos por corte de qualidade (< 65%)...")
    jogos_podados = {}
    for app_id, meta in metadados.items():
        pr = meta.get('positive_ratio')
        if pr is not None and pr < 65.0:
            titulo = titulos.get(app_id, f"Jogo {app_id}")
            jogos_podados[str(app_id)] = {
                "id": str(app_id),
                "titulo": titulo,
                "positive_ratio": pr
            }

    print(f"✓ {len(jogos_podados)} jogos com baixa aprovação catalogados com aviso prévio.")

    # 5. Processamento paralelo com ThreadPoolExecutor
    print("\nIniciando cálculo das recomendações com pool de threads...")
    t_inicio = time.time()
    banco_recomendacoes = {}
    concluidos = 0

    def processar_um(app_id):
        resultado = formatar_diagnostico_jogo(app_id, grafo, comunidades, metadados, titulos)
        return app_id, resultado

    max_workers = min(8, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {executor.submit(processar_um, aid): aid for aid in jogos_ids}
        for fut in as_completed(futuros):
            aid, res = fut.result()
            banco_recomendacoes[str(aid)] = res
            concluidos += 1
            if concluidos % 25 == 0 or concluidos == total_jogos:
                decorrido = time.time() - t_inicio
                taxa = concluidos / decorrido if decorrido > 0 else 1.0
                restantes = total_jogos - concluidos
                eta_s = int(restantes / taxa)
                eta_min = eta_s // 60
                eta_sec = eta_s % 60
                pct = (concluidos / total_jogos) * 100
                print(f"\rProgresso: [{concluidos}/{total_jogos}] {pct:.1f}% | Taxa: {taxa:.1f} jogos/s | ETA: {eta_min:02d}m{eta_sec:02d}s", end="", flush=True)

    print(f"\n✓ Todos os {total_jogos} jogos calculados em {time.time()-t_inicio:.1f} segundos!")

    # 6. Salva tudo em web/cache_recomendacoes.json
    dados_finais = {
        "versao": "2.0_nuvem_leve",
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_jogos": total_jogos,
        "jogos_busca": jogos_busca,
        "comunidades": servidor_web.ROTULOS_FIXOS,
        "jogos_podados": jogos_podados,
        "recomendacoes": banco_recomendacoes
    }

    caminho_saida = os.path.join(project_root, 'web', 'cache_recomendacoes.json')
    print(f"\nGravando arquivo de cache em: {caminho_saida}...")
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        json.dump(dados_finais, f, ensure_ascii=False, separators=(',', ':'))

    tamanho_mb = os.path.getsize(caminho_saida) / (1024 * 1024)
    print("=" * 65)
    print(f"CACHE GERADO COM SUCESSO!")
    print(f"Tamanho do arquivo: {tamanho_mb:.2f} MB")
    print(f"Pronto para ser commitado no GitHub e rodar no Render com < 40 MB RAM!")
    print("=" * 65)

if __name__ == "__main__":
    limite = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limite = int(sys.argv[1])
    gerar_cache_completo(limite_jogos=limite)
