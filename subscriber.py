import paho.mqtt.client as mqtt
import json

BROKER = "localhost"
PORT   = 1883

# Wildcard — subscreve todos os tópicos sob "sensor/"
TOPICO_WILDCARD = "sensor/#"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(TOPICO_WILDCARD, qos=1)
        print(f"Subscriber ligado — a escutar: {TOPICO_WILDCARD}\n")
        print(f"{'Tópico':<28} {'Payload'}")
        print("─" * 70)

def on_message(client, userdata, msg):
    topico = msg.topic
    try:
        dados = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[ERRO] Payload inválido em {topico}")
        return

    # Formatar saída consoante o tópico
    if "temperatura" in topico:
        print(f"[TEMP]   {topico:<28} {dados['temperatura']} °C  [{dados['status']}]")

    elif "vibracao" in topico:
        print(f"[VIB]    {topico:<28} {dados['rms_mm_s']} mm/s  freq={dados['freq_hz']} Hz  [{dados['status']}]")

    elif "corrente" in topico:
        # Adicionamos a leitura do estado_logico enviado pelo simulador
        estado = dados.get('estado_logico', 'N/A')
        print(f"[CURR]   {topico:<28} {dados['corrente_A']} A  {estado.upper()}  THD={dados['thd_pct']}%  [{dados['status']}]")
    else:
        print(f"[?]      {topico:<28} {dados}")
        

client = mqtt.Client(client_id="subscriber_monitor_01", protocol=mqtt.MQTTv311)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, keepalive=60)
client.loop_forever()
```

---

### Estrutura final
```
mqtt-iot-simulacao/
├── publisher.py        ← 3 sensores + publisher MQTT
├── subscriber.py       ← wildcard sensor/# + decoder por tipo
└── requirements.txt    ← paho-mqtt==1.6.1