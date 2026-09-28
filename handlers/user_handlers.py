"""Module principal de gestion de l'affichage des interactions utilisateurs et demandeurs."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager
from .user.compte import CompteManager
from .user.demande import DemandeManager
from .user.edition import EditionManager
from .user.formulaire import FormulaireManager
from .user.paiement import PaiementManager
from .user.relais import RelaisManager

from ui.user import compte as user_compte_ui
from ui.user import demandes as user_demandes_ui
from ui.user import paiement as user_paiement_ui
from ui.staff import notifs as staff_notifs_ui

logger = logging.getLogger(__name__)


class UserHandlers:
    """Contrôleur principal des interactions demandeurs et clients."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        self.compte = CompteManager(db_manager, config)
        self.formulaire = FormulaireManager(db_manager, config, self.compte)
        self.demande = DemandeManager(db_manager, config, self.compte)
        self.edition = EditionManager(db_manager, config)
        self.paiement = PaiementManager(db_manager, config)
        self.relais = RelaisManager(db_manager)

        self._staff_handlers = None

    @property
    def staff_handlers(self):
        """Lazy-loading du gestionnaire Staff pour éviter les cycles d'importation."""
        if self._staff_handlers is None:
            from handlers.staff_handlers import StaffHandlers
            self._staff_handlers = StaffHandlers(self.config, self.db_manager)
        return self._staff_handlers

    async def _check_required_membership(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Vérifie si l'utilisateur est membre du groupe obligatoire configuré par l'Owner."""
        user = update.effective_user
        if not user:
            return False

        owner_id_db = self.db_manager.get_owner_id()
        if (
            self.config.is_staff(user.id)
            or self.config.is_admin(user.id)
            or self.config.is_owner(user.id)
            or (owner_id_db and int(user.id) == int(owner_id_db))
        ):
            return True

        if not self.db_manager.is_required_group_enabled():
            return True

        raw_group_id = self.db_manager.get_required_group_id()
        try:
            group_id = int(raw_group_id)
        except (ValueError, TypeError):
            group_id = 0

        if not group_id or group_id == 0:
            return True

        if group_id > 0 and str(group_id).startswith("100"):
            group_id = -group_id

        telegram_err = None
        user_status = None
        try:
            member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
            user_status = member.status

            if user_status in ("member", "administrator", "creator"):
                return True

            if user_status == "restricted":
                if getattr(member, "is_member", True):
                    return True

            logger.info("Utilisateur %s non validé dans le groupe %s (statut : %s)", user.id, group_id, user_status)

        except Exception as exc:
            telegram_err = str(exc)
            logger.error("💥 Erreur get_chat_member (chat_id=%s, user_id=%s) : %s", group_id, user.id, exc)

        if update.callback_query and update.callback_query.data == "check_subscription":
            if telegram_err:
                await update.callback_query.answer(
                    f"⚠️ Erreur Telegram : {telegram_err[:180]} (Chat ID : {group_id})",
                    show_alert=True,
                )
            elif user_status:
                await update.callback_query.answer(
                    f"❌ Non détecté dans le groupe (Statut Telegram : {user_status}). Rejoignez le groupe avant de valider.",
                    show_alert=True,
                )

        raw_link = self.db_manager.get_group_subscription_link()
        if raw_link.startswith("@"):
            sub_url = f"https://t.me/{raw_link.lstrip('@')}"
        elif raw_link.startswith(("http://", "https://")):
            sub_url = raw_link
        else:
            sub_url = f"https://t.me/{raw_link}"

        msg_text, keyboard = user_compte_ui.get_required_membership_content(sub_url)

        if update.callback_query:
            try:
                await update.callback_query.message.edit_text(msg_text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                await update.callback_query.message.reply_text(msg_text, parse_mode="HTML", reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(msg_text, parse_mode="HTML", reply_markup=keyboard)

        return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée commande /start."""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name
        logger.info("🚀 Exécution de /start pour user_id=%s (%s)", user_id, first_name)

        try:
            await self.compte.ensure_user_registered(update)
            if not await self._check_required_membership(update, context):
                return

            welcome_msg, reply_markup = self.interface.get_start_interface(user_id, first_name)
            await update.message.reply_text(welcome_msg, parse_mode="HTML", reply_markup=reply_markup)
            logger.info("✅ Message de bienvenue envoyé avec succès à %s", user_id)

        except Exception as exc:
            logger.error("💥 Erreur lors de l'exécution de /start pour %s : %s", user_id, exc, exc_info=True)
            try:
                await update.message.reply_text(
                    "❌ Une erreur interne est survenue lors du chargement du menu. Réessayez dans quelques instants."
                )
            except Exception:
                pass

    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage des callbacks d'actions utilisateur."""
        query = update.callback_query
        if not query or not query.data:
            return

        data = query.data
        user_id = query.from_user.id

        if data == "check_subscription":
            if await self._check_required_membership(update, context):
                await query.answer("✅ Merci pour votre adhésion !", show_alert=True)
                welcome_msg, reply_markup = self.interface.get_start_interface(user_id, query.from_user.first_name)
                try:
                    await query.edit_message_text(welcome_msg, parse_mode="HTML", reply_markup=reply_markup)
                except Exception:
                    await query.message.reply_text(welcome_msg, parse_mode="HTML", reply_markup=reply_markup)
            return

        if not await self._check_required_membership(update, context):
            await query.answer("❌ Adhésion obligatoire non validée.", show_alert=True)
            return

        if data.startswith(("form_", "nav_", "new_demande")) and not self.config.are_demandes_enabled():
            await query.answer()
            text_err, kb_err = user_compte_ui.get_service_disabled_content()
            await query.edit_message_text(text_err, parse_mode="HTML", reply_markup=kb_err)
            return

        try:
            if data == "quota_reached_info":
                _, reason = self.demande.check_creation_quota(user_id)
                clean_reason = reason.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")[:150]
                await query.answer(clean_reason, show_alert=True)
                return

            elif data == "new_demande":
                await query.answer()
                can_create, reason_msg = self.demande.check_creation_quota(user_id)
                if not can_create:
                    text_q, kb_q = user_compte_ui.get_quota_reached_content(reason_msg)
                    await query.edit_message_text(text_q, parse_mode="HTML", reply_markup=kb_q)
                    return
                await self.formulaire.navigation.handle_form_navigation(update, context)

            elif data == "mes_archives" or data.startswith("user_arch_page_"):
                await self.demande.handle_navigation(update, context, data)

            elif data == "menu_vip_shop":
                await query.answer()
                is_vip_user = self.db_manager.is_user_vip(user_id)
                msg, kb = self.interface.get_vip_shop_menu(is_vip=is_vip_user)
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)

            elif data == "menu_vip_settings" or data.startswith("vip_set_assign_") or data == "vip_pick_auto_staff":
                if data == "menu_vip_settings":
                    await self.compte.show_vip_settings_menu(update, context)
                else:
                    await self.compte.handle_callback_routing(update, context, data)

            elif data == "buy_vip_month":
                await self.paiement.buy_vip_month(update, context)

            elif data.startswith("user_accept_remun_std_"):
                await query.answer()
                demande_id = int(data.replace("user_accept_remun_std_", ""))
                context.user_data["waiting_client_std_remun_amount"] = demande_id
                prompt_text, kb = user_paiement_ui.get_std_remun_allocation_prompt(demande_id)
                await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("user_refuse_remun_std_"):
                await query.answer()
                demande_id = int(data.replace("user_refuse_remun_std_", ""))
                demande = self.db_manager.archiver_demande_annulee(demande_id, raison="Refus de rémunération formulé par le demandeur")
                if demande:
                    req_num = demande.get("request_number", demande_id)
                    text_ref, kb_ref = user_paiement_ui.get_std_remun_refused_content(req_num)
                    await query.edit_message_text(text_ref, parse_mode="HTML", reply_markup=kb_ref)
                else:
                    await query.answer("❌ Demande introuvable.", show_alert=True)

            elif data.startswith("user_accept_remun_prio_"):
                demande_id = int(data.replace("user_accept_remun_prio_", ""))
                await self.paiement.accept_remun_prio(update, context, demande_id)

            elif data.startswith("user_refuse_remun_prio_"):
                demande_id = int(data.replace("user_refuse_remun_prio_", ""))
                await self.paiement.refuse_remun_prio(update, context, demande_id)

            elif data.startswith("upgrade_prio_"):
                demande_id = int(data.replace("upgrade_prio_", ""))
                await self.paiement.prompt_upgrade_prio(update, context, demande_id)

            elif data.startswith("pay_stars_prio_"):
                demande_id = int(data.replace("pay_stars_prio_", ""))
                await self.paiement.pay_stars_prio(update, context, demande_id)

            elif data.startswith("pay_contact_prio_"):
                demande_id = int(data.replace("pay_contact_prio_", ""))
                await self.paiement.pay_contact_prio(update, context, demande_id)

            elif data.startswith("remind_admin_free_"):
                demande_id = int(data.replace("remind_admin_free_", ""))
                can_remind, err_msg = self.db_manager.can_send_demande_reminder(demande_id)
                if not can_remind:
                    await query.answer(f"⚠️ {err_msg}", show_alert=True)
                    return
                await self._dispatch_admin_reminder(update, context, demande_id, is_paid_boost=False)

            elif data.startswith("remind_admin_pay_"):
                demande_id = int(data.replace("remind_admin_pay_", ""))
                can_remind, err_msg = self.db_manager.can_send_demande_reminder(demande_id)
                if not can_remind:
                    await query.answer(f"⚠️ {err_msg}", show_alert=True)
                    return
                await self.paiement.send_paid_reminder_invoice(update, context, demande_id)

            elif data.startswith(("vip_contact_admin_", "contact_admin_")):
                demande_id = int(data.split("_")[-1])
                await self._start_user_reply_contact(update, context, demande_id)

            elif data.startswith("vip_assign_admin_") or data.startswith("vip_opt_"):
                await self.formulaire.handle_vip_admin_choice(update, context)

            elif data.startswith("reprendre_demande_"):
                await self._handle_reprendre_demande(update, context, int(data.replace("reprendre_demande_", "")))

            elif data.startswith("archiver_demande_"):
                demande_id = int(data.replace("archiver_demande_", ""))
                demande = self.db_manager.archiver_demande_supprimee(demande_id, "Abandonnée par le demandeur")
                if demande:
                    text_arch, kb_arch = user_demandes_ui.get_archiver_demande_success_content()
                    await query.edit_message_text(text_arch, parse_mode="HTML", reply_markup=kb_arch)
                else:
                    await query.answer("❌ Erreur technique lors de l'archivage.", show_alert=True)

            elif data.startswith("ask_cancel_demande_"):
                demande_id = int(data.replace("ask_cancel_demande_", ""))
                context.user_data["waiting_cancel_reason_demande_id"] = demande_id
                prompt_text, kb = user_demandes_ui.get_client_cancel_prompt(demande_id)
                await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=kb)

            elif data.startswith("accept_cancel_"):
                await self._handle_staff_decision_cancel(update, context, int(data.replace("accept_cancel_", "")), accept=True)

            elif data.startswith("refuse_cancel_"):
                await self._handle_staff_decision_cancel(update, context, int(data.replace("refuse_cancel_", "")), accept=False)

            elif data.startswith("reply_to_admin_"):
                await query.answer()
                parts = data.split("_")
                demande_id = int(parts[3])
                admin_id = int(parts[4])
                context.user_data["replying_to_admin"] = {"demande_id": demande_id, "admin_id": admin_id}
                await query.message.reply_text(
                    "✍️ <b>Tapez votre réponse ou envoyez votre fichier ci-dessous :</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="cancel_user_reply")]]),
                )

            elif data == "cancel_user_reply":
                await query.answer()
                context.user_data.pop("replying_to_admin", None)
                await query.edit_message_text("❌ Réponse annulée.")

            elif data.startswith("form_"):
                await query.answer()
                await self.formulaire.navigation.handle_form_navigation(update, context)

            elif data.startswith("nav_"):
                await query.answer()
                await self.demande.handle_navigation(update, context, data)

            elif data.startswith("modify_"):
                await query.answer()
                await self.edition.handle_modify_request(update, context, data)

            elif data.startswith("edit_"):
                await query.answer()
                await self.edition.handle_edit_field(update, context, data)

            elif data.startswith("delete_"):
                await query.answer()
                await self.edition.handle_delete_request(update, context, data)

            elif data.startswith("confirm_delete_"):
                await query.answer()
                await self.edition.handle_confirm_delete(update, context, data)

            elif data == "cancel_edit":
                await query.answer()
                await self.edition.handle_cancel_edit(update, context)

            else:
                await query.answer("❌ Action non reconnue", show_alert=True)

        except Exception as exc:
            logger.error("Erreur callback %s : %s", data, exc, exc_info=True)
            try:
                await query.edit_message_text(
                    "❌ Une erreur est survenue lors du traitement de votre demande.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 RETOUR AU MENU 🔙", callback_data="start_menu")]]),
                )
            except Exception:
                pass

    async def _start_user_reply_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Prépare la session de contact direct client ➔ opérateur."""
        query = update.callback_query
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT admin_en_charge, request_number FROM demandes WHERE id = %s", (demande_id,))
            d_row = cursor.fetchone()

        if not d_row or not d_row.get("admin_en_charge"):
            await query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
            return

        admin_id = d_row["admin_en_charge"]
        if self.db_manager.is_staff_paused(admin_id):
            raw_alias = self.db_manager.get_staff_alias(admin_id)
            await query.answer(f"⏸️ Votre référent ({raw_alias}) est actuellement en pause. Réessayez ultérieurement.", show_alert=True)
            return

        context.user_data["replying_to_admin"] = {"demande_id": demande_id, "admin_id": admin_id}
        await query.answer()

        req_num = d_row.get("request_number", demande_id)
        alias = self.db_manager.get_staff_alias(admin_id)
        contact_text, contact_kb = user_demandes_ui.get_user_reply_contact_prompt(alias, req_num)

        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(chat_id=query.message.chat_id, text=contact_text, parse_mode="HTML", reply_markup=contact_kb)
        else:
            await query.edit_message_text(contact_text, parse_mode="HTML", reply_markup=contact_kb)

    async def _handle_reprendre_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Remet un dossier abandonné dans la file d'attente."""
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (demande_id,))
                cursor.execute(
                    "UPDATE demandes SET statut = '📥 Reçue', admin_en_charge = NULL, date_modification = NOW() WHERE id = %s AND user_id = %s",
                    (demande_id, user_id),
                )
            text_rep, kb_rep = user_demandes_ui.get_reprendre_demande_success_content()
            await query.edit_message_text(text_rep, parse_mode="HTML", reply_markup=kb_rep)
        except Exception as exc:
            logger.error("Erreur remise en dispo demande %s : %s", demande_id, exc)
            await query.answer("❌ Erreur technique lors de la remise en file d'attente.", show_alert=True)

    async def _handle_staff_decision_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, accept: bool):
        """Applique la décision du staff sur la demande d'annulation client."""
        query = update.callback_query
        await query.answer()

        if accept:
            raison = context.user_data.pop(f"cancel_reason_{demande_id}", "Convenance demandeur")
            demande = self.db_manager.archiver_demande_annulee(demande_id, raison)
            if demande:
                req_num = demande.get("request_number", demande_id)
                await query.edit_message_text(f"✅ <b>Annulation acceptée.</b> Le dossier #{req_num} est archivé sous « ❌ Annulée ».", parse_mode="HTML")
                try:
                    await context.bot.send_message(
                        chat_id=demande["user_id"],
                        text=f"✅ <b>Votre demande d'annulation pour le dossier #{req_num} a été acceptée par l'opérateur.</b>\nLe dossier est clôturé.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            else:
                await query.answer("❌ Demande introuvable ou déjà traitée.", show_alert=True)
        else:
            context.user_data.pop(f"cancel_reason_{demande_id}", None)
            await query.edit_message_text(f"❌ <b>Annulation refusée.</b> Le traitement du dossier #{demande_id} se poursuit.", parse_mode="HTML")
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT user_id, request_number FROM demandes WHERE id = %s", (demande_id,))
                dem = cursor.fetchone()
            if dem:
                try:
                    await context.bot.send_message(
                        chat_id=dem["user_id"],
                        text=f"⚠️ <b>Demande d'annulation refusée pour le dossier #{dem.get('request_number', demande_id)}.</b>\nLe piège est déjà trop avancé.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    async def _dispatch_admin_reminder(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, is_paid_boost: bool = False
    ):
        """Transmet la notification de rappel à l'opérateur en charge."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT request_number, prenom, user_id, admin_en_charge FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        if not row or not row.get("admin_en_charge"):
            if update.callback_query:
                await update.callback_query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
            return

        admin_id = row["admin_en_charge"]
        if self.db_manager.is_staff_paused(admin_id):
            raw_alias = self.db_manager.get_staff_alias(admin_id)
            if update.callback_query:
                await update.callback_query.answer(f"⏸️ Votre référent ({raw_alias}) est en pause.", show_alert=True)
            return

        req_num = html.escape(str(row.get("request_number", demande_id)))
        user = update.effective_user
        user_label = f"@{user.username}" if user.username else user.first_name
        user_label_esc = html.escape(user_label or f"User_{user.id}")
        prenom_esc = html.escape(str(row.get("prenom") or ""))

        tag = "⭐ VIP" if self.db_manager.is_user_vip(user.id) else ("⚡ Boost 1 €" if is_paid_boost else "💎 Prioritaire")
        remind_msg, admin_kb = staff_notifs_ui.format_admin_reminder_alert(req_num, user_label_esc, prenom_esc, tag, demande_id)

        try:
            await context.bot.send_message(chat_id=admin_id, text=remind_msg, parse_mode="HTML", reply_markup=admin_kb)
            self.db_manager.record_demande_reminder_sent(demande_id)
            confirm_txt = "✅ Rappel envoyé avec succès à votre référent !"
            if update.callback_query:
                await update.callback_query.answer(confirm_txt, show_alert=True)
            elif update.message:
                await update.message.reply_text(confirm_txt)
        except Exception as exc:
            logger.error("Erreur transmission rappel demande %s : %s", demande_id, exc)
            if update.callback_query:
                await update.callback_query.answer("❌ Erreur technique lors de l'envoi du rappel.", show_alert=True)

    async def handle_interface_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routeur des boutons de navigation générale."""
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        user_id = query.from_user.id
        first_name = query.from_user.first_name
        data = query.data

        owner_actions = {
            "gerer_admins", "admin_ajouter", "admin_supprimer", "gerer_staff", "staff_ajouter",
            "staff_supprimer", "gerer_bot", "bot_on", "bot_off", "bot_maintenance", "menu_channels",
            "menu_limits", "gerer_vips", "owner_add_vip", "owner_remove_vip", "menu_cfg_group",
            "toggle_cfg_group_enabled", "set_cfg_group_id", "set_cfg_group_link", "menu_cfg_support",
            "set_cfg_support_contact", "menu_danger_zone",
        }
        if (data in owner_actions or data.startswith("limit_")) and not self.config.is_admin(user_id):
            await query.answer("❌ Accès réservé aux administrateurs.", show_alert=True)
            return

        staff_actions = {"gerer_demandes", "demandes_disponibles", "demandes_suivies", "modifier_alias", "menu_notifs"}
        if data in staff_actions and not self.config.is_staff(user_id):
            await query.answer("❌ Accès réservé à l'équipe opérationnelle.", show_alert=True)
            return

        if data == "voir_demandes":
            await self.demande.voir_demandes(update, context)
            return

        if data == "menu_limits":
            msg, kb = self.interface.get_limits_menu()
            if query.message and query.message.photo:
                await query.message.delete()
                await context.bot.send_message(chat_id=query.message.chat_id, text=msg, parse_mode="HTML", reply_markup=kb)
            else:
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            return

        if data.startswith("limit_"):
            await self._handle_limit_buttons(query, context, data)
            return

        message, keyboard = self.interface.route_callback(data, user_id, first_name)
        if message and keyboard:
            if query.message and query.message.photo:
                chat_id = query.message.chat_id
                await query.message.delete()
                await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.answer("❌ Action indisponible.", show_alert=True)

    async def _handle_limit_buttons(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Ajustement des quotas en RAM et MySQL."""
        tot = self.config.get_max_total_demandes()
        usr = self.config.get_max_demandes_per_user()

        if data == "limit_total_0":
            self.config.set_max_total_demandes(0)
            self.db_manager.set_config_value("max_total_demandes", "0")
        elif data == "limit_total_add5":
            self.config.set_max_total_demandes(tot + 5)
            self.db_manager.set_config_value("max_total_demandes", str(tot + 5))
        elif data == "limit_total_sub5":
            new_tot = max(0, tot - 5)
            self.config.set_max_total_demandes(new_tot)
            self.db_manager.set_config_value("max_total_demandes", str(new_tot))
        elif data == "limit_user_3":
            self.config.set_max_demandes_per_user(3)
            self.db_manager.set_config_value("max_demandes_per_user", "3")
        elif data == "limit_user_add1":
            self.config.set_max_demandes_per_user(usr + 1)
            self.db_manager.set_config_value("max_demandes_per_user", str(usr + 1))
        elif data == "limit_user_sub1":
            new_usr = max(1, usr - 1)
            self.config.set_max_demandes_per_user(new_usr)
            self.db_manager.set_config_value("max_demandes_per_user", str(new_usr))
        elif data in ("limit_input_total", "limit_input_user", "limit_input_hetero_insta", "limit_input_hetero_snap", "limit_input_gay_insta", "limit_input_gay_snap"):
            field = data.replace("limit_input_", "")
            context.user_data["waiting_limit_input"] = field
            await query.edit_message_text(
                f"🔢 Tapez au clavier la valeur souhaitée pour <b>{field}</b> (0 = illimité) :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="menu_limits")]]),
            )
            return

        msg, kb = self.interface.get_limits_menu()
        try:
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage des saisies texte hors formulaires."""
        if not update.message:
            return

        # Saisie revalorisation par le staff
        if update.message.text and context.user_data and context.user_data.get("waiting_staff_revalorisation_prix"):
            sess = context.user_data.pop("waiting_staff_revalorisation_prix")
            raw_montant = update.message.text.strip().replace(",", ".").replace("€", "")
            try:
                nouveau_prix = float(raw_montant)
                if nouveau_prix <= sess["current_montant"]:
                    raise ValueError()
            except ValueError:
                context.user_data["waiting_staff_revalorisation_prix"] = sess
                await update.message.reply_text(
                    f"❌ Veuillez saisir un montant valide (minimum : <code>{sess['current_montant'] + 1:.2f} €</code>) :",
                    parse_mode="HTML",
                )
                return

            if self.db_manager.set_demande_proposed_price(sess["demande_id"], sess["staff_id"], nouveau_prix):
                await self._notify_client_revalorisation(update, context, sess["demande_id"], sess["staff_id"], nouveau_prix, sess["current_montant"])
            else:
                await update.message.reply_text("❌ Erreur technique lors de l'enregistrement de l'offre.")
            return

        # Saisie rémunération client (conversion standard)
        if update.message.text and context.user_data and context.user_data.get("waiting_client_std_remun_amount"):
            demande_id = context.user_data.pop("waiting_client_std_remun_amount")
            await self.paiement.process_upgrade_prio_text(update, context, demande_id)
            return

        # Signalement d'une demande disponible
        if update.message.text and context.user_data and context.user_data.get("waiting_staff_report_reason"):
            demande_id = context.user_data.pop("waiting_staff_report_reason")
            await self._process_staff_report_dispo(update, context, demande_id)
            return

        # Conversion en prioritaire classique
        if update.message.text and context.user_data and context.user_data.get("waiting_upgrade_prio_amount"):
            demande_id = context.user_data.pop("waiting_upgrade_prio_amount")
            await self.paiement.process_upgrade_prio_text(update, context, demande_id)
            return

        # Saisie d'une configuration Owner (Groupe, Support)
        if update.message.text and context.user_data and context.user_data.get("waiting_owner_input"):
            await self._process_owner_config_input(update, context)
            return

        # Saisie d'un quota par l'Owner
        if update.message.text and context.user_data and context.user_data.get("waiting_limit_input"):
            await self._process_limit_input(update, context)
            return

        # Motif d'annulation client
        if update.message.text and context.user_data and context.user_data.get("waiting_cancel_reason_demande_id"):
            demande_id = context.user_data.pop("waiting_cancel_reason_demande_id")
            await self._process_client_cancel_request(update, context, demande_id)
            return

        # Motif d'abandon opérateur
        if update.message.text and context.user_data and context.user_data.get("waiting_abandon_reason"):
            await self.staff_handlers.statuts.process_abandon_reason(update, context)
            return

        # Recherches textuelles
        if update.message.text and context.user_data and context.user_data.get("waiting_dispo_search"):
            await self.staff_handlers.dispo.handle_search_text_input(update, context)
            return
        if update.message.text and context.user_data and context.user_data.get("waiting_suivi_search"):
            await self.staff_handlers.suivi.handle_search_text_input(update, context)
            return

        # Collecte médias opérateur
        if context.user_data and context.user_data.get("contact_session"):
            if await self.staff_handlers.handle_collect_admin_media(update, context):
                return

        # Relais demandeur ➔ référent
        if context.user_data and context.user_data.get("replying_to_admin"):
            await self.relais.handle_user_reply_relay(update, context)
            return

        # Édition d'une demande par le client
        if update.message.text and context.user_data and context.user_data.get("editing"):
            await self.edition.handle_edit_text_input(update, context)
            return

        # Fallback général
        await self.compte.handle_text_messages(update, context)

    async def _notify_client_revalorisation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int, nouveau_prix: float, current_montant: float):
        """Envoie l'offre de revalorisation au demandeur."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, request_number, prenom, user_id FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if dem:
            req_num = dem.get("request_number", demande_id)
            prenom = html.escape(str(dem.get("prenom") or "votre contact"))
            alias_staff = self.db_manager.get_staff_alias(staff_id)
            client_alert, client_kb = user_paiement_ui.format_client_revalorisation_proposal(
                req_num, prenom, alias_staff, nouveau_prix, current_montant, demande_id
            )
            try:
                await context.bot.send_message(chat_id=dem["user_id"], text=client_alert, parse_mode="HTML", reply_markup=client_kb)
                await update.message.reply_text(f"✅ <b>Proposition de {nouveau_prix:.2f} € envoyée au demandeur pour le dossier #{req_num} !</b>", parse_mode="HTML")
            except Exception:
                await update.message.reply_text("❌ Impossible de transmettre la proposition au demandeur.")

    async def _process_staff_report_dispo(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Transmet le signalement d'une demande disponible aux superviseurs."""
        motif = update.message.text.strip()
        staff_user = update.effective_user
        staff_alias = self.db_manager.get_staff_alias(staff_user.id)
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, request_number, prenom FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if not dem:
            await update.message.reply_text("❌ Demande introuvable.")
            return

        req_num = dem.get("request_number", demande_id)
        prenom = html.escape(str(dem.get("prenom") or ""))
        admin_alert, admin_kb = staff_notifs_ui.build_staff_report_alert(
            staff_alias, staff_user.id, req_num, prenom, motif, demande_id
        )

        for admin_id in self.db_manager.get_monitoring_admins():
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="HTML", reply_markup=admin_kb)
            except Exception:
                pass
        await update.message.reply_text("✅ <b>Signalement transmis à l'administration avec succès !</b>", parse_mode="HTML")

    async def _process_owner_config_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite les entrées de configuration du propriétaire."""
        if not self.config.is_owner(update.effective_user.id):
            return
        mode = context.user_data.pop("waiting_owner_input")
        txt = update.message.text.strip()
        if mode == "required_group_id":
            try:
                gid = int(txt)
                self.db_manager.set_required_group_id(gid)
                await update.message.reply_text(f"✅ ID du groupe configuré sur : <code>{gid}</code>", parse_mode="HTML")
            except ValueError:
                await update.message.reply_text("❌ L'ID doit être un entier relatif.")
            msg, kb = self.interface.get_group_subscription_config_menu()
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
        elif mode == "group_subscription_link":
            self.db_manager.set_group_subscription_link(txt)
            await update.message.reply_text(f"✅ Lien mis à jour : <code>{html.escape(txt)}</code>", parse_mode="HTML")
            msg, kb = self.interface.get_group_subscription_config_menu()
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
        elif mode == "support_contact":
            self.db_manager.set_support_contact(txt)
            await update.message.reply_text(f"✅ Support mis à jour : <code>{html.escape(txt)}</code>", parse_mode="HTML")
            msg, kb = self.interface.get_support_config_menu()
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

    async def _process_limit_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Traite la saisie numérique d'un quota."""
        if not self.config.is_owner(update.effective_user.id):
            return
        raw = update.message.text.strip()
        if not raw.isdigit():
            await update.message.reply_text("❌ Veuillez saisir un nombre entier positif.")
            return

        mode = context.user_data.pop("waiting_limit_input")
        val = int(raw)
        key_map = {"total": "max_total_demandes", "user": "max_demandes_per_user", "hetero_insta": "max_hetero_insta", "hetero_snap": "max_hetero_snap", "gay_insta": "max_gay_insta", "gay_snap": "max_gay_snap"}
        cfg_key = key_map.get(mode, f"max_{mode}")

        if mode == "total":
            self.config.set_max_total_demandes(val)
        elif mode == "user":
            self.config.set_max_demandes_per_user(val)

        self.db_manager.set_config_value(cfg_key, str(val))
        libelle = "Illimité" if val == 0 else str(val)
        await update.message.reply_text(f"✅ Quota <b>{mode}</b> défini à : <b>{libelle}</b>", parse_mode="HTML")
        msg, kb = self.interface.get_limits_menu()
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)

    async def _process_client_cancel_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Transmet la demande d'annulation client à l'opérateur en charge."""
        raison = update.message.text.strip()
        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT admin_en_charge, request_number, prenom, user_id FROM demandes WHERE id = %s", (demande_id,))
            d = cursor.fetchone()

        if not d:
            await update.message.reply_text("❌ Demande introuvable.")
            return

        admin_id = d.get("admin_en_charge")
        req_num = d.get("request_number", demande_id)

        if admin_id:
            context.user_data[f"cancel_reason_{demande_id}"] = raison
            text_cancel, kb_cancel = staff_notifs_ui.build_staff_cancel_decision_alert(req_num, d.get("prenom"), raison, demande_id)
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=text_cancel,
                    parse_mode="HTML",
                    reply_markup=kb_cancel,
                )
                await update.message.reply_text("📨 <b>Votre demande d'annulation a été transmise à votre piégeur.</b>", parse_mode="HTML")
            except Exception:
                await update.message.reply_text("❌ Erreur lors de la transmission au piégeur.")
        else:
            self.db_manager.archiver_demande_annulee(demande_id, raison)
            await update.message.reply_text(f"✅ <b>Votre demande #{req_num} a été annulée et archivée.</b>", parse_mode="HTML")

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redirige vers l'affichage des demandes du client."""
        await self.demande.voir_demandes(update, context)