WEBAPP_NOT_CONFIGURED_TEXT = "WebApp URL is not configured yet."


def is_webapp_configured(webapp_base_url: str | None) -> bool:
    return bool((webapp_base_url or "").strip())
