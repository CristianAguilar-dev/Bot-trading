# 📱 Guía para Entregar y Usar el Bot en el Celular de tu Familiar

Esta solución permite que tu familiar controle el robot de trading **directamente desde la app de Telegram en su teléfono (Android o iPhone)** sin necesidad de instalar Python, programar ni lidiar con código.

---

## 🧭 ¿Cómo funciona?

1. El bot corre en tu ordenador (o servidor) conectado a los precios del exchange (Binance).
2. Tu familiar abre **Telegram en su móvil**, entra a la conversación con el bot y presiona **INICIAR**.
3. En la pantalla de su teléfono aparecerán **botones táctiles interactivos** para ver saldo, prender/apagar el bot, ver señales y recibir notificaciones push en tiempo real.

---

## 🛠️ Paso 1: Crear el Bot de Telegram (Solo toma 1 minuto)

1. En Telegram (en tu móvil o PC), busca el usuario oficial **`@BotFather`** (tiene una insignia azul de verificación).
2. Inicia el chat y escribe:
   ```text
   /newbot
   ```
3. Elige un nombre para el bot (ejemplo: `Trading Familiar`).
4. Elige un usuario único que termine en `bot` (ejemplo: `MiTradingFamiliarBot`).
5. **@BotFather te dará un Token secreto**, algo similar a:
   `7891234567:AAFn_xK90sDkd823jhKJHsd...`

---

## 🔑 Paso 2: Configurar el Token

Abre el archivo [`.env`](file:///c:/Users/crist/.gemini/antigravity/scratch/idm-clone/crypto_trading_bot/.env) en la carpeta `crypto_trading_bot/` y pega el token:

```ini
TELEGRAM_BOT_TOKEN=7891234567:AAFn_xK90sDkd823jhKJHsd...
```
*(O también puedes simplemente hacer doble clic en `iniciar_modo_movil.bat` y el sistema te pedirá el token la primera vez y lo guardará automáticamente).*

---

## 🚀 Paso 3: Poner a funcionar el Bot

En tu PC, haz doble clic en:
👉 **[`iniciar_modo_movil.bat`](file:///c:/Users/crist/.gemini/antigravity/scratch/idm-clone/crypto_trading_bot/iniciar_modo_movil.bat)**

Verás en la consola:
```text
📱 TELEGRAM MOBILE CONTROLLER INICIADO (100% OPERATIVO)
Dile a tu familiar que abra el bot en Telegram y pulse /start
```

---

## 📲 Paso 4: ¡Dáselo a tu familiar!

1. Pásale a tu familiar el enlace o el nombre de usuario de tu bot (ejemplo: `t.me/MiTradingFamiliarBot`).
2. Tu familiar entra desde su celular y toca **INICIAR** (o envía `/start`).
3. ¡Automáticamente se desplegará el panel con botones grandes táctiles en su pantalla!

### 🎛️ Botones que tendrá tu familiar en su pantalla:

| Botón | Función en el Móvil |
| :--- | :--- |
| **📊 Mi Saldo & Estado** | Muestra el saldo en USDT, el precio de Bitcoin y si hay una operación activa con su ganancia en verde (+%) o rojo (-%). Incluye botón para actualizar o cerrar de golpe. |
| **📈 Precio & Señal** | Descarga las velas en vivo y le dice qué recomiendan los indicadores (EMA + RSI): *COMPRA*, *VENTA* o *ESPERAR*. |
| **🚀 Iniciar Trading** | Activa el bot automático para que analice el mercado cada 15 segundos y compre/venda solo. |
| **⏹️ Pausar Trading** | Detiene las compras automáticas. |
| **📜 Historial** | Muestra las últimas compras y ventas ejecutadas con sus precios. |
| **🧪 Probar Backtest** | Permite seleccionar con un toque BTC, ETH, SOL o DOGE para ver cuánto habría ganado la estrategia en los últimos días. |
| **⚙️ Ajustes** | Permite cambiar de moneda o temporalidad con botones interactivos. |

---

## 🔔 Notificaciones Instantáneas al Teléfono

Tu familiar recibirá mensajes automáticos con sonido y vibración cada vez que:
- **El bot compre**: Le dirá a qué precio compró y cuánto USDT invirtió.
- **El bot venda**: Le avisará cuánto ganó (+%).
- **Llegue al Take-Profit o Stop-Loss**: Alerta de protección de capital inmediata.
