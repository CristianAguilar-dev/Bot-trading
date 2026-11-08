# ☁️ Guía: Ejecutar el Bot 24/7 sin depender de tu PC

Para que tu familiar pueda usar el bot **desde su celular las 24 horas del día sin que tú tengas que abrir tu PC ni dejarla encendida**, la mejor solución es alojarlo en la **nube gratuita**.

El proyecto ya viene 100% preparado con:
- `Dockerfile`
- `Procfile`
- `render.yaml`
- Servidor web interno de salud (para que los servidores gratuitos no lo suspendan).

---

## 🏆 Opción 1: Alojamiento en la Nube Gratuita (Render.com) [Recomendado]

Con esta opción, **puedes apagar tu PC por completo** y el bot seguirá respondiendo a tu familiar desde los servidores de Render en internet.

### Pasos (Toma unos 3 a 5 minutos):

1. **Subir el código a GitHub:**
   * Entra a [github.com](https://github.com) y crea una cuenta si no tienes una.
   * Crea un nuevo repositorio (puede ser privado o público), por ejemplo llamado `crypto-trading-bot`.
   * Sube los archivos de la carpeta `crypto_trading_bot/`.

2. **Crear el servicio en Render:**
   * Entra a [render.com](https://render.com) y regístrate con tu cuenta de GitHub o Google (es gratuito).
   * Haz clic en el botón azul **"New +"** y selecciona **"Web Service"**.
   * Conecta tu repositorio de GitHub `crypto-trading-bot`.

3. **Configuración en Render:**
   * **Name:** `crypto-trading-bot`
   * **Region:** Cualquiera (ej. Ohio o Frankfurt).
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python telegram_bot.py`
   * **Instance Type:** `Free` (Gratis)

4. **Agregar tu Token de Telegram:**
   * Baja a la sección **"Environment Variables"** (Variables de entorno).
   * Añade una variable:
     * **Key:** `TELEGRAM_BOT_TOKEN`
     * **Value:** *(Pega el token que te dio @BotFather)*
   * Añade otra variable (opcional):
     * **Key:** `BOT_MODE`
     * **Value:** `paper`

5. **Haz clic en "Deploy Web Service":**
   * En 1 minuto verás el mensaje: `🟢 Bot de Trading Operando 24/7 en la Nube`.
   * ¡Listo! El bot ya estará viviendo en internet de forma permanente e independiente. Tu PC ya no hace falta para nada.

*(Opcional: Si quieres que el plan gratuito nunca se duerma tras 15 minutos de inactividad, puedes registrar la URL que te da Render en un servicio gratuito de ping como [cron-job.org](https://cron-job.org) o [uptimerobot.com](https://uptimerobot.com) cada 10 minutos).*

---

## 🥈 Opción 2: Railway.app (Alternativa en la Nube de 1 Clic)

1. Entra a [railway.app](https://railway.app) e inicia sesión con GitHub.
2. Haz clic en **"New Project"** -> **"Deploy from GitHub repo"**.
3. Selecciona tu repositorio.
4. En **Variables**, agrega `TELEGRAM_BOT_TOKEN`.
5. ¡Listo! Railway detecta el `Dockerfile` automáticamente y lo deja corriendo en 30 segundos.

---

## 🥉 Opción 3: Modo Fantasma en tu PC (Sin abrir ventanas ni interactuar)

Si en algún momento prefieres que corra en tu PC pero **sin que tengas que abrir ventanas negras ni interactuar con ella cada vez que la prendas**:

1. Tienes el archivo [`ejecutar_en_segundo_plano.vbs`](file:///c:/Users/crist/.gemini/antigravity/scratch/idm-clone/crypto_trading_bot/ejecutar_en_segundo_plano.vbs).
2. Si presionas `Win + R`, escribes `shell:startup` y copias ese archivo allí, el bot arrancará de forma **completamente invisible en segundo plano** cada vez que tu ordenador se encienda.
