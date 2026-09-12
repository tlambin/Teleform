"""Module de gestion et de mise à jour des statuts des demandes par les administrateurs."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from .notifs import NotifsManager

logger = logging.getLogger(__name__)


class StatutsManager:
    """Gestionnaire des transitions d'états des demandes et des options associées."""

    def __init__(self, db_manager, config, statuts_disponibles=None):
        self.db_manager = db_manager
        self.config = config
        self.notifs_manager = NotifsManager(db_manager, config)
        logger.info("StatutsManager initialisé")

    async def show_status_change_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche le panneau principal de paramétrage du statut avec interrupteurs et sous-options."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.config.is_admin(update.effective_user.id):
            await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT request_number, prenom, nom, statut, is_difficile, reussie_substatus, photo_id
                    FROM demandes WHERE id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            prenom_esc = html.escape(str(demande.get("prenom") or ""))
            nom_esc = html.escape(str(demande.get("nom") or ""))
            nom_complet = f"{prenom_esc} {nom_esc}".strip()
            current_status = demande.get("statut") or "📥 Reçue"
            is_diff = bool(demande.get("is_difficile", False))
            reussie_sub = demande.get("reussie_substatus")
            statut_display = self.db_manager.format_statut_display(current_status, is_diff, reussie_sub)
            req_num = html.escape(str(demande.get("request_number", demande_id)))
            is_photo_message = bool(query.message and query.message.photo)

            keyboard = []

            # 1. Statuts principaux de traitement
            btn_attente = "• ⏳ En attente •" if current_status == "⏳ En attente" else "⏳ En attente"
            btn_encours = "• 🔄 En cours •" if current_status == "🔄 En cours" else "🔄 En cours"
            keyboard.append([
                InlineKeyboardButton(btn_attente, callback_data=f"status_apply_{demande_id}_attente"),
                InlineKeyboardButton(btn_encours, callback_data=f"status_apply_{demande_id}_encours")
            ])

            # 2. Interrupteur Difficile (si En attente ou En cours)
            if current_status in ("⏳ En attente", "🔄 En cours"):
                toggle_icon = "🟢 ACTIVÉE" if is_diff else "⚪ DÉSACTIVÉE"
                keyboard.append([
                    InlineKeyboardButton(f"⚠️ Option Difficile : {toggle_icon}", callback_data=f"status_toggle_diff_{demande_id}")
                ])

            # 3. Statut Réussie et Abandon
            btn_reussie = f"• {statut_display} •" if current_status == "✅ Réussie" else "✅ Réussie..."
            keyboard.append([
                InlineKeyboardButton(btn_reussie, callback_data=f"status_sub_reussie_{demande_id}"),
                InlineKeyboardButton("❌ Abandonner", callback_data=f"status_prompt_abandon_{demande_id}")
            ])

            # 4. Bouton Annuler (retour propre aux suivis)
            keyboard.append([InlineKeyboardButton("🔙 Annuler", callback_data="demandes_suivies")])

            text = (
                f"📊 <b>Changer le Statut</b>\n\n"
                f"📝 <b>Demande #{req_num}</b> - {nom_complet}\n"
                f"Statut actuel : <b>{html.escape(statut_display)}</b>\n\n"
                "Choisissez le nouveau statut ou ajustez les options ci-dessous :"
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
            logger.error("Erreur affichage menu changement statut : %s", exc, exc_info=True)

    async def show_reussie_suboptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche le sous-panneau de sélection pour le statut ✅ Réussie."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        is_photo = bool(query.message and query.message.photo)
        text = (
            "✅ <b>Demande Réussie - Précision</b>\n\n"
            "Veuillez définir la nature de la réussite :\n\n"
            "• <b>🟢 Active :</b> La demande a abouti, mais le suivi reste ouvert pour obtenir des contenus supplémentaires.\n"
            "• <b>❎ Terminée :</b> La demande est pleinement finalisée, aucun contenu de plus ne sera recherché."
        )

        keyboard = [
            [InlineKeyboardButton("🟢 Active (D'autres contenus possibles)", callback_data=f"status_apply_reussie_{demande_id}_active")],
            [InlineKeyboardButton("❎ Terminée (Dossier clos)", callback_data=f"status_apply_reussie_{demande_id}_terminee")],
            [InlineKeyboardButton("🔙 Retour", callback_data=f"change_status_{demande_id}")]
        ]

        if is_photo:
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_status_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routeur central des actions liées aux statuts."""
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        admin_id = update.effective_user.id
        if not self.config.is_admin(admin_id):
            await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
            return

        data = query.data
        try:
            # 1. Demande d'abandon
            if data.startswith("status_prompt_abandon_"):
                demande_id = int(data.replace("status_prompt_abandon_", ""))
                await self._initiate_abandon_flow(query, context, demande_id, admin_id)
                return

            # 2. Sous-options Réussie
            if data.startswith("status_sub_reussie_"):
                demande_id = int(data.replace("status_sub_reussie_", ""))
                await self.show_reussie_suboptions(update, context, demande_id)
                return

            # 3. Application Réussie (Active ou Terminée)
            if data.startswith("status_apply_reussie_"):
                parts = data.split("_")
                demande_id = int(parts[3])
                sub_type = parts[4]  # active ou terminee
                await self._apply_status_change(query, context, demande_id, "✅ Réussie", reussie_substatus=sub_type)
                return

            # 4. Archivage immédiat validé par l'admin
            if data.startswith("status_archive_now_"):
                demande_id = int(data.replace("status_archive_now_", ""))
                await self._archive_demande_now(query, context, demande_id)
                return

            # 5. Interrupteur Difficile
            if data.startswith("status_toggle_diff_"):
                demande_id = int(data.replace("status_toggle_diff_", ""))
                new_diff_state = self.db_manager.toggle_demande_difficile(demande_id)
                state_label = "activée ⚠️" if new_diff_state else "désactivée 🟢"
                await query.answer(f"Option Difficile {state_label} !", show_alert=False)

                # Récupération et notification de la mise à jour de difficulté
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, request_number, user_id, prenom, statut, is_difficile, reussie_substatus FROM demandes WHERE id = %s",
                        (demande_id,)
                    )
                    demande = cursor.fetchone()

                if demande:
                    admin_alias = self.db_manager.get_admin_alias(admin_id)
                    current_status = demande["statut"]
                    await self.notifs_manager.send_status_update_notification(
                        context=context,
                        user_id=demande["user_id"],
                        demande_id=demande["id"],
                        request_number=demande.get("request_number"),
                        prenom_cible=demande.get("prenom"),
                        old_status=current_status,
                        new_status=current_status,
                        is_difficile=new_diff_state,
                        reussie_substatus=demande.get("reussie_substatus"),
                        admin_alias=admin_alias,
                    )

                await self.show_status_change_menu(update, context, demande_id)
                return

            # 6. Application En attente / En cours
            if data.startswith("status_apply_"):
                parts = data.split("_")
                demande_id = int(parts[2])
                target = parts[3]
                statut_map = {
                    "attente": "⏳ En attente",
                    "encours": "🔄 En cours"
                }
                target_statut = statut_map.get(target)
                if target_statut:
                    await self._apply_status_change(query, context, demande_id, target_statut)
                return

        except Exception as exc:
            logger.error("Erreur routage callback statut : %s", exc, exc_info=True)
            await query.answer("❌ Erreur technique.", show_alert=True)

    async def _apply_status_change(
        self,
        query,
        context: ContextTypes.DEFAULT_TYPE,
        demande_id: int,
        nouveau_statut: str,
        reussie_substatus: str = None
    ):
        """Met à jour le statut, actualise les suivis, alerte le demandeur et informe l'admin."""
        admin_id = query.from_user.id
        admin_alias = self.db_manager.get_admin_alias(admin_id)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT d.*, u.username, u.first_name AS user_first_name
                FROM demandes d
                LEFT JOIN users u ON d.user_id = u.user_id
                WHERE d.id = %s
                """,
                (demande_id,)
            )
            demande = cursor.fetchone()

        if not demande:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        old_status = demande["statut"]
        old_diff = bool(demande.get("is_difficile", False))
        old_sub = demande.get("reussie_substatus")
        old_label = self.db_manager.format_statut_display(old_status, old_diff, old_sub)

        # Enregistrement en base
        self.db_manager.update_demande_statut(demande_id, nouveau_statut, reussie_substatus=reussie_substatus)

        # Maintien ou clôture dans demandes_suivi
        with self.db_manager.transaction() as cursor:
            if nouveau_statut in ("⏳ En attente", "🔄 En cours", "✅ Réussie"):
                suivi_etat = "active" if (nouveau_statut != "✅ Réussie" or reussie_substatus == "active") else "closed"
                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), %s)
                    ON DUPLICATE KEY UPDATE 
                        admin_id = VALUES(admin_id),
                        derniere_action = NOW(),
                        statut_suivi = VALUES(statut_suivi)
                    """,
                    (demande_id, admin_id, suivi_etat)
                )

        # Notification explicative au demandeur
        new_diff = old_diff if nouveau_statut in ("⏳ En attente", "🔄 En cours") else False
        await self.notifs_manager.send_status_update_notification(
            context=context,
            user_id=demande["user_id"],
            demande_id=demande["id"],
            request_number=demande.get("request_number"),
            prenom_cible=demande.get("prenom"),
            old_status=old_label,
            new_status=nouveau_statut,
            is_difficile=new_diff,
            reussie_substatus=reussie_substatus,
            admin_alias=admin_alias,
        )

        # Rechargement des données fraîches pour l'affichage fiche
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT * FROM demandes WHERE id = %s", (demande_id,))
            demande_fresh = cursor.fetchone()

        await query.answer("✅ Statut mis à jour !")
        if query.message and query.message.photo:
            await self._update_photo_caption(query, demande_fresh)
        else:
            await self._update_existing_text_message(query, demande_fresh)

        # Alertes et rappels de livraison pour l'administrateur
        req_num = html.escape(str(demande.get("request_number", demande_id)))
        prenom_esc = html.escape(str(demande.get("prenom") or "la cible"))
        has_delivered = bool(demande_fresh.get("has_delivered_content", False))

        if nouveau_statut == "✅ Réussie" and reussie_substatus == "active":
            remind_text = (
                f"💡 <b>Rappel de livraison (Demande #{req_num})</b>\n\n"
                f"Le statut a été passé en <b>Réussie (🟢 Active)</b>.\n"
                f"Pensez à transmettre dès à présent à l'utilisateur le contenu déjà obtenu sur <b>{prenom_esc}</b> !"
            )
            remind_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Transmettre le contenu obtenu", callback_data=f"contacter_{demande_id}")]
            ])
            await context.bot.send_message(chat_id=admin_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)

        elif nouveau_statut == "✅ Réussie" and reussie_substatus == "terminee":
            if not has_delivered:
                remind_text = (
                    f"⚠️ <b>Action requise (Demande #{req_num})</b>\n\n"
                    f"La demande a été déclarée <b>Réussie (❎ Terminée)</b>.\n\n"
                    f"👉 Vous devez <b>obligatoirement envoyer le contenu obtenu</b> à l'utilisateur.\n"
                    "<i>Le bouton d'archivage sera débloqué dès votre premier envoi (et la demande s'auto-archivera sous 72h).</i>"
                )
                remind_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Transmettre le contenu maintenant", callback_data=f"contacter_{demande_id}")]
                ])
                await context.bot.send_message(chat_id=admin_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)
            else:
                remind_text = (
                    f"📦 <b>Dossier #{req_num} prêt pour l'archivage</b>\n\n"
                    "Le contenu a bien été livré. Vous pouvez archiver ce dossier immédiatement pour clore la fiche, "
                    "ou le laisser s'archiver automatiquement dans 72h."
                )
                remind_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📦 Archiver le dossier maintenant", callback_data=f"status_archive_now_{demande_id}")]
                ])
                await context.bot.send_message(chat_id=admin_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)

    async def _archive_demande_now(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Archive immédiatement une demande terminée ayant livré son contenu."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT * FROM demandes WHERE id = %s", (demande_id,))
            demande = cursor.fetchone()

        if not demande:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        if not demande.get("has_delivered_content"):
            await query.answer("⚠️ Impossible d'archiver : vous devez d'abord transmettre le contenu au client !", show_alert=True)
            return

        success = self.db_manager.archiver_demande_reussie(demande_id)
        if success:
            req_num = html.escape(str(demande.get("request_number", demande_id)))
            await query.answer(f"✅ Demande #{req_num} archivée avec succès !")
            back_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Retour à mes suivis", callback_data="demandes_suivies")
            ]])
            msg = (
                f"📦 <b>Demande #{req_num} archivée !</b>\n\n"
                "Le dossier est désormais clos et archivé. Le quota du demandeur a été libéré."
            )
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await context.bot.send_message(chat_id=query.from_user.id, text=msg, parse_mode="HTML", reply_markup=back_kb)
            else:
                await query.edit_message_text(text=msg, parse_mode="HTML", reply_markup=back_kb)
        else:
            await query.answer("❌ Erreur lors de l'archivage.", show_alert=True)

    async def _initiate_abandon_flow(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, admin_id: int):
        """Initialise la demande du motif d'abandon auprès de l'administrateur."""
        context.user_data["waiting_abandon_reason"] = {"demande_id": demande_id}

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT request_number FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        req_num = html.escape(str(row.get("request_number", demande_id))) if row else str(demande_id)
        prompt_text = (
            f"⚠️ <b>Abandon de la demande #{req_num}</b>\n\n"
            "Veuillez taper au clavier la <b>raison de l'abandon</b>.\n\n"
            "<i>Ce message sera transmis au demandeur pour qu'il comprenne la situation "
            "et choisisse soit de remettre la demande en disponible (pour un autre admin), "
            "soit de l'abandonner définitivement (ce qui libère son quota).</i>"
        )
        cancel_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="demandes_suivies")
        ]])

        if query.message and query.message.photo:
            await query.message.delete()
            await context.bot.send_message(chat_id=admin_id, text=prompt_text, parse_mode="HTML", reply_markup=cancel_kb)
        else:
            await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=cancel_kb)

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
        admin_alias_esc = html.escape(str(admin_alias))
        raison_esc = html.escape(raison)

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
                    nouvelle_raison_str = f"{prev_raison}\n• <b>{admin_alias_esc} :</b> « <i>{raison_esc}</i> »"
                else:
                    nouvel_alias_str = admin_alias
                    nouvelle_raison_str = f"• <b>{admin_alias_esc} :</b> « <i>{raison_esc}</i> »"

                cursor.execute(
                    """
                    UPDATE demandes 
                    SET statut = '❌ Abandonnée',
                        is_difficile = FALSE,
                        reussie_substatus = NULL,
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
            req_num = html.escape(str(demande.get("request_number", demande_id)))

            abandon_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Remettre en disponible", callback_data=f"reprendre_demande_{demande_id}")],
                [InlineKeyboardButton("🗑️ Laisser tomber (archiver)", callback_data=f"archiver_demande_{demande_id}")]
            ])

            msg_demandeur = (
                f"⚠️ <b>Information sur votre demande #{req_num}</b>\n\n"
                f"L'administrateur <b>{admin_alias_esc}</b> n'est plus en mesure de traiter votre demande.\n\n"
                f"📝 <b>Motif communiqué :</b>\n"
                f"« <i>{raison_esc}</i> »\n\n"
                "Que souhaitez-vous faire ?\n"
                "• <b>Remettre en disponible :</b> un autre administrateur pourra la prendre en charge.\n"
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
                logger.warning("Échec envoi motif abandon à %s : %s", user_id_demande, notif_exc)

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
            logger.error("Erreur traitement motif abandon demande %s : %s", demande_id, exc, exc_info=True)
            await update.message.reply_text("❌ Une erreur est survenue lors de l'enregistrement de l'abandon.")

    def _build_demande_keyboard(self, demande: dict) -> InlineKeyboardMarkup:
        """Construit le clavier d'actions avec insertion conditionnelle du bouton d'archivage."""
        demande_id = demande["id"]
        is_reussie = (demande.get("statut") == "✅ Réussie")
        sub_status = demande.get("reussie_substatus")
        has_delivered = bool(demande.get("has_delivered_content", False))

        keyboard = [
            [
                InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande_id}"),
                InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande_id}"),
            ],
            [
                InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande_id}")
            ]
        ]

        # Condition d'affichage pour la demande réussie et terminée
        if is_reussie and sub_status == "terminee":
            if has_delivered:
                keyboard.insert(1, [
                    InlineKeyboardButton("📦 Archiver le dossier", callback_data=f"status_archive_now_{demande_id}")
                ])
            else:
                keyboard.insert(1, [
                    InlineKeyboardButton("⚠️ Transmettre le contenu d'abord", callback_data=f"contacter_{demande_id}")
                ])

        keyboard.append([InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")])
        return InlineKeyboardMarkup(keyboard)

    async def _update_existing_text_message(self, query, demande: dict):
        """Actualise le corps du message texte après transition d'état."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_val = float(demande.get("montant") or 0.0)
        montant_str = f" ({montant_val:.2f}€)" if demande.get("prioritaire") else ""

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
            f"🙋 <b>Demandeur :</b> {user_display}",
        ]

        if demande.get("raison_abandon"):
            lines.append(
                f"\n⚠️ <b>HISTORIQUE - TENTATIVE(S) PRÉCÉDENTE(S) :</b>\n"
                f"{demande['raison_abandon']}"
            )

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
            det = str(demande["details"])
            det_court = (det[:150] + "...") if len(det) > 150 else det
            lines.append(f"💬 <b>Détails :</b> <i>{html.escape(det_court)}</i>")

        lines.append(f"\n📅 <i>Reçue le {date_str}</i>")

        await query.edit_message_text(
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=self._build_demande_keyboard(demande),
            disable_web_page_preview=True,
        )

    async def _update_photo_caption(self, query, demande: dict):
        """Actualise la légende de l'image après transition d'état."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_val = float(demande.get("montant") or 0.0)
        montant_str = f" ({montant_val:.2f}€)" if demande.get("prioritaire") else ""

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

        caption_lines = [
            f"📷 <b>Photo de la demande #{req_num}</b>\n",
            f"👤 {nom_complet} ({demande.get('age', '?')} ans) | {loc_esc}",
            f"🎯 {priorite_icon} {type_str}{montant_str}",
            f"📊 Statut : <code>{statut_esc}</code>"
        ]

        if demande.get("raison_abandon"):
            caption_lines.append(
                "⚠️ <b>Relancée après tentative(s) sans suite</b>"
            )

        caption = "\n".join(caption_lines)

        await query.edit_message_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=self._build_demande_keyboard(demande),
        )