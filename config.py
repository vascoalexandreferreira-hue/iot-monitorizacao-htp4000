# -*- coding: utf-8 -*-
"""
Configuração central do sistema de monitorização HTP-4000.

A password da base de dados NÃO está escrita aqui. É lida da variável de
ambiente MYSQL_PASSWORD. Se essa variável não existir, usa-se um valor por
defeito ("") — o utilizador deve definir a sua própria password.

Como definir a password (escolhe UMA das formas):

  1) Ficheiro .env (recomendado, mais simples):
     - Cria um ficheiro chamado .env na raiz do projeto
     - Escreve lá dentro:  MYSQL_PASSWORD=a_tua_password
     - Este ficheiro está no .gitignore e nunca vai para o GitHub

  2) Variável de ambiente no terminal:
     Windows (PowerShell):  $env:MYSQL_PASSWORD="a_tua_password"
     Linux / macOS:         export MYSQL_PASSWORD="a_tua_password"
"""

import os

# Tenta carregar o ficheiro .env, se existir (requer python-dotenv).
# Se o pacote não estiver instalado, ignora silenciosamente e usa apenas
# as variáveis de ambiente do sistema.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Configuração da Base de Dados ─────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("MYSQL_HOST", "localhost"),
    "port":     int(os.environ.get("MYSQL_PORT", 3306)),
    "user":     os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "iot_sensores"),
}

# ── Configuração MQTT ─────────────────────────────────────────────────
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))

# ── Limiar de motor desligado (partilhado por vários módulos) ─────────
CORRENTE_MINIMA_MOTOR = float(os.environ.get("CORRENTE_MINIMA_MOTOR", 0.5))
