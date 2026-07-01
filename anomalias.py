import mysql.connector
import numpy as np
import os
import json
import time
from datetime import datetime

# A password e o limiar de motor são lidos do config.py (que lê o .env).
from config import DB_CONFIG, CORRENTE_MINIMA_MOTOR

# ── Configuração dos métodos por sensor ─────────────────────────────
# tolerancia_min: variação absoluta da média abaixo da qual ignora anomalias
#                 (usado apenas no modo de recurso / fallback estatístico)
SENSORES = {
    "sensor/temperatura": {"campo": "temperatura", "unidade": "°C",   "janela": 30, "tolerancia_min": 1.0},
    "sensor/vibracao":    {"campo": "rms_mm_s",    "unidade": "mm/s", "janela": 30, "tolerancia_min": 0.5},
    "sensor/corrente":    {"campo": "corrente_A",  "unidade": "A",    "janela": 30, "tolerancia_min": 0.5}
}

# ── Parâmetros das Cartas de Controlo (Fase I) ──────────────────────
K_AVISO   = 2          # AVISO   = LC ± 2σ
K_CRITICO = 3          # CRÍTICO = LC ± 3σ
N_PERSISTENCIA = 10     # nº de leituras consecutivas fora antes de disparar

# ── Limiar de motor desligado ───────────────────────────────────────
# CORRENTE_MINIMA_MOTOR é importado do config.py (ver import no topo).
# Se a corrente mais recente for inferior a este valor, considera-se que
# o motor está parado e suprimem-se todas as anomalias.

# Sensores cujo limite inferior é truncado a 0 (não admitem valores negativos)
TRUNCAR_ZERO = {"sensor/vibracao", "sensor/corrente"}

# Caminho do JSON gerado pela Fase I (mesmo diretório deste ficheiro)
CAMINHO_LIMITES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "limites_fase1.json")

# ── Mapeamento de regimes ───────────────────────────────────────────
# O db_subscriber.py grava na coluna 'status' da corrente o regime de
# funcionamento ("parado", "vazio" ou "carga"). O limites_fase1.json
# define limites por regime usando os nomes "VAZIO" e "TRABALHO".
# Este mapa traduz o regime gravado para a chave do JSON.
# O regime "parado" não tem entrada — nesse caso não se avaliam anomalias.
MAPA_REGIME = {
    "vazio": "VAZIO",
    "carga": "TRABALHO",
}


def conectar():
    return mysql.connector.connect(**DB_CONFIG)


def motor_esta_ligado(cursor):
    """
    Verifica a leitura de corrente mais recente. Devolve True se o motor
    estiver em funcionamento (corrente >= CORRENTE_MINIMA_MOTOR), False se
    estiver desligado ou se não houver leituras de corrente recentes.
    """
    cursor.execute("""
        SELECT corrente_A
        FROM leituras_sensores
        WHERE topico = 'sensor/corrente'
          AND corrente_A IS NOT NULL
        ORDER BY criado_em DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row is None:
        return False  # sem dados de corrente — assume desligado por segurança
    return float(row["corrente_A"]) >= CORRENTE_MINIMA_MOTOR


def carregar_limites_fase1():
    """
    Lê o limites_fase1.json e devolve os limites organizados por regime:
        { "VAZIO":    { "sensor/...": {"LC":.., "sigma":..}, ... },
          "TRABALHO": { "sensor/...": {"LC":.., "sigma":..}, ... } }

    Devolve {} se o ficheiro não existir ou for inválido — nesse caso o
    detector cai no modo de recurso (estatística sobre janela móvel).
    """
    if not os.path.exists(CAMINHO_LIMITES):
        return {}
    try:
        with open(CAMINHO_LIMITES, encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    bloco = dados.get("limites", {})
    limites = {}
    for regime, sensores in bloco.items():
        regime_lim = {}
        for topico, info in sensores.items():
            if "LC" in info and "sigma" in info:
                regime_lim[topico] = {
                    "LC":    float(info["LC"]),
                    "sigma": float(info["sigma"]),
                }
        if regime_lim:
            limites[regime] = regime_lim
    return limites


def detetar_regime_atual(cursor):
    """
    Lê o 'status' da leitura de corrente mais recente, que o db_subscriber.py
    gravou como o regime de funcionamento ("parado"/"vazio"/"carga").
    Devolve a chave de regime do JSON ("VAZIO"/"TRABALHO") ou None se o
    regime atual não tiver limites associados (ex.: "parado").
    """
    cursor.execute("""
        SELECT status
        FROM leituras_sensores
        WHERE topico = 'sensor/corrente'
          AND status IS NOT NULL
        ORDER BY criado_em DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row is None or row["status"] is None:
        return None
    regime_gravado = str(row["status"]).lower()
    return MAPA_REGIME.get(regime_gravado)


def avaliar_nivel_fase1(valor, lc, sigma, truncar_zero):
    """
    Classifica um valor face aos limites da Fase I.
    Devolve (nivel, k_usado, lim_sup, lim_inf) ou (None, ...) se estiver dentro.
    CRÍTICO tem prioridade sobre AVISO.
    """
    lsc3 = lc + K_CRITICO * sigma
    lic3 = lc - K_CRITICO * sigma
    lsc2 = lc + K_AVISO * sigma
    lic2 = lc - K_AVISO * sigma
    if truncar_zero:
        lic3 = max(0.0, lic3)
        lic2 = max(0.0, lic2)

    if valor > lsc3 or valor < lic3:
        return "CRITICO", K_CRITICO, lsc3, lic3
    if valor > lsc2 or valor < lic2:
        return "AVISO", K_AVISO, lsc2, lic2
    return None, None, None, None


def detectar_por_fase1(cursor, conn, topico, cfg, limites_sensor):
    """
    Deteção baseada nos limites fixos da Fase I, com persistência:
    só dispara se as últimas N_PERSISTENCIA leituras estiverem TODAS fora
    do mesmo nível (ou pior). Devolve 1 se gerou alerta, 0 caso contrário.
    """
    campo   = cfg["campo"]
    lc      = limites_sensor["LC"]
    sigma   = limites_sensor["sigma"]
    truncar = topico in TRUNCAR_ZERO

    if sigma <= 0:
        return 0  # baseline degenerado — não dá para calcular limites

    cursor.execute(f"""
        SELECT id, device_id, {campo} AS valor, criado_em
        FROM leituras_sensores
        WHERE topico = %s
          AND {campo} IS NOT NULL
        ORDER BY criado_em DESC
        LIMIT %s
    """, (topico, N_PERSISTENCIA))
    rows = cursor.fetchall()

    if len(rows) < N_PERSISTENCIA:
        return 0  # ainda não há leituras suficientes para confirmar persistência

    niveis = []
    for r in rows:
        nivel, _, _, _ = avaliar_nivel_fase1(float(r["valor"]), lc, sigma, truncar)
        niveis.append(nivel)

    # Persistência: todas as N têm de estar fora (nível não-nulo)
    if any(n is None for n in niveis):
        return 0

    nivel_final = "CRITICO" if all(n == "CRITICO" for n in niveis) else "AVISO"

    ultima      = rows[0]
    valor_atual = float(ultima["valor"])
    k_usado     = K_CRITICO if nivel_final == "CRITICO" else K_AVISO
    lim_sup     = lc + k_usado * sigma
    lim_inf     = lc - k_usado * sigma
    if truncar:
        lim_inf = max(0.0, lim_inf)

    mensagem = (
        f"ANOMALIA [Carta Fase I] {topico.split('/')[1].upper()}: "
        f"valor {round(valor_atual, 3)} {cfg['unidade']} "
        f"fora de {k_usado}sigma por {N_PERSISTENCIA} leituras "
        f"| LC={round(lc,3)} | limites [{round(lim_inf,3)}, {round(lim_sup,3)}]"
    )

    cursor.execute("""
        SELECT COUNT(*) AS n FROM alertas
        WHERE device_id = %s
          AND topico = %s
          AND nivel = %s
          AND mensagem LIKE %s
          AND criado_em >= NOW() - INTERVAL 60 SECOND
    """, (ultima["device_id"], topico, nivel_final, "%Carta Fase I%"))

    if cursor.fetchone()["n"] == 0:
        cursor.execute("""
            INSERT INTO alertas (device_id, topico, nivel, mensagem, valor, limiar)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            ultima["device_id"], topico, nivel_final, mensagem,
            valor_atual, round(lim_sup, 3)
        ))
        conn.commit()
        print(f"[ANOMALIA {nivel_final}] {mensagem}")
        return 1
    return 0


def detectar_por_estatistica(cursor, conn, topico, cfg):
    """
    MODO DE RECURSO (fallback) — usado quando ainda não há limites da Fase I.
    Mantém a lógica original: Z-score + IQR sobre janela móvel, com filtro
    de tolerância mínima. Devolve 1 se gerou alerta, 0 caso contrário.
    """
    campo          = cfg["campo"]
    janela         = cfg["janela"]
    tolerancia_min = cfg["tolerancia_min"]

    cursor.execute(f"""
        SELECT id, device_id, {campo} AS valor, criado_em
        FROM leituras_sensores
        WHERE topico = %s
          AND {campo} IS NOT NULL
        ORDER BY criado_em DESC
        LIMIT %s
    """, (topico, janela))
    rows = cursor.fetchall()
    if len(rows) < 10:
        return 0

    valores     = np.array([float(r["valor"]) for r in rows])
    ultima      = rows[0]
    valor_atual = float(ultima["valor"])

    media   = np.mean(valores)
    desvio  = np.std(valores)
    z_score = abs((valor_atual - media) / desvio) if desvio > 0 else 0

    q1, q3     = np.percentile(valores, [25, 75])
    iqr        = q3 - q1
    limite_inf = q1 - 1.5 * iqr
    limite_sup = q3 + 1.5 * iqr
    outlier_iqr = valor_atual < limite_inf or valor_atual > limite_sup

    if abs(valor_atual - media) < tolerancia_min:
        return 0

    anomalia = False
    metodo   = None
    nivel    = None
    if z_score > 3.0:
        anomalia = True
        metodo   = "Z-score"
        nivel    = "CRITICO" if z_score > 4.0 else "AVISO"
    elif outlier_iqr:
        anomalia = True
        metodo   = "IQR"
        nivel    = "AVISO"

    if not anomalia:
        return 0

    mensagem = (
        f"ANOMALIA [{metodo}] {topico.split('/')[1].upper()}: "
        f"valor {round(valor_atual, 3)} {cfg['unidade']} "
        f"| Z={round(z_score, 2)} | IQR [{round(limite_inf,2)}, {round(limite_sup,2)}]"
    )

    cursor.execute("""
        SELECT COUNT(*) AS n FROM alertas
        WHERE device_id = %s
          AND topico = %s
          AND mensagem LIKE %s
          AND criado_em >= NOW() - INTERVAL 60 SECOND
    """, (ultima["device_id"], topico, f"%ANOMALIA%{metodo}%"))

    if cursor.fetchone()["n"] == 0:
        cursor.execute("""
            INSERT INTO alertas (device_id, topico, nivel, mensagem, valor, limiar)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            ultima["device_id"], topico, nivel, mensagem,
            valor_atual, round(float(media + 3 * desvio), 3)
        ))
        conn.commit()
        print(f"[ANOMALIA {nivel}] {mensagem}")
        return 1
    return 0


def detectar_anomalias():
    conn   = conectar()
    cursor = conn.cursor(dictionary=True)
    total_anomalias = 0

    # Se o motor estiver desligado, não analisa nenhuma anomalia
    if not motor_esta_ligado(cursor):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Motor desligado — anomalias suprimidas.")
        cursor.close()
        conn.close()
        return

    # Recarregar os limites da Fase I a cada ciclo (permite atualizar o JSON
    # sem reiniciar o detector)
    limites_por_regime = carregar_limites_fase1()

    if limites_por_regime:
        # Modo Fase I — seleciona o conjunto de limites conforme o regime atual
        regime = detetar_regime_atual(cursor)

        if regime is None or regime not in limites_por_regime:
            # Regime sem limites (ex.: "parado") ou indeterminado — não avalia
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Regime sem limites aplicáveis — anomalias não avaliadas.")
            cursor.close()
            conn.close()
            return

        limites_sensores = limites_por_regime[regime]
        for topico, cfg in SENSORES.items():
            if topico in limites_sensores:
                total_anomalias += detectar_por_fase1(
                    cursor, conn, topico, cfg, limites_sensores[topico]
                )
            else:
                total_anomalias += detectar_por_estatistica(cursor, conn, topico, cfg)

        if total_anomalias == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Sem anomalias detectadas. (regime: {regime})")
    else:
        # Modo de recurso — sem limites da Fase I, usa Z-score/IQR
        for topico, cfg in SENSORES.items():
            total_anomalias += detectar_por_estatistica(cursor, conn, topico, cfg)

        if total_anomalias == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Sem anomalias detectadas. (modo: recurso Z-score/IQR)")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    limites = carregar_limites_fase1()
    print("Detector de anomalias iniciado — verifica de 5 em 5 segundos")
    if limites:
        regimes = ", ".join(limites.keys())
        print(f"Limites Fase I: CARREGADOS (regimes: {regimes})\n")
    else:
        print("Limites Fase I: ausentes (modo de recurso Z-score/IQR)\n")
    try:
        while True:
            detectar_anomalias()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nDetector de anomalias terminado.")
