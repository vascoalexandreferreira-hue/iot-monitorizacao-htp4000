import paho.mqtt.client as mqtt
import time
import random
import json
from datetime import datetime

# ════════════════════════════════════════════════════════════════════
# PUBLISHER "NORMAL" — Cenário de demonstração SEM alertas
# ════════════════════════════════════════════════════════════════════
# Ao contrário do publisher.py (que gera dados que se desviam da
# assinatura real e por isso disparam anomalias), este simulador gera
# os três sensores COORDENADOS pelo mesmo regime de funcionamento e
# centrados nos valores de baseline da Fase I (limites_fase1.json).
#
# Resultado: as leituras caem dentro das cartas de controlo de cada
# regime, demonstrando o sistema em funcionamento normal e estável.
#
# Use este publisher para mostrar o sistema "sereno"; use o publisher.py
# original para demonstrar a deteção de anomalias.
# ════════════════════════════════════════════════════════════════════

# ── Configuração do Broker ──────────────────────────────────────────
BROKER    = "localhost"
PORT      = 1883
INTERVALO = 2.0  # segundos entre publicações

# ── Tópicos MQTT ────────────────────────────────────────────────────
TOPICO_TEMP     = "sensor/temperatura"
TOPICO_VIB      = "sensor/vibracao"
TOPICO_CORRENTE = "sensor/corrente"

# ── Baseline da Fase I (LC e sigma por regime) ──────────────────────
# Valores extraídos do limites_fase1.json. Cada sensor é gerado com uma
# gaussiana centrada no LC, com desvio = sigma/2 para ficar folgadamente
# dentro dos limites de 2σ (que disparam o nível de AVISO).
BASELINE = {
    "VAZIO": {
        "temperatura": {"lc": 35.193, "sigma": 2.4965},
        "vibracao":    {"lc": 1.167,  "sigma": 0.4439},
        "corrente":    {"lc": 19.638, "sigma": 0.5037},
    },
    "TRABALHO": {
        "temperatura": {"lc": 35.408, "sigma": 3.4886},
        "vibracao":    {"lc": 1.940,  "sigma": 0.4816},
        "corrente":    {"lc": 35.725, "sigma": 8.6411},
    },
}

# Fração do sigma usada como dispersão na simulação.
# 0.4 → leituras concentram-se a ~±0.8σ no máximo, bem dentro dos 2σ.
FATOR_DISPERSAO = 0.4

# Limiares de regime (coerentes com db_subscriber.py e dashboard.html)
LIMIAR_LIGADO = 2.5   # A
LIMIAR_CARGA  = 21.0  # A


# ════════════════════════════════════════════════════════════════════
# Máquina de estados — decide o regime e mantém-no durante um período
# ════════════════════════════════════════════════════════════════════
class MaquinaRegime:
    def __init__(self):
        # Sequência de demonstração: vazio → trabalho → vazio → trabalho ...
        # (não inclui "desligado" para manter a monitorização sempre ativa;
        #  se quiseres incluir paragens, acrescenta "DESLIGADO" à sequência)
        self.sequencia = ["VAZIO", "TRABALHO"]
        self.idx = 0
        self.regime = self.sequencia[0]
        self.inicio_estado = datetime.now()
        self.duracao = 60  # segundos em cada regime antes de transitar

    def atualizar(self):
        if (datetime.now() - self.inicio_estado).total_seconds() >= self.duracao:
            self.idx = (self.idx + 1) % len(self.sequencia)
            self.regime = self.sequencia[self.idx]
            self.inicio_estado = datetime.now()
            print(f"\n[SIMULADOR] Transição de regime -> {self.regime}")
        return self.regime


# ════════════════════════════════════════════════════════════════════
# Geração de valores centrados no baseline do regime
# ════════════════════════════════════════════════════════════════════
def gerar_valor(regime, sensor):
    """Gera um valor gaussiano centrado no LC do regime, com dispersão
    controlada (sigma * FATOR_DISPERSAO) para ficar dentro dos limites."""
    base = BASELINE[regime][sensor]
    valor = random.gauss(base["lc"], base["sigma"] * FATOR_DISPERSAO)
    return valor


def gerar_corrente_no_regime(regime):
    """A corrente define o regime, por isso tem de cair na banda correta.
    Gera centrada no LC mas com guarda extra para não cruzar a fronteira
    de regime (o que mudaria a classificação a jusante)."""
    base = BASELINE[regime]["corrente"]
    valor = random.gauss(base["lc"], base["sigma"] * FATOR_DISPERSAO)

    if regime == "VAZIO":
        # Manter folgadamente entre LIMIAR_LIGADO e LIMIAR_CARGA
        valor = max(LIMIAR_LIGADO + 0.5, min(valor, LIMIAR_CARGA - 0.2))
    elif regime == "TRABALHO":
        # Manter acima da fronteira de carga
        valor = max(LIMIAR_CARGA + 0.5, valor)

    return valor


def construir_pacote_temp(regime):
    valor = round(gerar_valor(regime, "temperatura"), 2)
    return {
        "device_id":   "simulador_normal_01",
        "temperatura": valor,
        "unidade":     "C",
        "status":      "normal",
        "timestamp":   datetime.now().isoformat(),
    }


def construir_pacote_vib(regime):
    valor = max(0.0, round(gerar_valor(regime, "vibracao"), 3))
    return {
        "device_id": "simulador_normal_01",
        "rms_mm_s":  valor,
        "freq_hz":   50.0,
        "amplitude": valor,
        "status":    "normal",
        "timestamp": datetime.now().isoformat(),
    }


def construir_pacote_corrente(regime):
    valor = round(gerar_corrente_no_regime(regime), 3)
    return {
        "device_id":      "simulador_normal_01",
        "corrente_A":     valor,
        "thd_pct":        round(random.uniform(1.5, 5.0), 2),
        "fator_potencia": round(random.uniform(0.88, 0.98), 3),
        # O status é deixado a cargo do db_subscriber.py, que reclassifica
        # a corrente em regime (parado/vazio/carga). Enviamos "normal".
        "status":         "normal",
        "timestamp":      datetime.now().isoformat(),
    }


# ════════════════════════════════════════════════════════════════════
# Cliente MQTT
# ════════════════════════════════════════════════════════════════════
def on_connect(client, userdata, flags, rc):
    estado = "Ligado com sucesso" if rc == 0 else f"Erro: {rc}"
    print(f"[BROKER] Estado da ligação: {estado}")


def publicar(client, topico, payload_dict):
    payload = json.dumps(payload_dict, ensure_ascii=False)
    result  = client.publish(topico, payload, qos=1, retain=False)
    return result.rc == mqtt.MQTT_ERR_SUCCESS


client = mqtt.Client(client_id="publisher_normal_01", protocol=mqtt.MQTTv311)
client.on_connect = on_connect

print("A ligar ao broker MQTT...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
time.sleep(1)

maquina = MaquinaRegime()

print("Simulação NORMAL iniciada — Ctrl+C para parar")
print("Gera dados coordenados dentro dos limites da Fase I (sem alertas)\n")
print("─" * 70)

try:
    while True:
        regime = maquina.atualizar()

        dados_temp     = construir_pacote_temp(regime)
        dados_vib      = construir_pacote_vib(regime)
        dados_corrente = construir_pacote_corrente(regime)

        ok_t = publicar(client, TOPICO_TEMP,     dados_temp)
        ok_v = publicar(client, TOPICO_VIB,      dados_vib)
        ok_c = publicar(client, TOPICO_CORRENTE, dados_corrente)

        st = "OK" if ok_t else "ERRO"
        sv = "OK" if ok_v else "ERRO"
        sc = "OK" if ok_c else "ERRO"

        print(f"[{regime:8}] "
              f"T={dados_temp['temperatura']:>5} °C [{st}]  "
              f"V={dados_vib['rms_mm_s']:>5} mm/s [{sv}]  "
              f"I={dados_corrente['corrente_A']:>6} A [{sc}]")

        time.sleep(INTERVALO)

except KeyboardInterrupt:
    print("\nSimulador normal interrompido pelo utilizador.")
    client.loop_stop()
    client.disconnect()
