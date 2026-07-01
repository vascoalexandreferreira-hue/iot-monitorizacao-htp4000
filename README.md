# Monitorização de Condição e Manutenção Preditiva — HTP-4000

Sistema IoT de monitorização industrial para uma misturadora HTP-4000, desenvolvido no âmbito do curso de Engenharia de Produção Industrial do ISVOUGA.

O sistema recolhe **temperatura**, **vibração** e **corrente** de um motor industrial através de um ESP32, transmite os dados por MQTT, armazena-os em MySQL e apresenta-os num dashboard web com deteção de anomalias baseada em cartas de controlo estatístico (SPC / Shewhart).

---

## Arquitetura

O sistema está organizado em três camadas:

- **Perceção** — ESP32 (WEMOS D1 R32) com três sensores: MLX90614 (temperatura por infravermelhos), MPU6050 (vibração) e SCT-013 (corrente).
- **Rede** — broker MQTT (Mosquitto) que recebe as leituras e um subscritor Python que as grava em MySQL.
- **Aplicação** — dashboard web (Flask) com gráficos em tempo real, cartas de controlo, alertas e exportação para Excel.

A deteção de anomalias usa uma metodologia de duas fases: um modelo *Isolation Forest* limpa o baseline (Fase I), e cartas de controlo de Shewhart com limites por regime de funcionamento (vazio / trabalho) vigiam o processo em tempo real (Fase II).

---

## Como executar a simulação

Esta versão permite correr o sistema **sem o hardware físico**, usando um simulador que gera dados realistas dos três sensores. É necessário ter instalado o MySQL e o Mosquitto (ver pré-requisitos).

### Pré-requisitos

- [Python 3.11+](https://www.python.org/downloads/)
- [MySQL](https://dev.mysql.com/downloads/installer/) (servidor de base de dados)
- [Mosquitto](https://mosquitto.org/download/) (broker MQTT)

### Passo 1 — Obter o código

Descarrega o repositório (botão verde **Code → Download ZIP**) e extrai para uma pasta.

### Passo 2 — Instalar as dependências Python

Abre um terminal na pasta do projeto e corre:

```bash
pip install -r requirements.txt
```

### Passo 3 — Configurar a password do MySQL

Copia o ficheiro `.env.exemplo` para um novo ficheiro chamado `.env` e preenche a tua password do MySQL:

```
MYSQL_PASSWORD=a_tua_password
```

### Passo 4 — Criar a base de dados

No MySQL, corre o script `mysql.sql` para criar a base de dados e as tabelas:

```bash
mysql -u root -p < mysql.sql
```

### Passo 5 — Arrancar os serviços

**Nota:** o broker Mosquitto e o servidor MySQL têm de estar a correr antes de arrancar a simulação. O MySQL costuma correr automaticamente como serviço do Windows. Para o Mosquitto, consulta a secção "Iniciar o Mosquitto" abaixo.

#### Opção A — Arranque automático (Windows)

Faz duplo-clique no ficheiro **`arrancar_simulacao.bat`**. Ele verifica se o `.env` existe, e depois arranca os cinco processos Python (subscritor, alertas, anomalias, dashboard e o simulador normal), cada um na sua janela.

#### Opção B — Arranque manual (qualquer sistema)

Abre um terminal separado para cada um destes comandos (pela ordem indicada):

```bash
# 1. Subscritor — grava as leituras na base de dados
python db_subscriber.py

# 2. Monitor de alertas (temperatura e vibração)
python alertas.py

# 3. Detetor de anomalias (corrente, por regime)
python anomalias.py

# 4. Dashboard web
python app.py

# 5. Simulador de sensores — ESCOLHE UM:
python publisher.py            # gera anomalias (demonstra deteção)
python publisher_normal.py     # funcionamento normal (sem alertas)
```

#### Iniciar o Mosquitto

Se o Mosquitto não estiver já a correr como serviço, abre um terminal e corre:

```bash
mosquitto -v
```

Deixa esse terminal aberto durante a simulação.

### Passo 6 — Abrir o dashboard

No browser, abre:

```
http://localhost:5000
```

---

## Dois cenários de simulação

- **`publisher.py`** — gera dados que se desviam do baseline, fazendo o sistema disparar alertas e anomalias. Demonstra a **capacidade de deteção**.
- **`publisher_normal.py`** — gera os três sensores coordenados e dentro dos limites de cada regime. Demonstra o sistema em **funcionamento normal e estável**, sem alertas.

Ao trocar de simulador, aguarda alguns minutos para a janela de dados do dashboard limpar o rasto do simulador anterior.

---

## Estrutura do repositório

```
├── app.py                  Dashboard web (Flask)
├── db_subscriber.py        Subscritor MQTT → MySQL
├── alertas.py              Monitor de alertas (temperatura, vibração)
├── anomalias.py            Detetor de anomalias (corrente, por regime SPC)
├── publisher.py            Simulador — cenário com anomalias
├── publisher_normal.py     Simulador — cenário normal
├── fase1_limites.py        Geração dos limites de controlo (Fase I)
├── config.py               Configuração central (lê o .env)
├── mysql.sql               Script de criação da base de dados
├── limites_fase1.json      Limites de controlo por regime
├── arrancar_simulacao.bat  Arranque automático da simulação (Windows)
├── templates/
│   └── dashboard.html      Interface do dashboard
├── requirements.txt        Dependências Python
├── .env.exemplo            Modelo de configuração
└── .gitignore
```

---

## Nota sobre o hardware

Na instalação real, o simulador (`publisher.py`) é substituído pelo firmware do ESP32 (`inciarESP32.ino`), que lê os sensores físicos e publica nos mesmos tópicos MQTT. O restante sistema funciona sem alterações.

---

## Contexto académico

Projeto desenvolvido no Instituto Superior de Entre Douro e Vouga (ISVOUGA), no curso de Engenharia de Produção Industrial. O equipamento monitorizado é uma misturadora industrial HTP-4000 de uma cooperativa de produção de leite.
