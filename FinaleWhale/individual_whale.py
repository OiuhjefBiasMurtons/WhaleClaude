#!/usr/bin/env python3
"""
Script para monitorear trades de un usuario específico de Polymarket.
Uso: python3 individual_whale.py <wallet_address>
"""

import sys
import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuración
DATA_API = "https://data-api.polymarket.com"
TELEGRAM_TOKEN = os.getenv('API_INDIVIDUAL')
CHAT_ID = os.getenv('CHAT_ID')
CHECK_INTERVAL = 10  # Segundos entre checks

class IndividualWhaleMonitor:
    def __init__(self, wallet_address):
        self.wallet = wallet_address
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.last_seen_trades = set()
        self.username = None

    def get_user_info(self):
        """Obtiene información básica del usuario desde el perfil web de Polymarket"""
        try:
            import re

            # Intentar obtener username desde la página de perfil
            url = f"https://polymarket.com/profile/{self.wallet}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 200:
                # Buscar username en el HTML
                # Patrón 1: En meta tags o títulos
                username_match = re.search(r'"username":"([^"]+)"', response.text)
                if username_match:
                    self.username = username_match.group(1)
                    return self.username

                # Patrón 2: Buscar @username en el HTML
                at_match = re.search(r'@([a-zA-Z0-9_-]+)', response.text)
                if at_match:
                    # Verificar que no sea un handle genérico
                    potential_username = at_match.group(1)
                    if potential_username not in ['polymarket', 'twitter', 'x']:
                        self.username = potential_username
                        return self.username

            # Fallback: usar nombre de los trades
            trades_url = f"{DATA_API}/trades"
            params = {'user': self.wallet, '_limit': 1}  # Parámetro correcto
            trades_response = self.session.get(trades_url, params=params, timeout=10)
            data = trades_response.json()

            if data and len(data) > 0:
                trade = data[0]
                self.username = trade.get('name') or trade.get('pseudonym') or 'Anónimo'
            else:
                self.username = 'Anónimo'

            return self.username

        except Exception as e:
            print(f"⚠️ Error obteniendo info de usuario: {e}")
            self.username = 'Anónimo'
            return self.username

    def get_recent_trades(self, limit=5):
        """Obtiene los últimos N trades del usuario"""
        try:
            url = f"{DATA_API}/trades"
            params = {
                'user': self.wallet,  # Parámetro correcto (no 'maker')
                '_limit': 100  # Obtener más para poder ordenar correctamente
            }
            response = self.session.get(url, params=params, timeout=10)
            trades = response.json()

            # Ordenar por timestamp descendente (más reciente primero)
            trades_sorted = sorted(
                trades,
                key=lambda x: x.get('timestamp', 0),
                reverse=True
            )

            # Retornar solo los N más recientes
            return trades_sorted[:limit]
        except Exception as e:
            print(f"❌ Error obteniendo trades: {e}")
            return []

    def format_trade_info(self, trade):
        """Formatea la información de un trade para mostrar"""
        # Información básica
        market = trade.get('title', 'Desconocido')
        outcome = trade.get('outcome', 'N/A')
        side = trade.get('side', 'N/A').upper()
        price = float(trade.get('price', 0))
        size = float(trade.get('size', 0))
        valor = price * size
        timestamp = trade.get('timestamp', '')

        # Convertir timestamp a hora legible
        if timestamp:
            try:
                # Si es un timestamp epoch (número)
                if isinstance(timestamp, (int, float)):
                    dt = datetime.fromtimestamp(timestamp)
                # Si es un string ISO
                else:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hora = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                hora = 'N/A'
        else:
            hora = 'N/A'

        # Crear ID único usando múltiples campos (por si no hay transactionHash)
        tx_hash = trade.get('transactionHash')
        if tx_hash:
            unique_id = tx_hash
        else:
            # Fallback: crear ID único con timestamp + conditionId + side + size
            unique_id = f"{timestamp}_{trade.get('conditionId', '')}_{side}_{size}"

        return {
            'market': market,
            'outcome': outcome,
            'side': side,
            'price': price,
            'size': size,
            'valor': valor,
            'hora': hora,
            'trade_id': unique_id
        }

    def send_telegram_alert(self, message):
        """Envía alerta por Telegram"""
        if not TELEGRAM_TOKEN or not CHAT_ID:
            return

        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            print(f"⚠️ Error enviando Telegram: {e}")

    def send_initial_summary(self, username, trades_info):
        """Envía resumen inicial de los últimos 5 trades por Telegram"""
        if not TELEGRAM_TOKEN or not CHAT_ID:
            return

        # Construir mensaje
        message = f"🐋 <b>MONITOR INICIADO - {username}</b>\n"
        message += f"📍 Wallet: <code>{self.wallet[:10]}...{self.wallet[-8:]}</code>\n\n"
        message += f"📊 <b>ÚLTIMOS 5 TRADES:</b>\n"
        message += "─" * 40 + "\n\n"

        for i, info in enumerate(trades_info, 1):
            message += f"<b>{i}.</b> {info['market'][:55]}\n"
            message += f"   📈 Outcome: <b>{info['outcome']}</b>\n"
            message += f"   💰 {info['side']}: {info['size']:.2f} @ ${info['price']:.4f}\n"
            message += f"   💵 Valor: <b>${info['valor']:.2f}</b>\n"
            message += f"   🕐 {info['hora']}\n\n"

        message += "─" * 40 + "\n"
        message += "🔍 <i>Monitoreo activo iniciado...</i>"

        self.send_telegram_alert(message)

    def display_initial_info(self):
        """Muestra información inicial del usuario y últimos trades"""
        print("=" * 80)
        print("🐋 MONITOR DE TRADER INDIVIDUAL - POLYMARKET")
        print("=" * 80)

        # Obtener info del usuario
        username = self.get_user_info()
        print(f"\n👤 Usuario: {username}")
        print(f"📍 Wallet: {self.wallet}")
        print(f"\n📊 ÚLTIMOS 5 TRADES:")
        print("-" * 80)

        # Obtener últimos 50 trades para inicializar el set (evita falsos positivos)
        all_trades = self.get_recent_trades(50)

        if not all_trades:
            print("No se encontraron trades para este wallet.")
            return

        # Inicializar el set con TODOS los trades existentes
        for trade in all_trades:
            tx_hash = trade.get('transactionHash')
            if tx_hash:
                self.last_seen_trades.add(tx_hash)
            else:
                timestamp = trade.get('timestamp', '')
                side = trade.get('side', '').upper()
                size = float(trade.get('size', 0))
                trade_id = f"{timestamp}_{trade.get('conditionId', '')}_{side}_{size}"
                self.last_seen_trades.add(trade_id)

        # Mostrar solo los primeros 5
        trades_info = []
        for i, trade in enumerate(all_trades[:5], 1):
            info = self.format_trade_info(trade)

            print(f"\n{i}. {info['market'][:60]}")
            print(f"   Outcome: {info['outcome']}")
            print(f"   {info['side']}: {info['size']:.2f} shares @ ${info['price']:.4f} (Valor: ${info['valor']:.2f})")
            print(f"   Hora: {info['hora']}")

            trades_info.append(info)

        print("\n" + "=" * 80)
        print("🔍 Iniciando monitoreo activo... (Ctrl+C para detener)")
        print("=" * 80 + "\n")

        # Enviar resumen por Telegram
        self.send_initial_summary(username, trades_info)

    def check_new_trades(self):
        """Verifica si hay nuevos trades"""
        try:
            # Obtener últimos 10 trades (para asegurar que capturamos todos los nuevos)
            recent_trades = self.get_recent_trades(10)

            for trade in recent_trades:
                # Crear el mismo ID que en format_trade_info
                tx_hash = trade.get('transactionHash')
                if tx_hash:
                    trade_id = tx_hash
                else:
                    timestamp = trade.get('timestamp', '')
                    side = trade.get('side', '').upper()
                    size = float(trade.get('size', 0))
                    trade_id = f"{timestamp}_{trade.get('conditionId', '')}_{side}_{size}"

                # Si es un trade nuevo (no visto antes)
                if trade_id and trade_id not in self.last_seen_trades:
                    self.last_seen_trades.add(trade_id)
                    self.notify_new_trade(trade)

        except Exception as e:
            print(f"⚠️ Error verificando nuevos trades: {e}")

    def notify_new_trade(self, trade):
        """Notifica un nuevo trade por consola y Telegram"""
        info = self.format_trade_info(trade)

        # Mensaje en consola
        print(f"\n🚨 NUEVO TRADE DETECTADO!")
        print(f"   Mercado: {info['market'][:60]}")
        print(f"   Outcome: {info['outcome']}")
        print(f"   {info['side']}: {info['size']:.2f} shares @ ${info['price']:.4f}")
        print(f"   Valor: ${info['valor']:.2f}")
        print(f"   Hora: {info['hora']}\n")

        # Mensaje por Telegram
        side_emoji = "📈" if info['side'] == "BUY" else "📉"

        telegram_msg = f"<b>🚨 NUEVO TRADE - {self.username}</b>\n\n"
        telegram_msg += f"{side_emoji} <b>{info['side']}</b>\n"
        telegram_msg += f"📊 <b>Mercado:</b> {info['market'][:50]}\n"
        telegram_msg += f"🎯 <b>Outcome:</b> {info['outcome']}\n"
        telegram_msg += f"💰 <b>Cantidad:</b> {info['size']:.2f} shares\n"
        telegram_msg += f"💵 <b>Precio:</b> ${info['price']:.4f}\n"
        telegram_msg += f"💸 <b>Valor:</b> ${info['valor']:.2f}\n"
        telegram_msg += f"🕐 <b>Hora:</b> {info['hora']}\n"
        telegram_msg += f"\n👤 <b>Trader:</b> {self.username}\n"
        telegram_msg += f"📍 <code>{self.wallet[:10]}...{self.wallet[-8:]}</code>"

        self.send_telegram_alert(telegram_msg)

    def run(self):
        """Ejecuta el monitoreo continuo"""
        # Mostrar información inicial
        self.display_initial_info()

        # Enviar notificación inicial por Telegram
        inicio_msg = f"<b>🐋 Monitor Iniciado</b>\n\n"
        inicio_msg += f"👤 <b>Usuario:</b> {self.username}\n"
        inicio_msg += f"📍 <b>Wallet:</b> <code>{self.wallet[:10]}...{self.wallet[-8:]}</code>\n"
        inicio_msg += f"🔍 <b>Estado:</b> Monitoreando activamente"
        self.send_telegram_alert(inicio_msg)

        # Loop de monitoreo
        try:
            while True:
                self.check_new_trades()
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n⛔ Monitoreo detenido por el usuario.")
            stop_msg = f"<b>⛔ Monitor Detenido</b>\n\n"
            stop_msg += f"👤 Usuario: {self.username}\n"
            stop_msg += f"El monitoreo ha sido detenido."
            self.send_telegram_alert(stop_msg)


def main():
    # Verificar argumentos
    if len(sys.argv) < 2:
        print("❌ Error: Debes proporcionar una wallet address")
        print("\nUso:")
        print("  python3 individual_whale.py <wallet_address>")
        print("\nEjemplo:")
        print("  python3 individual_whale.py 0x1234567890abcdef...")
        sys.exit(1)

    wallet_address = sys.argv[1]

    # Validar formato básico de wallet
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        print("⚠️ Advertencia: El formato de wallet parece incorrecto")
        print("   Se espera una dirección Ethereum válida (0x... con 42 caracteres)")
        respuesta = input("¿Continuar de todos modos? (s/n): ")
        if respuesta.lower() != 's':
            print("Operación cancelada.")
            sys.exit(0)

    # Verificar configuración de Telegram
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("\n⚠️ Advertencia: Telegram no configurado")
        print("   Asegúrate de tener API_INDIVIDUAL y CHAT_ID en tu .env")
        print("   El script funcionará, pero sin alertas por Telegram.\n")

    # Iniciar monitor
    monitor = IndividualWhaleMonitor(wallet_address)
    monitor.run()


if __name__ == "__main__":
    main()
