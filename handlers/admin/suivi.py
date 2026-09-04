"""Module de gestion des demandes prises en charge par les administrateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class SuiviManager:
    """Gestionnaire des demandes suivies par l'administrateur connecté."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("SuiviManager initialisé")

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
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM demandes_suivi WHERE demande_id = %s AND admin_id = %s",
                    (demande_id, user_id),
                )
                if cursor.fetchone():
                    return

                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi)
                    VALUES (%s, %s, NOW())
                    """,
                    (demande_id, user_id),
                )

                # Mise à jour du statut et de l'administrateur référent
                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = '⏳ En attente', admin_en_charge = %s, date_modification = NOW()
                    WHERE id = %s AND statut = '📨 Reçue'
                    """,
                    (user_id, demande_id),
                )

            # Rafraîchit l'affichage en basculant directement sur les demandes suivies
            await self.show_demandes_suivies(update, context)

        except Exception as exc:
            logger.error("Erreur prise en charge demande %s: %s", demande_id, exc, exc_info=True)

    async def show_demandes_suivies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée pour afficher la première page des demandes suivies."""
        await self.show_demandes_suivies_page(update, context, page=0)

    async def show_demandes_suivies_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche les demandes suivies avec pagination dynamique sur un seul message éditable."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id

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
                    (user_id,),
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
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)
                return

            total = len(demandes)
            page = max(0, min(page, total - 1))
            demande = demandes[page]

            message = self._format_suivi_card(demande, page, total)
            keyboard = self._build_suivi_keyboard(demande, page, total)

            await query.edit_message_text(
                message,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

        except Exception as exc:
            logger.error("Erreur affichage demandes suivies: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Une erreur est survenue lors du chargement de vos suivis.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="start_menu")
                ]])
            )

    def _format_suivi_card(self, demande: dict, page: int, total: int) -> str:
        """Formate la fiche d'une demande suivie."""
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
            det_court = (det[:150] + "...") if len(det) > 150 else det
            lines.append(f"💬 <b>Détails :</b> <i>{det_court}</i>")

        if demande.get("notes_admin"):
            lines.append(f"📝 <b>Note privée :</b> <i>{demande['notes_admin']}</i>")

        lines.append(f"\n📅 <i>Créée le {date_crea_str} | Suivie le {date_suivi_str}</i>")
        return "\n".join(lines)

    def _build_suivi_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit le clavier d'actions (statut, photo, contact) et de pagination."""
        demande_id = demande["id"]
        buttons = []

        # Actions principales
        action_row = [
            InlineKeyboardButton("🔄 Changer Statut", callback_data=f"change_status_{demande_id}")
        ]
        if demande.get("photo_id"):
            action_row.append(InlineKeyboardButton("📷 Photo", callback_data=f"voir_photo_{demande_id}"))

        buttons.append(action_row)

        # Contact direct du demandeur
        buttons.append([
            InlineKeyboardButton("💬 Contacter le demandeur", callback_data=f"contacter_{demande_id}")
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