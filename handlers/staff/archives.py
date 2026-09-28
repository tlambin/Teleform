"""Module de consultation des demandes archivées pour l'équipe Staff et Administration."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes
from ui.staff import demandes as ui

logger = logging.getLogger(__name__)


class ArchivesManager:
    """Gestionnaire d'affichage et de navigation dans les archives (personnelles ou générales)."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ArchivesManager initialisé avec support double vue (personnelle & générale)")

    async def _safe_edit_media_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, reply_markup):
        """Met à jour une photo existante ou envoie une nouvelle bulle photo proprement."""
        if query.message and query.message.photo:
            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML"),
                    reply_markup=reply_markup,
                )
                return
            except Exception:
                pass

        if query.message:
            try:
                await query.message.delete()
            except Exception:
                pass

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def _safe_edit_text_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup):
        """Met à jour un message texte ou supprime l'ancienne photo pour réémettre du texte."""
        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )

    async def show_archives(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0, is_global: bool = False):
        """Affiche les archives personnelles de l'opérateur ou les archives générales pour les admins."""
        query = update.callback_query
        user = update.effective_user
        if not user:
            return

        user_id = user.id

        if is_global:
            privs = self.db_manager.get_admin_privileges(user_id)
            if not (self.db_manager.is_owner(user_id) or privs.get("can_view_archives", False)):
                if query:
                    await query.answer("❌ Vous n'avez pas la permission de consulter les archives générales.", show_alert=True)
                return
            admin_target = None
        else:
            if not self.config.is_staff(user_id):
                if query:
                    await query.answer("❌ Accès réservé au personnel opérationnel.", show_alert=True)
                return
            admin_target = user_id

        total = self.db_manager.get_archives_count(admin_id=admin_target)
        back_cb = "parametres" if is_global else "gerer_demandes"
        back_label = "⬅️ RETOUR"

        if total == 0:
            if is_global:
                msg = "📭 <b>Archives Générales</b>\n\nAucun dossier archivé enregistré sur la plateforme."
            else:
                msg = "📭 <b>Mes Dossiers Clôturés</b>\n\nVous n'avez pas encore finalisé ou archivé de demande."

            kb = InlineKeyboardMarkup([[InlineKeyboardButton(back_label, callback_data=back_cb)]])
            if query:
                await self._safe_edit_text_or_send(query, context, msg, kb)
            else:
                await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
            return

        page = max(0, min(page, total - 1))
        demande = self.db_manager.get_archives_page(page=page, admin_id=admin_target)
        if not demande:
            return

        staff_alias = None
        if is_global and demande.get("admin_en_charge"):
            staff_alias = self.db_manager.get_staff_alias(demande["admin_en_charge"])

        caption = ui.format_archive_card(demande, page, total, is_global=is_global, staff_alias=staff_alias)

        admin_charge = demande.get("admin_en_charge")
        is_admin_or_owner = self.config.is_admin(user_id) or self.config.is_owner(user_id)
        is_referent = (admin_charge is not None and int(admin_charge) == int(user_id))
        can_manage = is_admin_or_owner or is_referent

        kb = ui.build_archive_keyboard(demande, page, total, can_manage=can_manage, is_global=is_global)
        photo_id = demande.get("photo_id")

        if query:
            if photo_id:
                await self._safe_edit_media_or_send(query, context, photo_id, caption, kb)
            else:
                await self._safe_edit_text_or_send(query, context, caption, kb)
        else:
            if photo_id:
                await update.message.reply_photo(photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                await update.message.reply_text(caption, parse_mode="HTML", reply_markup=kb)

    async def handle_archives_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite les actions de contact et d'annulation d'archivage."""
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        user_id = update.effective_user.id
        data = query.data

        if data.startswith("contacter_archive_"):
            archive_id = int(data.replace("contacter_archive_", ""))
            archive = self.db_manager.get_archive_by_id(archive_id)
            if not archive:
                await query.answer("❌ Archive introuvable.", show_alert=True)
                return

            admin_charge = archive.get("admin_en_charge")
            can_manage = (self.config.is_admin(user_id) or self.config.is_owner(user_id) or (admin_charge and int(admin_charge) == user_id))
            if not can_manage:
                await query.answer("🔒 Action réservée à l'opérateur en charge ou à un administrateur.", show_alert=True)
                return

            context.user_data["contact_session"] = {
                "target_user_id": archive["user_id"],
                "origin_type": "archive",
                "archive_id": archive_id,
            }
            client_prenom = html.escape(str(archive.get("prenom") or "le client"))
            msg = (
                f"💬 <b>Messagerie directe avec le client (Dossier #{archive.get('original_id') or archive['id']})</b>\n\n"
                f"Cible : <b>{client_prenom}</b>\n\n"
                "Tapez votre message ou transmettez des fichiers (photos, vidéos, documents).\n"
                "Tapez /stop pour annuler à tout moment."
            )
            cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_user_contact")]])
            await self._safe_edit_text_or_send(query, context, msg, cancel_kb)
            return

        elif data.startswith("unarchive_reussie_"):
            parts = data.split("_")
            archive_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
            is_global = bool(int(parts[4])) if len(parts) > 4 else False

            archive = self.db_manager.get_archive_by_id(archive_id)
            if not archive:
                await query.answer("❌ Archive introuvable.", show_alert=True)
                return

            admin_charge = archive.get("admin_en_charge")
            can_manage = (self.config.is_admin(user_id) or self.config.is_owner(user_id) or (admin_charge and int(admin_charge) == user_id))
            if not can_manage:
                await query.answer("🔒 Action réservée à l'opérateur en charge ou à un administrateur.", show_alert=True)
                return

            restored = self.db_manager.desarchiver_vers_reussie_active(archive_id)
            if restored:
                new_id = restored.get("new_demande_id")
                await query.answer("✅ Dossier restauré en statut « Réussie (Active) » !", show_alert=True)
                logger.info("Dossier archive #%s restauré en active #%s par %s", archive_id, new_id, user_id)
                await self.show_archives(update, context, page=max(0, page - 1), is_global=is_global)
            else:
                await query.answer("❌ Échec lors de la restauration du dossier.", show_alert=True)
            return

        elif data.startswith("unarchive_abandon_"):
            parts = data.split("_")
            archive_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
            is_global = bool(int(parts[4])) if len(parts) > 4 else False

            archive = self.db_manager.get_archive_by_id(archive_id)
            if not archive:
                await query.answer("❌ Archive introuvable.", show_alert=True)
                return

            admin_charge = archive.get("admin_en_charge")
            can_manage = (self.config.is_admin(user_id) or self.config.is_owner(user_id) or (admin_charge and int(admin_charge) == user_id))
            if not can_manage:
                await query.answer("🔒 Action réservée à l'opérateur en charge ou à un administrateur.", show_alert=True)
                return

            success, alert_msg, restored = self.db_manager.desarchiver_demande_abandonnee(archive_id, operator_id=user_id)
            if success:
                await query.answer(f"✅ {alert_msg}", show_alert=True)
                await self.show_archives(update, context, page=max(0, page - 1), is_global=is_global)
            else:
                await query.answer(f"🚫 {alert_msg}", show_alert=True)
            return