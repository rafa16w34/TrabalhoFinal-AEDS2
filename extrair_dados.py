import csv
import os
from collections import defaultdict

def extrair(input_path, output_path, min_hours=5.0, min_jogos_por_usuario=3, min_avaliacoes_por_jogo=10):
    """
    Algoritmo de 2 Passos para limapar dataset
    Passo 1: Descobre o grau dos vértices
    Passo 2: Filtra os dados encontrados usando K-CORE
    """
    if not os.path.exists(input_path):
        print(f"ERRO: Arquivo não encontrado.")
        return

    print("="*50)
    print("Iniciando Filtragem..")
    print("="*50)

    
    contagem_usuarios = defaultdict(int)# Dicionários otimizados para contagem, para otimização
    contagem_jogos = defaultdict(int)

    # ---------------------------------------------------------
    # Passo 1
    # ---------------------------------------------------------
    print("\n[PASSO 1/2] Analisando os graus dos vertices...")
    linhas_lidas_passo1 = 0
    
    with open(input_path, mode='r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        
        for row in reader:
            linhas_lidas_passo1 += 1
            if linhas_lidas_passo1 % 5000000 == 0:
                print(f"  -> Lidas {linhas_lidas_passo1} linhas...")

            try:
                is_recommended = str(row.get('is_recommended', '')).strip().lower()
                hours_str = row.get('hours', '0')
                hours = float(hours_str) if hours_str else 0.0

                #Apenas receomndados e com horas minímas
                if is_recommended in ['true', '1'] and hours >= min_hours:
                    user_id = row.get('user_id')
                    app_id = row.get('app_id')
                    
                    if user_id and app_id:
                        contagem_usuarios[user_id] += 1
                        contagem_jogos[app_id] += 1
            except ValueError:
                continue
                
    print(f"Análise concluída! {len(contagem_usuarios)} users válidos e {len(contagem_jogos)} jogos.")

    # ---------------------------------------------------------
    # Passo 2
    # ---------------------------------------------------------
    print(f"\n[PASSO 2/2] Fazendo Filtragem K-CORE...")
    print(f"Parametros: Minimo de jogos: {min_jogos_por_usuario} Minimo de arestas {min_avaliacoes_por_jogo} Minimo de horas {min_hours} ")
    
    linhas_lidas_passo2 = 0
    linhas_salvas = 0

    with open(input_path, mode='r', encoding='utf-8') as f_in, \
         open(output_path, mode='w', encoding='utf-8', newline='') as f_out:
         
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)
        writer.writeheader()

        for row in reader:
            linhas_lidas_passo2 += 1
            if linhas_lidas_passo2 % 5000000 == 0:
                print(f"  -> Processando {linhas_lidas_passo2} linhas...")

            try:
                is_recommended = str(row.get('is_recommended', '')).strip().lower()
                hours_str = row.get('hours', '0')
                hours = float(hours_str) if hours_str else 0.0

                if is_recommended in ['true', '1'] and hours >= min_hours:
                    user_id = row.get('user_id')
                    app_id = row.get('app_id')

                    #Filtro K-Core
                    if contagem_usuarios[user_id] >= min_jogos_por_usuario and contagem_jogos[app_id] >= min_avaliacoes_por_jogo:
                        writer.writerow(row)
                        linhas_salvas += 1

            except ValueError:
                continue

    print("="*50)
    print("FILTTRAGEM CONCLUÍDA!")
    print(f"Total de arestas analisadas: {linhas_lidas_passo1}")
    print(f"Total de arestas salvas: {linhas_salvas}")
    print(f"Arquivo gerado: {output_path}")
    print("="*50)


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INPUT_FILE = os.path.join(BASE_DIR, 'extracted_data', 'recommendations.csv')
    OUTPUT_FILE = os.path.join(BASE_DIR, 'extracted_data', 'sampled_recommendations.csv')

    #K-Core
    extrair(
        input_path=INPUT_FILE, 
        output_path=OUTPUT_FILE, 
        min_hours=50.0,            
        min_jogos_por_usuario=10,        
        min_avaliacoes_por_jogo=50      
    )
