import csv
import os

def extrair(input_path, output_path, min_hours=5.0):

    """
    Função principal que analisa nosso banco de dados e 
    extrai as linhas onde encontramos usuários que recomendaram o jogo
    e tem horas jogadas minímas de 5 horas
    """

    if not os.path.exists(input_path):
        print(f"ERRO: Arquivo não encontrado em {input_path}")
        return

    print("Iniciando extração dos dados")

    linhas_processadas = 0;
    linhas_salvas = 0

    with open(input_path, mode='r', encoding='utf-8') as f_in,\
        open(output_path, mode='w', encoding='utf-8', newline='') as f_out:

        reader = csv.DictReader(f_in);

        writer = csv.DictWriter(f_out, fieldnames=reader.fieldnames)

        writer.writeheader()

        for row in reader:

            linhas_processadas+=1

            if linhas_processadas % 10000 == 0:
                print(f"Processando {linhas_processadas} linhas lidas")

            try:
                is_recommended = str(row.get('its_recommended'),'').strip().lower()

                hours_str = float(hours_str) if hours_str else 0.0

                if is_recommended in ['true', '1'] and hours >= min_hours;

                    writer.writerow(row)
                    linhas_salvas += 1

            except ValueError:

                continue

    print("-" * 30)
    print("Concluído!")
    print(f"Total de avaliações lidas: {linhas_processadas}")
    print(f"Total de avaliações salvas no sample: {linhas_salvas}")
    print(f"Novo arquivo gerado em: {output_path}")

    if __name__ == "__main__":

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        INPUT_FILE = os.path.join(BASE_DIR, 'extracted_data', 'recommendations.csv')
        OUTPUT_FILE = os.path.join(BASE_DIR, 'extracted_data', 'sampled_recommendations.csv')

        extrair(INPUT_FILE, OUTPUT_FILE, min_hours=5.0)
