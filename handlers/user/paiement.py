"""Module de gestion des flux de paiement (Telegram Stars & Direct) et conversions tarifaires."""

import html
import logging
from telegram import LabeledPrice, Update
from telegram.error import Forbidden
from telegram.ext import ContextTypes
from . import paiement_ui as ui

logger = logging.getLogger(__name__)


class PaiementManager:
    """Gère la facturation Stars, l'encaissement, le paiement direct et les négociations/conversions de montant."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config

    # ==================== TELEGRAM STARS (ÉMISSION FACTURES) ====================

    async def buy_vip_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Émet la facture Stars pour l'abonnement VIP 30 jours."""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()

        inv = ui.get_vip_invoice_details(user_id)
        prices = [LabeledPrice(label=inv["title"], amount=inv["stars_price"])]

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=inv["title"],
            description=inv["description"],
            payload=inv["payload"],
            currency="XTR",
            prices=prices,
            provider_token="",
        )

    async def pay_stars_prio(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Émet la facture Stars pour le règlement d'une prestation prioritaire."""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, request_number, prenom, montant, paiement_statut, admin_en_charge FROM demandes WHERE id = %s AND user_id = %s",
                (demande_id, user_id),
            )
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        admin_id = dem.get("admin_en_charge")
        if admin_id:
            p_methods = self.db_manager.get_staff_payment_methods(admin_id)
            if not p_methods.get("accept_stars", True):
                await query.answer("⚠️ Votre piégeur n'accepte pas le règlement en Stars. Utilisez le paiement direct.", show_alert=True)
                return

        if dem.get("paiement_statut") == "paye":
            await query.answer("✅ Cette demande a déjà été réglée.", show_alert=True)
            return

        montant = float(dem.get("montant") or 0.0)
        if montant <= 0:
            await query.answer("❌ Aucun montant n'est associé à cette demande.", show_alert=True)
            return

        req_num = dem.get("request_number", demande_id)
        prenom = dem.get("prenom", "la cible")
        inv = ui.get_prio_invoice_details(demande_id, req_num, prenom, montant, user_id)

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=inv["title"],
            description=inv["description"],
            payload=inv["payload"],
            currency="XTR",
            prices=[LabeledPrice(label=inv["label"], amount=inv["stars_amount"])],
            provider_token="",
        )

    async def send_paid_reminder_invoice(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Émet la facture Stars pour le rappel hebdomadaire payant (1 € = 50 Stars)."""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()

        inv = ui.get_paid_reminder_invoice_details(demande_id, user_id)

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=inv["title"],
            description=inv["description"],
            payload=inv["payload"],
            currency="XTR",
            prices=[LabeledPrice(label=inv["label"], amount=inv["stars_amount"])],
            provider_token="",
        )

    # ==================== TELEGRAM STARS (VALIDATION & ENCAISSEMENT) ====================

    async def precheckout_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide les commandes Stars avant débit du compte utilisateur."""
        query = update.pre_checkout_query
        payload = query.invoice_payload

        if payload.startswith(("vip_sub_", "remind_pay_", "prio_pay_")):
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="Erreur de validation de la transaction.")

    async def successful_payment_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active les prestations une fois le paiement Stars confirmé par Telegram."""
        payment = update.message.successful_payment
        payload = payment.invoice_payload
        user_id = update.effective_user.id
        user_handlers = context.application.bot_data.get("user_handlers")

        # 1. Abonnement VIP 30 jours
        if payload.startswith(f"vip_sub_{user_id}_"):
            self.db_manager.set_user_vip(user_id, is_vip=True, duration_days=30)
            merci_msg, kb = ui.get_vip_success_content()
            await update.message.reply_text(merci_msg, parse_mode="HTML", reply_markup=kb)
            logger.info("Abonnement VIP 30 jours activé via Stars pour l'utilisateur %s", user_id)

        # 2. Relance hebdomadaire payante
        elif payload.startswith("remind_pay_"):
            parts = payload.split("_")
            demande_id = int(parts[2])

            if user_handlers:
                await user_handlers._dispatch_admin_reminder(update, context, demande_id, is_paid_boost=True)
                logger.info("Rappel payant validé pour la demande #%s par l'utilisateur %s", demande_id, user_id)
            else:
                logger.error("UserHandlers non trouvé dans bot_data.")

        # 3. Règlement de la prestation prioritaire
        elif payload.startswith("prio_pay_"):
            parts = payload.split("_")
            demande_id = int(parts[2])

            self.db_manager.set_demande_paiement_statut(demande_id, "paye")

            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT request_number, prenom, admin_en_charge, montant FROM demandes WHERE id = %s",
                    (demande_id,)
                )
                dem = cursor.fetchone()

            req_num = html.escape(str(dem.get("request_number", demande_id) if dem else demande_id))
            prenom_cible = html.escape(str(dem.get("prenom", "") if dem else ""))

            merci_msg, kb_client = ui.get_prio_paid_client_content(req_num)
            await update.message.reply_text(
                merci_msg,
                parse_mode="HTML",
                reply_markup=kb_client
            )

            if dem and dem.get("admin_en_charge"):
                admin_id = dem["admin_en_charge"]
                montant = float(dem.get("montant") or 0.0)

                admin_alert, alert_kb = ui.build_prio_paid_admin_alert(req_num, prenom_cible, montant, demande_id)
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_alert,
                        parse_mode="HTML",
                        reply_markup=alert_kb,
                    )
                except Forbidden:
                    logger.warning("Alerte règlement non remise au staff %s (bot bloqué).", admin_id)
                except Exception as notif_err:
                    logger.warning("Impossible d'avertir l'opérateur %s du paiement Stars : %s", admin_id, notif_err)

            logger.info("Prestation prioritaire #%s payée via Stars par l'utilisateur %s", demande_id, user_id)

    # ==================== PAIEMENT DIRECT ====================

    async def pay_contact_prio(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Ouvre le dialogue pour convenir d'un paiement direct (PayPal, virement, etc.)."""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, request_number, admin_en_charge, montant, prenom FROM demandes WHERE id = %s AND user_id = %s",
                (demande_id, user_id),
            )
            dem = cursor.fetchone()

        if not dem or not dem.get("admin_en_charge"):
            await query.answer("❌ Aucun opérateur n'est assigné à cette demande.", show_alert=True)
            return

        admin_id = dem["admin_en_charge"]
        p_methods = self.db_manager.get_staff_payment_methods(admin_id)
        if not p_methods.get("accept_direct", True):
            await query.answer("⚠️ Votre piégeur n'accepte pas le règlement direct. Réglez par Telegram Stars.", show_alert=True)
            return

        req_num = dem.get("request_number", demande_id)
        montant = float(dem.get("montant") or 0.0)
        alias = self.db_manager.get_staff_alias(admin_id)

        context.user_data["replying_to_admin"] = {
            "demande_id": demande_id,
            "admin_id": admin_id,
        }

        try:
            user = update.effective_user
            u_label = f"@{user.username}" if user.username else user.first_name
            admin_alert, kb_admin = ui.build_direct_payment_alert_for_admin(req_num, u_label, dem.get("prenom"), montant, demande_id)
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_alert,
                parse_mode="HTML",
                reply_markup=kb_admin,
            )
        except Exception as notif_err:
            logger.warning("Impossible d'avertir l'opérateur pour paiement alternatif : %s", notif_err)

        contact_text, contact_kb = ui.build_direct_payment_client_prompt(alias, req_num, montant)

        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=contact_text,
                parse_mode="HTML",
                reply_markup=contact_kb,
            )
        else:
            await query.edit_message_text(contact_text, parse_mode="HTML", reply_markup=contact_kb)

    # ==================== REVALORISATION & NÉGOCIATION ====================

    async def accept_remun_prio(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Valide la revalorisation de prix proposée par le staff."""
        query = update.callback_query
        await query.answer()

        assigned_demande = self.db_manager.accept_proposed_price_and_assign(demande_id)
        if not assigned_demande:
            await query.answer("❌ Offre introuvable ou dossier déjà attribué.", show_alert=True)
            return

        req_num = assigned_demande.get("request_number", demande_id)
        nouveau_montant = assigned_demande["nouveau_montant"]
        staff_id = assigned_demande["staff_id"]
        staff_alias = self.db_manager.get_staff_alias(staff_id)
        prenom = html.escape(str(assigned_demande.get("prenom") or ""))

        client_text, client_kb = ui.build_accept_remun_prio_content(req_num, nouveau_montant, staff_alias, prenom)
        await query.edit_message_text(client_text, parse_mode="HTML", reply_markup=client_kb)

        try:
            alert_staff, kb_staff = ui.build_accept_remun_staff_alert(req_num, nouveau_montant, prenom, demande_id)
            await context.bot.send_message(
                chat_id=staff_id,
                text=alert_staff,
                parse_mode="HTML",
                reply_markup=kb_staff,
            )
        except Exception as err_s:
            logger.warning("Impossible de notifier le staff de l'acceptation du prix : %s", err_s)

    async def refuse_remun_prio(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Refuse la revalorisation proposée par le staff."""
        query = update.callback_query
        await query.answer()

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, request_number, prenom, montant, proposed_price, proposed_by FROM demandes WHERE id = %s",
                (demande_id,),
            )
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        req_num = dem.get("request_number", demande_id)
        staff_id = dem.get("proposed_by")
        montant_initial = float(dem.get("montant") or 0.0)
        prenom = html.escape(str(dem.get("prenom") or ""))

        self.db_manager.clear_demande_proposed_price(demande_id)

        client_text, client_kb = ui.build_refuse_remun_prio_content(req_num, montant_initial)
        await query.edit_message_text(client_text, parse_mode="HTML", reply_markup=client_kb)

        if staff_id:
            try:
                alert_staff, kb_staff = ui.build_refuse_remun_staff_alert(req_num, prenom, montant_initial)
                await context.bot.send_message(
                    chat_id=staff_id,
                    text=alert_staff,
                    parse_mode="HTML",
                    reply_markup=kb_staff,
                )
            except Exception as err_s:
                logger.warning("Impossible de notifier le staff du refus de prix : %s", err_s)

    # ==================== CONVERSION STANDARD ➔ PRIORITAIRE ====================

    async def prompt_upgrade_prio(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Demande la saisie du montant pour basculer une demande en prioritaire."""
        query = update.callback_query
        await query.answer()
        context.user_data["waiting_upgrade_prio_amount"] = demande_id

        text_prompt, kb = ui.get_upgrade_prio_prompt_content(demande_id)

        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text_prompt,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            try:
                await query.edit_message_text(text_prompt, parse_mode="HTML", reply_markup=kb)
            except Exception:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text_prompt,
                    parse_mode="HTML",
                    reply_markup=kb,
                )

    async def process_upgrade_prio_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Traite le montant texte de conversion et diffuse l'alerte à l'équipe."""
        raw_montant = update.message.text.strip().replace(",", ".")

        try:
            montant = float(raw_montant)
            if montant <= 0:
                raise ValueError()
        except ValueError:
            context.user_data["waiting_upgrade_prio_amount"] = demande_id
            await update.message.reply_text(
                "❌ Veuillez saisir un montant valide supérieur à 0 (ex : <code>15</code> ou <code>20.50</code>) :",
                parse_mode="HTML",
            )
            return

        user_id = update.effective_user.id
        ok, msg_result = self.db_manager.upgrade_demande_to_prioritaire(demande_id, user_id, montant)

        if not ok:
            await update.message.reply_text(f"⚠️ {msg_result}")
            return

        text_success, kb = ui.build_upgrade_prio_success_content(demande_id, montant)
        await update.message.reply_text(text_success, parse_mode="HTML", reply_markup=kb)
        await self._broadcast_upgrade_alert(context, demande_id, montant)

    async def _broadcast_upgrade_alert(self, context: ContextTypes.DEFAULT_TYPE, demande_id: int, montant: float):
        """Alerte le référent ou l'ensemble du staff après rehaussement prioritaire."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT request_number, prenom, orientation, instagram, snapchat, admin_en_charge FROM demandes WHERE id = %s",
                    (int(demande_id),),
                )
                d_info = cursor.fetchone()

            if not d_info:
                return

            req_num = d_info.get("request_number") or demande_id
            prenom = html.escape(str(d_info.get("prenom") or "la cible"))
            admin_id = d_info.get("admin_en_charge")

            if admin_id:
                msg_referent, kb_ref = ui.build_upgrade_referent_alert(req_num, prenom, montant, demande_id)
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=msg_referent,
                        parse_mode="HTML",
                        reply_markup=kb_ref,
                    )
                except Exception as e_notif:
                    logger.warning("Impossible de notifier le référent %s de l'upgrade : %s", admin_id, e_notif)
                return

            ori = d_info.get("orientation", "hetero")
            has_insta = bool(d_info.get("instagram"))
            has_snap = bool(d_info.get("snapchat"))

            staff_members = self.config.get_all_staff()
            for st_id in staff_members:
                if self.db_manager.is_staff_paused(st_id):
                    continue

                perms = self.db_manager.get_staff_permissions(st_id)
                p_ori = perms.get("perm_orientation", "all")
                p_res = perms.get("perm_reseaux", "all")

                if p_ori != "all" and p_ori != ori and ori != "bi":
                    continue
                if p_res == "insta" and not has_insta:
                    continue
                if p_res == "snap" and not has_snap:
                    continue

                prefs = self.db_manager.get_admin_preferences(st_id)
                notif_mode = prefs.get("notif_new_mode", "sound")
                if notif_mode == "off":
                    continue

                is_silent = (notif_mode == "silent")
                msg_staff, kb_staff = ui.build_upgrade_broadcast_alert(req_num, prenom, montant, demande_id)

                try:
                    await context.bot.send_message(
                        chat_id=st_id,
                        text=msg_staff,
                        parse_mode="HTML",
                        reply_markup=kb_staff,
                        disable_notification=is_silent,
                    )
                except Exception:
                    pass

        except Exception as exc_notif:
            logger.error("Erreur diffusion alertes upgrade prio : %s", exc_notif)