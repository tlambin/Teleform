"""Module de gestion de l'affichage des photos jointes aux demandes."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class PhotosManager:
    """Gestionnaire d'affichage des fiches demandes avec photo intégrée."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("PhotosManager initialisé")

    async def voir_photo_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche ou met à jour la fiche avec sa photo native sans bouton de bascule texte."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            return

        try:
            demande_id = int(query.data.split("_")[2])
        except (IndexError, ValueError) as exc:
            logger.error("Erreur format callback photo : %s", exc)
            return

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

            priorite_icon = "💎" if demande.get("prioritaire") else "📝"
            type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
            montant_val = float(demande.get("montant") or 0.0)
            montant_str = f" ({montant_val:.2f} €)" if demande.get("prioritaire") else ""

            prenom_esc = html.escape(str(demande.get("prenom") or ""))
            nom_esc = html.escape(str(demande.get("nom") or ""))
            nom_complet = f"{prenom_esc} {nom_esc}".strip()
            loc_esc = html.escape(str(demande.get("localisation") or "Non précisée"))
            
            statut_display = self.db_manager.format_statut_display(
                demande.get("statut", "📥 Reçue"),
                demande.get("is_difficile", False),
                demande.get("reussie_substatus")
            )
            statut_esc = html.escape(statut_display)
            req_num = html.escape(str(demande.get("request_number", demande["id"])))

            if demande.get("username"):
                user_display = f"@{html.escape(demande['username'])}"
            elif demande.get("user_first_name"):
                user_display = html.escape(demande["user_first_name"])
            else:
                user_display = f"User {demande['user_id']}"

            date_str = str(demande.get("date_creation", ""))[:16]

            caption_lines = [
                f"📷 <b>Photo de la demande #{req_num}</b>\n",
                f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)",
                f"📍 <b>Localisation :</b> {loc_esc}",
                f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
                f"📊 <b>Statut :</b> <code>{statut_esc}</code>",
                f"🙋 <b>Demandeur :</b> {user_display}"
            ]

            if demande.get("details"):
                det = str(demande["details"])
                det_court = (det[:100] + "...") if len(det) > 100 else det
                caption_lines.append(f"💬 <b>Détails :</b> <i>{html.escape(det_court)}</i>")

            caption_lines.append(f"\n📅 <i>Reçue le {date_str}</i>")
            caption = "\n".join(caption_lines)

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande['id']}"),
                    InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")
                ]
            ])

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
        """Redirige proprement vers la fiche native (avec photo si disponible, texte sinon)."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            return

        try:
            demande_id = int(query.data.split("_")[-1])
        except (IndexError, ValueError) as exc:
            logger.error("Erreur extraction demande_id depuis %s : %s", query.data, exc)
            return

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
                return

            if demande.get("photo_id"):
                await self.voir_photo_demande(update, context)
                return

            priorite_icon = "💎" if demande.get("prioritaire") else "📝"
            type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
            montant_val = float(demande.get("montant") or 0.0)
            montant_str = f" ({montant_val:.2f} €)" if demande.get("prioritaire") else ""

            prenom_esc = html.escape(str(demande.get("prenom") or ""))
            nom_esc = html.escape(str(demande.get("nom") or ""))
            nom_complet = f"{prenom_esc} {nom_esc}".strip()
            loc_esc = html.escape(str(demande.get("localisation") or "Non précisée"))
            
            statut_display = self.db_manager.format_statut_display(
                demande.get("statut", "📥 Reçue"),
                demande.get("is_difficile", False),
                demande.get("reussie_substatus")
            )
            statut_esc = html.escape(statut_display)
            req_num = html.escape(str(demande.get("request_number", demande["id"])))

            if demande.get("username"):
                user_display = f"@{html.escape(demande['username'])}"
            elif demande.get("user_first_name"):
                user_display = html.escape(demande["user_first_name"])
            else:
                user_display = f"User {demande['user_id']}"

            date_str = str(demande.get("date_creation", ""))[:16]

            lines = [
                f"💌 <b>Demande #{req_num}</b>\n",
                f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)",
                f"📍 <b>Localisation :</b> {loc_esc}",
                f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
                f"📊 <b>Statut :</b> <code>{statut_esc}</code>",
                f"🙋 <b>Demandeur :</b> {user_display}"
            ]

            reseaux = []
            if demande.get("instagram"):
                ig = html.escape(str(demande["instagram"]))
                reseaux.append(f"📷 <a href='https://instagram.com/{ig}'>@{ig}</a>")
            if demande.get("snapchat"):
                snap = html.escape(str(demande["snapchat"]))
                reseaux.append(f"👻 <a href='https://snapchat.com/add/{snap}'>{snap}</a>")
            if reseaux:
                lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

            if demande.get("details"):
                lines.append(f"💬 <b>Détails :</b> <i>{html.escape(str(demande['details']))}</i>")

            lines.append(f"\n📅 <i>Reçue le {date_str}</i>")

            keyboard = [
                [
                    InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande['id']}"),
                    InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande['id']}")
                ],
                [
                    InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")
                ]
            ]

            chat_id = query.message.chat_id if query.message else None
            try:
                await query.message.delete()
            except Exception:
                pass

            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="\n".join(lines),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    disable_web_page_preview=True
                )

        except Exception as exc:
            logger.error("Erreur retour vue : %s", exc, exc_info=True)