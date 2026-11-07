import os
import sys
import json
import time

# Garante acesso aos módulos em src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Removido: import main (evita o ciclo com main.py)
import recommender

def processar_recomendacoes_em_lote(caminho_entrada=None, caminho_saida=None, motor=None):
    """
    Lê uma lista de App IDs de um arquivo de texto e gera um relatório formatado
    com o Top 10 de recomendações para cada jogo.
    
    Aceita 'motor' opcional como tupla (grafo, titulos, metadados, comunidades)
    para evitar reprocessar o grafo se já estiver em memória no main.py.
    """
    src_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(src_dir, '..'))

    if caminho_entrada is None:
        caminho_entrada = os.path.join(project_root, 'jogos_entrada.txt')

    if caminho_saida is None:
        caminho_saida = os.path.join(project_root, 'output', 'relatorio_recomendacoes_lote.txt')

    # Cria arquivo de exemplo se não existir
    if not os.path.exists(caminho_entrada):
        with open(caminho_entrada, 'w', encoding='utf-8') as f:
            f.write("# Digite um App ID por linha (linhas com # são ignoradas)\n")
            f.write("1245620  # ELDEN RING\n")
            f.write("227300   # Euro Truck Simulator 2\n")
            f.write("678950   # DRAGON BALL FighterZ\n")
            f.write("584400   # Sonic Mania\n")
            f.write("945360   # Among Us\n")
            f.write("271590   # Grand Theft Auto V\n")
            f.write("1091500  # Cyberpunk 2077\n")
            f.write("367520   # Hollow Knight\n")
        print(f"Arquivo de entrada criado com exemplos em: {caminho_entrada}")

    # 1. Carrega os App IDs válidos do arquivo
    ids_alvo = []
    with open(caminho_entrada, 'r', encoding='utf-8') as f:
        for linha in f:
            linha_limpa = linha.split('#')[0].strip()
            if linha_limpa and linha_limpa.isdigit():
                ids_alvo.append(linha_limpa)

    if not ids_alvo:
        print(f"Aviso: Nenhum App ID numérico válido encontrado em {caminho_entrada}.")
        return

    print("=" * 65)
    print("PROCESSAMENTO DE RECOMENDAÇÕES EM LOTE")
    print(f"Arquivo de entrada: {caminho_entrada} ({len(ids_alvo)} jogos para processar)")
    print(f"Arquivo de saída:   {caminho_saida}")
    print("=" * 65)

    # 2. Inicializa o motor (import diferido para quebrar importação circular)
    if motor is not None:
        grafo, titulos, metadados, comunidades = motor
    else:
        import main
        grafo, titulos, metadados, comunidades = main.inicializacao()

    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    tempo_inicio = time.time()

    # 3. Executa as recomendações e gera o relatório
    with open(caminho_saida, 'w', encoding='utf-8') as f_out:
        f_out.write("=" * 80 + "\n")
        f_out.write(" RELATÓRIO DE RECOMENDAÇÕES EM LOTE (AEDS 2 - SISTEMA HÍBRIDO)\n")
        f_out.write(f" Data de Geração: {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
        f_out.write(f" Total de Jogos Alvo Processados: {len(ids_alvo)}\n")
        f_out.write("=" * 80 + "\n\n")

        for idx, app_id in enumerate(ids_alvo, 1):
            nome_alvo = titulos.get(app_id, f"Jogo Desconhecido ({app_id})")
            node_alvo = f"game_{app_id}"
            comm_alvo = comunidades.get(node_alvo, -1)
            meta_alvo = metadados.get(app_id, {})
            generos_alvo = ", ".join(meta_alvo.get('genres', [])) or "N/D"

            print(f"[{idx}/{len(ids_alvo)}] Processando: {nome_alvo} (ID: {app_id})...")

            f_out.write("-" * 80 + "\n")
            f_out.write(f"JOGO ALVO #{idx}: {nome_alvo} (App ID: {app_id})\n")
            f_out.write(f"Gêneros Oficiais: {generos_alvo} | Super-Nó Louvain: {comm_alvo}\n")
            f_out.write("-" * 80 + "\n")

            if node_alvo not in grafo:
                f_out.write("  [AVISO] Este jogo não está presente no grafo (filtrado no K-Core ou sem tags).\n\n")
                continue

            # Gera recomendações
            recs, _ = recommender.recomendar_jogos(
                grafo, 
                app_id, 
                comunidades, 
                metadados, 
                top_k_users=50, 
                top_n_jogos=10,
                silencioso=True
            )

            if not recs:
                f_out.write("  [AVISO] Nenhuma recomendação atendeu ao limiar mínimo de Jaccard (0.20).\n\n")
                continue

            f_out.write(f" {'Pos.':<5} | {'App ID':<10} | {'Título Recomendado':<40} | {'Score':<8} | {'Comunidade':<10}\n")
            f_out.write(" " + "-" * 78 + "\n")

            for pos, (node_rec, score) in enumerate(recs, 1):
                clean_id = node_rec.replace("game_", "")
                titulo_rec = titulos.get(clean_id, f"Desconhecido ({clean_id})")
                comm_rec = comunidades.get(node_rec, -1)
                mesma_comm = "Mesma" if comm_rec == comm_alvo else f"Nó {comm_rec}"
                f_out.write(f" {pos:2d}º   | {clean_id:<10} | {titulo_rec:<40} | {score:<8.2f} | {mesma_comm:<10}\n")

            f_out.write("\n")

        tempo_total = time.time() - tempo_inicio
        f_out.write("=" * 80 + "\n")
        f_out.write(f" Processamento em lote finalizado com sucesso em {tempo_total:.2f} segundos!\n")
        f_out.write("=" * 80 + "\n")

    print("\n" + "=" * 65)
    print(f"RELATÓRIO CONCLUÍDO COM SUCESSO!")
    print(f"Arquivo gerado em: {caminho_saida}")
    print(f"Tempo total de execução: {tempo_total:.2f} segundos")
    print("=" * 65)

if __name__ == "__main__":
    arq_in = sys.argv[1] if len(sys.argv) > 1 else None
    arq_out = sys.argv[2] if len(sys.argv) > 2 else None
    processar_recomendacoes_em_lote(arq_in, arq_out)