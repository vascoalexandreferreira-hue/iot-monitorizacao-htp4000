# -*- coding: utf-8 -*-
import paho.mqtt.client as mqtt
import mysql.connector
import json
import time
from datetime import datetime

# ── Configuração MQTT ────────────────────────────────────────────────
BROKER          = "localhost"
PORT            = 1883
TOPICO_WILDCARD = "sensor/#"

# ── Configuração MySQL ───────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "super.",
    "database": "iot_sensores"
}

# Limiares do motor para classificação automática de regime
# Coerentes com o dashboard.html (LIMIAR_LIGADO=2.5, LIMIAR_CARGA=21.0):
#   corrente <  2.5 A  -> "parado"   (sem limites; anomalias não avaliadas)
#   2.5 a 21 A         -> "vazio"    (limites do regime VAZIO)
#   >= 21 A            -> "carga"    (limites do regime TRABALHO)
REGIME_LIMIAR_PARADO = 2.5    # A
REGIME_LIMIAR_CARGA  = 21.0   # A

def classificar_regime(corrente):
    """Devolve o regime de funcionamento a partir do valor de corrente (A)."""
    if corrente is None:
        return None
    try:
        i = float(corrente)
    except (TypeError, ValueError):
        return None
    if i < REGIME_LIMIAR_PARADO:
        return "parado"
    if i < REGIME_LIMIAR_CARGA:
        return "vazio"
    return "carga"

# ── Execução de Queries com Auto-Reconexão Segura ────────────────────
def executar_insert_seguro(sql, valores):
    """Abre, executa e fecha a conexão à BD de forma isolada e segura para evitar quedas noturnas."""
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(sql, valores)
        conn.commit()
        return True
    except mysql.connector.Error as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [BD] Erro na inserção/conexão: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ── Inserir leitura na BD ────────────────────────────────────────────
def inserir_leitura(topico, dados):
    # Parsear timestamp de forma segura
    ts_raw = dados.get("timestamp")
    if ts_raw is None or isinstance(ts_raw, (int, float)):
        ts = datetime.now()
    else:
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except ValueError:
            ts = datetime.now()

    sql = """
        INSERT INTO leituras_sensores (
            device_id, topico,
            temperatura,
            rms_mm_s, freq_hz, amplitude,
            corrente_A, thd_pct, fator_potencia,
            status, timestamp_sensor
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    status_original = dados.get("status")
    if "corrente" in topico and dados.get("corrente_A") is not None:
        regime = classificar_regime(dados.get("corrente_A"))
        status_a_gravar = regime if regime is not None else status_original
    else:
        status_a_gravar = status_original

    valores = (
        dados.get("device_id", "HTP-4000"),
        topico,
        dados.get("temperatura"),
        dados.get("rms_mm_s"),
        dados.get("freq_hz"),
        dados.get("amplitude"),
        dados.get("corrente_A"),
        dados.get("thd_pct"),
        dados.get("fator_potencia"),
        status_a_gravar,
        ts
    )

    if executar_insert_seguro(sql, valores):
        # Apenas um pequeno output para saberes que está vivo
        print(f"[{ts.strftime('%H:%M:%S')}] Registado → {topico} | {status_a_gravar}")

# ── Callbacks MQTT ───────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPICO_WILDCARD, qos=1)
        print(f"\n[MQTT] Ligado ao broker Mosquitto — A escutar: {TOPICO_WILDCARD}")
    else:
        print(f"[MQTT] Falha na ligação. Código de erro: {rc}")

def on_message(client, userdata, msg):
    topico = msg.topic
    try:
        dados = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[MQTT] Payload inválido detetado em {topico}")
        return
        
    inserir_leitura(topico, dados)

def on_disconnect(client, userdata, rc):
    agora = datetime.now().strftime('%H:%M:%S')
    print(f"[{agora}] [MQTT] Conexão perdida com o Mosquitto (Código: {rc}).")
    if rc != 0:
        print("[MQTT] O cliente tentará restabelecer a ligação automaticamente...")

# ── Iniciar Serviço Principal ────────────────────────────────────────
if __name__ == "__main__":
    print("═" * 70)
    print("  INICIANDO SUBSCRITOR IOT INDUSTRIAL — PROLEITE (V7)")
    print("═" * 70)

    client = mqtt.Client(client_id="db_subscriber_01", protocol=mqtt.MQTTv311, clean_session=False)
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    # Loop principal blindado
    while True:
        try:
            client.connect(BROKER, PORT, keepalive=60)
            client.loop_forever() # Mantém o programa a correr e gere reconexões nativas
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Rede] Falha crítica: {e}. Nova tentativa em 5 segundos...")
            time.sleep(5)