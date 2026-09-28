"""Module de gestion et de mise à jour des statuts des demandes par les opérateurs (Staff)."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from .notifs import NotifsManager
from ui.staff import demandes as ui

logger = logging.getLogger(__name__)


class StatutsManager:
    """Gestionnaire des transitions d'états des demandes et des options associées."""

    def __init__(self, db_manager, config, statuts_disponibles=None):
        self.db_manager = db_manager
        self.config = config
        self.notifs_manager = NotifsManager(db_manager, config)
        logger.info("StatutsManager initialisé avec support Staff/Admin, Surveillance et Dénouement Période d'essai")

    async def show_status_change_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche le panneau principal de paramétrage du statut avec logique stricte de progression."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        if not self.db_manager.is_staff(update.effective_user.id):
            await query.answer("❌ Action réservée aux membres de l'équipe (Staff).", show_alert=True)
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, statut, is_difficile, reussie_substatus, photo_id
                    FROM demandes WHERE id = %s
                    """,
                    (demande_id,),
                )
                demande = cursor.fetchone()

            if not demande:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            current_status = demande.get("statut") or "📥 Reçue"
            is_diff = bool(demande.get("is_difficile", False))
            reussie_sub = demande.get("reussie_substatus")
            statut_display = self.db_manager.format_statut_display(current_status, is_diff, reussie_sub)
            statut_display_esc = html.escape(str(statut_display))
            is_photo_message = bool(query.message and query.message.photo)

            keyboard = ui.build_status_change_keyboard(demande_id, current_status, is_diff)
            text = (
                "📌 <b>CHANGER LE STATUT</b> 📌\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• {statut_display_esc} •\n\n"
                "<i>Sélectionnez le nouveau statut :</i>"
            )

            if is_photo_message:
                await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur affichage menu changement statut : %s", exc, exc_info=True)

    async def show_reussie_suboptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche le sous-panneau de sélection pour le statut ✅ Réussie."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        is_photo = bool(query.message and query.message.photo)
        text = (
            "✅ <b>DEMANDE RÉUSSIE</b> ✅\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "• <b>Active :</b> La demande reste active, de nouveaux éléments peuvent être obtenus.\n"
            "• <b>Terminée :</b> La demande est réussie et définitivement clôturée.\n\n"
            "<i>Sélectionnez le statut actuel :</i>"
        )
        keyboard = ui.build_reussie_suboptions_keyboard(demande_id)

        if is_photo:
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)

    async def handle_status_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routeur central des actions liées aux statuts."""
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        staff_id = update.effective_user.id
        if not self.db_manager.is_staff(staff_id):
            await query.answer("❌ Action réservée aux membres de l'équipe (Staff).", show_alert=True)
            return

        data = query.data
        try:
            if data.startswith("status_prompt_abandon_"):
                demande_id = int(data.replace("status_prompt_abandon_", ""))
                await self._initiate_abandon_flow(query, context, demande_id, staff_id)
                return

            if data.startswith("status_sub_reussie_"):
                demande_id = int(data.replace("status_sub_reussie_", ""))
                await self.show_reussie_suboptions(update, context, demande_id)
                return

            if data.startswith("status_apply_reussie_"):
                parts = data.split("_")
                demande_id = int(parts[3])
                sub_type = parts[4]
                await self._apply_status_change(query, context, demande_id, "✅ Réussie", reussie_substatus=sub_type)
                return

            if data.startswith("status_archive_now_"):
                demande_id = int(data.replace("status_archive_now_", ""))
                await self._archive_demande_now(query, context, demande_id)
                return

            if data.startswith("status_toggle_diff_"):
                demande_id = int(data.replace("status_toggle_diff_", ""))
                new_diff_state = self.db_manager.toggle_demande_difficile(demande_id)
                state_label = "OUI ⚠️" if new_diff_state else "NON"
                await query.answer(f"Difficulté définie sur : {state_label}", show_alert=False)

                with self.db_manager.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, request_number, user_id, prenom, statut, is_difficile, reussie_substatus FROM demandes WHERE id = %s",
                        (demande_id,)
                    )
                    demande = cursor.fetchone()

                if demande:
                    staff_alias = self.db_manager.get_staff_alias(staff_id)
                    current_status = demande["statut"]
                    await self.notifs_manager.send_status_update_notification(
                        context=context,
                        user_id=demande["user_id"],
                        demande_id=demande["id"],
                        request_number=demande["id"],
                        prenom_cible=demande.get("prenom"),
                        old_status=current_status,
                        new_status=current_status,
                        is_difficile=new_diff_state,
                        reussie_substatus=demande.get("reussie_substatus"),
                        admin_alias=staff_alias,
                    )

                await self.show_status_change_menu(update, context, demande_id)
                return

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
        """Met à jour le statut, actualise les suivis, alerte le demandeur et informe les superviseurs."""
        staff_id = query.from_user.id
        staff_alias = self.db_manager.get_staff_alias(staff_id)

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

        # Garde-fous serveur anti-régression
        if old_status == "✅ Réussie" and nouveau_statut in ("⏳ En attente", "🔄 En cours"):
            await query.answer("🚫 Un dossier réussi ne peut plus repasser en attente ou en cours.", show_alert=True)
            return

        if old_status == "🔄 En cours" and nouveau_statut == "⏳ En attente":
            await query.answer("🚫 Un dossier en cours ne peut pas redevenir en attente.", show_alert=True)
            return

        real_id = html.escape(str(demande.get("request_number") or demande["id"]))
        old_diff = bool(demande.get("is_difficile", False))
        old_sub = demande.get("reussie_substatus")
        old_label = self.db_manager.format_statut_display(old_status, old_diff, old_sub)

        self.db_manager.update_demande_statut(demande_id, nouveau_statut, reussie_substatus=reussie_substatus)

        with self.db_manager.transaction() as cursor:
            if nouveau_statut in ("⏳ En attente", "🔄 En cours", "✅ Réussie"):
                cursor.execute(
                    """
                    UPDATE demandes_suivi
                    SET admin_id = %s, derniere_action = NOW(), statut_suivi = 'active'
                    WHERE demande_id = %s
                    """,
                    (staff_id, demande_id)
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                        VALUES (%s, %s, NOW(), NOW(), 'active')
                        """,
                        (demande_id, staff_id)
                    )

        # Dénouement période d'essai (Succès)
        if nouveau_statut == "✅ Réussie" and self.db_manager.is_staff_trial(staff_id):
            self.db_manager.set_staff_trial(staff_id, False)
            logger.info("🎉 Période d'essai validée avec succès pour l'opérateur %s", staff_id)
            try:
                congrats_msg = (
                    "🎉 <b>FÉLICITATIONS ! PÉRIODE D'ESSAI VALIDÉE !</b>\n\n"
                    f"Votre prise en charge de la demande <b>#{real_id}</b> est un succès.\n"
                    "Votre statut probatoire est désormais levé : vous avez un <b>accès complet</b> à l'ensemble des demandes disponibles !"
                )
                await context.bot.send_message(chat_id=staff_id, text=congrats_msg, parse_mode="HTML")
            except Exception as notif_trial_err:
                logger.warning("Impossible d'envoyer les félicitations de fin d'essai à %s : %s", staff_id, notif_trial_err)

        new_diff = old_diff if nouveau_statut in ("⏳ En attente", "🔄 En cours") else False
        await self.notifs_manager.send_status_update_notification(
            context=context,
            user_id=demande["user_id"],
            demande_id=demande["id"],
            request_number=demande.get("request_number") or demande["id"],
            prenom_cible=demande.get("prenom"),
            old_status=old_label,
            new_status=nouveau_statut,
            is_difficile=new_diff,
            reussie_substatus=reussie_substatus,
            admin_alias=staff_alias,
        )

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT * FROM demandes WHERE id = %s", (demande_id,))
            demande_fresh = cursor.fetchone()

        # Alerte surveillance staff (Admins)
        try:
            action_tag = "reussite" if nouveau_statut == "✅ Réussie" else "changement_statut"
            monitors = self.db_manager.get_monitoring_admins(action=action_tag)

            target_prenom = html.escape(str(demande.get("prenom") or "la cible"))
            staff_alias_esc = html.escape(str(staff_alias))
            nouveau_statut_display = html.escape(str(self.db_manager.format_statut_display(nouveau_statut, new_diff, reussie_substatus)))

            alert_text = (
                f"👀 <b>SURVEILLANCE STAFF — CHANGEMENT DE STATUT</b>\n\n"
                f"• <b>Opérateur :</b> {staff_alias_esc} (<code>{staff_id}</code>)\n"
                f"• <b>Dossier :</b> #{real_id} ({target_prenom})\n"
                f"• <b>Nouveau statut :</b> <code>{nouveau_statut_display}</code>"
            )

            if bool(demande_fresh.get("prioritaire")):
                montant_mon = float(demande_fresh.get("montant") or 0.0)
                alert_text += f"\n• <b>Montant :</b> <code>{montant_mon:.2f} €</code>"

            kb_mon = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Voir le dossier", callback_data=f"retour_texte_{demande_id}")]
            ])

            for mon_id in monitors:
                if int(mon_id) != int(staff_id):
                    try:
                        await context.bot.send_message(
                            chat_id=mon_id,
                            text=alert_text,
                            parse_mode="HTML",
                            reply_markup=kb_mon
                        )
                    except Exception:
                        pass
        except Exception as mon_err:
            logger.warning("Erreur notification surveillance staff changement statut : %s", mon_err)

        await query.answer("✅ Statut mis à jour !")
        card_text = ui.format_demande_suivi_text(demande_fresh, self.db_manager)
        card_kb = ui.build_demande_card_keyboard(demande_fresh)

        if query.message and query.message.photo:
            await query.edit_message_caption(caption=card_text, parse_mode="HTML", reply_markup=card_kb)
        else:
            await query.edit_message_text(text=card_text, parse_mode="HTML", reply_markup=card_kb, disable_web_page_preview=True)

        req_num = html.escape(str(demande_fresh.get("request_number") or demande_fresh.get("id")))
        prenom_esc = html.escape(str(demande_fresh.get("prenom") or "la cible"))
        has_delivered = bool(demande_fresh.get("has_delivered_content", False))
        is_prio = bool(demande_fresh.get("prioritaire", False))
        montant = float(demande_fresh.get("montant") or 0.0)
        p_statut = demande_fresh.get("paiement_statut", "non_requis")

        if nouveau_statut == "✅ Réussie" and reussie_substatus == "active":
            remind_text, remind_kb = ui.build_reussie_active_notice(req_num, prenom_esc, demande_id)
            await context.bot.send_message(chat_id=staff_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)

        elif nouveau_statut == "✅ Réussie" and reussie_substatus == "terminee":
            if is_prio and montant > 0 and p_statut == "en_attente":
                prio_wait_text, prio_wait_kb = ui.build_prio_wait_payment_notice(req_num, montant, demande_id)
                await context.bot.send_message(chat_id=staff_id, text=prio_wait_text, parse_mode="HTML", reply_markup=prio_wait_kb)
            elif not has_delivered:
                remind_text, remind_kb = ui.build_delivery_required_notice(req_num, demande_id)
                await context.bot.send_message(chat_id=staff_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)
            else:
                remind_text, remind_kb = ui.build_ready_to_archive_notice(req_num, demande_id)
                await context.bot.send_message(chat_id=staff_id, text=remind_text, parse_mode="HTML", reply_markup=remind_kb)

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
            real_id = html.escape(str(demande.get("request_number") or demande["id"]))
            await query.answer(f"✅ Demande #{real_id} archivée avec succès !")
            back_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")
            ]])
            msg = (
                f"📦 <b>Demande #{real_id} archivée !</b>\n\n"
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
        """Initialise la demande du motif d'abandon auprès de l'opérateur."""
        context.user_data["waiting_abandon_reason"] = {"demande_id": demande_id}

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, request_number FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        real_id = html.escape(str(row.get("request_number") or row["id"])) if row else str(demande_id)
        prompt_text = (
            f"⚠️ <b>Abandon de la demande #{real_id}</b>\n\n"
            "Veuillez taper au clavier la <b>raison de l'abandon</b>.\n\n"
            "<i>Ce message sera transmis au demandeur pour qu'il comprenne la situation "
            "et choisisse soit de remettre la demande en disponible (pour un autre membre), "
            "soit de l'abandonner définitivement (ce qui libère son quota).</i>"
        )
        cancel_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data=f"change_status_{demande_id}")
        ]])

        if query.message and query.message.photo:
            await query.message.delete()
            await context.bot.send_message(chat_id=admin_id, text=prompt_text, parse_mode="HTML", reply_markup=cancel_kb)
        else:
            await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=cancel_kb)

    async def process_abandon_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre le motif d'abandon, gère le maintien de l'essai et notifie le demandeur et les administrateurs."""
        if not update.message or not update.message.text:
            return

        abandon_data = context.user_data.pop("waiting_abandon_reason", None)
        if not abandon_data:
            return

        demande_id = abandon_data["demande_id"]
        raison = update.message.text.strip()
        staff_id = update.effective_user.id
        staff_alias = self.db_manager.get_staff_alias(staff_id)
        staff_alias_esc = html.escape(str(staff_alias))
        raison_esc = html.escape(raison)

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, user_id, prenom, ancien_admin_alias, raison_abandon
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
                    nouvel_alias_str = f"{prev_alias}, {staff_alias}"
                    nouvelle_raison_str = f"{prev_raison}\n• {staff_alias_esc} : « {raison_esc} »"
                else:
                    nouvel_alias_str = staff_alias
                    nouvelle_raison_str = f"• {staff_alias_esc} : « {raison_esc} »"

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
                    (staff_id, nouvel_alias_str, nouvelle_raison_str, demande_id)
                )
                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (demande_id,))

            user_id_demande = demande["user_id"]
            real_id = html.escape(str(demande.get("request_number") or demande["id"]))

            abandon_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Remettre en disponible", callback_data=f"reprendre_demande_{demande_id}")],
                [InlineKeyboardButton("🗑️ Laisser tomber (archiver)", callback_data=f"archiver_demande_{demande_id}")]
            ])

            msg_demandeur = (
                f"⚠️ <b>Information sur votre demande #{real_id}</b>\n\n"
                f"L'opérateur <b>{staff_alias_esc}</b> n'est plus en mesure de traiter votre demande.\n\n"
                f"📝 <b>Motif communiqué :</b>\n"
                f"« <i>{raison_esc}</i> »\n\n"
                "Que souhaitez-vous faire ?\n"
                "• <b>Remettre en disponible :</b> un autre membre pourra la prendre en charge.\n"
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

            try:
                monitors = self.db_manager.get_monitoring_admins(action="abandon")
                alert_abandon = (
                    f"⚠️ <b>SURVEILLANCE STAFF — ABANDON DE DOSSIER</b>\n\n"
                    f"• <b>Opérateur :</b> {staff_alias_esc} (<code>{staff_id}</code>)\n"
                    f"• <b>Dossier :</b> #{real_id}\n"
                    f"• <b>Motif invoqué :</b> « <i>{raison_esc}</i> »"
                )
                for mon_id in monitors:
                    if int(mon_id) != int(staff_id):
                        try:
                            await context.bot.send_message(chat_id=mon_id, text=alert_abandon, parse_mode="HTML")
                        except Exception:
                            pass
            except Exception as mon_err:
                logger.warning("Erreur surveillance abandon staff : %s", mon_err)

            is_trial = self.db_manager.is_staff_trial(staff_id)
            trial_feedback = ""
            if is_trial:
                trial_feedback = (
                    "\n\n🧪 <b>Information Période d'essai :</b>\n"
                    "Ce dossier test ayant été abandonné, votre période d'essai reste active.\n"
                    "Vous devez retourner dans les demandes disponibles pour qu'un nouveau dossier test vous soit assigné."
                )

            back_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("💌 Demandes suivies", callback_data="demandes_suivies"),
                InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")
            ]])
            await update.message.reply_text(
                f"✅ <b>Demande #{real_id} passée en statut ❌ Abandonnée.</b>\n\n"
                f"Le demandeur a été notifié avec votre motif.{trial_feedback}",
                parse_mode="HTML",
                reply_markup=back_kb
            )

        except Exception as exc:
            logger.error("Erreur traitement motif abandon demande %s : %s", demande_id, exc, exc_info=True)
            await update.message.reply_text("❌ Une erreur est survenue lors de l'enregistrement de l'abandon.")