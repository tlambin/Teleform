"""Module de recherche de membres et de gestion des bannissements."""

import logging
from telegram import Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes
from utils.session import session_manager
from ui.admin import users as ui

logger = logging.getLogger(__name__)


class MembresManager:
    """Gère l'affichage de l'annuaire des bannis, les révocations et la recherche textuelle/ID avec résilience uWSGI."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                    )

    # ==================== RECHERCHE DE MEMBRE ====================

    async def prompt_search(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la saisie du terme de recherche."""
        await query.answer()
        user_id = query.from_user.id
        context.user_data["waiting_member_search"] = True
        session_manager.set_state(user_id, "waiting_member_search", True, ttl=600.0)

        text_search, kb = ui.get_search_prompt_content()
        await self._safe_edit_or_send(query, context, text_search, reply_markup=kb)

    async def handle_search_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Traite la réponse textuelle de recherche."""
        if not update.message or not update.message.text:
            return False

        user_id = update.effective_user.id
        is_waiting = context.user_data.pop("waiting_member_search", False) or session_manager.get_state(user_id, "waiting_member_search")
        if not is_waiting:
            return False

        session_manager.clear_state(user_id, "waiting_member_search")
        saisie = update.message.text.strip().replace("@", "")

        with self.db_manager.get_cursor() as cursor:
            if saisie.isdigit():
                cursor.execute("SELECT user_id, first_name, username FROM users WHERE user_id = %s", (int(saisie),))
            else:
                cursor.execute("SELECT user_id, first_name, username FROM users WHERE LOWER(username) = LOWER(%s)", (saisie,))
            user_data = cursor.fetchone()

        if not user_data:
            text_err, kb_err = ui.get_member_not_found_content()
            await update.message.reply_text(
                text_err,
                parse_mode="HTML",
                reply_markup=kb_err,
            )
            return True

        target_id = int(user_data["user_id"])
        from handlers.staff.profils import ProfilsManager
        prof = ProfilsManager(self.db_manager, self.config)

        if self.db_manager.is_staff(target_id):
            await prof.show_admin_profile(update, context, target_id)
        else:
            await prof._render_user_profile(update, context, target_id)
        return True

    # ==================== LISTE DES BANNIS ====================

    async def show_banned_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche les comptes actuellement bannis."""
        query = update.callback_query
        if query:
            await query.answer()

        limit = 5
        offset = page * limit

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM banned_users")
            total = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT b.user_id, b.banned_by, b.reason, b.date_ban,
                       u.first_name, u.username,
                       a.alias AS admin_alias
                FROM banned_users b
                LEFT JOIN users u ON b.user_id = u.user_id
                LEFT JOIN admins a ON b.banned_by = a.user_id
                ORDER BY b.date_ban DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            bannis = cursor.fetchall()

        text, keyboard = ui.build_banned_list_content(bannis, total, page, limit)

        if query:
            await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    # ==================== BANNISSEMENTS & MOTIFS ====================

    async def prompt_ban_reason(self, query, context: ContextTypes.DEFAULT_TYPE, target_id: int, is_staff: bool, origin_demande_id: int = 0):
        """Demande le motif du bannissement au clavier."""
        user_id = query.from_user.id
        ban_payload = {
            "target_id": target_id,
            "is_staff": is_staff,
            "origin_demande_id": origin_demande_id,
        }
        context.user_data["pending_ban_data"] = ban_payload
        context.user_data["waiting_ban_reason"] = True
        session_manager.set_state(user_id, "ban_process", ban_payload, ttl=900.0)

        text, kb = ui.get_ban_reason_prompt_content(target_id, is_staff, origin_demande_id)
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)

    async def handle_ban_reason_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Enregistre le bannissement après saisie de la raison."""
        if not update.message or not update.message.text:
            return False

        admin_id = update.effective_user.id
        ban_data = context.user_data.pop("pending_ban_data", None) or session_manager.get_state(admin_id, "ban_process")
        context.user_data.pop("waiting_ban_reason", None)
        session_manager.clear_state(admin_id, "ban_process")

        if not ban_data:
            return False

        reason = update.message.text.strip()
        if reason.lower() in ("passer", "non", "aucun", "none"):
            reason = "Non spécifié"

        target_id = ban_data["target_id"]
        is_staff = ban_data["is_staff"]

        self.db_manager.ban_user(target_id, banned_by=admin_id, reason=reason)

        if is_staff:
            self.db_manager.abandon_staff_demandes_for_pause(target_id)
            self.db_manager.set_staff_pause_status(target_id, paused=True)

        try:
            msg_banni = ui.get_ban_notification_message(reason)
            await context.bot.send_message(chat_id=target_id, text=msg_banni, parse_mode="HTML")
        except Forbidden:
            logger.info("L'utilisateur %s a déjà bloqué le bot lors de son bannissement.", target_id)
            try:
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("UPDATE users SET is_bot_blocked = 1 WHERE user_id = %s", (target_id,))
            except Exception as block_err:
                logger.debug("Impossible d'actualiser le flag bloqué pour %s : %s", target_id, block_err)
        except TelegramError as tg_err:
            logger.warning("Échec notification bannissement à %s : %s", target_id, tg_err)

        success_msg, kb = ui.build_ban_success_content(target_id, reason, is_staff)
        await update.message.reply_text(success_msg, parse_mode="HTML", reply_markup=kb)
        return True