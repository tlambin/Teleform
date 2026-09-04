"""Module de gestion des administrateurs par le propriétaire (Owner)."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.validators import ValidationError, Validators, convert_utc_to_paris

logger = logging.getLogger(__name__)


class AdminManager:
    """Gestionnaire de l'équipe d'administration (attribution et révocation)."""

    WAITING_ADMIN_ID = 1
    WAITING_ADMIN_REMOVE = 2
    WAITING_CONFIRMATION = 3

    def __init__(self, db_manager, config, interface_manager=None):
        self.db_manager = db_manager
        self.config = config
        self.interface = interface_manager
        logger.info("AdminManager initialisé")

    def set_interface_manager(self, interface_manager):
        """Injection différée de l'InterfaceManager si nécessaire."""
        self.interface = interface_manager

    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste complète des administrateurs enregistrés."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            if update.message:
                await update.message.reply_text("❌ Action réservée au propriétaire.")
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.user_id, a.alias, a.first_name, a.username, a.date_added,
                           u.first_name AS nom_ajouteur
                    FROM admins a
                    LEFT JOIN users u ON a.added_by = u.user_id
                    ORDER BY a.date_added ASC
                    """
                )
                admins = cursor.fetchall()

            if not admins:
                msg = (
                    "📭 <b>Aucun administrateur secondaire</b>\n\n"
                    f"👑 Propriétaire unique : ID <code>{self.config.OWNER_ID}</code>"
                )
                if update.message:
                    await update.message.reply_text(msg, parse_mode="HTML")
                return

            lines = [f"👥 <b>Équipe d'administration</b> ({len(admins)})\n"]
            for adm in admins:
                pseudo = f"@{adm['username']}" if adm.get("username") else adm.get("first_name", "")
                date_paris = convert_utc_to_paris(adm["date_added"])
                date_str = date_paris.strftime("%d/%m/%Y à %H:%M")
                par_qui = adm.get("nom_ajouteur") or "Système"

                lines.append(
                    f"• <b>{adm['alias']}</b> ({pseudo})\n"
                    f"  ID : <code>{adm['user_id']}</code> | Ajouté le {date_str} par {par_qui}\n"
                )

            lines.append(f"👑 <b>Propriétaire :</b> <code>{self.config.OWNER_ID}</code>")
            if update.message:
                await update.message.reply_text("\n".join(lines), parse_mode="HTML")

        except Exception as exc:
            logger.error("Erreur récupération liste admins: %s", exc, exc_info=True)
            if update.message:
                await update.message.reply_text("❌ Impossible de charger la liste des administrateurs.")

    async def admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ouvre le formulaire d'ajout d'administrateur."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM admins")
                count = cursor.fetchone()["count"]

            text = (
                "👤 <b>Ajout d'un Administrateur</b>\n\n"
                f"Équipe actuelle : <b>{count}</b> administrateur(s)\n\n"
                "Envoyez l'<b>ID Telegram</b> (ex: <code>123456789</code>) "
                "ou le <b>@username</b> de l'utilisateur à promouvoir.\n\n"
                "<i>Rappel : L'utilisateur doit avoir déjà interagi au moins une fois avec le bot (/start).</i>"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")
            ]])

            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
            return self.WAITING_ADMIN_ID

        except Exception as exc:
            logger.error("Erreur interface ajout admin: %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide l'identifiant et enregistre le nouvel administrateur."""
        if not update.message or not update.message.text:
            return self.WAITING_ADMIN_ID

        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            return ConversationHandler.END

        saisie = update.message.text.strip().replace("@", "")

        try:
            with self.db_manager.get_cursor() as cursor:
                if saisie.isdigit():
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (int(saisie),))
                else:
                    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (saisie.lower(),))
                user_data = cursor.fetchone()

            if not user_data:
                await update.message.reply_text(
                    f"❌ L'utilisateur <code>{saisie}</code> est introuvable dans la base.\n"
                    "Il doit obligatoirement envoyer /start au bot avant de pouvoir être nommé administrateur.",
                    parse_mode="HTML"
                )
                return self.WAITING_ADMIN_ID

            target_id = user_data["user_id"]

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (target_id,))
                if cursor.fetchone():
                    await update.message.reply_text("⚠️ Cet utilisateur possède déjà les privilèges administrateur.")
                    return self.WAITING_ADMIN_ID

                base_alias = user_data.get("first_name") or user_data.get("username") or f"Admin{target_id}"
                alias = base_alias[:20]

                cursor.execute(
                    """
                    INSERT INTO admins (user_id, alias, first_name, username, date_added, added_by)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                    """,
                    (target_id, alias, user_data.get("first_name", ""), user_data.get("username", ""), user.id)
                )

            self.config.add_admin(target_id)
            logger.info("Admin promu: %s (%s) par le propriétaire", target_id, alias)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            await update.message.reply_text(
                f"✅ <b>Administrateur ajouté avec succès !</b>\n\n"
                f"👤 <b>Nom :</b> {user_data.get('first_name', '')}\n"
                f"🆔 <b>ID :</b> <code>{target_id}</code>\n"
                f"🏷️ <b>Alias initial :</b> <code>{alias}</code>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement administrateur: %s", exc, exc_info=True)
            await update.message.reply_text("❌ Erreur technique lors de l'enregistrement.")
            return ConversationHandler.END

    async def cancel_admin_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interrompt la procédure d'ajout d'administrateur."""
        query = update.callback_query
        if query and self.interface:
            message, keyboard = self.interface.get_gerer_admins_menu()
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
        return ConversationHandler.END

    async def admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des administrateurs pouvant être révoqués."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, alias, first_name, username, date_added
                    FROM admins
                    WHERE user_id != %s
                    ORDER BY date_added DESC
                    """,
                    (user.id,)
                )
                admins = cursor.fetchall()

            if not admins:
                await query.edit_message_text(
                    "👥 <b>Révocation d'Administrateur</b>\n\n"
                    "Aucun administrateur révocable n'est configuré actuellement.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")
                    ]])
                )
                return ConversationHandler.END

            lines = [
                "👥 <b>Révocation d'Administrateur</b>\n",
                f"Administrateurs en service : <b>{len(admins)}</b>\n"
            ]
            for idx, adm in enumerate(admins, 1):
                pseudo = f"@{adm['username']}" if adm.get("username") else adm.get("first_name", "")
                date_str = str(adm.get("date_added", ""))[:10]
                lines.append(f"{idx}. <b>{adm['alias']}</b> ({pseudo}) — ID: <code>{adm['user_id']}</code> [{date_str}]")

            lines.append("\nEnvoyez le <b>numéro</b> de l'administrateur à révoquer :")

            context.user_data["admins_list"] = admins
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
            ]])

            await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
            return self.WAITING_ADMIN_REMOVE

        except Exception as exc:
            logger.error("Erreur affichage suppression admin: %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Intercepte le choix numérique de l'administrateur à révoquer."""
        if not update.message or not update.message.text:
            return self.WAITING_ADMIN_REMOVE

        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            return ConversationHandler.END

        choix = update.message.text.strip()
        admins_list = context.user_data.get("admins_list", [])

        if not choix.isdigit():
            await update.message.reply_text("❌ Veuillez entrer un numéro valide issu de la liste :")
            return self.WAITING_ADMIN_REMOVE

        idx = int(choix) - 1
        if idx < 0 or idx >= len(admins_list):
            await update.message.reply_text(f"❌ Numéro hors plage. Choisissez entre 1 et {len(admins_list)} :")
            return self.WAITING_ADMIN_REMOVE

        selected = admins_list[idx]
        context.user_data["admin_to_remove"] = selected

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer la suppression", callback_data="confirm_admin_remove"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
            ]
        ])

        pseudo = f"@{selected['username']}" if selected.get("username") else selected.get("first_name", "")
        await update.message.reply_text(
            f"⚠️ <b>Confirmation de révocation</b>\n\n"
            f"Êtes-vous certain de vouloir retirer les accès administrateur à :\n"
            f"• <b>Alias :</b> {selected['alias']}\n"
            f"• <b>Profil :</b> {pseudo}\n"
            f"• <b>ID :</b> <code>{selected['user_id']}</code> ?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return self.WAITING_CONFIRMATION

    async def confirmer_admin_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Supprime l'administrateur sélectionné de la base de données et du cache."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user or not self.config.is_owner(user.id):
            return ConversationHandler.END

        selected = context.user_data.pop("admin_to_remove", None)
        context.user_data.pop("admins_list", None)

        if not selected:
            await query.edit_message_text("❌ Erreur : aucun administrateur sélectionné.")
            return ConversationHandler.END

        target_id = selected["user_id"]
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (target_id,))

            self.config.remove_admin(target_id)
            logger.info("Droits administrateur supprimés pour %s", target_id)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            await query.edit_message_text(
                f"✅ <b>Droits administrateur retirés avec succès pour {selected['alias']}.</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur exécution révocation admin: %s", exc, exc_info=True)
            await query.edit_message_text("❌ Erreur technique lors de la révocation.")
            return ConversationHandler.END

    async def cancel_admin_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la révocation et nettoie le contexte."""
        query = update.callback_query
        context.user_data.pop("admins_list", None)
        context.user_data.pop("admin_to_remove", None)

        if query and self.interface:
            message, keyboard = self.interface.get_gerer_admins_menu()
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
        return ConversationHandler.END