"""Module de gestion et consultation des demandes suivies par les administrateurs avec affichage automatique des photos."""

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class SuiviManager:
    """Gestionnaire des demandes prises en charge avec rendu visuel direct."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("SuiviManager initialisé")

    async def show_demandes_suivies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée pour afficher la première page des demandes suivies."""
        await self.show_demandes_suivies_page(update, context, page=0)

    async def show_demandes_suivies_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche les demandes suivies avec photo directe et pagination fluide."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        admin_id = update.effective_user.id

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name,
                           ds.date_suivi, ds.notes_admin
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    JOIN users u ON d.user_id = u.user_id
                    WHERE ds.admin_id = %s
                    ORDER BY ds.date_suivi DESC
                    """,
                    (admin_id,),
                )
                demandes = cursor.fetchall()

            if not demandes:
                msg = (
                    "💌 <b>Mes Demandes Suivies</b>\n\n"
                    "❤️ Vous ne suivez aucune demande actuellement.\n"
                    "Consultez les demandes disponibles pour en prendre en charge."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])
                await self._render_clean_text(query, context, msg, keyboard)
                return

            total = len(demandes)
            page = max(0, min(page, total - 1))
            demande = demandes[page]

            text_card = self._format_suivi_card(demande, page, total)
            keyboard = self._build_suivi_keyboard(demande, page, total)
            photo_id = demande.get("photo_id")

            if photo_id:
                await self._render_photo(query, context, photo_id, text_card, keyboard)
            else:
                await self._render_clean_text(query, context, text_card, keyboard)

        except Exception as exc:
            logger.error("Erreur affichage demandes suivies: %s", exc, exc_info=True)
            await query.answer("❌ Erreur lors du chargement des suivis.", show_alert=True)

    async def suivre_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Assigne une demande disponible à l'administrateur connecté."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.config.is_admin(user_id):
            return

        try:
            demande_id = int(query.data.split("_")[-1])
        except (IndexError, ValueError) as exc:
            logger.error("Erreur extraction demande_id depuis %s: %s", query.data, exc)
            return

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    "SELECT id FROM demandes_suivi WHERE demande_id = %s AND admin_id = %s",
                    (demande_id, user_id),
                )
                if cursor.fetchone():
                    await query.answer("⚠️ Demande déjà suivie.")
                    return

                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), 'active')
                    """,
                    (demande_id, user_id),
                )

                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = '⏳ En attente', admin_en_charge = %s, date_modification = NOW()
                    WHERE id = %s AND statut = '📨 Reçue'
                    """,
                    (user_id, demande_id),
                )

            await query.answer("✅ Demande prise en charge !")
            await self.show_demandes_suivies(update, context)

        except Exception as exc:
            logger.error("Erreur prise en charge demande %s: %s", demande_id, exc, exc_info=True)
            await query.answer("❌ Erreur lors de la prise en charge.", show_alert=True)

    async def _render_photo(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, keyboard: InlineKeyboardMarkup):
        """Met à jour l'affichage en mode photo via context.bot."""
        is_current_photo = bool(query.message and query.message.photo)
        chat_id = query.message.chat_id

        try:
            if is_current_photo:
                new_media = InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML")
                await query.edit_message_media(media=new_media, reply_markup=keyboard)
            else:
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        except Exception as err:
            logger.warning("Recréation du message photo suivi suite à: %s", err)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    async def _render_clean_text(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
        """Gère l'affichage en mode texte (si aucune photo n'est associée)."""
        is_current_photo = bool(query.message and query.message.photo)

        if is_current_photo:
            chat_id = query.message.chat_id
            await query.message.delete()
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

    def _format_suivi_card(self, demande: dict, page: int, total: int) -> str:
        """Formate la fiche d'une demande suivie (adaptée aux limites de légende photo)."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

        demandeur = f"@{demande['username']}" if demande.get("username") else (demande.get("user_first_name") or f"User {demande['user_id']}")
        date_crea_str = str(demande.get("date_creation", ""))[:16]
        date_suivi_str = str(demande.get("date_suivi", ""))[:16]

        lines = [
            f"💌 <b>Demande suivie #{demande.get('request_number', demande['id'])}</b> ({page + 1}/{total})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
            f"📍 <b>Localisation :</b> {demande['localisation']}",
            f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
            f"📊 <b>Statut :</b> <code>{demande.get('statut')}</code>",
            f"🙋 <b>Demandeur :</b> {demandeur}"
        ]

        reseaux = []
        if demande.get("instagram"):
            reseaux.append(f"📷 <a href='https://instagram.com/{demande['instagram']}'>@{demande['instagram']}</a>")
        if demande.get("snapchat"):
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{demande['snapchat']}'>{demande['snapchat']}</a>")
        if reseaux:
            lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if demande.get("details"):
            det = demande["details"]
            det_court = (det[:140] + "...") if len(det) > 140 else det
            lines.append(f"💬 <b>Détails :</b> <i>{det_court}</i>")

        if demande.get("notes_admin"):
            lines.append(f"📝 <b>Note privée :</b> <i>{demande['notes_admin']}</i>")

        lines.append(f"\n📅 <i>Créée le {date_crea_str} | Suivie le {date_suivi_str}</i>")
        return "\n".join(lines)

    def _build_suivi_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit le clavier d'actions (statut, contact) et de pagination."""
        demande_id = demande["id"]
        buttons = []

        # Actions principales
        buttons.append([
            InlineKeyboardButton("🔄 Changer Statut", callback_data=f"change_status_{demande_id}"),
            InlineKeyboardButton("💬 Contacter le demandeur", callback_data=f"contacter_{demande_id}"),
        ])

        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"suivi_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"suivi_next_{page}"))

        if nav_row:
            buttons.append(nav_row)

        # Raccourcis globaux
        buttons.append([
            InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_suivies"),
            InlineKeyboardButton("📮 Disponibles", callback_data="demandes_disponibles")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)