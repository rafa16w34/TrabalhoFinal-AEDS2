import os
import sys
import time
import math
import streamlit as st

# Garante acesso aos módulos em src/
root_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(root_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import main
import recommender

# 1. Configuração Inicial da Página
logo_path = os.path.join(root_dir, 'web', 'logo.png')
st.set_page_config(
    page_title="Steam Finder | AEDS 2",
    page_icon=logo_path if os.path.exists(logo_path) else "🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Estilos Personalizados Steam Dark Mode
st.markdown("""
<style>
    /* Estilos Globais Steam */
    .stApp {
        background: radial-gradient(circle at 50% 0%, #172435 0%, #0d1218 70%);
        color: #f1f5f9;
        font-family: 'Inter', -apple-system, sans-serif;
    }
    
    /* Header e Títulos */
    h1, h2, h3 {
        color: #ffffff !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }
    
    /* Badges personalizadas */
    .badge-instituto {
        background: rgba(30, 44, 61, 0.7);
        border: 1px solid #2a3f5a;
        padding: 6px 14px;
        border-radius: 8px;
        color: #66c0f4;
        font-size: 0.82rem;
        display: inline-block;
        margin-bottom: 12px;
    }
    
    .card-rec {
        background: #16202d;
        border: 1px solid #2a3f5a;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 16px;
        transition: all 0.2s ease;
    }
    .card-rec:hover {
        border-color: #66c0f4;
        transform: translateY(-2px);
    }
    
    .podium-1 { border-left: 4px solid #ffd700; }
    .podium-2 { border-left: 4px solid #c0c0c0; }
    .podium-3 { border-left: 4px solid #cd7f32; }
    
    .tag-chip {
        background: rgba(102, 192, 244, 0.12);
        border: 1px solid rgba(102, 192, 244, 0.3);
        color: #9bc9ea;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.72rem;
        display: inline-block;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)

# 3. Cache do Motor de Grafos (Carregado uma única vez na nuvem)
@st.cache_resource(show_spinner="Carregando Grafo de 2.39 Milhões de Arestas e Super-Nós de Louvain...")
def carregar_motor():
    return main.inicializacao()

grafo, titulos, metadados, comunidades = carregar_motor()

ROTULOS_FIXOS = {
    0: {"nome": "Indie & Roguelike 2D", "subtitulo": "Roguelike • Pixel Art • Metroidvania"},
    1: {"nome": "Aventura Narrativa & Puzzle", "subtitulo": "Point & Click • Quebra-Cabeça • Mistério"},
    2: {"nome": "Estratégia & Simulação Tática", "subtitulo": "Grande Estratégia • RTS • Wargame • 4X"},
    3: {"nome": "FPS Clássico & Ação Retrô", "subtitulo": "Boomer Shooter • Tiro em 1ª Pessoa • Retrô"},
    4: {"nome": "JRPG & RPG Narrativo / Anime", "subtitulo": "Anime • JRPG • Visual Novel • Ação Japonesa"},
    5: {"nome": "Simulação, Direção & Mundo Aberto", "subtitulo": "Automobilismo • Mundo Aberto • Corrida • VR"},
    6: {"nome": "Multiplayer & Sobrevivência Cooperativa", "subtitulo": "Co-op Online • Sobrevivência • Crafting"}
}

# 4. Barra Lateral (Sidebar)
with st.sidebar:
    if os.path.exists(logo_path):
        st.image(logo_path, width=80)
    st.title("Steam Finder")
    st.markdown("**Sistema Híbrido de Recomendação**  \n*AEDS 2 • CEFET-MG / UFC-IMG*")
    st.markdown("---")
    
    st.markdown("### 🎓 Equipe")
    st.markdown("- **Rafael Alves Faria**  \n- **Gabriel Alves Faria**")
    st.caption("Orientação: Prof. Michel Pires da Silva")
    st.markdown("---")
    
    st.markdown("### ⚙️ Hiperparâmetros da BFS")
    top_k = st.slider("Top Jogadores Influentes (k)", min_value=20, max_value=500, value=100, step=10, 
                      help="Quantidade de usuários mais dedicados e bem avaliados no grafo expandidos na BFS.")
    
    st.markdown("---")
    st.markdown("### 📊 Estatísticas do Grafo")
    st.metric("Vértices no Grafo", f"{grafo.number_of_nodes():,}")
    st.metric("Arestas Bipartidas", f"{grafo.number_of_edges():,}")
    st.metric("Super-Nós Louvain", f"{len(set(comunidades.values()))}")
    st.caption("Poda prévia ativa: Jogos < 65% de aprovação descartados.")

# 5. Cabeçalho Principal (Hero)
col_h1, col_h2 = st.columns([1, 8])
with col_h1:
    if os.path.exists(logo_path):
        st.image(logo_path, width=90)
with col_h2:
    st.markdown('<div class="badge-instituto">🎓 CEFET-MG / UFC-IMG • Algoritmos e Estruturas de Dados II</div>', unsafe_allow_html=True)
    st.title("Steam Finder — Recomendador por Grafos")
    st.caption("Busca em Largura Híbrida (BFS) em 2 Níveis com Comunidades de Louvain e Consenso de Tags SteamSpy")

st.markdown("---")

# 6. Atalhos Rápidos para Demonstração
st.markdown("##### 🚀 Teste Rápido (Jogos de Demonstração):")
pills = {
    "🚗 GTA V": "271590",
    "🧟 Resident Evil 2": "883710",
    "🚛 Euro Truck 2": "227300",
    "⚔️ ELDEN RING": "1245620",
    "🪓 Hollow Knight": "367520",
    "🚀 Among Us": "945360",
    "🌆 Cyberpunk 2077": "1091500",
    "🎯 Half-Life 2": "220"
}

cols_pills = st.columns(len(pills))
jogo_selecionado_pill = None
for i, (label, aid) in enumerate(pills.items()):
    if cols_pills[i].button(label, use_container_width=True):
        st.session_state['app_id_ativo'] = aid

# 7. Caixa de Pesquisa com Autocomplete
lista_opcoes = []
id_para_label = {}
for aid, tit in titulos.items():
    lbl = f"{tit} (ID: {aid})"
    lista_opcoes.append(lbl)
    id_para_label[aid] = lbl

lista_opcoes.sort()

# Define valor inicial da busca
indice_padrao = 0
if 'app_id_ativo' in st.session_state and st.session_state['app_id_ativo'] in id_para_label:
    lbl_alvo = id_para_label[st.session_state['app_id_ativo']]
    if lbl_alvo in lista_opcoes:
        indice_padrao = lista_opcoes.index(lbl_alvo)

escolha_busca = st.selectbox(
    "🔍 Pesquise por Nome do Jogo ou App ID da Steam:",
    options=lista_opcoes,
    index=indice_padrao,
    help="Digite qualquer letra para filtrar os mais de 3.500 jogos indexados."
)

# Extrai o App ID selecionado
import re
match_id = re.search(r'\(ID:\s*(\d+)\)', escolha_busca)
app_id_selecionado = match_id.group(1) if match_id else None

# 8. Execução da Recomendação e Renderização
if app_id_selecionado:
    node_alvo = f"game_{app_id_selecionado}"
    nome_alvo = titulos.get(app_id_selecionado, f"Jogo {app_id_selecionado}")
    meta_alvo = metadados.get(app_id_selecionado, {})
    pr_alvo = meta_alvo.get('positive_ratio', 80.0)

    # Verificação de Poda Prévia por Qualidade
    if node_alvo not in grafo:
        if pr_alvo < 65.0:
            st.error(f"""
            ### ⚠️ Jogo Excluído por Baixa Aprovação da Comunidade
            O jogo **{nome_alvo}** (App ID: {app_id_selecionado}) possui apenas **{pr_alvo}% de avaliações positivas** na Steam.
            
            **Por que isso acontece?**  
            Para manter a integridade das recomendações e economizar memória computacional, o sistema aplica uma **Poda Prévia de Qualidade**, descartando títulos com aprovação inferior a 65%.
            """)
            if os.path.exists(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_selecionado}/header.jpg"):
                st.image(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_selecionado}/header.jpg", width=300)
        else:
            st.warning(f"O jogo '{nome_alvo}' não foi encontrado no grafo (filtrado no K-Core ou sem tags cadastradas).")
    else:
        # Jogo Válido: Mostra Card de Topo
        comm_alvo_id = comunidades.get(node_alvo, -1)
        comm_info = ROTULOS_FIXOS.get(comm_alvo_id, {"nome": f"Super-Nó {comm_alvo_id}", "subtitulo": ""})
        
        st.markdown("---")
        col_t1, col_t2 = st.columns([1.5, 3.5])
        with col_t1:
            st.image(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id_selecionado}/header.jpg", use_container_width=True)
        with col_t2:
            st.caption("🎯 JOGO ALVO SELECIONADO")
            st.subheader(f"{nome_alvo}")
            c_b1, c_b2, c_b3 = st.columns(3)
            c_b1.info(f"**App ID:** {app_id_selecionado}")
            c_b2.success(f"**Aprovação:** 👍 {pr_alvo}% Positivas")
            c_b3.warning(f"**Super-Nó {comm_alvo_id}:** {comm_info['nome']}")
            st.caption(f"**Gêneros Oficiais:** {', '.join(meta_alvo.get('genres', [])) or 'N/D'} • *{comm_info['subtitulo']}*")

        # Executa a recomendação
        t_ini = time.time()
        with st.spinner("Calculando fluxo de arestas e similaridade semântica..."):
            resultados, top_usuarios = recommender.recomendar_jogos(
                grafo,
                app_id_selecionado,
                comunidades,
                metadados,
                top_k_users=top_k,
                top_n_jogos=10,
                silencioso=True
            )
        t_ms = (time.time() - t_ini) * 1000

        st.markdown(f"### 🏆 Top 10 Recomendações Híbridas *(processado em {t_ms:.1f} ms via {top_k} usuários)*")

        if not resultados:
            st.info("Nenhuma recomendação atendeu ao limiar semântico mínimo de tags (0.20).")
        else:
            max_score = resultados[0][1] if resultados else 1.0
            tags_alvo_set = set(t.lower() for t in meta_alvo.get('tags', []))
            user_nodes = [u[0] if isinstance(u, tuple) else u for u in top_usuarios]

            # Exibe os 10 cards em 2 colunas amplas
            col_esq, col_dir = st.columns(2)
            
            for idx, (node_rec, score) in enumerate(resultados):
                col_atual = col_esq if (idx % 2 == 0) else col_dir
                rec_id = node_rec.replace("game_", "")
                titulo_rec = titulos.get(rec_id, f"Jogo {rec_id}")
                meta_rec = metadados.get(rec_id, {})
                comm_rec_id = comunidades.get(node_rec, -1)
                comm_rec_info = ROTULOS_FIXOS.get(comm_rec_id, {"nome": f"Comunidade {comm_rec_id}", "subtitulo": ""})
                
                afinidade = round((score / max_score) * 100, 1)
                
                # Dados de Diagnóstico
                tags_rec_list = meta_rec.get('tags', [])
                tags_comuns = [t for t in tags_rec_list if t.lower() in tags_alvo_set]
                fator_jaccard, bonus_genero = recommender.jaccard(meta_alvo, meta_rec)
                mesma_comm = (comm_rec_id == comm_alvo_id)
                bonus_comm = 3.0 if mesma_comm else 1.0
                
                devs_alvo = meta_alvo.get('developers', set())
                devs_rec = meta_rec.get('developers', set())
                devs_comuns = list(devs_alvo & devs_rec) if devs_alvo and devs_rec else []
                
                vizinhos_rec = set(grafo.neighbors(node_rec)) if node_rec in grafo else set()
                usuarios_ponte = len([u for u in user_nodes if u in vizinhos_rec])
                pr_rec = meta_rec.get('positive_ratio', 80.0)
                grau_rec = grafo.degree(node_rec) if node_rec in grafo else 0
                fator_grau = round(1.0 / (grau_rec ** 0.35), 4) if grau_rec > 0 else 1.0

                with col_atual:
                    # Header do card com Pódio
                    podium_icon = "🥇 1º Lugar" if idx == 0 else ("🥈 2º Lugar" if idx == 1 else ("🥉 3º Lugar" if idx == 2 else f"{idx+1}º Lugar"))
                    
                    with st.container():
                        st.markdown(f"#### {podium_icon} — {titulo_rec}")
                        c_img, c_info = st.columns([1.2, 2])
                        with c_img:
                            st.image(f"https://cdn.cloudflare.steamstatic.com/steam/apps/{rec_id}/header.jpg", use_container_width=True)
                        with c_info:
                            st.caption(f"App ID: {rec_id} | Score: **{score:.2f}**")
                            st.progress(afinidade / 100.0, text=f"Afinidade: {afinidade}%")
                            
                            if mesma_comm:
                                st.success(f"✓ Mesma Comunidade ({comm_rec_id}: {comm_rec_info['nome'].split('&')[0].strip()})")
                            else:
                                st.info(f"Nó {comm_rec_id}: {comm_rec_info['nome'].split('&')[0].strip()}")
                            
                            st.markdown(f"[🎮 Abrir na Loja Steam ↗](https://store.steampowered.com/app/{rec_id})")

                        # Pop-up / Expander de Explicabilidade Algorítmica
                        with st.expander(f"🔍 Ver Diagnóstico do Score ({score:.2f} pts)"):
                            st.markdown("**Como este score foi calculado?**")
                            
                            col_d1, col_d2 = st.columns(2)
                            with col_d1:
                                st.markdown(f"- **Jaccard Semântico:** `{fator_jaccard*100:.1f}%` ({len(tags_comuns)} tags em comum)")
                                st.markdown(f"- **Super-Nó Louvain:** `{bonus_comm}x` ({'Mesma comunidade' if mesma_comm else 'Comunidade externa'})")
                                st.markdown(f"- **Usuários-Ponte no Grafo:** `{usuarios_ponte} de {len(user_nodes)} jogadores` avaliaram ambos")
                            with col_d2:
                                st.markdown(f"- **Modulador de Gênero:** `{bonus_genero}x` impulso")
                                st.markdown(f"- **Bônus de Estúdio:** `{'+0.10' if devs_comuns else '+0.00'}` ({', '.join(devs_comuns) if devs_comuns else 'Estúdios diferentes'})")
                                st.markdown(f"- **Prior de Qualidade:** `👍 {pr_rec}%` (Fator: {pr_rec/100:.2f}x)")
                                st.markdown(f"- **Atenuação Anti-Hub:** Grau {grau_rec} (`{fator_grau}`)")
                            
                            if tags_comuns:
                                st.caption("Tags compartilhadas: " + " • ".join(tags_comuns[:8]))
                        
                        st.markdown("---")
