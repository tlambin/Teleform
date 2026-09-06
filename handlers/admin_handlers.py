"""Routeur principal des actions et callbacks d'administration avec relais groupé."""

import asyncio
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager

from .admin.alias import AliasManager
from .admin.dispo import DispoManager
from .admin.photos import PhotosManager
from .admin.statuts import StatutsManager
from .admin.suivi import SuiviManager

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Gestionnaire central des fonctionnalités administrateur."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        self.statuts_disponibles = [
            "📨 Reçue",
            "⏳ En attente",
            "🔄 En cours",
            "✅ Réussie",
            "⚠️ Difficile",
            "❌ Abandonnée",
        ]

        self.suivi = SuiviManager(db_manager, config)
        self.statuts = StatutsManager(db_manager, config, self.statuts_disponibles)
        self.photos = PhotosManager(db_manager, config)
        self.dispo = DispoManager(db_manager, config)
        self.alias = AliasManager(db_manager, config)

    async def handle_admin_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage sécurisé des callbacks administrateurs."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        data = query.data or ""

        if not self.config.is_admin(user_id, secure_mode=True):
            logger.warning("Tentative d'accès administrateur refusée pour l'utilisateur %s", user_id)
            await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        await query.answer()

        try:
            if data == "demandes_disponibles":
                await self.dispo.show_demandes_disponibles(update, context)

            elif data.startswith("dispo_"):
                await self.dispo.handle_callback_routing(update, context, data)

            elif data == "demandes_suivies":
                await self.suivi.show_demandes_suivies(update, context)

            elif data.startswith("suivi_"):
                await self.suivi.handle_callback_routing(update, context, data)

            elif data.startswith("voir_photo_"):
                await self.photos.voir_photo_demande(update, context)

            elif data.startswith("retour_texte_"):
                await self.photos.retour_texte_demande(update, context)

            elif data.startswith("suivre_demande_"):
                await self.suivi.suivre_demande(update, context)

            elif data.startswith("change_status_"):
                demande_id = int(data.split("_")[2])
                await self.statuts.show_status_change_menu(update, context, demande_id)

            elif data.startswith("set_status_"):
                await self.statuts.set_status_demande(update, context)

            elif data.startswith("mark_treated_menu_"):
                demande_id = int(data.replace("mark_treated_menu_", ""))
                await self.statuts.show_status_change_menu(update, context, demande_id)

            elif data.startswith("contacter_"):
                demande_id = int(data.replace("contacter_", ""))
                await self._prompt_contact_user(update, context, demande_id)

            elif data.startswith("contact_mode_"):
                parts = data.split("_")
                demande_id = int(parts[2])
                allow_reply = (parts[3] == "yes")
                await self._start_contact_input(update, context, demande_id, allow_reply)

            elif data.startswith("send_batch_"):
                demande_id = int(data.replace("send_batch_", ""))
                await self._dispatch_media_batch(update, context, demande_id)

            elif data.startswith("cancel_contact_"):
                demande_id = int(data.replace("cancel_contact_", ""))
                context.user_data.pop("contact_session", None)
                await query.edit_message_text(
                    "❌ Envoi annulé. Aucun fichier n'a été transmis.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{demande_id}")
                    ]])
                )

            else:
                logger.warning("Callback admin non intercepté: %s", data)
                await query.answer("Action non reconnue.", show_alert=True)

        except Exception as exc:
            logger.error("Erreur callback admin '%s': %s", data, exc, exc_info=True)
            await self._handle_callback_error(query)

    """ async def _route_dispo_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        parts = data.split("_")
        page = 0
        if len(parts) >= 3 and parts[-1].isdigit():
            current_idx = int(parts[-1])
            if "prev" in data:
                page = max(0, current_idx - 1)
            elif "next" in data:
                page = current_idx + 1
        await self.dispo.show_demandes_disponibles_page(update, context, page)"""

    async def _route_suivi_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        parts = data.split("_")
        page = 0
        if len(parts) >= 3 and parts[-1].isdigit():
            current_idx = int(parts[-1])
            if "prev" in data:
                page = max(0, current_idx - 1)
            elif "next" in data:
                page = current_idx + 1
        await self.suivi.show_demandes_suivies_page(update, context, page)

    async def _prompt_contact_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Demande d'abord si l'utilisateur doit pouvoir répondre."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id, request_number, user_id, prenom FROM demandes WHERE id = %s",
                    (demande_id,),
                )
                row = cursor.fetchone()

            if not row:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            req_num = row.get("request_number", row["id"])

            text = (
                f"💬 <b>Contacter {row['prenom']}</b> (Demande #{req_num})\n\n"
                "Souhaitez-vous autoriser le demandeur à répondre à cet envoi ?"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💬 Oui (avec bouton réponse)", callback_data=f"contact_mode_{demande_id}_yes"),
                    InlineKeyboardButton("🔒 Non (informatif / clôture)", callback_data=f"contact_mode_{demande_id}_no")
                ],
                [InlineKeyboardButton("❌ Annuler", callback_data=f"retour_texte_{demande_id}")]
            ])

            if query.message and query.message.photo:
                await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur prompt contact utilisateur: %s", exc)
            await query.answer("❌ Erreur technique.", show_alert=True)

    async def _start_contact_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, allow_reply: bool):
        """Initialise la session de collecte de messages et fichiers."""
        query = update.callback_query
        if not query:
            return

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, request_number, user_id, prenom FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        if not row:
            await query.answer("❌ Demande introuvable.")
            return

        req_num = row.get("request_number", row["id"])

        # Structure de la file d'attente de messages/médias
        context.user_data["contact_session"] = {
            "demande_id": demande_id,
            "target_user_id": row["user_id"],
            "prenom": row["prenom"],
            "req_num": req_num,
            "allow_reply": allow_reply,
            "visual_media": [],  # Photos et vidéos (regroupées en albums)
            "doc_media": [],     # Documents génériques
            "text_notes": [],    # Messages texte
        }

        mode_str = "💬 Réponse autorisée (1 fois)" if allow_reply else "🔒 Message informatif (réponse bloquée)"
        text = (
            f"📦 <b>Session d'envoi vers {row['prenom']} (Demande #{req_num})</b>\n"
            f"Mode : <b>{mode_str}</b>\n\n"
            "Envoyez vos photos, vidéos, documents ou messages texte (en un seul envoi ou plusieurs).\n\n"
            "<i>Tous vos éléments seront conservés et transmis en groupe quand vous validerez.</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Valider et envoyer le lot (0 élément)", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_contact_{demande_id}")]
        ])

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def handle_collect_admin_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Collecte les fichiers sans spammer la conversation, en mettant à jour un statut propre."""
        msg = update.message
        if not msg:
            return False

        session = context.user_data.get("contact_session")
        if not session:
            return False

        demande_id = session["demande_id"]
        caption = (msg.caption or "").strip()

        # 1. Traitement des photos
        if msg.photo:
            file_id = msg.photo[-1].file_id
            session["visual_media"].append({"type": "photo", "file_id": file_id, "caption": caption})
        # 2. Traitement des vidéos
        elif msg.video:
            file_id = msg.video.file_id
            session["visual_media"].append({"type": "video", "file_id": file_id, "caption": caption})
        # 3. Traitement des documents
        elif msg.document:
            file_id = msg.document.file_id
            session["doc_media"].append({"file_id": file_id, "caption": caption})
        # 4. Traitement du texte pur
        elif msg.text:
            session["text_notes"].append(msg.text.strip())

        total = len(session["visual_media"]) + len(session["doc_media"]) + len(session["text_notes"])

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🚀 Envoyer tout le lot ({total} élément{'s' if total > 1 else ''})", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("❌ Annuler tout", callback_data=f"cancel_contact_{demande_id}")]
        ])

        status_text = (
            f"📥 <b>Panier d'envoi mis à jour : {total} élément{'s' if total > 1 else ''} prêt{'s' if total > 1 else ''}</b>\n\n"
            "Vous pouvez encore déposer d'autres fichiers ou cliquer ci-dessous pour expédier l'ensemble :"
        )

        # Si un message d'état existe déjà, on le met à jour pour éviter le spam visuel
        last_status_msg_id = session.get("last_status_msg_id")
        if last_status_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=msg.chat_id,
                    message_id=last_status_msg_id,
                    text=status_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return True
            except Exception:
                pass

        # Premier message de validation du lot
        sent_msg = await msg.reply_text(
            status_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        session["last_status_msg_id"] = sent_msg.message_id
        return True

    async def _dispatch_media_batch(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Envoie l'ensemble du lot au demandeur sous forme d'albums natifs et documents groupés."""
        query = update.callback_query
        session = context.user_data.pop("contact_session", None)

        if not session or session.get("demande_id") != demande_id:
            if query:
                await query.answer("❌ Aucune session active.", show_alert=True)
            return

        admin_id = update.effective_user.id
        target_user_id = session["target_user_id"]
        req_num = session["req_num"]
        allow_reply = session["allow_reply"]
        alias = self.db_manager.get_admin_alias(admin_id)

        visuals = session["visual_media"]
        docs = session["doc_media"]
        texts = session["text_notes"]

        if not visuals and not docs and not texts:
            if query:
                await query.answer("⚠️ Le lot est vide. Envoyez au moins un élément avant d'expédier.", show_alert=True)
            context.user_data["contact_session"] = session
            return

        if query:
            await query.edit_message_text("⏳ Transmission du lot en cours...")

        # Préparation du texte d'en-tête
        combined_text = "\n".join(texts)
        corps = f"\n\n« {combined_text} »" if combined_text else ""
        footer = "\n\n<i>Vous pouvez répondre une seule fois ci-dessous.</i>" if allow_reply else ""

        header_text = (
            f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\n"
            f"De : <b>{alias}</b>"
            f"{corps}"
            f"{footer}"
        )

        user_keyboard = None
        if allow_reply:
            user_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Répondre", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
            ]])

        try:
            # 1. Envoi des Photos et Vidéos par lots de 10 (limite native de Telegram)
            if visuals:
                for i in range(0, len(visuals), 10):
                    batch = visuals[i:i + 10]
                    media_group = []
                    for idx, item in enumerate(batch):
                        # Légende sur le tout premier fichier du premier album
                        item_caption = header_text if (i == 0 and idx == 0) else item["caption"]
                        if item["type"] == "photo":
                            media_group.append(InputMediaPhoto(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))
                        elif item["type"] == "video":
                            media_group.append(InputMediaVideo(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))

                    if len(media_group) == 1:
                        # Si un seul visuel isolé
                        single = media_group[0]
                        if isinstance(single, InputMediaPhoto):
                            await context.bot.send_photo(chat_id=target_user_id, photo=single.media, caption=single.caption, parse_mode="HTML")
                        else:
                            await context.bot.send_video(chat_id=target_user_id, video=single.media, caption=single.caption, parse_mode="HTML")
                    else:
                        # Envoi sous forme d'ALBUM natif Telegram
                        await context.bot.send_media_group(chat_id=target_user_id, media=media_group)

            # 2. Envoi des Documents par lots de 10
            if docs:
                for i in range(0, len(docs), 10):
                    batch = docs[i:i + 10]
                    doc_group = []
                    for idx, item in enumerate(batch):
                        # Légende si pas encore de visuel envoyé
                        item_caption = header_text if (not visuals and i == 0 and idx == 0) else item["caption"]
                        doc_group.append(InputMediaDocument(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))

                    if len(doc_group) == 1:
                        await context.bot.send_document(chat_id=target_user_id, document=doc_group[0].media, caption=doc_group[0].caption, parse_mode="HTML")
                    else:
                        await context.bot.send_media_group(chat_id=target_user_id, media=doc_group)

            # 3. Si aucun fichier (texte seul)
            if not visuals and not docs and texts:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=header_text,
                    parse_mode="HTML",
                    reply_markup=user_keyboard
                )

            # 4. Si fichiers avec réponse autorisée : envoi du bouton de réponse dédié
            elif user_keyboard:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="💬 <i>Vous pouvez répondre à cet envoi en cliquant ci-dessous :</i>",
                    parse_mode="HTML",
                    reply_markup=user_keyboard
                )

            total_items = len(visuals) + len(docs) + len(texts)
            done_text = (
                f"✅ <b>Lot de {total_items} élément{'s' if total_items > 1 else ''} envoyé avec succès !</b>\n"
                f"Les fichiers ont été regroupés sous votre alias officiel : <code>{alias}</code>"
            )
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{demande_id}")
            ]])

            if query and query.message:
                await query.message.reply_text(done_text, parse_mode="HTML", reply_markup=back_keyboard)
            else:
                await context.bot.send_message(chat_id=admin_id, text=done_text, parse_mode="HTML", reply_markup=back_keyboard)

        except Exception as exc:
            logger.error("Échec dispatch batch vers %s : %s", target_user_id, exc, exc_info=True)
            if query and query.message:
                await query.message.reply_text("❌ Une erreur est survenue lors de l'envoi du lot.")

    async def _handle_callback_error(self, query):
        try:
            if query.message and query.message.photo:
                await query.answer("❌ Une erreur technique est survenue.", show_alert=True)
            else:
                await query.edit_message_text(
                    "❌ <b>Erreur technique</b> lors du traitement de l'action admin.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Menu Admin", callback_data="gerer_demandes")
                    ]])
                )
        except Exception as fallback_exc:
            logger.error("Échec notification erreur admin: %s", fallback_exc)
            await query.answer("❌ Erreur système.")