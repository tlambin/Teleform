"""Module de gestion et de mise à jour des statuts des demandes par les administrateurs."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
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
        """Applique le nouveau statut ou intercepte l'abandon pour demander un motif."""
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

            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.*, d.user_id AS user_id, u.username, u.first_name AS user_first_name
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            # CAS PARTICULIER : ABANDON -> Demande de motif à l'administrateur
            if "abandon" in nouveau_statut.lower():
                context.user_data["waiting_abandon_reason"] = {
                    "demande_id": demande_id,
                    "status_index": status_index,
                }
                req_num = demande.get("request_number", demande_id)
                prompt_text = (
                    f"⚠️ <b>Abandon de la demande #{req_num}</b>\n\n"
                    "Veuillez taper au clavier la <b>raison de l'abandon</b>.\n\n"
                    "<i>Ce message sera transmis au demandeur pour qu'il comprenne la situation "
                    "et décide soit de la relancer (remise en dispo), soit de l'archiver (libérant son quota).</i>"
                )
                cancel_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data=f"retour_texte_{demande_id}")
                ]])

                if query.message and query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(chat_id=admin_id, text=prompt_text, parse_mode="HTML", reply_markup=cancel_kb)
                else:
                    await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=cancel_kb)
                return

            # TOUS LES AUTRES STATUTS : application directe
            admin_alias = self.db_manager.get_admin_alias(admin_id)
            old_status = demande["statut"]
            user_id_demande = demande["user_id"]
            prenom = demande["prenom"]
            req_num = demande.get("request_number", demande_id)

            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = %s, admin_en_charge = %s, date_modification = NOW()
                    WHERE id = %s
                    """,
                    (nouveau_statut, admin_id, demande_id),
                )

                if any(k in nouveau_statut for k in ("En cours", "En attente", "Difficile")):
                    cursor.execute(
                        """
                        INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                        VALUES (%s, %s, NOW(), NOW(), 'active')
                        ON DUPLICATE KEY UPDATE 
                            admin_id = VALUES(admin_id),
                            derniere_action = NOW(),
                            statut_suivi = 'active'
                        """,
                        (demande_id, admin_id),
                    )

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

            demande["statut"] = nouveau_statut
            if query.message and query.message.photo:
                await self._update_photo_caption(query, demande, nouveau_statut)
            else:
                await self._update_existing_text_message(query, demande, nouveau_statut)

        except Exception as exc:
            logger.error("Erreur mise à jour statut demande: %s", exc, exc_info=True)

    async def process_abandon_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre le motif d'abandon fourni au clavier, cumule l'historique et notifie le demandeur."""
        if not update.message or not update.message.text:
            return

        abandon_data = context.user_data.pop("waiting_abandon_reason", None)
        if not abandon_data:
            return

        demande_id = abandon_data["demande_id"]
        raison = update.message.text.strip()
        admin_id = update.effective_user.id
        admin_alias = self.db_manager.get_admin_alias(admin_id)

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT request_number, user_id, prenom, ancien_admin_alias, raison_abandon 
                    FROM demandes WHERE id = %s
                    """,
                    (demande_id,)
                )
                demande = cursor.fetchone()

                if not demande:
                    await update.message.reply_text("❌ Demande introuvable.")
                    return

                prev_alias = demande.get("ancien_admin_alias")
                prev_raison = demande.get("raison_abandon")

                if prev_alias and prev_raison:
                    nouvel_alias_str = f"{prev_alias}, {admin_alias}"
                    nouvelle_raison_str = f"{prev_raison}\n• <b>{admin_alias} :</b> « <i>{raison}</i> »"
                else:
                    nouvel_alias_str = admin_alias
                    nouvelle_raison_str = f"• <b>{admin_alias} :</b> « <i>{raison}</i> »"

                cursor.execute(
                    """
                    UPDATE demandes 
                    SET statut = '❌ Abandonnée',
                        admin_en_charge = %s,
                        ancien_admin_alias = %s,
                        raison_abandon = %s,
                        date_modification = NOW() 
                    WHERE id = %s
                    """,
                    (admin_id, nouvel_alias_str, nouvelle_raison_str, demande_id)
                )
                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (demande_id,))

            user_id_demande = demande["user_id"]
            req_num = demande.get("request_number", demande_id)

            abandon_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Remettre en disponible", callback_data=f"reprendre_demande_{demande_id}")
                ],
                [
                    InlineKeyboardButton("🗑️ Laisser tomber (archiver)", callback_data=f"archiver_demande_{demande_id}")
                ]
            ])

            msg_demandeur = (
                f"⚠️ <b>Information sur votre demande #{req_num}</b>\n\n"
                f"L'administrateur <b>{admin_alias}</b> n'est plus en mesure de traiter votre demande.\n\n"
                f"📝 <b>Motif communiqué :</b>\n"
                f"« <i>{raison}</i> »\n\n"
                "Que souhaitez-vous faire ?\n"
                "• <b>Remettre en disponible :</b> un autre administrateur pourra la reprendre dans les demandes disponibles (votre demande reste active).\n"
                "• <b>Laisser tomber :</b> la demande sera archivée et votre quota sera libéré immédiatement."
            )

            try:
                await context.bot.send_message(
                    chat_id=user_id_demande,
                    text=msg_demandeur,
                    parse_mode="HTML",
                    reply_markup=abandon_keyboard,
                )
            except Exception as notif_exc:
                logger.warning("Échec envoi motif abandon à %s: %s", user_id_demande, notif_exc)

            back_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Retour aux demandes suivies", callback_data="demandes_suivies")
            ]])
            await update.message.reply_text(
                f"✅ <b>Demande #{req_num} passée en statut ❌ Abandonnée.</b>\n\n"
                "Le demandeur a été notifié avec votre motif.",
                parse_mode="HTML",
                reply_markup=back_kb
            )

        except Exception as exc:
            logger.error("Erreur traitement motif abandon demande %s: %s", demande_id, exc, exc_info=True)
            await update.message.reply_text("❌ Une erreur est survenue lors de l'enregistrement de l'abandon.")

    async def _update_existing_text_message(self, query, demande: dict, nouveau_statut: str):
        """Actualise le corps du message texte après transition d'état avec historique cumulé."""
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

        if demande.get("raison_abandon"):
            lines.append(
                f"\n⚠️ <b>HISTORIQUE - TENTATIVE(S) PRÉCÉDENTE(S) :</b>\n"
                f"{demande['raison_abandon']}"
            )

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
            [
                InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande['id']}")
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

        caption_lines = [
            f"📷 <b>Photo de la demande #{demande.get('request_number', demande['id'])}</b>\n",
            f"👤 {nom_complet} ({demande['age']} ans) | {demande['localisation']}",
            f"🎯 {priorite_icon} {type_str}{montant_str}",
            f"📊 Statut : <code>{nouveau_statut}</code>"
        ]

        if demande.get("raison_abandon"):
            caption_lines.append(
                "⚠️ <b>Relancée après tentative(s) sans suite</b>"
            )

        caption = "\n".join(caption_lines)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande['id']}"),
                InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande['id']}"),
            ],
            [
                InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande['id']}")
            ],
            [InlineKeyboardButton("📄 Mode Texte", callback_data=f"retour_texte_{demande['id']}")],
        ])

        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )