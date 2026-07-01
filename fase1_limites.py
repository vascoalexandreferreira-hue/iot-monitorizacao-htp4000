# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
 FASE I — Estabelecimento dos Limites de Controlo e Escalas Fixas do Eixo Y
═══════════════════════════════════════════════════════════════════════════

 Projeto: Monitorização de Condição e Manutenção Preditiva — HTP-4000 (Mx01)
 Disciplina: Manutenção Industrial — ISVOUGA

 OBJETIVO
 --------
 Recebe ficheiros Excel exportados pelo dashboard, sincroniza os dados
 através do Timestamp, e separa as leituras nos estados reais da máquina
 (VAZIO e TRABALHO) baseando-se na Corrente.

 Metodologia em duas etapas (aplicada a cada estado isoladamente):
   1) LIMPEZA (Machine Learning): modelo Isolation Forest para remover ruído.
   2) CÁLCULO DOS LIMITES (Shewhart): Cálculo de LC, LSC, LIC e Eixos Y Fixos.

 O resultado é um JSON com dupla estrutura ("TRABALHO" e "VAZIO"), 
 contendo limites fixos e eixos Y estáticos para evitar auto-scaling.
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import argparse
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# ── Configuração de Estados e Sensores ───────────────────────────────────
LIMIAR_LIGADO = 2.5   # A — Abaixo disto ignora-se (máquina desligada)
LIMIAR_CARGA  = 21.0  # A — Fronteira entre rodar em Vazio e rodar em Trabalho

SENSORES = [
    {"folha": "Temperatura", "topico": "sensor/temperatura", "nome": "Temperatura", "unidade": "°C",   "truncar_zero": False},
    {"folha": "Vibracao",    "topico": "sensor/vibracao",    "nome": "Vibração",    "unidade": "mm/s", "truncar_zero": True},
    {"folha": "Corrente",    "topico": "sensor/corrente",    "nome": "Corrente",    "unidade": "A",    "truncar_zero": True},
]


def carregar_e_sincronizar_dados(caminhos):
    """
    Lê as folhas do Excel, alinha os sensores ao segundo (Timestamp)
    e cria uma coluna de 'Estado' baseada na Corrente.
    """
    dfs = []
    for caminho in caminhos:
        try:
            xls = pd.ExcelFile(caminho)
            df_sync = None

            for s in SENSORES:
                if s["folha"] in xls.sheet_names:
                    df_temp = pd.read_excel(xls, sheet_name=s["folha"])
                    if len(df_temp.columns) < 3: continue

                    # Assume Coluna 0 = Timestamp | Coluna 2 = Valor
                    col_tempo = df_temp.columns[0]
                    col_valor = df_temp.columns[2]

                    df_s = df_temp[[col_tempo, col_valor]].copy()
                    df_s.columns = ['hora_str', s['topico']]

                    # Converte para datetime e arredonda ao segundo
                    df_s['Timestamp'] = pd.to_datetime(df_s['hora_str'], errors='coerce').dt.floor('s')
                    df_s = df_s.dropna(subset=['Timestamp', s['topico']])

                    # Agrupa pelo segundo exato (média se houver >1 leitura no mesmo segundo)
                    df_s = df_s.groupby('Timestamp')[s['topico']].mean().reset_index()

                    if df_sync is None:
                        df_sync = df_s
                    else:
                        df_sync = pd.merge(df_sync, df_s, on='Timestamp', how='outer')

            if df_sync is not None and not df_sync.empty:
                dfs.append(df_sync)
        except Exception as e:
            print(f"  ⚠ Erro ao ler {caminho}: {e}")

    if not dfs:
        return pd.DataFrame()

    # Junta todos os ficheiros, ordena por tempo e preenche pequenas falhas de milissegundos
    df_final = pd.concat(dfs, ignore_index=True).sort_values('Timestamp')
    df_final = df_final.set_index('Timestamp').ffill(limit=2).dropna(subset=['sensor/corrente']).reset_index()

    # Classifica o estado de cada linha
    def classificar_estado(c):
        if c < LIMIAR_LIGADO: return "DESLIGADO"
        elif c <= LIMIAR_CARGA: return "VAZIO"
        else: return "TRABALHO"

    df_final['Estado'] = df_final['sensor/corrente'].apply(classificar_estado)
    return df_final


def limpar_baseline_ml(valores, contaminacao):
    """Etapa 1 — Limpeza por ML (Isolation Forest)"""
    if len(valores) < 10:
        return valores, np.ones(len(valores), dtype=bool), 0

    X = valores.reshape(-1, 1)
    modelo = IsolationForest(contamination=contaminacao, random_state=42, n_estimators=200)
    pred = modelo.fit_predict(X) 
    mascara = pred == 1
    n_removidos = int((~mascara).sum())
    return valores[mascara], mascara, n_removidos


def calcular_limites_spc(valores, k, truncar_zero):
    """Etapa 2 — Cálculo SPC Clássico (Shewhart) com limites fixos de Eixo Y"""
    lc    = float(np.mean(valores))
    sigma = float(np.std(valores, ddof=1))
    lsc   = lc + k * sigma
    lic   = lc - k * sigma
    
    if truncar_zero and lic < 0:
        lic = 0.0

    # ── CÁLCULO DA ESCALA Y FIXA (Margem de visualização estável de 20%) ──
    # Evita que a linha do LSC cole no topo superior do gráfico
    intervalo = lsc - lic if (lsc - lic) > 0 else lc * 0.2
    y_max = lsc + (intervalo * 0.2)
    y_min = lic - (intervalo * 0.2)
    
    if truncar_zero and y_min < 0:
        y_min = 0.0

    return {
        "LC":     round(lc, 4),
        "LSC":    round(lsc, 4),
        "LIC":    round(lic, 4),
        "y_min":  round(y_min, 4),  # Injetado para controlo fixo do eixo Y no Dashboard
        "y_max":  round(y_max, 4),  # Injetado para controlo fixo do eixo Y no Dashboard
        "sigma":  round(sigma, 5),
        "n":      int(len(valores)),
    }


def analisar(caminhos, k, contaminacao):
    print("═" * 70)
    print("  FASE I — GERAÇÃO DE LIMITES E ESCALAS FIXAS Y")
    print("═" * 70)
    
    df_dados = carregar_e_sincronizar_dados(caminhos)
    if df_dados.empty:
        print("✗ Erro: Nenhum dado válido foi sincronizado. Verifique as folhas do Excel.")
        return None, None

    estados_alvo = ["TRABALHO", "VAZIO"]
    json_export = {"disponivel": True, "limites": {"TRABALHO": {}, "VAZIO": {}}}
    linhas_excel = []

    for estado in estados_alvo:
        df_estado = df_dados[df_dados['Estado'] == estado]
        print(f"\n▼ PROCESSANDO ESTADO: {estado} ({len(df_estado)} registos sincronizados)")
        
        if df_estado.empty:
            print("  ↳ Sem dados para este estado no ficheiro fornecido.")
            continue

        for s in SENSORES:
            valores_brutos = df_estado[s['topico']].dropna().values
            if len(valores_brutos) == 0:
                continue

            limpos, _, n_rem = limpar_baseline_ml(valores_brutos, contaminacao)
            limites_finais = calcular_limites_spc(limpos, k, s["truncar_zero"])

            # Grava no objeto JSON mantendo compatibilidade total com as tuas chaves
            json_export["limites"][estado][s["topico"]] = limites_finais

            # Guarda para o Excel corporativo/relatório
            linhas_excel.append({
                "Estado": estado,
                "Sensor": s["nome"],
                "Unidade": s["unidade"],
                "LC (final)": limites_finais["LC"],
                "LSC (final)": limites_finais["LSC"],
                "LIC (final)": limites_finais["LIC"],
                "Y Mínimo (Fixo)": limites_finais["y_min"],
                "Y Máximo (Fixo)": limites_finais["y_max"],
                "σ (final)": limites_finais["sigma"],
                "N (limpos)": limites_finais["n"],
                "Outliers Rem.": n_rem,
            })

            print(f"  {s['nome']:<12} | LC: {limites_finais['LC']:<7} | Escala Y Fixa: [{limites_finais['y_min']} a {limites_finais['y_max']}]")

    df_excel = pd.DataFrame(linhas_excel) if linhas_excel else None
    return json_export, df_excel


def main():
    parser = argparse.ArgumentParser(description="Fase I — Limites de Controlo e Escalas Estáticas Y")
    parser.add_argument("ficheiros", nargs="+", help="Ficheiro(s) Excel exportado(s) pelo dashboard")
    parser.add_argument("--k", type=float, default=3.0, help="Fator sigma dos limites (default 3)")
    parser.add_argument("--contaminacao", type=float, default=0.02, help="Fração de outliers (default 0.02)")
    parser.add_argument("--saida-json", default="limites_fase1.json")
    parser.add_argument("--saida-xlsx", default="limites_fase1.xlsx")
    args = parser.parse_args()

    json_export, df_excel = analisar(args.ficheiros, args.k, args.contaminacao)

    if not json_export or df_excel is None:
        print("\n✗ Falha: Verifique os ficheiros de entrada (formato ou conteúdo vazio).")
        sys.exit(1)

    # Exportar JSON para o Dashboard ler de forma assíncrona
    with open(args.saida_json, "w", encoding="utf-8") as f:
        json.dump(json_export, f, indent=2, ensure_ascii=False)

    # Exportar Excel para validação de engenharia
    df_excel.to_excel(args.saida_xlsx, index=False, sheet_name="Limites_Fase_I")

    print("\n" + "═" * 70)
    print(f"✓ Ficheiro {args.saida_json} gerado com sucesso!")
    print(f"✓ Ficheiro {args.saida_xlsx} gerado com sucesso!")
    print("O Dashboard lerá agora o y_min e y_max estáticos para fixar o eixo Y.")
    print("═" * 70)


if __name__ == "__main__":
    main()