import requests
from typing import Dict, Any

def get_fear_and_greed_index() -> Dict[str, Any]:
    """
    Consulta el indice Crypto Fear & Greed (Miedo y Codicia) oficial en tiempo real.
    0 = Pánico Extremo (Oportunidad de rebote)
    100 = Codicia Extrema (Riesgo alto de corrección)
    """
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()["data"][0]
            val = int(data["value"])
            classification_en = data["value_classification"]

            # Traduccion y emojis
            if val >= 75:
                status = "🔥 Codicia Extrema"
                advice = "El mercado está eufórico. El bot aumentará el rigor del Stop-Loss para no comprar en techos."
            elif val >= 55:
                status = "🟢 Codicia"
                advice = "Sentimiento alcista favorable para compras en ruptura de EMA."
            elif val >= 45:
                status = "⚖️ Neutral"
                advice = "Mercado equilibrado. Operaciones estándar según indicadores."
            elif val >= 25:
                status = "😨 Miedo"
                advice = "Incertidumbre. Buenas oportunidades de rebote desde sobreventa."
            else:
                status = "🩸 Pánico Extremo"
                advice = "Precios de descuento. El bot busca rebotes de RSI en mínimos."

            return {
                "success": True,
                "value": val,
                "status": status,
                "advice": advice,
                "timestamp": data.get("timestamp")
            }
    except Exception as e:
        pass

    return {
        "success": False,
        "value": 50,
        "status": "⚖️ Neutral (Estimado)",
        "advice": "No se pudo conectar a la API de sentimiento; operando con reglas normales."
    }
