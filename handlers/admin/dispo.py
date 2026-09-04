"""Module de gestion et consultation des demandes disponibles pour les administrateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class DispoManager:
    """Gestionnaire des demandes non assignées en attente de prise en charge."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("DispoManager initialisé")

    async def show_demandes_disponibles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée pour afficher la première page des demandes disponibles."""
        await self.show_demandes_disponibles_page(update, context, page=0)

    async def show_demandes_disponibles_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche les demandes disponibles avec pagination dynamique sur un seul message éditable."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    JOIN users u ON d.user_id = u.user_id
                    LEFT JOIN demandes_suivi ds ON d.id = ds.demande_id AND ds.admin_id = %s
                    WHERE ds.demande_id IS NULL
                    AND d.statut IN ('📨 Reçue', '⏳ En attente')
                    ORDER BY d.prioritaire DESC, d.date_creation DESC
                    """,
                    (user_id,),
                )
                demandes = cursor.fetchall()

            if not demandes:
                msg = (
                    "📮 <b>Demandes Disponibles</b>\n\n"
                    "🔍 Aucune nouvelle demande disponible pour le moment."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_disponibles")],
                    [InlineKeyboardButton("💌 Demandes Suivies", callback_data="demandes_suivies")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)
                return

            total = len(demandes)
            page = max(0, min(page, total - 1))
            demande = demandes[page]

            # Mise en forme
            message = self._format_demande_card(demande, page, total)
            keyboard = self._build_navigation_keyboard(demande, page, total)

            await query.edit_message_text(
                message,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

        except Exception as exc:
            logger.error("Erreur consultation demandes disponibles: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Une erreur est survenue lors du chargement des demandes disponibles.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="start_menu")
                ]])
            )

    def _format_demande_card(self, demande: dict, page: int, total: int) -> str:
        """Formate la fiche d'une demande disponible."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

        demandeur = f"@{demande['username']}" if demande.get("username") else (demande.get("user_first_name") or f"User {demande['user_id']}")
        date_str = str(demande.get("date_creation", ""))[:16]

        lines = [
            f"📮 <b>Demande disponible #{demande.get('request_number', demande['id'])}</b> ({page + 1}/{total})\n",
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

        lines.append(f"\n📅 <i>Reçue le {date_str}</i>")
        return "\n".join(lines)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit le clavier d'actions (prise en charge, photo) et de pagination."""
        demande_id = demande["id"]
        buttons = []

        # Actions directes sur la demande
        action_row = [
            InlineKeyboardButton("❤️ Prendre en charge", callback_data=f"suivre_demande_{demande_id}")
        ]
        if demande.get("photo_id"):
            action_row.append(InlineKeyboardButton("📷 Photo", callback_data=f"voir_photo_{demande_id}"))

        buttons.append(action_row)

        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"dispo_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"dispo_next_{page}"))

        if nav_row:
            buttons.append(nav_row)

        # Raccourcis globaux
        buttons.append([
            InlineKeyboardButton("🔄 Actualiser", callback_data="demandes_disponibles"),
            InlineKeyboardButton("💌 Mes Suivis", callback_data="demandes_suivies")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)