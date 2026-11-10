import os
import sys
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import webbrowser
import time

# Garante acesso aos módulos em src
src_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(src_dir, '..'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import main
import recommender
import export_to_gephi
import recomendar_lote

# Variáveis globais do motor em memória
GRAFO = None
TITULOS = None
METADADOS = None
COMUNIDADES = None
ROTULOS_COMUNIDADES = {}
JOGOS_LISTA_BUSCA = []
CACHE_RECOMENDACOES = None
MODO_CACHE = False

ROTULOS_FIXOS = {
    0: {"nome": "Indie & Roguelike 2D", "subtitulo": "Roguelike • Pixel Art • Metroidvania"},
    1: {"nome": "Aventura Narrativa & Puzzle", "subtitulo": "Point & Click • Quebra-Cabeça • Mistério"},
    2: {"nome": "Estratégia & Simulação Tática", "subtitulo": "Grande Estratégia • RTS • Wargame • 4X"},
    3: {"nome": "FPS Clássico & Ação Retrô", "subtitulo": "Boomer Shooter • Tiro em 1ª Pessoa • Retrô"},
    4: {"nome": "JRPG & RPG Narrativo / Anime", "subtitulo": "Anime • JRPG • Visual Novel • Ação Japonesa"},
    5: {"nome": "Simulação, Direção & Mundo Aberto", "subtitulo": "Automobilismo • Mundo Aberto • Corrida • VR"}
}

def inicializar_motor(motor=None, forcar_dinamico=False):
    """Carrega os dados e o grafo apenas uma vez na inicialização."""
    global GRAFO, TITULOS, METADADOS, COMUNIDADES, ROTULOS_COMUNIDADES, JOGOS_LISTA_BUSCA
    global CACHE_RECOMENDACOES, MODO_CACHE
    print("=" * 65)
    print("INICIALIZANDO MOTOR DE RECOMENDAÇÃO WEB (STEAM GRAPH)")
    print("=" * 65)
    
    # 1. Tenta carregar cache pré-calculado (Modo Nuvem Leve para Render / Servidores)
    caminho_cache = os.path.join(project_root, 'web', 'cache_recomendacoes.json')
    if not forcar_dinamico and motor is None and os.path.exists(caminho_cache):
        try:
            print(">> Modo Nuvem Leve: carregando cache pré-calculado...")
            with open(caminho_cache, 'r', encoding='utf-8') as f:
                CACHE_RECOMENDACOES = json.load(f)
            MODO_CACHE = True
            JOGOS_LISTA_BUSCA = CACHE_RECOMENDACOES.get('jogos_busca', [])
            qtd_recs = len(CACHE_RECOMENDACOES.get('recomendacoes', {}))
            print(f"✓ Sucesso! {len(JOGOS_LISTA_BUSCA)} jogos catalogados e {qtd_recs} recomendações prontas.")
            print(f"✓ Consumo estimado de memória: ~40 MB RAM (100% seguro para o Render).")
            print("=" * 65)
            return
        except Exception as e:
            print(f"[AVISO] Falha ao ler cache ({e}). Recorrendo ao motor dinâmico...")

    if motor is not None:
        GRAFO, TITULOS, METADADOS, COMUNIDADES = motor
    else:
        GRAFO, TITULOS, METADADOS, COMUNIDADES = main.inicializacao()

    # Prepara lista otimizada para autocomplete rápido no frontend
    print("Indexando títulos para busca instantânea...")
    jogos_busca = []
    for app_id, titulo in TITULOS.items():
        node_id = f"game_{app_id}"
        if node_id in GRAFO:
            cid = COMUNIDADES.get(node_id, -1)
            pr = METADADOS.get(app_id, {}).get('positive_ratio', 80.0)
            genres = list(METADADOS.get(app_id, {}).get('genres', []))
            jogos_busca.append({
                "id": str(app_id),
                "nome": titulo,
                "comm_id": cid,
                "positive_ratio": pr,
                "genres": genres
            })
    
    # Ordena alfabeticamente
    jogos_busca.sort(key=lambda x: x["nome"].lower())
    JOGOS_LISTA_BUSCA = jogos_busca
    print(f"Indexação concluída: {len(JOGOS_LISTA_BUSCA)} jogos disponíveis no grafo.")

class RecommenderHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        # Permite CORS para desenvolvimento local se necessário
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/" or path == "/index.html":
            self.servir_html()
        elif path in ["/logo.png", "/favicon.ico"]:
            self.servir_estatico("logo.png", "image/png")
        elif path.startswith("/static/") or path.startswith("/assets/"):
            rel_path = path.lstrip("/")
            self.servir_estatico(rel_path)
        elif path == "/api/jogos":
            self.servir_jogos()
        elif path == "/api/comunidades":
            self.servir_comunidades()
        elif path == "/api/recomendar":
            app_id = query.get("id", [""])[0].strip()
            self.servir_recomendacao(app_id)
        elif path == "/api/relatorio_lote":
            self.servir_relatorio_lote()
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b"404 - Nao encontrado")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/lote":
            self.processar_lote_api()
        elif path == "/api/gephi":
            self.processar_gephi_api()
        else:
            self.send_response(404)
            self.end_headers()

    def servir_html(self):
        caminho_html = os.path.join(project_root, 'web', 'index.html')
        if not os.path.exists(caminho_html):
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"Arquivo HTML nao encontrado em {caminho_html}".encode('utf-8'))
            return

        with open(caminho_html, 'rb') as f:
            conteudo = f.read()

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def servir_estatico(self, nome_arquivo, content_type=None):
        caminho = os.path.join(project_root, 'web', os.path.basename(nome_arquivo))
        if not os.path.exists(caminho):
            self.send_response(404)
            self.end_headers()
            return

        if content_type is None:
            if caminho.endswith(".png"):
                content_type = "image/png"
            elif caminho.endswith(".jpg") or caminho.endswith(".jpeg"):
                content_type = "image/jpeg"
            elif caminho.endswith(".svg"):
                content_type = "image/svg+xml"
            elif caminho.endswith(".ico"):
                content_type = "image/x-icon"
            elif caminho.endswith(".css"):
                content_type = "text/css"
            elif caminho.endswith(".js"):
                content_type = "application/javascript"
            else:
                content_type = "application/octet-stream"

        with open(caminho, 'rb') as f:
            conteudo = f.read()

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(conteudo)))
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(conteudo)

    def servir_jogos(self):
        """Retorna a lista completa de jogos para autocomplete no cliente."""
        dados = json.dumps(JOGOS_LISTA_BUSCA).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def servir_comunidades(self):
        """Retorna os metadados dos Super-Nós / Comunidades."""
        dados = json.dumps(ROTULOS_FIXOS).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def servir_recomendacao(self, app_id):
        if not app_id:
            self.responder_erro("Parametro 'id' obrigatorio.", 400)
            return

        # Atendimento instantâneo pelo cache pré-calculado (Modo Nuvem Leve / Render)
        if MODO_CACHE and CACHE_RECOMENDACOES:
            recs_dict = CACHE_RECOMENDACOES.get('recomendacoes', {})
            podados_dict = CACHE_RECOMENDACOES.get('jogos_podados', {})
            if app_id in recs_dict:
                corpo = json.dumps(recs_dict[app_id], ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return
            elif app_id in podados_dict:
                p_info = podados_dict[app_id]
                titulo = p_info.get('titulo', f"Jogo {app_id}")
                pr = p_info.get('positive_ratio', 50.0)
                msg = f"O jogo '{titulo}' possui apenas {pr}% de avaliações positivas na Steam e foi previamente excluído do Grafo de Recomendações (a Poda de Qualidade exige no mínimo 65% de aprovação comprovada da comunidade)."
                resposta = {
                    "status": "erro_qualidade",
                    "mensagem": msg,
                    "titulo": titulo,
                    "id": app_id,
                    "positive_ratio": pr,
                    "imagem": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    "imagem_capsule": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_616x353.jpg"
                }
                corpo = json.dumps(resposta, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return
            else:
                self.responder_erro(f"Jogo {app_id} não encontrado no grafo filtrado (fora da amostragem K-Core).", 404)
                return

        node_alvo = f"game_{app_id}"
        if node_alvo not in GRAFO:
            meta_alvo = METADADOS.get(app_id, {})
            pr = meta_alvo.get('positive_ratio')
            titulo = TITULOS.get(app_id, f"Jogo {app_id}")
            if pr is not None and pr < 65.0:
                msg = f"O jogo '{titulo}' possui apenas {pr}% de avaliações positivas na Steam e foi previamente excluído do Grafo de Recomendações (a Poda de Qualidade exige no mínimo 65% de aprovação comprovada da comunidade)."
                resposta = {
                    "status": "erro_qualidade",
                    "mensagem": msg,
                    "titulo": titulo,
                    "id": app_id,
                    "positive_ratio": pr,
                    "imagem": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    "imagem_capsule": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_616x353.jpg"
                }
                corpo = json.dumps(resposta, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return
            else:
                self.responder_erro(f"Jogo {app_id} não encontrado no grafo filtrado (fora da amostragem K-Core).", 404)
                return

        tempo_ini = time.time()
        resultados, top_usuarios = recommender.recomendar_jogos(
            GRAFO,
            app_id,
            COMUNIDADES,
            METADADOS,
            top_n_jogos=10,
            silencioso=True
        )
        tempo_ms = round((time.time() - tempo_ini) * 1000, 1)

        meta_alvo = METADADOS.get(app_id, {})
        comm_alvo_id = COMUNIDADES.get(node_alvo, -1)
        comm_alvo_info = ROTULOS_FIXOS.get(comm_alvo_id, {"nome": f"Comunidade {comm_alvo_id}", "subtitulo": ""})

        # Monta dados do jogo alvo
        alvo_dto = {
            "id": app_id,
            "titulo": TITULOS.get(app_id, f"Jogo {app_id}"),
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

        # Monta recomendações
        recs_dto = []
        max_score = resultados[0][1] if resultados else 1.0

        tags_alvo_set = set(t.lower() for t in meta_alvo.get('tags', []))
        user_nodes = [u[0] if isinstance(u, tuple) else u for u in top_usuarios]

        for pos, (node_rec, score) in enumerate(resultados, 1):
            rec_id = node_rec.replace("game_", "")
            meta_rec = METADADOS.get(rec_id, {})
            comm_rec_id = COMUNIDADES.get(node_rec, -1)
            comm_rec_info = ROTULOS_FIXOS.get(comm_rec_id, {"nome": f"Comunidade {comm_rec_id}", "subtitulo": ""})
            
            # Tags em comum para explicabilidade
            tags_rec_list = meta_rec.get('tags', [])
            tags_todas_comuns = [t for t in tags_rec_list if t.lower() in tags_alvo_set]
            tags_comuns_topo = tags_todas_comuns[:4]

            # Similaridade semântica (Jaccard + modulação de gênero)
            fator_jaccard, bonus_genero = recommender.jaccard(meta_alvo, meta_rec)

            # Bônus de comunidade Louvain
            mesma_comm = (comm_rec_id == comm_alvo_id)
            bonus_comm = 3.0 if mesma_comm else 1.0

            # Bônus de estúdio
            devs_alvo = meta_alvo.get('developers', set())
            devs_rec = meta_rec.get('developers', set())
            devs_em_comum = list(devs_alvo & devs_rec) if devs_alvo and devs_rec else []
            bonus_dev = 0.10 if devs_em_comum else 0.0

            # Usuários ponte que jogaram ambos os jogos
            vizinhos_rec = set(GRAFO.neighbors(node_rec)) if node_rec in GRAFO else set()
            usuarios_ponte = len([u for u in user_nodes if u in vizinhos_rec])

            # Prior de qualidade (positive_ratio)
            pr = meta_rec.get('positive_ratio', 80.0)
            fator_qualidade = round(pr / 100.0, 2)

            # Grau e amortecimento de super-populares
            grau = GRAFO.degree(node_rec) if node_rec in GRAFO else 0
            amortecimento_grau = round(1.0 / (grau ** 0.35), 4) if grau > 0 else 1.0

            afinidade = round((score / max_score) * 100, 1)

            # Diagnóstico minucioso das forças de recomendação com escala cromática
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
                "fator_qualidade": fator_qualidade,
                "grau": grau,
                "amortecimento_grau": amortecimento_grau
            }

            recs_dto.append({
                "posicao": pos,
                "id": rec_id,
                "titulo": TITULOS.get(rec_id, f"Jogo {rec_id}"),
                "imagem": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{rec_id}/header.jpg",
                "imagem_capsule": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{rec_id}/capsule_616x353.jpg",
                "score": round(score, 2),
                "afinidade": afinidade,
                "generos": list(meta_rec.get('genres', [])),
                "tags_comuns": tags_comuns_topo,
                "developers": list(devs_rec),
                "positive_ratio": pr,
                "comunidade_id": comm_rec_id,
                "comunidade_nome": comm_rec_info["nome"],
                "comunidade_subtitulo": comm_rec_info["subtitulo"],
                "mesma_comunidade": mesma_comm,
                "diagnostico": diagnostico
            })

        resposta = {
            "status": "ok",
            "tempo_ms": tempo_ms,
            "alvo": alvo_dto,
            "total_recomendacoes": len(recs_dto),
            "recomendacoes": recs_dto
        }

        corpo = json.dumps(resposta, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def servir_relatorio_lote(self):
        caminho_relatorio = os.path.join(project_root, 'output', 'relatorio_recomendacoes_lote.txt')
        if not os.path.exists(caminho_relatorio):
            self.responder_erro("Relatório em lote ainda não foi gerado.", 404)
            return

        with open(caminho_relatorio, 'r', encoding='utf-8') as f:
            conteudo = f.read()

        dados = json.dumps({"relatorio": conteudo}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def processar_lote_api(self):
        try:
            print("[Web API] Disparando processamento em lote...")
            recomendar_lote.processar_recomendacoes_em_lote(
                motor=(GRAFO, TITULOS, METADADOS, COMUNIDADES)
            )
            caminho_relatorio = os.path.join(project_root, 'output', 'relatorio_recomendacoes_lote.txt')
            with open(caminho_relatorio, 'r', encoding='utf-8') as f:
                linhas = f.readlines()
                resumo = "".join(linhas[:40]) + "\n... (veja o arquivo completo no botão abaixo) ..."

            corpo = json.dumps({
                "status": "ok",
                "mensagem": "Processamento em lote finalizado com sucesso!",
                "resumo": resumo
            }).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        except Exception as e:
            self.responder_erro(f"Erro ao processar lote: {str(e)}", 500)

    def processar_gephi_api(self):
        try:
            print("[Web API] Disparando exportação Gephi...")
            export_to_gephi.exportar_para_gephi_hibrido(seed=42)
            corpo = json.dumps({
                "status": "ok",
                "mensagem": "Arquivos .gexf gerados na pasta 'output/' com sucesso!"
            }).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        except Exception as e:
            self.responder_erro(f"Erro ao exportar Gephi: {str(e)}", 500)

    def responder_erro(self, msg, status_code):
        corpo = json.dumps({"status": "erro", "mensagem": msg}).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

def iniciar_servidor(porta=5000, abrir_navegador=True, motor=None, forcar_dinamico=False):
    inicializar_motor(motor=motor, forcar_dinamico=forcar_dinamico)
    servidor = HTTPServer(('0.0.0.0', porta), RecommenderHandler)
    url = f"http://localhost:{porta}"
    print("=" * 65)
    print(f" SERVIDOR WEB STEAM RECOMENDAÇÃO PRONTO!")
    print(f" Acesse no navegador: {url}")
    print(" Pressione Ctrl+C para encerrar o servidor.")
    print("=" * 65)

    if abrir_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado pelo usuário.")
        servidor.server_close()

if __name__ == '__main__':
    forcar_din = '--dinamico' in sys.argv
    args_limpos = [a for a in sys.argv[1:] if a != '--dinamico']
    port_env = os.environ.get('PORT')
    if port_env and port_env.isdigit():
        p = int(port_env)
        abrir_nav = False
    elif len(args_limpos) > 0 and args_limpos[0].isdigit():
        p = int(args_limpos[0])
        abrir_nav = False
    else:
        p = 5000
        abrir_nav = True
    iniciar_servidor(porta=p, abrir_navegador=abrir_nav, forcar_dinamico=forcar_din)
