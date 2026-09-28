"""Gestion du compte utilisateur, des privilèges et des réglages d'attribution VIP."""

import html
import logging
from telegram import Update
from telegram.ext import ContextTypes
from ui.user import compte as ui

logger = logging.getLogger(__name__)


class CompteManager:
    """Gestionnaire de persistance, de statut et de préférences pour les utilisateurs."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("CompteManager initialisé avec support réglages VIP")

    async def ensure_user_registered(self, update: Update) -> bool:
        """Enregistre ou met à jour les informations du profil utilisateur en base."""
        user = update.effective_user
        if not user:
            logger.warning("Impossible d'extraire les données utilisateur depuis la mise à jour.")
            return False

        full_first_name = user.first_name or ""
        if user.last_name:
            full_first_name = f"{full_first_name} {user.last_name}".strip()

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, date_inscription, derniere_activite)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        username = VALUES(username),
                        first_name = VALUES(first_name),
                        derniere_activite = NOW()
                    """,
                    (
                        int(user.id),
                        user.username or None,
                        full_first_name[:64],
                    ),
                )

                if cursor.rowcount == 1:
                    logger.info("Nouvel utilisateur enregistré : %s (%s)", user.id, full_first_name)
                elif cursor.rowcount == 2:
                    logger.debug("Profil utilisateur synchronisé : %s", user.id)

                return True

        except Exception as exc:
            logger.error("Erreur enregistrement utilisateur %s : %s", user.id, exc, exc_info=True)
            return False

    async def update_user_activity(self, user_id: int) -> bool:
        """Met à jour le timestamp de dernière activité."""
        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    "UPDATE users SET derniere_activite = NOW() WHERE user_id = %s",
                    (int(user_id),),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("Erreur mise à jour activité utilisateur %s : %s", user_id, exc)
            return False

    async def get_user_display_name(self, user_id: int) -> str:
        """Retourne un nom d'affichage propre (Prénom, @username ou identifiant)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT first_name, username FROM users WHERE user_id = %s",
                    (int(user_id),),
                )
                row = cursor.fetchone()

                if row:
                    if row.get("first_name"):
                        return html.escape(row["first_name"])
                    if row.get("username"):
                        return f"@{html.escape(row['username'])}"

            return f"User {user_id}"

        except Exception as exc:
            logger.error("Erreur récupération nom utilisateur %s : %s", user_id, exc)
            return f"User {user_id}"

    # ==================== RÉGLAGES VIP ASSIGNATION AUTOMATIQUE ====================

    async def show_vip_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau de préférences d'attribution pour les membres VIP."""
        query = update.callback_query
        user = update.effective_user
        if not user:
            return

        if not self.db_manager.is_user_vip(user.id):
            if query:
                await query.answer("⭐ Cette fonctionnalité est réservée aux membres VIP.", show_alert=True)
            return

        if query:
            await query.answer()

        current_pref = self.db_manager.get_user_vip_auto_assign(user.id)
        target_staff_alias = None
        if current_pref not in ("prompt", "none") and current_pref.isdigit():
            target_staff_alias = self.db_manager.get_staff_alias(int(current_pref))

        text, kb = ui.build_vip_settings_content(current_pref, target_staff_alias)

        if query:
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            else:
                try:
                    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
                except Exception:
                    await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Aiguille les modifications de préférences d'assignation VIP."""
        query = update.callback_query
        user = update.effective_user
        if not query or not user:
            return

        if not self.db_manager.is_user_vip(user.id):
            await query.answer("⭐ Réservé aux membres VIP.", show_alert=True)
            return

        if data == "vip_set_assign_prompt":
            self.db_manager.set_user_vip_auto_assign(user.id, "prompt")
            await query.answer("✅ Préférence enregistrée : Choix manuel à chaque création.")
            await self.show_vip_settings_menu(update, context)
            return

        elif data == "vip_set_assign_none":
            self.db_manager.set_user_vip_auto_assign(user.id, "none")
            await query.answer("✅ Préférence enregistrée : Attribution directe à toute l'équipe.")
            await self.show_vip_settings_menu(update, context)
            return

        elif data == "vip_pick_auto_staff":
            await query.answer()
            await self._show_vip_staff_auto_picker(query, context, user.id)
            return

        elif data.startswith("vip_set_assign_staff_"):
            target_staff_id = data.replace("vip_set_assign_staff_", "")
            self.db_manager.set_user_vip_auto_assign(user.id, target_staff_id)
            alias = self.db_manager.get_staff_alias(int(target_staff_id))
            await query.answer(f"✅ Piégeur par défaut défini : {alias} !")
            await self.show_vip_settings_menu(update, context)
            return

    async def _show_vip_staff_auto_picker(self, query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Affiche les piégeurs disponibles pour définir un référent attitré."""
        equipe = self.db_manager.get_available_staff()
        text, kb = ui.build_vip_staff_picker_content(equipe, user_id)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Répond aux messages texte non reconnus hors navigation et édition."""
        if not update.effective_user or not update.message:
            return

        await self.update_user_activity(update.effective_user.id)
        await update.message.reply_text(
            ui.get_unrecognized_text_message(),
            parse_mode="HTML",
        )