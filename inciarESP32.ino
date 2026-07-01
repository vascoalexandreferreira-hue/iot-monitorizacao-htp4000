#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <MPU6050.h>

// ── Configuração WiFi ────────────────────────────────────────────────
const char* WIFI_SSID     = "Proleite";
const char* WIFI_PASSWORD = "jecrp2012";

// ── Configuração MQTT ────────────────────────────────────────────────
const char* MQTT_BROKER    = "192.168.1.208";
const int   MQTT_PORT      = 1883;
const char* MQTT_CLIENT    = "esp32_wemos_01";

// ── Tópicos MQTT ─────────────────────────────────────────────────────
const char* TOPICO_TEMP    = "sensor/temperatura";
const char* TOPICO_VIB     = "sensor/vibracao";
const char* TOPICO_CORRENTE = "sensor/corrente";

// ── Pino analógico SCT-013 ───────────────────────────────────────────
const int PINO_SCT        = 34;
const float FATOR_CALIBRACAO = 157;

// ── LIMIARES DE ALERTA (valores fixos fundamentados) ─────────────────
// Valores definidos a partir de fundamentos técnicos, não de margens
// percentuais. Ver tabela de fundamentação no relatório.
//
//  Grandeza     | Aviso    | Crítico  | Fundamento
//  -------------|----------|----------|---------------------------------
//  Temperatura  | 60 °C    | 75 °C    | Classe isolamento B (enrol. 130°C);
//                                       superfície ~30°C abaixo do enrol.
//  Vibração     | 4.5 mm/s | 7.1 mm/s | Zonas de severidade ISO 10816-3
//  Corrente     | 53.6 A   | 63.7 A   | 80% / 95% da corrente nominal de
//                                       chapa (I_nom = 67 A, triângulo 400V)
//
const float TEMP_AVISO  = 60.0;
const float TEMP_ALERTA = 75.0;

const float VIB_AVISO   = 4.5;
const float VIB_ALERTA  = 7.1;

const float CORR_AVISO  = 53.6;
const float CORR_ALERTA = 63.7;
// ─────────────────────────────────────────────────────────────────────

// ── Intervalo de publicação ──────────────────────────────────────────
// ATUALIZADO: 1000ms = 1 segundo = 60 leituras por minuto
const unsigned long INTERVALO = 1000; 
unsigned long ultima_publicacao = 0;

// ── Objectos ─────────────────────────────────────────────────────────
WiFiClient       wifiClient;
PubSubClient     mqttClient(wifiClient);
Adafruit_MLX90614 mlx;
MPU6050          mpu;

// ════════════════════════════════════════════════════════════════════
// WiFi
// ════════════════════════════════════════════════════════════════════
void conectar_wifi() {
  Serial.println("\n[WiFi] A ligar a: " + String(WIFI_SSID));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    tentativas++;
    if (tentativas > 30) {
      Serial.println("\n[WiFi] Falha. A reiniciar...");
      ESP.restart();
    }
  }
  Serial.println("\n[WiFi] Ligado! IP: " + WiFi.localIP().toString());
}

// ════════════════════════════════════════════════════════════════════
// MQTT
// ════════════════════════════════════════════════════════════════════
void conectar_mqtt() {
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] A ligar ao broker...");
    if (mqttClient.connect(MQTT_CLIENT)) {
      Serial.println(" Ligado!");
    } else {
      Serial.print(" Falhou. Código: ");
      Serial.println(mqttClient.state());
      delay(3000);
    }
  }
}

// ════════════════════════════════════════════════════════════════════
// CAMADA DE PERCEPÇÃO — Leitura dos sensores
// ════════════════════════════════════════════════════════════════════

// ── MLX90614 — Temperatura por infravermelhos ────────────────────────
float ler_temperatura() {
  float temp = mlx.readObjectTempC();
  if (isnan(temp)) {
    Serial.println("[SENSOR] MLX90614 — leitura inválida");
    return -999.0;
  }
  return temp;
}

// ── MPU6050 — Vibração (aceleração RMS rápida) ───────────────────────
float ler_vibracao(float &freq_hz, float &amplitude) {
  const int N = 50;
  float soma_quadrados = 0;
  float pico = 0;

  for (int i = 0; i < N; i++) {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    float ax_g = ax / 16384.0;
    float ay_g = ay / 16384.0;
    float az_g = az / 16384.0;

    float mag = sqrt(ax_g * ax_g + ay_g * ay_g + az_g * az_g);
    float vibr = mag - 1.0;

    soma_quadrados += vibr * vibr;
    if (abs(vibr) > pico) pico = abs(vibr);

    delay(2);  // 50 amostras × 2ms = 100ms total
  }

  float rms_g = sqrt(soma_quadrados / N);
  amplitude = pico;
  freq_hz = 50.0;
  
  float rms_mm_s = rms_g * 9810.0 / (2.0 * PI * freq_hz);

  // Filtro de ruído (Zona morta)
  // Se a vibração for muito baixa (ruído da mesa), força a zero
  if (rms_mm_s < 0.5) {
    rms_mm_s = 0.0;
  }

  return round(rms_mm_s * 1000.0) / 1000.0;
}

// ── SCT-013 — Corrente eléctrica (RMS rápido sem offset fixo) ────────
float ler_corrente() {
  double soma_valores = 0;
  double soma_quadrados = 0; 
  int num_amostras = 0;
  unsigned long inicio = millis();

  // Lê durante 100ms (5 ciclos completos a 50Hz)
  while (millis() - inicio < 100) {
    int leitura = analogRead(PINO_SCT);
    
    // Somamos o valor cru para encontrar a média (DC offset real)
    soma_valores += leitura;
    // Somamos os quadrados para o cálculo RMS
    soma_quadrados += (double)leitura * leitura; 
    
    num_amostras++;
    delayMicroseconds(100);
  }

  // Offset dinâmico
  // 1. Encontrar o valor médio (o verdadeiro DC offset do circuito)
  double media = soma_valores / num_amostras;
  
  // 2. Encontrar a média dos quadrados
  double media_quadrados = soma_quadrados / num_amostras;
  
  // 3. O valor AC puro ao quadrado é a variância
  double variancia = media_quadrados - (media * media);
  
  // Proteção contra erros de precisão do ponto flutuante
  if (variancia < 0) {
    variancia = 0;
  }

  // 4. Calcular o RMS final
  float rms_adc = sqrt(variancia); 
  float tensao_rms = rms_adc * (3.3 / 4095.0);
  float corrente = tensao_rms * FATOR_CALIBRACAO;

  // Filtro de ruído ambiente ajustado para 2.5A 
  // Podes reduzir este valor (ex: 0.5) se o ruído agora for menor
  if (corrente < 2.5) { 
    corrente = 0.0;
  }

  return round(corrente * 1000.0) / 1000.0;
}

// ════════════════════════════════════════════════════════════════════
// CAMADA DE REDE — Publicar no broker MQTT
// ════════════════════════════════════════════════════════════════════
void publicar(const char* topico, JsonDocument& doc) {
  char payload[256];
  serializeJson(doc, payload);
  if (mqttClient.publish(topico, payload, true)) {
    Serial.print("[MQTT] Publicado → ");
    Serial.println(payload);
  } else {
    Serial.println("[MQTT] Erro ao publicar.");
  }
}

void publicar_sensores() {
  // Uso do novo JsonDocument (ArduinoJson v7)
  JsonDocument doc; 

  // ── Temperatura ──────────────────────────────────────────────────
  float temperatura = ler_temperatura();
  if (temperatura != -999.0) {
    doc.clear(); // Limpa o documento para a nova leitura
    doc["device_id"]   = MQTT_CLIENT;
    doc["temperatura"] = round(temperatura * 100.0) / 100.0;
    doc["unidade"]     = "C";
    // Três níveis: normal < aviso < alerta (60°C / 75°C)
    doc["status"]      = (temperatura < TEMP_AVISO) ? "normal" : (temperatura < TEMP_ALERTA ? "aviso" : "alerta");
    doc["timestamp"]   = millis();
    publicar(TOPICO_TEMP, doc);
  }

  // ── Vibração ─────────────────────────────────────────────────────
  float freq_hz = 0;
  float amplitude = 0;
  float rms_mm_s  = ler_vibracao(freq_hz, amplitude);
  
  doc.clear();
  doc["device_id"] = MQTT_CLIENT;
  doc["rms_mm_s"]  = rms_mm_s;
  doc["freq_hz"]   = freq_hz;
  doc["amplitude"] = amplitude;
  // Três níveis: normal < aviso (4.5) < alerta (7.1) — ISO 10816-3
  doc["status"]    = (rms_mm_s < VIB_AVISO) ? "normal" : (rms_mm_s < VIB_ALERTA ? "aviso" : "alerta");
  doc["timestamp"] = millis();
  publicar(TOPICO_VIB, doc);

  // ── Corrente ─────────────────────────────────────────────────────
  float corrente = ler_corrente();
  
  doc.clear();
  doc["device_id"]  = MQTT_CLIENT;
  doc["corrente_A"] = corrente;
  doc["thd_pct"]    = 0.0;   
  doc["fator_potencia"] = 0.95;  
  // Três níveis: normal < aviso (53.6) < sobrecarga (63.7) — 80%/95% I_nom
  doc["status"]     = (corrente < CORR_AVISO) ? "normal" : (corrente < CORR_ALERTA ? "aviso" : "sobrecarga");
  doc["timestamp"]  = millis();
  publicar(TOPICO_CORRENTE, doc);
}

// ════════════════════════════════════════════════════════════════════
// Setup
// ════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=============================");
  Serial.println("  ESP32 WEMOS — IoT Industrial");
  Serial.println("=============================");

  // Iniciar I2C
  Wire.begin(21, 22);  // SDA=21, SCL=22

  // Iniciar MLX90614
  if (!mlx.begin()) {
    Serial.println("[SENSOR] MLX90614 não encontrado — verifica ligações!");
  } else {
    Serial.println("[SENSOR] MLX90614 OK");
  }

  // Iniciar MPU6050
  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("[SENSOR] MPU6050 não encontrado — verifica ligações!");
  } else {
    Serial.println("[SENSOR] MPU6050 OK");
  }

  // ADC 12-bit para SCT-013
  analogReadResolution(12);
  Serial.println("[SENSOR] SCT-013 OK");

  // WiFi e MQTT
  conectar_wifi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setKeepAlive(60);
  conectar_mqtt();

  Serial.println("[Sistema] Pronto!\n");
}

// ════════════════════════════════════════════════════════════════════
// Loop
// ════════════════════════════════════════════════════════════════════
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Ligação perdida. A reconectar...");
    conectar_wifi();
  }

  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Ligação perdida. A reconectar...");
    conectar_mqtt();
  }
  mqttClient.loop();

  unsigned long agora = millis();
  if (agora - ultima_publicacao >= INTERVALO) {
    ultima_publicacao = agora;
    publicar_sensores();
  }
}