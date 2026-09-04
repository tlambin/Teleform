"""Gestion visualisation demandes selon architecture modulaire"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)

class DemandeManager:
    """Gestionnaire visualisation demandes - ÉTAPE 4.1"""

    def __init__(self, db_manager, config, account_manager):
        """Initialisation avec CompteManager injecté selon ÉTAPE 2"""
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager


        logger.info("DemandeManager initialisé - Migration ÉTAPE 4.1")

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affichage individuel des demandes selon nouveau format"""
        # ✅ GESTION DOUBLE ENTRÉE : message /demandes ET callback voir_demandes
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id

            # Affichage via callback - éditer le message initial
            await self.show_demandes_individually(update, context, user_id, via_callback=True)
        else:
            # Affichage via commande /demandes
            user_id = update.effective_user.id
            await self.account_manager.ensure_user_registered(update)

            # Affichage via message - envoyer nouveaux messages
            await self.show_demandes_individually(update, context, user_id, via_callback=False)

    async def show_demandes_individually(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, via_callback: bool = False):
        """Affiche chaque demande dans un message séparé"""
        try:
            with self.db_manager.get_cursor() as cursor:
                # Récupérer toutes les demandes
                cursor.execute("""
                    SELECT id, request_number, prenom, nom, age, localisation,
                           statut, prioritaire, montant, date_creation, date_modification, instagram, snapchat, details
                    FROM demandes
                    WHERE user_id = %s
                    ORDER BY date_creation DESC
                """, (user_id,))

                demandes = cursor.fetchall()

                if not demandes:
                    await self._send_no_requests_message(update, via_callback)
                    return

                # Message d'en-tête
                header_msg = f"📋 <b>Vos demandes ({len(demandes)})</b>\n\nVoici le détail de chaque demande :"

                if via_callback:
                    query = update.callback_query
                    await query.edit_message_text(header_msg, parse_mode='HTML')
                else:
                    await update.message.reply_text(header_msg, parse_mode='HTML')

                # Envoyer chaque demande individuellement
                for i, demande in enumerate(demandes):
                    await self._send_individual_demande(update, demande, via_callback and i == 0)

                # Message de fin avec navigation
                footer_msg = (
                    f"📝 <b>Total : {len(demandes)} demande(s)</b>\n\n"
                    "Utilisez les boutons de chaque demande pour les gérer."
                )

                footer_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Nouvelle demande", callback_data="new_demande")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])

                if via_callback and len(demandes) == 0:
                    # Si via callback et aucune demande, le message header devient le footer
                    query = update.callback_query
                    await query.edit_message_text(
                        footer_msg,
                        parse_mode='HTML',
                        reply_markup=footer_keyboard
                    )
                else:
                    # Envoyer message de fin
                    if update.callback_query:
                        # Mode callback - envoyer nouveau message pour le footer
                        await update.callback_query.message.reply_text(
                            footer_msg,
                            parse_mode='HTML',
                            reply_markup=footer_keyboard
                        )
                    else:
                        # Mode message direct
                        await update.message.reply_text(
                            footer_msg,
                            parse_mode='HTML',
                            reply_markup=footer_keyboard
                        )

        except Exception as e:
            logger.error(f"Erreur show_demandes_individually: {e}")
            await self._send_error_message(update, via_callback)

    async def _send_individual_demande(self, update: Update, demande: dict, edit_first_message: bool = False):
        """Envoie une demande individuelle avec le nouveau format structuré"""

        # TITRE selon le type de demande
        if demande['prioritaire']:
            # Format prioritaire avec montant
            titre = f"💎 <b>Demande n°{demande['request_number']} : {demande['montant']:.0f}€</b>"
        else:
            # Format standard sans montant
            titre = f"🔹 <b>Demande n°{demande['request_number']}</b>"

        # INFORMATIONS PRINCIPALES
        nom_complet = demande['prenom']
        if demande['nom']:
            nom_complet += f" {demande['nom']}"

        # Informations de base
        info_principales = [
            f"👤 {nom_complet} ({demande['age']} ans)",
            f"📍 {demande['localisation']}"
        ]

        # SECTION RÉSEAUX (si au moins un réseau disponible)
        section_reseaux = []
        if demande['instagram'] or demande['snapchat']:
            section_reseaux.append("\n<b>Réseaux :</b>")
            if demande['instagram']:
                instagram_url = f"https://instagram.com/{demande['instagram']}"
                section_reseaux.append(f"📷 <a href='{instagram_url}'>{demande['instagram']}</a>")
            if demande['snapchat']:
                snapchat_url = f"https://snapchat.com/add/{demande['snapchat']}"
                section_reseaux.append(f"👻 <a href='{snapchat_url}'>{demande['snapchat']}</a>")

        # SECTION COMMENTAIRE
        section_commentaire = []
        if demande['details']:
            details_display = demande['details']
            if len(details_display) > 150:
                details_display = details_display[:150] + "..."

            section_commentaire.extend([
                "\n<b>Commentaire :</b>",
                details_display
            ])

        # SECTION STATUT
        date_creation = convert_utc_to_paris(demande['date_creation'])

        section_statut = [f"\n<b>Statut :</b>"]
        section_statut.append(f"{demande['statut']}")

        # Date de modification si différente
        if demande['date_modification']:
            date_modification = convert_utc_to_paris(demande['date_modification'])
            if date_modification.date() != date_creation.date():
                section_statut.append(f"🔄 {date_modification.strftime('%d/%m/%Y à %H:%M')}")


        # DATE DE CRÉATION EN BAS
        date_creation_str = date_creation.strftime("%d/%m/%Y à %H:%M")
        section_date = [
            f"\n<b>Créée le :</b>",
            f"📅 {date_creation_str}"]

        # CONSTRUCTION DU MESSAGE FINAL
        message_parts = [titre, ""]  # Titre + ligne vide
        message_parts.extend(info_principales)  # Infos principales

        if section_reseaux:
            message_parts.extend(section_reseaux)  # Section réseaux

        if section_commentaire:
            message_parts.extend(section_commentaire)

        message_parts.extend(section_statut)  # Section statut
        message_parts.extend(section_date)    # Date de création

        message = "\n".join(message_parts)

        # Boutons conditionnels selon le statut
        keyboard = self._create_demande_action_buttons(demande)

        # Envoi du message
        if edit_first_message and update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            else:
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )


    def _create_demande_action_buttons(self, demande: dict) -> InlineKeyboardMarkup:
        """Crée les boutons d'action selon le statut de la demande"""
        demande_id = demande['id']
        statut = demande['statut']

        # ✅ Boutons selon statut
        if statut == "📨 Reçue":
            # Statut initial - Modification et suppression possibles
            keyboard = [
                [
                    InlineKeyboardButton("✏️ Modifier", callback_data=f"modify_{demande_id}"),
                    InlineKeyboardButton("🗑️ Supprimer", callback_data=f"delete_{demande_id}")
                ]
            ]
        else:
            # Autres statuts - Seulement annulation (fonctionnalité future)
            keyboard = [
                [InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_demande_{demande_id}")]
            ]

        return InlineKeyboardMarkup(keyboard)

    async def _send_no_requests_message(self, update: Update, via_callback: bool):
        """Message quand aucune demande"""
        message = (
            "📭 <b>Aucune demande</b>\n\n"
            "Vous n'avez pas encore créé de demande.\n"
            "Utilisez le bouton ci-dessous pour commencer !"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Créer une demande", callback_data="new_demande")],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])

        if via_callback:
            query = update.callback_query
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)

    async def _send_error_message(self, update: Update, via_callback: bool):
        """Message d'erreur"""
        message = "❌ Erreur lors de la récupération des demandes"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])

        if via_callback:
            query = update.callback_query
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=keyboard)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)
