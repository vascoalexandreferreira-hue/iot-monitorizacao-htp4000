import mysql.connector
import time
from datetime import datetime

# ── Configuração da Base de Dados ─────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "super.",
    "database": "iot_sensores"
}

# ── Âmbito deste monitor ──────────────────────────────────────────────
# Este monitor trata apenas dos alertas de TEMPERATURA e VIBRAÇÃO, cujo
# estado ("normal"/"aviso"/"alerta"/"sobrecarga") é reportado pelo ESP32
# na coluna 'status'.
#
# A deteção de anomalias da CORRENTE é da responsabilidade do anomalias.py,
# que aplica controlo estatístico do processo (cartas da Fase I) com lógica
# de regime de funcionamento e persistência. A corrente é deliberadamente
# excluída deste monitor para evitar duplicação e porque, na corrente, a
# coluna 'status' passou a registar o regime (parado/vazio/carga) e não um
# estado de alerta.


def conectar():
    return mysql.connector.connect(**DB_CONFIG)


# ── Lógica de Verificação (Baseada no estado do Arduino) ──────────────
def verificar_alertas():
    conn   = conectar()
    cursor = conn.cursor(dictionary=True)
    alertas_gerados = 0

    # Vai buscar as leituras dos últimos 10 segundos
    cursor.execute("""
        SELECT device_id, topico, temperatura, rms_mm_s, corrente_A, status, criado_em
        FROM leituras_sensores
        WHERE criado_em >= NOW() - INTERVAL 10 SECOND
        ORDER BY criado_em DESC
    """)
    leituras = cursor.fetchall()

    for leitura in leituras:
        topico = leitura["topico"]
        estado_arduino = leitura["status"]

        # Se o Arduino disse que está tudo bem (ou se não enviou estado), ignora
        if not estado_arduino or estado_arduino == "normal":
            continue

        # Configura as variáveis dependendo do sensor.
        # A corrente é tratada pelo anomalias.py e ignorada aqui.
        if "temperatura" in topico:
            valor = leitura.get("temperatura")
            unidade = "°C"
            sensor_nome = "TEMPERATURA"
        elif "vibracao" in topico:
            valor = leitura.get("rms_mm_s")
            unidade = "mm/s"
            sensor_nome = "VIBRAÇÃO"
        else:
            continue

        # O Arduino envia "aviso", "alerta" ou "sobrecarga"
        # Mapeamos isso para os níveis da base de dados (AVISO ou CRITICO)
        if estado_arduino == "aviso":
            nivel = "AVISO"
        else:
            nivel = "CRITICO"

        mensagem = f"{sensor_nome}: valor {valor} {unidade} (Estado reportado: {estado_arduino.upper()})"

        # Verifica se já gerámos um alerta igual nos últimos 30 segundos (evita spam)
        cursor.execute("""
            SELECT COUNT(*) AS n FROM alertas
            WHERE device_id = %s AND topico = %s AND nivel = %s
            AND criado_em >= NOW() - INTERVAL 30 SECOND
        """, (leitura["device_id"], topico, nivel))

        if cursor.fetchone()["n"] == 0:
            # Insere o novo alerta (o limiar fica a 0 pois a matemática ficou no ESP32)
            cursor.execute("""
                INSERT INTO alertas (device_id, topico, nivel, mensagem, valor, limiar)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (leitura["device_id"], topico, nivel, mensagem, valor, 0))

            conn.commit()
            prefixo = "[CRITICO]" if nivel == "CRITICO" else "[AVISO]  "
            print(f"{prefixo} {mensagem}")
            alertas_gerados += 1

    if alertas_gerados == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Tudo normal — sem alertas.")

    cursor.close()
    conn.close()


# ── Loop Principal ────────────────────────────────────────────────────
print("Monitor de alertas iniciado — verifica de 5 em 5 segundos\n")
try:
    while True:
        verificar_alertas()
        time.sleep(5)
except KeyboardInterrupt:
    print("\nMonitor de alertas terminado.")
