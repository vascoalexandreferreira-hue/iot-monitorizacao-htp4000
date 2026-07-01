import paho.mqtt.client as mqtt
import time
import random
import math
import json
from datetime import datetime

# ── Configuração do Broker ──────────────────────────────────────────
BROKER    = "localhost"
PORT      = 1883
INTERVALO = 2.0  # segundos entre publicações

# ── Tópicos MQTT ────────────────────────────────────────────────────
TOPICO_TEMP     = "sensor/temperatura"
TOPICO_VIB      = "sensor/vibracao"
TOPICO_CORRENTE = "sensor/corrente"

# ── Estado interno da simulação ─────────────────────────────────────
t = 0  # contador de tempo (para sinal da vibração)

# ════════════════════════════════════════════════════════════════════
# CAMADA DE PERCEPÇÃO — Modelos de simulação por sensor
# ════════════════════════════════════════════════════════════════════

def simular_temperatura():
    """
    Sensor de temperatura com variação gaussiana (ruído branco).
    """
    base   = 28.0          # temperatura ambiente base (°C)
    ruido  = random.gauss(0, 0.8)   # ruído gaussiano σ=0.8
    drift  = random.uniform(-0.3, 0.3)  # deriva lenta
    valor  = round(base + ruido + drift, 2)
    return {
        "device_id": "simulador_01",
        "temperatura": valor,
        "unidade":   "C",
        "status":    "normal" if 15 < valor < 60 else "aviso",
        "timestamp": datetime.now().isoformat()
    }

def simular_vibracao(t):
    """
    Sensor de vibração (Sinal senoidal + harmónicos + ruído).
    """
    freq_base = 50.0        # frequência (Hz)
    amp       = 3.0 + random.uniform(-0.5, 0.5)  # amplitude base
    sinal = (
        amp * math.sin(2 * math.pi * freq_base * t)
        + 0.4 * amp * math.sin(2 * math.pi * 2 * freq_base * t)
        + random.gauss(0, 0.2)
    )
    rms = round(abs(sinal), 3)
    return {
        "device_id":    "simulador_01",
        "rms_mm_s":     rms,
        "freq_hz":      freq_base,
        "amplitude":    round(amp, 3),
        "status":       "normal" if rms < 4.5 else "aviso",
        "timestamp":    datetime.now().isoformat()
    }

class SimuladorCorrente:
    def __init__(self):
        self.estado_atual_nome = "desligado"
        self.tempo_inicio_estado = datetime.now()
        self.duracao_minima = 30  # 180 segundos por patamar de estado
        
        # Sequência padrão inicial: Desligado -> Vazio -> Carga -> Vazio
        self.sequencia_padrao = ["desligado", "vazio", "carga", "vazio"]
        self.idx_seq = 0

    def gerar_valor(self):
        if self.estado_atual_nome == "desligado":
            # Valores próximos de 0 (Até ao limiar de 2.5 A)
            return round(random.uniform(0.0, 2.49), 3)
        elif self.estado_atual_nome == "vazio":
            # Valores de vazio (De 2.5 A a 20.99 A)
            return round(random.uniform(19, 20.99), 3)
        else:  
            # Valores de carga (De 21 A a 80 A)
            return round(random.uniform(21.0, 50.0), 3)

    def proximo_passo(self):
        # Avalia a transição automática após os 180 segundos estipulados
        if (datetime.now() - self.tempo_inicio_estado).total_seconds() >= self.duracao_minima:
            self.idx_seq += 1
            
            # Se ainda estiver dentro do ciclo obrigatório
            if self.idx_seq < len(self.sequencia_padrao):
                self.estado_atual_nome = self.sequencia_padrao[self.idx_seq]
            else:
                # Fim do ciclo obrigatório. Decide de forma aleatória o próximo estado
                escolha = random.choice(["desligado", "carga"])
                if escolha == "desligado":
                    self.idx_seq = 0  # Reinicia o ciclo completo desde o início
                    self.estado_atual_nome = "desligado"
                else:
                    self.idx_seq = 2  # Salta diretamente para o estado de carga da sequência
                    self.estado_atual_nome = "carga"
            
            self.tempo_inicio_estado = datetime.now()
            print(f"\n[SIMULADOR] Transição de regime -> {self.estado_atual_nome.upper()}")

        corrente = self.gerar_valor()
        
        return {
            "device_id": "simulador_01",
            "corrente_A": corrente,
            "estado_logico": self.estado_atual_nome,
            "thd_pct": round(random.uniform(1.5, 5.0), 2),
            "fator_potencia": round(random.uniform(0.88, 0.98), 3),
            "status": "normal" if corrente < 53.6 else "aviso",
            "timestamp": datetime.now().isoformat()
        }

# ════════════════════════════════════════════════════════════════════
# CAMADA DE REDE — Cliente MQTT (Publisher)
# ════════════════════════════════════════════════════════════════════

def on_connect(client, userdata, flags, rc):
    codigos = {
        0: "Ligado com sucesso",
        1: "Versão de protocolo incorreta",
        2: "Client ID inválido",
        3: "Servidor indisponível",
        4: "Credenciais incorretas",
        5: "Não autorizado"
    }
    print(f"[BROKER] Estado da ligação: {codigos.get(rc, f'Erro: {rc}')}")

def publicar(client, topico, payload_dict):
    payload = json.dumps(payload_dict, ensure_ascii=False)
    result  = client.publish(topico, payload, qos=1, retain=False)
    return result.rc == mqtt.MQTT_ERR_SUCCESS

# ── Inicializar Cliente MQTT ─────────────────────────────────────────
client = mqtt.Client(client_id="publisher_industrial_01", protocol=mqtt.MQTTv311)
client.on_connect = on_connect

print("A ligar ao broker MQTT...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_start()
time.sleep(1)  # Aguarda estabilização da rede

# Instanciar a classe do simulador de corrente
simulador_corrente = SimuladorCorrente()

print("Simulação iniciada — Ctrl+C para parar\n")
print("─" * 70)

# ── Loop Principal de Publicação ─────────────────────────────────────
try:
    while True:
        t += INTERVALO

        # Gerar dados dinâmicos dos 3 sensores
        dados_temp     = simular_temperatura()
        dados_vib      = simular_vibracao(t)
        dados_corrente = simulador_corrente.proximo_passo()

        # Publicar pacotes via MQTT nos tópicos independentes
        ok_t = publicar(client, TOPICO_TEMP,     dados_temp)
        ok_v = publicar(client, TOPICO_VIB,      dados_vib)
        ok_c = publicar(client, TOPICO_CORRENTE, dados_corrente)

        # Retorno de logs no terminal
        st = "OK" if ok_t else "ERRO"
        sv = "OK" if ok_v else "ERRO"
        sc = "OK" if ok_c else "ERRO"

        print(f"[{st}] {TOPICO_TEMP:<20} → {dados_temp['temperatura']} °C ({dados_temp['status']})")
        print(f"[{sv}] {TOPICO_VIB:<20} → {dados_vib['rms_mm_s']} mm/s ({dados_vib['status']})")
        print(f"[{sc}] {TOPICO_CORRENTE:<20} → {dados_corrente['corrente_A']} A [{dados_corrente['estado_logico'].upper()}]")
        print("─" * 70)

        time.sleep(INTERVALO)

except KeyboardInterrupt:
    print("\nSimulador interrompido pelo utilizador.")
    client.loop_stop()
    client.disconnect()