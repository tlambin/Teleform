"""Gestion de la consultation et du cycle de vie des demandes utilisateur."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class DemandeManager:
    """Gestionnaire d'affichage et de navigation dans les demandes."""

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager
        logger.info("DemandeManager initialisé")

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
        """Gère la pagination des demandes (nav_page_X)."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        parts = callback_data.split("_")

        if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
            target_page = int(parts[2])
            await self.show_demande_page(update, context, update.effective_user.id, page=target_page, edit_message=True)
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
        """Affiche une demande à la fois avec navigation dynamique (page précédente / suivante)."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, age, localisation,
                           photo_id, statut, prioritaire, montant, date_creation,
                           date_modification, instagram, snapchat, details
                    FROM demandes
                    WHERE user_id = %s
                    ORDER BY id DESC
                    """,
                    (user_id,),
                )
                demandes = cursor.fetchall()

            if not demandes:
                await self._send_no_requests_message(update, edit_message)
                return

            total_pages = len(demandes)
            page = max(0, min(page, total_pages - 1))
            demande = demandes[page]

            # Construction de la fiche
            message = self._format_demande_card(demande, page, total_pages)
            keyboard = self._build_navigation_keyboard(demande, page, total_pages)

            if edit_message and update.callback_query:
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            else:
                target = update.message or (update.callback_query.message if update.callback_query else None)
                if target:
                    await target.reply_text(
                        message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )

        except Exception as exc:
            logger.error("Erreur consultation demandes: %s", exc, exc_info=True)
            await self._send_error_message(update, edit_message)

    def _format_demande_card(self, demande: dict, current_page: int, total_pages: int) -> str:
        """Met en forme la fiche d'une demande."""
        type_badge = "💎 Prioritaire" if demande.get("prioritaire") else "📝 Standard"
        montant_str = f" - <b>{float(demande['montant']):.2f}€</b>" if demande.get("prioritaire") else ""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

        lignes = [
            f"📋 <b>Demande #{demande.get('request_number', demande['id'])}</b> ({current_page + 1}/{total_pages})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
            f"📍 <b>Localisation :</b> {demande['localisation']}",
            f"🎯 <b>Type :</b> {type_badge}{montant_str}",
            f"📊 <b>Statut :</b> <code>{demande.get('statut', 'En cours')}</code>"
        ]

        # Réseaux
        reseaux = []
        if demande.get("instagram"):
            reseaux.append(f"📷 <a href='https://instagram.com/{demande['instagram']}'>@{demande['instagram']}</a>")
        if demande.get("snapchat"):
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{demande['snapchat']}'>{demande['snapchat']}</a>")
        if reseaux:
            lignes.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        # Détails
        if demande.get("details"):
            det = demande["details"]
            det_short = (det[:150] + "...") if len(det) > 150 else det
            lignes.append(f"💬 <b>Remarque :</b> <i>{det_short}</i>")

        # Date de création
        date_str = str(demande.get("date_creation", ""))[:16]
        lignes.append(f"\n📅 <i>Créée le {date_str}</i>")

        return "\n".join(lignes)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Génère les boutons de pagination et d'actions (modifier/supprimer)."""
        buttons = []
        demande_id = demande["id"]
        statut = demande.get("statut", "")

        # Actions sur la demande si elle n'est pas encore traitée
        if statut in ["📨 Reçue", "En attente"]:
            buttons.append([
                InlineKeyboardButton("✏️ Modifier", callback_data=f"modify_{demande_id}"),
                InlineKeyboardButton("🗑️ Supprimer", callback_data=f"delete_{demande_id}")
            ])

        # Barre de pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"nav_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"nav_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        # Raccourcis globaux
        buttons.append([
            InlineKeyboardButton("➕ Nouvelle demande", callback_data="new_demande"),
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)

    async def _send_no_requests_message(self, update: Update, edit_message: bool):
        """Message affiché quand aucune demande n'est enregistrée."""
        text = (
            "📭 <b>Aucune demande active</b>\n\n"
            "Vous n'avez pas encore soumis de demande.\n"
            "Cliquez ci-dessous pour en créer une !"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Créer une demande", callback_data="new_demande")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])

        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            target = update.message or (update.callback_query.message if update.callback_query else None)
            if target:
                await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_error_message(self, update: Update, edit_message: bool):
        """Message en cas de problème de connexion base."""
        text = "❌ <b>Erreur technique</b> lors de la récupération de vos demandes."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        if edit_message and update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            target = update.message or (update.callback_query.message if update.callback_query else None)
            if target:
                await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)