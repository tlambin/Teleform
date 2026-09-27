"""Composants visuels et formatage textuel du tableau de bord des statistiques."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def format_stats_message(stats: dict) -> str:
    """Met en forme l'affichage des métriques d'activité et de performances."""
    storage = float(stats.get("storage_usage") or 0.0)
    db_size = stats.get("db_stats", {}).get("total_size_mb", 0.0)

    lines = [
        "📈 <b>Tableau de Bord & Statistiques</b>\n",
        "👥 <b>Communauté & Équipe :</b>",
        f"• Inscrits totaux : <b>{stats.get('total_users', 0)}</b>",
        f"• Membres VIP actifs : <b>{stats.get('total_vips', 0)}</b>",
        f"• Opérateurs Staff : <b>{stats.get('total_staff', 0)}</b>",
        f"• Direction & Admins : <b>{stats.get('total_admins', 0)}</b>",
        f"• Actifs (dernières 24h) : <b>{stats.get('active_24h', 0)}</b>",
        f"• Nouveaux (7 derniers jours) : <b>{stats.get('new_7d', 0)}</b>\n",
        "📋 <b>Volume de Demandes :</b>",
        f"• Actives : <b>{stats.get('total_demandes', 0)}</b>",
        f"• Reçues aujourd'hui : <b>{stats.get('demandes_today', 0)}</b>",
        f"• Archivées : <b>{stats.get('total_archives', 0)}</b>",
        f"• Répartition actives : 💎 <b>{stats.get('nb_prio', 0)}</b> prioritaires | 📝 <b>{stats.get('nb_std', 0)}</b> standard",
        f"• Montant cumulé total : <b>{stats.get('total_montant', 0.0):.2f} €</b> (moyenne prio : {stats.get('avg_montant', 0.0):.2f} €)\n",
        "📊 <b>Statuts des demandes en cours :</b>"
    ]

    for s in stats.get("statuts", []):
        statut_nom = html.escape(str(s.get("statut") or "Inconnu"))
        lines.append(f"• {statut_nom} : {s.get('count', 0)}")

    storage_pct = (storage / 512.0) * 100.0 if storage else 0.0
    lines.append("\n💾 <b>Ressources Système :</b>")
    lines.append(f"• Stockage local : <b>{storage:.1f} Mo / 512 Mo</b> ({storage_pct:.1f} %)")
    lines.append(f"• Base de données MySQL : <b>{db_size} Mo</b>")

    return "\n".join(lines)


def build_stats_keyboard(is_owner: bool) -> InlineKeyboardMarkup:
    """Génère le clavier de rafraîchissement et de retour vers la section appropriée."""
    retour_callback = "gerer_bot" if is_owner else "parametres"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualiser", callback_data="bot_stats")],
        [InlineKeyboardButton("🔙 Retour", callback_data=retour_callback)]
    ])