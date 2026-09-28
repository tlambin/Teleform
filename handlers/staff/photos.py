"""Module de gestion de l'affichage des photos et fiches textuelles jointes aux demandes."""

import logging
from telegram import InputMediaPhoto, Update
from telegram.ext import ContextTypes
from ui.staff import demandes as ui

logger = logging.getLogger(__name__)


class PhotosManager:
    """Gestionnaire d'affichage des fiches demandes avec photo intégrée ou vue texte."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("PhotosManager initialisé avec supervision hiérarchique")

    async def voir_photo_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche ou met à jour la fiche avec sa photo native sans bouton de bascule texte."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_staff(update.effective_user.id):
            return

        data = query.data or ""
        custom_back = None
        if "_back_" in data:
            parts = data.replace("voir_photo_", "").split("_back_")
            demande_id = int(parts[0])
            custom_back = parts[1]
        else:
            try:
                demande_id = int(data.split("_")[2])
            except (IndexError, ValueError) as exc:
                logger.error("Erreur format callback photo : %s", exc)
                return

        viewer_id = update.effective_user.id
        is_admin_or_owner = self.config.is_admin(viewer_id) or self.config.is_owner(viewer_id)

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande or not demande.get("photo_id"):
                await query.answer("❌ Aucune photo associée à cette demande.", show_alert=True)
                return

            caption = ui.format_photo_demande_card(demande, self.db_manager, is_photo=True)
            keyboard = ui.build_keyboard_for_viewer(demande, viewer_id, custom_back, is_admin_or_owner=is_admin_or_owner)
            chat_id = query.message.chat_id if query.message else None

            if query.message and query.message.photo:
                media = InputMediaPhoto(
                    media=demande["photo_id"],
                    caption=caption,
                    parse_mode="HTML"
                )
                await query.edit_message_media(media=media, reply_markup=keyboard)
            else:
                if query.message:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                if chat_id:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=demande["photo_id"],
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )

        except Exception as exc:
            logger.error("Erreur affichage photo intégrée %s : %s", demande_id, exc, exc_info=True)

    async def retour_texte_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la fiche textuelle complète ou redirige vers la photo selon le contenu."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_staff(update.effective_user.id):
            return

        data = query.data or ""
        custom_back = None
        if "_back_" in data:
            parts = data.replace("retour_texte_", "").split("_back_")
            demande_id = int(parts[0])
            custom_back = parts[1]
        else:
            try:
                demande_id = int(data.split("_")[-1])
            except (IndexError, ValueError) as exc:
                logger.error("Erreur extraction demande_id depuis %s : %s", query.data, exc)
                return

        viewer_id = update.effective_user.id
        is_admin_or_owner = self.config.is_admin(viewer_id) or self.config.is_owner(viewer_id)

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            if demande.get("photo_id") and not custom_back:
                await self.voir_photo_demande(update, context)
                return

            admin_en_charge = demande.get("admin_en_charge")
            admin_alias = self.db_manager.get_staff_alias(admin_en_charge) if admin_en_charge else "Non assigné"

            text = ui.format_photo_demande_card(demande, self.db_manager, is_photo=False, admin_alias=admin_alias)
            keyboard = ui.build_keyboard_for_viewer(demande, viewer_id, custom_back, is_admin_or_owner=is_admin_or_owner)
            chat_id = query.message.chat_id if query.message else None

            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
            else:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )

        except Exception as exc:
            logger.error("Erreur retour vue texte : %s", exc, exc_info=True)