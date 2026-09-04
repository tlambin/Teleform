"""Module de gestion de l'affichage des photos jointes aux demandes."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class PhotosManager:
    """Gestionnaire de bascule entre l'affichage photo et la fiche textuelle."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("PhotosManager initialisé")

    async def voir_photo_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bascule le message texte existant vers l'affichage photo avec légende enrichie."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            return

        try:
            demande_id = int(query.data.split("_")[2])
        except (IndexError, ValueError) as exc:
            logger.error("Erreur format callback photo: %s", exc)
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande or not demande.get("photo_id"):
                return

            priorite_icon = "💎" if demande.get("prioritaire") else "📝"
            type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
            montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
            nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()
            user_display = f"@{demande['username']}" if demande.get("username") else (demande.get("user_first_name") or f"User {demande['user_id']}")
            date_str = str(demande.get("date_creation", ""))[:16]

            caption_lines = [
                f"📷 <b>Photo de la demande #{demande.get('request_number', demande['id'])}</b>\n",
                f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
                f"📍 <b>Localisation :</b> {demande['localisation']}",
                f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
                f"📊 <b>Statut :</b> <code>{demande.get('statut')}</code>",
                f"🙋 <b>Demandeur :</b> {user_display}"
            ]

            if demande.get("details"):
                det = demande["details"]
                det_court = (det[:100] + "...") if len(det) > 100 else det
                caption_lines.append(f"💬 <b>Détails :</b> <i>{det_court}</i>")

            caption_lines.append(f"\n📅 <i>Reçue le {date_str}</i>")
            caption = "\n".join(caption_lines)

            # Sécurité limite 1024 caractères Telegram pour les captions
            if len(caption) > 1000:
                caption = caption[:997] + "..."

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Changer Statut", callback_data=f"change_status_{demande['id']}"),
                    InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("📄 Revenir au texte", callback_data=f"retour_texte_{demande['id']}")
                ]
            ])

            media = InputMediaPhoto(
                media=demande["photo_id"],
                caption=caption,
                parse_mode="HTML"
            )

            await query.edit_message_media(media=media, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur affichage photo intégrée %s: %s", demande_id, exc, exc_info=True)

    async def retour_texte_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Supprime le message photo et renvoie la fiche textuelle standard pour restaurer la vue."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            return

        try:
            demande_id = int(query.data.split("_")[-1])
        except (IndexError, ValueError) as exc:
            logger.error("Erreur extraction demande_id depuis %s: %s", query.data, exc)
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                return

            priorite_icon = "💎" if demande.get("prioritaire") else "📝"
            type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
            montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
            nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()
            user_display = f"@{demande['username']}" if demande.get("username") else (demande.get("user_first_name") or f"User {demande['user_id']}")
            date_str = str(demande.get("date_creation", ""))[:16]

            lines = [
                f"💌 <b>Demande #{demande.get('request_number', demande['id'])}</b>\n",
                f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
                f"📍 <b>Localisation :</b> {demande['localisation']}",
                f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
                f"📊 <b>Statut :</b> <code>{demande.get('statut')}</code>",
                f"🙋 <b>Demandeur :</b> {user_display}"
            ]

            reseaux = []
            if demande.get("instagram"):
                reseaux.append(f"📷 <a href='https://instagram.com/{demande['instagram']}'>@{demande['instagram']}</a>")
            if demande.get("snapchat"):
                reseaux.append(f"👻 <a href='https://snapchat.com/add/{demande['snapchat']}'>{demande['snapchat']}</a>")
            if reseaux:
                lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

            if demande.get("details"):
                lines.append(f"💬 <b>Détails :</b> <i>{demande['details']}</i>")

            lines.append(f"\n📅 <i>Reçue le {date_str}</i>")

            keyboard = [
                [
                    InlineKeyboardButton("📷 Photo", callback_data=f"voir_photo_{demande['id']}"),
                    InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande['id']}"),
                    InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")
                ]
            ]

            # Telegram n'autorise pas la conversion directe d'un message photo en message texte pur :
            # on supprime le message média actuel et on envoie le message texte propre.
            chat_id = query.message.chat_id
            await query.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )

        except Exception as exc:
            logger.error("Erreur retour vue texte: %s", exc, exc_info=True)