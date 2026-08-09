from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    "pt-BR": {
        "lang":             "pt-BR",
        "brand":            "Rota Otimizada",
        "brand_slug":       "rota-otimizada",
        "icon":             "/icon-rota-otimizada.png",
        "logo":             "/logo-rota-otimizada.png",

        # <head>
        "page_title":       "Rota Otimizada | Otimize Rotas com Múltiplos Endereços Gratuitamente",
        "page_description": "Otimize sua rota de entregas: informe os endereços e receba a ordem mais eficiente de visita, com link direto para o Google Maps.",
        "og_locale":        "pt_BR",
        "og_currency":      "BRL",
        "ld_language":      "pt-BR",
        "ld_description":   "Otimize sua rota de entregas gratuitamente. Informe os endereços e receba a ordem mais eficiente de visita, com link direto para Google Maps ou Waze.",
        "ld_features": [
            "Otimização de rota com múltiplos endereços",
            "Importação de endereços via CSV e Excel",
            "Integração com Google Maps e Waze",
            "Modo Execução de Rota parada a parada",
            "Gratuito sem cadastro",
        ],

        # app.js (injected via window.I18N)
        "share_title":      "Rota — Rota Otimizada",
        "share_msg":        "Veja os endereços que separei para você — clique em otimizar para encontrar a melhor rota!",
        "copy_signature":   "Rota otimizada com rotaotimizada.com.br",
        "how_to_title":     "Como usar o Rota Otimizada",
    },
    "en-US": {
        "lang":             "en-US",
        "brand":            "Find My Route",
        "brand_slug":       "find-my-route",
        "icon":             "/icon-find-my-route.png",
        "logo":             "/logo-find-my-route.png",

        # <head>
        "page_title":       "Find My Route | Optimize Routes with Multiple Addresses for Free",
        "page_description": "Optimize your delivery route: enter your addresses and get the most efficient visit order, with a direct link to Google Maps.",
        "og_locale":        "en_US",
        "og_currency":      "USD",
        "ld_language":      "en-US",
        "ld_description":   "Optimize your delivery route for free. Enter your addresses and get the most efficient visit order, with a direct link to Google Maps or Waze.",
        "ld_features": [
            "Route optimization with multiple addresses",
            "Import addresses via CSV and Excel",
            "Google Maps and Waze integration",
            "Step-by-step Route Execution mode",
            "Free with no sign-up required",
        ],

        # app.js (injected via window.I18N)
        "share_title":      "Route — Find My Route",
        "share_msg":        "Check out the addresses I put together — click optimize to find the best route!",
        "copy_signature":   "Optimized route by findmyroute.com.br",
        "how_to_title":     "How to use Find My Route",
    },
}


def get_strings(locale: str) -> dict[str, str]:
    return _STRINGS.get(locale, _STRINGS["pt-BR"])
