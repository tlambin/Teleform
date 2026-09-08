"""Module de consultation des profils statistiques pour administrateurs et utilisateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ProfilsManager:
    """Gestionnaire de rendu des profils de performance (Admin) et d'activité (Demandeur)."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ProfilsManager initialisé")

    def _render_progress_bar(self, rate: float) -> str:
        """Génère une jauge graphique sur 10 blocs."""
        filled = int(round(rate / 10))
        filled = max(0, min(10, filled))
        empty = 10 - filled
        return f"{'🟩' * filled}{'⬜' * empty}"

    # ==================== PROFIL ADMINISTRATEUR ====================

    async def show_admin_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int):
        """Affiche la fiche détaillée de performance d'un administrateur."""
        query = update.callback_query
        if not query:
            return

        user_id = update.effective_user.id
        is_owner = self.config.is_owner(user_id)

        if not is_owner and user_id != admin_id:
            await query.answer("❌ Seul le propriétaire peut consulter le profil d'autres administrateurs.", show_alert=True)
            return

        stats = self.db_manager.get_admin_stats(admin_id)
        alias = stats["alias"]

        if is_owner and admin_id == self.config.OWNER_ID:
            date_str = "Créateur / Propriétaire"
        else:
            date_str = stats["date_added"].strftime("%d/%m/%Y") if stats.get("date_added") else "Inconnue"

        taux = stats["taux_reussite"]
        bar = self._render_progress_bar(taux)

        res_label = {"all": "Insta & Snap", "insta": "Insta seul", "snap": "Snap seul"}.get(stats["perm_reseaux"], stats["perm_reseaux"])
        typ_label = {"all": "Tous types", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(stats["perm_type"], stats["perm_type"])

        lines = [
            f"🦈 <b>Profil Administrateur : {alias}</b>",
            f"🆔 ID Telegram : <code>{admin_id}</code>",
            f"📅 Dans l'équipe : <b>{date_str}</b>",
            f"🛡️ Permissions : <i>{res_label} | {typ_label}</i>\n",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>PERFORMANCE OPÉRATIONNELLE</b>\n",
            f"⏳ <b>En cours de traitement :</b> <code>{stats['en_cours']}</code>",
            f"✅ <b>Demandes réussies :</b> <code>{stats['reussies']}</code>",
            f"❌ <b>Demandes abandonnées :</b> <code>{stats['abandonnees']}</code>",
            f"📦 <b>Total demandes clôturées :</b> <code>{stats['total_traitees']}</code>\n",
            f"📈 <b>Taux de succès :</b> <b>{taux}%</b>",
            f"{bar}\n",
            "💎 <b>GESTION PRIORITAIRE</b>",
            f"• Demandes prioritaires : <b>{stats['prioritaires_traitees']}</b>",
            f"• Volume financier traité : <b>{stats['montant_total']:.2f}€</b>"
        ]

        text = "\n".join(lines)

        buttons = []
        if is_owner:
            buttons.append([
                InlineKeyboardButton("🛡️ Modifier ses droits", callback_data=f"perm_admin_{admin_id}"),
                InlineKeyboardButton("🏷️ Renommer", callback_data=f"owner_edit_alias_{admin_id}")
            ])
            buttons.append([InlineKeyboardButton("👥 Retour Équipe", callback_data="gerer_admins")])
        else:
            buttons.append([InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")])

        keyboard = InlineKeyboardMarkup(buttons)

        if query.message and query.message.photo:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== PROFIL DEMANDEUR / UTILISATEUR ====================

    async def show_user_profile_by_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Résout le demandeur Telegram directement via la demande."""
        query = update.callback_query
        if not query:
            return

        user_id = update.effective_user.id
        if not self.config.is_admin(user_id):
            await query.answer("❌ Réservé à l'équipe d'administration.", show_alert=True)
            return

        demande = None
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.date_creation,
                           u.first_name AS user_first_name, u.username AS user_username,
                           u.date_inscription, u.derniere_activite
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,)
                )
                demande = cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur récupération demande #%s: %s", demande_id, exc)

        if not demande:
            await query.answer("❌ Demande introuvable en base.", show_alert=True)
            return

        target_user_id = int(demande["user_id"])
        stats = self.db_manager.get_user_stats(target_user_id)

        # Prénom du compte Telegram demandeur
        prenom_demandeur = (
            demande.get("user_first_name")
            or stats.get("prenom")
            or demande.get("user_username")
            or f"Utilisateur {target_user_id}"
        )

        # Pseudo Telegram
        pseudo_val = demande.get("user_username") or stats.get("username")
        pseudo = f"@{pseudo_val}" if pseudo_val else "Sans @username"

        # Dates
        dt_insc = demande.get("date_inscription") or stats.get("date_inscription") or demande.get("date_creation")
        date_insc = dt_insc.strftime("%d/%m/%Y") if dt_insc else "Inconnue"

        dt_act = demande.get("derniere_activite") or stats.get("derniere_activite")
        date_act = str(dt_act)[:16] if dt_act else "Inconnue"

        lines = [
            f"👤 <b>Fiche Utilisateur : {prenom_demandeur}</b>",
            f"🏷️ Pseudo : {pseudo}",
            f"🆔 ID : <code>{target_user_id}</code>\n",
            f"📅 Inscrit le : <b>{date_insc}</b>",
            f"⏱️ Dernière activité : <i>{date_act}</i>\n",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📋 <b>HISTORIQUE DES DEMANDES</b>\n",
            f"🗳️ <b>Total demandes soumises :</b> <code>{stats['total_demandes']}</code>",
            f"⏳ En cours de traitement : <b>{stats['en_cours']}</b>",
            f"📨 En attente de prise en charge : <b>{stats['en_attente']}</b>",
            f"✅ Terminées avec succès : <b>{stats['reussies']}</b>",
            f"❌ Demandes échouées / refusées : <b>{stats['abandonnees']}</b>\n",
            f"💎 <b>Demandes payantes :</b> {stats['total_prio']} (Total investi : <b>{stats['montant_total_investi']:.2f}€</b>)"
        ]

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{demande_id}")
        ]])

        if query.message and query.message.photo:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)