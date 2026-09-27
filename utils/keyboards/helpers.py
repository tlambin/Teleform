"""Utilitaires de formatage pour les claviers et messages d'interface."""


def format_datetime_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA."""
    if not val:
        return "Inconnue"
    try:
        if hasattr(val, "strftime"):
            return val.strftime("%d/%m/%Y")
        parts = str(val)[:10].split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(val)[:10]