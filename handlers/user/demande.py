"""Gestion de la consultation et du cycle de vie des demandes utilisateur."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes
from . import demande_ui as ui

logger = logging.getLogger(__name__)


class DemandeManager:
    """Gestionnaire d'affichage, de navigation et de vérification des quotas."""

    ACTIVE_STATUSES = ("📥 Reçue", "⏳ En attente", "🔄 En cours")

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager
        logger.info("DemandeManager initialisé avec charte graphique unifiée et support RBAC")

    def check_creation_quota(self, user_id: int) -> tuple[bool, str]:
        """Contrôle les plafonds global et individuel avant création (contourné pour VIP)."""
        if self.db_manager.is_user_vip(user_id):
            return True, ""

        placeholders = ", ".join(["%s"] * len(self.ACTIVE_STATUSES))
        status_filter = f"statut IN ({placeholders})"

        max_total = self.config.get_max_total_demandes()
        if max_total > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM demandes WHERE {status_filter}",
                    self.ACTIVE_STATUSES,
                )
                row = cursor.fetchone()
                total_actif = row["total"] if row else 0

            if total_actif >= max_total:
                return False, (
                    "🚫 <b>SERVICE SATURÉ</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Le plafond global des demandes en cours sur la plateforme est atteint.\n\n"
                    "<i>Veuillez patienter ou réessayer un peu plus tard.</i>"
                )

        max_user = self.config.get_max_demandes_per_user()
        if max_user > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS count_user FROM demandes WHERE user_id = %s AND {status_filter}",
                    (int(user_id), *self.ACTIVE_STATUSES),
                )
                row = cursor.fetchone()
                user_actif = row["count_user"] if row else 0

            if user_actif >= max_user:
                return False, (
                    "⚠️ <b>QUOTA PERSONNEL ATTEINT</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"Vous avez déjà <b>{user_actif}/{max_user}</b> demande(s) actives en traitement.\n\n"
                    "Attendez qu'un dossier se termine pour en créer un autre.\n\n"
                    "⭐ <i>Le statut VIP permet d'ouvrir des demandes en illimité.</i>"
                )

        return True, ""

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée pour afficher les demandes de l'utilisateur."""
        user = update.effective_user
        if not user:
            return

        if update.callback_query:
            await update.callback_query.answer()
            await self.show_demande_page(update, context, user.id, page=0, edit_message=True)
        else:
            await self.account_manager.ensure_user_registered(update)
            await self.show_demande_page(update, context, user.id, page=0, edit_message=False)

    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Gère la pagination des demandes actives et des archives."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        parts = callback_data.split("_")

        if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
            target_page = int(parts[2])
            await self.show_demande_page(update, context, update.effective_user.id, page=target_page, edit_message=True)

        elif len(parts) >= 4 and parts[1] == "arch" and parts[2] == "page" and parts[3].isdigit():
            target_page = int(parts[3])
            await self.show_user_archive_page(update, context, update.effective_user.id, page=target_page)

        elif callback_data == "mes_archives":
            await self.show_user_archive_page(update, context, update.effective_user.id, page=0)

        else:
            await self.voir_demandes(update, context)

    async def show_demande_page(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        page: int = 0,
        edit_message: bool = True
    ):
        """Affiche une demande à la fois avec sa photo obligatoire et sa pagination."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM demandes WHERE user_id = %s", (int(user_id),))
                count_res = cursor.fetchone()
                total_pages = count_res["total"] if count_res else 0

                if total_pages == 0:
                    await self._send_no_requests_message(update, context, edit_message, user_id)
                    return

                page = max(0, min(page, total_pages - 1))

                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, age, localisation,
                           photo_id, statut, is_difficile, reussie_substatus,
                           prioritaire, montant, date_creation,
                           date_modification, instagram, snapchat, details,
                           admin_en_charge, ancien_admin_alias, raison_abandon,
                           last_vip_reminder, paiement_statut
                    FROM demandes
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1 OFFSET %s
                    """,
                    (int(user_id), page),
                )
                demande = cursor.fetchone()

            if not demande:
                await self._send_no_requests_message(update, context, edit_message, user_id)
                return

            caption_text = ui.format_demande_card(demande, page, total_pages, self.db_manager)
            can_create, _ = self.check_creation_quota(user_id)
            nb_archives = self.db_manager.get_archives_count(user_id=user_id)
            keyboard = ui.build_navigation_keyboard(demande, page, total_pages, user_id, can_create, nb_archives, self.db_manager)
            photo_id = demande.get("photo_id")
            chat_id = update.effective_chat.id if update.effective_chat else None

            if edit_message and update.callback_query and update.callback_query.message:
                query = update.callback_query

                if query.message.photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=photo_id, caption=caption_text, parse_mode="HTML"),
                        reply_markup=keyboard,
                    )
                else:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    if chat_id:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_id,
                            caption=caption_text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
            else:
                if chat_id:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_id,
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )

        except Exception as exc:
            logger.error("Erreur consultation demandes : %s", exc, exc_info=True)
            await self._send_error_message(update, context, edit_message)

    async def show_user_archive_page(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        page: int = 0
    ):
        """Affiche les demandes archivées propres à l'utilisateur."""
        query = update.callback_query
        total_archives = self.db_manager.get_archives_count(user_id=user_id)

        if total_archives == 0:
            msg = (
                "📦 <b>MES ARCHIVES PERSONNELLES</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Vous n'avez actuellement aucun dossier archivé.\n\n"
                "<i>Les demandes finalisées ou annulées apparaîtront ici automatiquement.</i>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Voir mes demandes actives", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            if query:
                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=msg,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                else:
                    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            return

        page = max(0, min(page, total_archives - 1))
        archive_item = self.db_manager.get_archives_page(page=page, user_id=user_id)
        if not archive_item:
            return

        caption_text = ui.format_user_archive_card(archive_item, page, total_archives, self.db_manager)
        keyboard = ui.build_user_archive_keyboard(page, total_archives)
        photo_id = archive_item.get("photo_id")
        chat_id = update.effective_chat.id if update.effective_chat else None

        if query and query.message:
            if query.message.photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_id, caption=caption_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
            else:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_id,
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
        else:
            if chat_id:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

    async def _send_no_requests_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool, user_id: int):
        """Message affiché quand aucune demande n'est enregistrée."""
        can_create, _ = self.check_creation_quota(user_id)
        nb_archives = self.db_manager.get_archives_count(user_id=user_id)
        keyboard = ui.build_no_requests_keyboard(can_create, nb_archives)

        text = (
            "📭 <b>AUCUN DOSSIER ACTIF</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Vous n'avez aucune demande en cours de traitement pour le moment.\n\n"
            "<i>Créez votre première demande ou consultez vos archives :</i>"
        )
        chat_id = update.effective_chat.id if update.effective_chat else None

        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_error_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool):
        """Message en cas de problème de connexion base."""
        text = "❌ <b>Erreur technique</b> lors de la récupération de vos demandes."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
        ])
        chat_id = update.effective_chat.id if update.effective_chat else None

        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)