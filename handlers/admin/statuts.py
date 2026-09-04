"""Module de gestion et de mise à jour des statuts des demandes par les administrateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris
from .alias import AliasManager

logger = logging.getLogger(__name__)


class StatutsManager:
    """Gestionnaire des transitions d'états des demandes et des notifications associées."""

    def __init__(self, db_manager, config, statuts_disponibles):
        self.db_manager = db_manager
        self.config = config
        self.statuts_disponibles = statuts_disponibles
        self.alias_manager = AliasManager(db_manager, config)
        logger.info("StatutsManager initialisé")

    async def show_status_change_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche la liste des statuts disponibles sous forme de boutons."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT request_number, prenom, nom, statut, photo_id
                    FROM demandes WHERE id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                return

            nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()
            is_photo_message = bool(query.message and query.message.photo)

            keyboard = []
            for idx, statut in enumerate(self.statuts_disponibles):
                label = f"• {statut} •" if statut == demande["statut"] else statut
                keyboard.append([
                    InlineKeyboardButton(label, callback_data=f"set_status_{demande_id}_{idx}")
                ])

            return_callback = f"voir_photo_{demande_id}" if is_photo_message else f"retour_texte_{demande_id}"
            keyboard.append([
                InlineKeyboardButton("🔙 Annuler", callback_data=return_callback)
            ])

            text = (
                f"📊 <b>Changer le Statut</b>\n\n"
                f"📝 <b>Demande #{demande.get('request_number', demande_id)}</b> - {nom_complet}\n"
                f"Statut actuel : <code>{demande['statut']}</code>\n\n"
                "Sélectionnez le nouveau statut ci-dessous :"
            )

            if is_photo_message:
                await query.edit_message_caption(
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )

        except Exception as exc:
            logger.error("Erreur affichage menu changement statut: %s", exc, exc_info=True)

    async def set_status_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Applique le nouveau statut en base de façon atomique et notifie le demandeur."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        admin_id = update.effective_user.id
        if not self.config.is_admin(admin_id):
            return

        try:
            parts = query.data.split("_")
            demande_id = int(parts[2])
            status_index = int(parts[3])

            if status_index >= len(self.statuts_disponibles):
                return

            nouveau_statut = self.statuts_disponibles[status_index]
            admin_alias = self.db_manager.get_admin_alias(admin_id)

            # Transaction atomique : vérification, mise à jour du statut et synchronisation du suivi
            with self.db_manager.transaction() as cursor:
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

                old_status = demande["statut"]
                user_id_demande = demande["user_id"]
                prenom = demande["prenom"]
                req_num = demande.get("request_number", demande_id)

                # 1. Mise à jour dans la table des demandes
                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = %s, admin_en_charge = %s, date_modification = NOW()
                    WHERE id = %s
                    """,
                    (nouveau_statut, admin_id, demande_id),
                )

                # 2. Inscription automatique dans les demandes suivies si le statut devient "En cours"
                if "En cours" in nouveau_statut:
                    cursor.execute(
                        """
                        INSERT INTO demandes_suivi (demande_id, admin_id, date_prise_en_charge)
                        VALUES (%s, %s, NOW())
                        ON DUPLICATE KEY UPDATE date_prise_en_charge = NOW()
                        """,
                        (demande_id, admin_id),
                    )

            # Notification au demandeur si le statut a changé
            if old_status != nouveau_statut:
                try:
                    await self.alias_manager.send_status_notification(
                        context,
                        user_id_demande,
                        req_num,
                        prenom,
                        old_status,
                        nouveau_statut,
                        admin_alias,
                    )
                except Exception as notif_err:
                    logger.warning("Échec notification demandeur: %s", notif_err)

            # Rafraîchissement de la vue admin
            demande["statut"] = nouveau_statut
            if query.message and query.message.photo:
                await self._update_photo_caption(query, demande, nouveau_statut)
            else:
                await self._update_existing_text_message(query, demande, nouveau_statut)

        except Exception as exc:
            logger.error("Erreur mise à jour statut demande: %s", exc, exc_info=True)

    async def _update_existing_text_message(self, query, demande: dict, nouveau_statut: str):
        """Actualise le corps du message texte après transition d'état."""
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
            f"📊 <b>Statut :</b> <code>{nouveau_statut}</code>",
            f"🙋 <b>Demandeur :</b> {user_display}",
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

        keyboard = [
            [
                InlineKeyboardButton("🔄 Changer Statut", callback_data=f"change_status_{demande['id']}"),
                InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}"),
            ],
            [InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")],
        ]
        if demande.get("photo_id"):
            keyboard[0].insert(0, InlineKeyboardButton("📷 Photo", callback_data=f"voir_photo_{demande['id']}"))

        await query.edit_message_text(
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def _update_photo_caption(self, query, demande: dict, nouveau_statut: str):
        """Actualise la légende de l'image après transition d'état."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

        caption = (
            f"📷 <b>Photo de la demande #{demande.get('request_number', demande['id'])}</b>\n\n"
            f"👤 {nom_complet} ({demande['age']} ans) | {demande['localisation']}\n"
            f"🎯 {priorite_icon} {type_str}{montant_str}\n"
            f"📊 Statut : <code>{nouveau_statut}</code>"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande['id']}"),
                InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}"),
            ],
            [InlineKeyboardButton("📄 Mode Texte", callback_data=f"retour_texte_{demande['id']}")],
        ])

        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )