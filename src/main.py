import os 
import sys
import json

# Garante que módulos locais na pasta src sejam importados de qualquer diretório
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import networkx.algorithms.community as nx_comm

from recommender import (
    construir_grafo, carregar_titulos_jogos, carregar_tags_jogos, recomendar_jogos
)

from export_to_gephi import exportar_para_gephi_hibrido
from recomendar_lote import processar_recomendacoes_em_lote

seed = 16  # Seed fixa para determinismo do Louvain

JOGOS_TESTE = {   
    "1": ("271590",  "Grand Theft Auto V"),
    "2": ("374320",  "DARK SOULS™ III"),
    "3": ("21130",   "LEGO® Harry Potter: Years 1-4"),
    "4": ("367520",  "Hollow Knight"),
    "5": ("1091500", "Cyberpunk 2077"),
    "6": ("304240",  "Resident Evil HD Remaster"),
    "7": ("1245620", "ELDEN RING"),
    "8": ("227300",  "Euro Truck Simulator 2")
}

def cabecalho():
    print("\n" + "-"*50)
    print(" Sistema de Recomendacao de Jogos (Trabalho Final AEDS2)")
    print(" Feito por: Gabriel Alves F. e Rafael Alves F.")
    print("-"*50)

def garantir_dados_zenodo():
    """Verifica se os arquivos essenciais estão presentes em extracted_data.
    Se não estiverem, realiza o download e extração automáticos a partir do Zenodo (DOI: 10.5281/zenodo.23861070)."""
    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(src_dir, '..'))
    dest_dir = os.path.join(project_root, 'extracted_data')
    
    arquivos_obrigatorios = ['games.csv', 'games_metadata.json', 'sampled_recommendations.csv']
    if all(os.path.exists(os.path.join(dest_dir, f)) for f in arquivos_obrigatorios):
        return True
        
    print("\n" + "=" * 65)
    print(" BASE DE DADOS AUSENTE: Baixando do Zenodo (DOI: 10.5281/zenodo.23861070)")
    print("=" * 65)
    os.makedirs(dest_dir, exist_ok=True)
    
    url = "https://zenodo.org/records/23861070/files/Data-Steam.zip?download=1"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    zip_temp = os.path.join(dest_dir, "temp_zenodo.zip")
    
    try:
        import requests
        import zipfile
        import shutil
        
        with requests.get(url, headers=headers, stream=True, timeout=120) as r:
            r.raise_for_status()
            total_len = int(r.headers.get('content-length', 0))
            baixado = 0
            with open(zip_temp, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
                        baixado += len(chunk)
                        if total_len:
                            pct = (baixado / total_len) * 100
                            mb = baixado / (1024 * 1024)
                            tot_mb = total_len / (1024 * 1024)
                            print(f"\rBaixando base de dados: {mb:.1f}MB / {tot_mb:.1f}MB ({pct:.1f}%)", end="", flush=True)
        print("\nDownload concluído! Descompactando dados...")
        
        with zipfile.ZipFile(zip_temp, 'r') as zf:
            for member in zf.infolist():
                filename = os.path.basename(member.filename)
                if not filename:
                    continue
                dest_file = os.path.join(dest_dir, filename)
                with zf.open(member) as src, open(dest_file, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                print(f" -> Extraído: {filename}")
                
        if os.path.exists(zip_temp):
            os.remove(zip_temp)
        print("✓ Base de dados configurada com sucesso!\n")
        return True
    except Exception as e:
        print(f"\n[ERRO] Falha ao baixar base do Zenodo: {e}")
        if os.path.exists(zip_temp):
            os.remove(zip_temp)
        return False

def inicializacao():
    """Carrega os dados, constrói o grafo e mapeia as comunidades"""
    garantir_dados_zenodo()
    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(src_dir, '..'))
    caminho_amostra = os.path.join(project_root, 'extracted_data', 'sampled_recommendations.csv')
    caminho_games = os.path.join(project_root, 'extracted_data', 'games.csv')
    caminho_json = os.path.join(project_root, 'extracted_data', 'games_metadata.json')
    caminho_comunidades_json = os.path.join(project_root, 'output', 'comunidades_louvain.json')

    print('Carregando metadados e títulos...')
    titulos = carregar_titulos_jogos(caminho_games)
    metadados = carregar_tags_jogos(caminho_json, caminho_games=caminho_games)

    print('Construindo Grafo bipartido...')
    grafo = construir_grafo(caminho_amostra, caminho_games=caminho_games, min_positive_ratio=65.0)

    if not grafo:
        print("ERRO: Não foi possível construir o grafo.")
        sys.exit(1)

    # Cache de comunidades do Louvain para carregamento instantâneo
    if os.path.exists(caminho_comunidades_json):
        print('Carregando comunidades do Louvain salvas em cache...')
        with open(caminho_comunidades_json, 'r', encoding='utf-8') as f:
            comunidades = json.load(f)
        total_comunidades = len(set(comunidades.values()))
        print(f'Sucesso ({total_comunidades} Super Nós carregados instantaneamente)')
    else:
        print(f'Executando algoritmo de Louvain (seed = {seed})...')
        lista_comunidades = nx_comm.louvain_communities(grafo, weight='weight', seed=seed)

        comunidades = {}
        for id_comm, grupo in enumerate(lista_comunidades):
            for no in grupo:
                comunidades[no] = id_comm

        os.makedirs(os.path.join(project_root, 'output'), exist_ok=True)
        with open(caminho_comunidades_json, 'w', encoding='utf-8') as f:
            json.dump(comunidades, f)
        print(f'Sucesso ({len(lista_comunidades)} Super Nós mapeados e salvos em cache)')

    return grafo, titulos, metadados, comunidades

def recomendar(grafo, titulos, metadados, comunidades):
    """Menu interativo para recomendação de jogos"""
    while True:
        print("\n" + "-"*4 + "Recomendacao" + "-"*4)
        print("Escolha um jogo de demonstração ou digite qualquer App ID:")
        for k, (app_id, nome) in JOGOS_TESTE.items():
            print(f"  [{k}] {nome} (ID: {app_id})")
        print("  (9) Digitar outro App ID manualmente")
        print("  (0) Voltar ao Menu Principal")

        opcao = input("Escolha: ").strip()

        if opcao == "0":
            break
        elif opcao in JOGOS_TESTE:
            id_alvo = JOGOS_TESTE[opcao][0]
        elif opcao == "9":
            id_alvo = input("Digite o App ID da Steam: ").strip()
        else:
            print("ERRO: Digite uma opcao valida")
            continue

        nome_alvo = titulos.get(id_alvo, f"Jogo {id_alvo}")
        node_alvo = f"game_{id_alvo}"
        if node_alvo not in grafo:
            pr = metadados.get(id_alvo, {}).get('positive_ratio')
            if pr is not None and pr < 65.0:
                print(f"\n[AVISO] O jogo '{nome_alvo}' (App ID: {id_alvo}) foi excluído previamente do grafo devido à sua baixa taxa de avaliações positivas na Steam ({pr}% < corte de 65%).")
            else:
                print(f"\n[AVISO] O jogo '{nome_alvo}' (App ID: {id_alvo}) não foi encontrado no grafo filtrado.")
            continue

        print(f" Buscando Recomendações para: {nome_alvo} (ID: {id_alvo})")

        resultados, top_users = recomendar_jogos(
            grafo, 
            id_alvo, 
            comunidades, 
            metadados, 
            top_n_jogos=10
        )
        if not resultados:
            print("ERRO: Nenhuma recomendação encontrada ou jogo fora do grafo.")
            continue

        print("\n--- TOP 10 RECOMENDAÇÕES HÍBRIDAS ---")
        for i, (jogo_id, score) in enumerate(resultados):
            id_limpo = jogo_id.replace("game_", "")
            titulo_rec = titulos.get(id_limpo, "Nome Desconhecido")
            print(f" {i+1:2d}º Lugar - {titulo_rec:<45} | Score: {score:.2f}")

def menu_exportar():
    """Executa a exportação para o Gephi."""
    print("\n" + "-"*4 + "Gerar arquivo Gephi" + "-"*4)

    confirmacao = input(f"Deseja gerar os arquivos .gexf agora (seed = {seed})? [s/n]: ").strip().lower()
    if confirmacao == 's':
        exportar_para_gephi_hibrido(seed=seed)
    else:
        print("Voltando ao menu principal..")

def main():
    cabecalho()                              
    grafo, titulos, metadados, comunidades = inicializacao()

    while True:
        cabecalho()
        print("  [1] Recomendar Jogos (Interativo)")
        print("  [2] Recomendar em Lote (Arquivo jogos_entrada.txt)")
        print("  [3] Gerar arquivo Gephi")
        print("  [4] Iniciar Interface Web (Navegador)")
        print("  [0] Sair")
        print("=" * 70)
        escolha = input("Digite uma das opcoes acima: ").strip()

        if escolha == "1":
            recomendar(grafo, titulos, metadados, comunidades)

        elif escolha == "2":
            processar_recomendacoes_em_lote()

        elif escolha == "3":
            menu_exportar()

        elif escolha == "4":
            import servidor_web
            servidor_web.iniciar_servidor(porta=5000, abrir_navegador=True, motor=(grafo, titulos, metadados, comunidades))

        elif escolha == "0":
            print("\nFinalizando programa...")
            break

        else:
            print("\nOpção inválida! Pressione Enter para continuar.")
            input()

if __name__ == "__main__":
    main()
