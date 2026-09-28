"""Module de gestion des fonctions d'administration et de gouvernance (Admin & Owner)."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.interface_manager import InterfaceManager
from utils.maintenance import check_storage_usage, daily_maintenance
from .staff.alias import AliasManager
from .staff.archives import ArchivesManager
from .admin.config import ConfigManager
from .admin.stats import StatsManager
from .admin.bot import BotManager
from .admin.staff import StaffManager
from .admin.purge import PurgeManager
from .admin.membres import MembresManager
from .admin.vips import VipManager
from ui.admin import users as users_ui, system as system_ui

logger = logging.getLogger(__name__)

ALLOWED_ADMIN_PERMISSIONS = frozenset({
    "can_manage_staff",
    "can_manage_vips",
    "can_view_stats",
    "can_manage_delais",
    "can_view_archives",
    "can_monitor_staff",
    "can_ban_users",
    "can_edit_others_demandes",
    "is_vip",
    "is_owner",
})


class AdminHandlers:
    """Gestionnaire central de la gouvernance, des droits et de la maintenance du bot."""

    WAITING_STAFF_ID = 1
    WAITING_STAFF_CONFIG = 2
    WAITING_STAFF_REMOVE = 3
    WAITING_STAFF_CONFIRMATION = 4

    WAITING_ADMIN_ID = 5
    WAITING_ADMIN_REMOVE = 6
    WAITING_ADMIN_CONFIRMATION = 7

    WAITING_VIP_USER = 10
    WAITING_VIP_DURATION = 11
    WAITING_VIP_REMOVE = 12

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)
        self.alias_manager = AliasManager(db_manager, config)
        self.archives_manager = ArchivesManager(db_manager, config)

        self.config_manager = ConfigManager(db_manager, config)
        self.stats_manager = StatsManager(db_manager, config)
        self.bot_manager = BotManager(db_manager, config, self.interface)
        self.staff_manager = StaffManager(db_manager, config, self.interface)
        self.purge_manager = PurgeManager(db_manager, config, self.interface)
        self.membres_manager = MembresManager(db_manager, config)
        self.vip_manager = VipManager(db_manager, config, self.interface)

        logger.info("AdminHandlers initialisé avec architecture allégée (Purge, Membres, VIPs isolés).")

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        if query.message and query.message.photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                    )

    # ==================== MAINTENANCE ====================

    async def run_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la routine de purge et d'optimisation (Owner only)."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            if update.callback_query:
                await update.callback_query.answer("❌ Accès réservé aux propriétaires.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Accès non autorisé.")
            return

        if update.callback_query:
            await update.callback_query.answer()
            await self._safe_edit_or_send(update.callback_query, context, "🔧 <b>Maintenance en cours...</b>")
        else:
            await update.message.reply_text("🔧 <b>Maintenance en cours...</b>", parse_mode="HTML")

        try:
            storage_before = await check_storage_usage()
            await daily_maintenance(self.db_manager)
            storage_after = await check_storage_usage()

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM demandes")
                demandes_count = cursor.fetchone()["count"]
                cursor.execute("SELECT COUNT(*) AS count FROM archives")
                archives_count = cursor.fetchone()["count"]

            message, keyboard = system_ui.format_maintenance_summary(storage_before, storage_after, demandes_count, archives_count)

            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, message, reply_markup=keyboard)
            else:
                await update.message.reply_text(message, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur maintenance manuelle : %s", exc, exc_info=True)
            if update.callback_query:
                await self._safe_edit_or_send(update.callback_query, context, "❌ Échec lors de la maintenance.")
            else:
                await update.message.reply_text("❌ Échec lors de la maintenance.")

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_manager.bot_on(update, context)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return
        await query.answer()
        text, keyboard = system_ui.get_bot_off_confirmation_content()
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def confirmer_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_manager.bot_off(update, context)

    async def cancel_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        await query.answer()
        message, keyboard = self.interface.get_gerer_bot_menu()
        await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)

    async def toggle_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.effective_user or not self.config.is_owner(update.effective_user.id):
            return
        if self.config.are_demandes_enabled():
            self.config.disable_demandes()
            await update.message.reply_text("🚫 <b>Service suspendu :</b> Création bloquée.", parse_mode="HTML")
        else:
            self.config.enable_demandes()
            await update.message.reply_text("✅ <b>Service actif :</b> Création autorisée.", parse_mode="HTML")

    # ==================== ROUTEUR DES CALLBACKS ====================

    async def handle_admin_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        user_id = update.effective_user.id
        data = query.data or ""

        # Moyens de paiement staff
        if data == "staff_payment_settings" and (self.config.is_staff(user_id) or self.config.is_admin(user_id)):
            await query.answer()
            text_menu, kb_menu = self.interface.get_staff_payment_settings_menu(user_id)
            await self._safe_edit_or_send(query, context, text_menu, reply_markup=kb_menu)
            return

        if data.startswith("toggle_pay_staff_") and (self.config.is_staff(user_id) or self.config.is_admin(user_id)):
            method = data.replace("toggle_pay_staff_", "")
            ok, msg_err = self.db_manager.toggle_staff_payment_method(user_id, method)
            if not ok:
                await query.answer(f"⚠️ {msg_err}", show_alert=True)
                return
            await query.answer("✅ Option mise à jour !")
            text_menu, kb_menu = self.interface.get_staff_payment_settings_menu(user_id)
            await self._safe_edit_or_send(query, context, text_menu, reply_markup=kb_menu)
            return

        if not self.config.is_admin(user_id):
            await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        privs = self.db_manager.get_admin_privileges(user_id)
        is_owner = privs.get("is_owner", False) or self.config.is_owner(user_id)
        can_ban = is_owner or privs.get("can_ban_users", False) or privs.get("perm_ban", False)

        # Service bot
        if data == "bot_on" and is_owner:
            await self.bot_on(update, context)
        elif data == "bot_off" and is_owner:
            await self.bot_off(update, context)
        elif data == "confirm_bot_off" and is_owner:
            await self.confirmer_bot_off(update, context)
        elif data == "cancel_bot_off" and is_owner:
            await self.cancel_bot_off(update, context)
        elif data == "maintenance" and is_owner:
            await self.run_maintenance(update, context)

        # Adhésion groupe obligatoire
        elif data == "menu_cfg_group" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_group_subscription_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "toggle_cfg_group_enabled" and is_owner:
            new_state = self.db_manager.toggle_required_group_enabled()
            await query.answer(f"Obligation d'adhésion {'activée' if new_state else 'désactivée'} !")
            msg, kb = self.interface.get_group_subscription_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "set_cfg_group_id" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "required_group_id"
            await query.edit_message_text(
                "🆔 <b>Entrez le Chat ID numérique du groupe obligatoire</b> (ex: <code>-1001234567890</code>) :\n\n"
                "<i>Assurez-vous que le bot est bien présent dans ce groupe en tant qu'administrateur.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_group")]]),
            )

        elif data == "set_cfg_group_link" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "group_subscription_link"
            await query.edit_message_text(
                "🔗 <b>Entrez le nom du bot ou l'URL t.me d'inscription</b> (ex: <code>@parascriptionbot</code>) :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_group")]]),
            )

        # Support
        elif data == "menu_cfg_support" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_support_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "set_cfg_support_contact" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "support_contact"
            await query.edit_message_text(
                "🎧 <b>Entrez le @username ou le lien du support</b> (ex: <code>@ContactParaBot</code>) :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_support")]]),
            )

        # Purges (PurgeManager)
        elif data == "menu_danger_zone" and is_owner:
            await self.purge_manager.show_purge_menu(query, context)

        elif data.startswith("danger_purge_") and is_owner:
            target = data.replace("danger_purge_", "")
            await self.purge_manager.prompt_confirmation(query, context, target)

        elif data.startswith("danger_confirm_yes_") and is_owner:
            target = data.replace("danger_confirm_yes_", "")
            await self.purge_manager.prompt_text_confirmation(query, context, target)

        # Statistiques
        elif data == "bot_stats" and privs.get("can_view_stats", True):
            await self.stats_manager.show_general_stats(update, context)

        # Membres & Bannissements (MembresManager)
        elif data == "menu_membres":
            await query.answer()
            msg, kb = self.interface.get_membres_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "search_member_prompt":
            await self.membres_manager.prompt_search(query, context)

        elif data.startswith("liste_bannis_"):
            try:
                page = int(data.replace("liste_bannis_", ""))
            except ValueError:
                page = 0
            await self.membres_manager.show_banned_list(update, context, page=page)

        elif data.startswith("ban_prompt_user_") and can_ban:
            await query.answer()
            parts = data.split("_")
            target_user_id = int(parts[3])
            origin_demande_id = int(parts[4]) if len(parts) > 4 else 0
            await self.membres_manager.prompt_ban_reason(query, context, target_user_id, is_staff=False, origin_demande_id=origin_demande_id)

        elif data.startswith("ban_prompt_staff_") and can_ban:
            await query.answer()
            target_staff_id = int(data.replace("ban_prompt_staff_", ""))
            await self.membres_manager.prompt_ban_reason(query, context, target_staff_id, is_staff=True)

        elif data.startswith("unban_user_") and can_ban:
            await query.answer()
            parts = data.split("_")
            target_user_id = int(parts[2])
            origin_demande_id = int(parts[3]) if len(parts) > 3 else 0
            self.db_manager.unban_user(target_user_id)
            await query.answer("🟢 Utilisateur débanni avec succès !", show_alert=True)
            from handlers.staff.profils import ProfilsManager
            prof = ProfilsManager(self.db_manager, self.config)
            await prof._render_user_profile(query, context, target_user_id, origin_demande_id=origin_demande_id)

        elif data.startswith("unban_staff_") and can_ban:
            await query.answer()
            target_staff_id = int(data.replace("unban_staff_", ""))
            self.db_manager.unban_user(target_staff_id)
            await query.answer("🟢 Piégeur débanni avec succès !", show_alert=True)
            from handlers.staff.profils import ProfilsManager
            prof = ProfilsManager(self.db_manager, self.config)
            await prof.show_admin_profile(update, context, target_staff_id)

        elif data.startswith("unban_from_list_") and can_ban:
            target_id = int(data.replace("unban_from_list_", ""))
            self.db_manager.unban_user(target_id)
            await query.answer("🟢 Compte débanni avec succès !", show_alert=True)
            await self.membres_manager.show_banned_list(update, context, page=0)

        # VIPs (VipManager)
        elif data == "gerer_vips" and privs.get("can_manage_vips", True):
            await query.answer()
            msg, kb = self.interface.get_gerer_vips_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        # Archives générales
        elif data == "admin_global_archives":
            await self.archives_manager.show_archives(update, context, page=0, is_global=True)

        elif data.startswith("global_arch_page_"):
            try:
                page = int(data.replace("global_arch_page_", ""))
            except ValueError:
                page = 0
            await self.archives_manager.show_archives(update, context, page=page, is_global=True)

        elif data.startswith(("contacter_archive_", "unarchive_reussie_", "unarchive_abandon_")):
            await self.archives_manager.handle_archives_callbacks(update, context)

        # Staff
        elif data == "gerer_staff" and privs.get("can_manage_staff", True):
            await query.answer()
            msg, kb = self.interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data.startswith("staff_view_demandes_") and privs.get("can_manage_staff", True):
            parts = data.split("_")
            target_staff_id = int(parts[3])
            page = int(parts[4]) if len(parts) >= 5 else 0
            await self.show_staff_dossiers_page(update, context, target_staff_id, page)

        elif data.startswith("admin_remind_staff_demande_") and privs.get("can_manage_staff", True):
            await self.handle_admin_remind_staff_demande(update, context, data)

        # Admins (Owner only)
        elif data == "gerer_admins" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_gerer_admins_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "menu_channels" and is_owner:
            await self.config_manager.show_channels_menu(update, context)
        elif data.startswith("toggle_allow_") and is_owner:
            key_name = data.replace("toggle_", "")
            await self.config_manager.toggle_channel_setting(update, context, key_name)

        # Délais
        elif data == "menu_delais" and (is_owner or privs.get("can_manage_delais", False)):
            await self.config_manager.show_delais_menu(update, context)
        elif data == "cfg_sub_archive_hours" and (is_owner or privs.get("can_manage_delais", False)):
            await self.config_manager.show_archive_hours_menu(update, context)
        elif data == "cfg_sub_reminder_days" and (is_owner or privs.get("can_manage_delais", False)):
            await self.config_manager.show_reminder_days_menu(update, context)
        elif data == "cfg_sub_payrem_days" and (is_owner or privs.get("can_manage_delais", False)):
            await self.config_manager.show_payment_reminder_days_menu(update, context)
        elif data == "cfg_sub_remun_days" and (is_owner or privs.get("can_manage_delais", False)):
            await self.config_manager.show_remun_expiration_days_menu(update, context)

        elif data.startswith("set_arch_hours_") and (is_owner or privs.get("can_manage_delais", False)):
            try:
                val = int(data.replace("set_arch_hours_", ""))
                self.db_manager.set_auto_archive_hours(val)
                await query.answer(f"✅ Auto-archivage fixé à {val}h !")
                await self.config_manager.show_delais_menu(update, context)
            except Exception:
                await query.answer("❌ Erreur valeur.", show_alert=True)

        elif data.startswith("set_rem_days_") and (is_owner or privs.get("can_manage_delais", False)):
            try:
                val = int(data.replace("set_rem_days_", ""))
                self.db_manager.set_delivery_reminder_days(val)
                await query.answer(f"✅ Relance fixée à {val} jours !")
                await self.config_manager.show_delais_menu(update, context)
            except Exception:
                await query.answer("❌ Erreur valeur.", show_alert=True)

        elif data.startswith("set_payrem_days_") and (is_owner or privs.get("can_manage_delais", False)):
            try:
                val = int(data.replace("set_payrem_days_", ""))
                self.db_manager.set_payment_reminder_days(val)
                await query.answer(f"✅ Rappel impayé fixé à {val} jours !")
                await self.config_manager.show_delais_menu(update, context)
            except Exception:
                await query.answer("❌ Erreur valeur.", show_alert=True)

        elif data.startswith("set_remun_days_") and (is_owner or privs.get("can_manage_delais", False)):
            try:
                val = int(data.replace("set_remun_days_", ""))
                self.db_manager.set_remun_expiration_days(val)
                await query.answer(f"✅ Délai rémunération fixé à {val} jours !")
                await self.config_manager.show_delais_menu(update, context)
            except Exception:
                await query.answer("❌ Erreur valeur.", show_alert=True)

        # Droits staff & admins
        elif data.startswith("perm_staff_") and privs.get("can_manage_staff", True):
            try:
                target_id = int(data.replace("perm_staff_", ""))
                await self.show_staff_permissions_menu(update, context, target_id)
            except Exception:
                pass
        elif data.startswith("set_permstaff_") and privs.get("can_manage_staff", True):
            await self.handle_set_staff_permission(update, context, data)

        elif data.startswith("perm_admin_") and is_owner:
            try:
                target_id = int(data.replace("perm_admin_", ""))
                await self.show_admin_permissions_menu(update, context, target_id)
            except Exception:
                pass
        elif data.startswith("set_permadmin_") and is_owner:
            await self.handle_set_admin_permission(update, context, data)

    # Entrées texte
    async def handle_member_search_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return await self.membres_manager.handle_search_input(update, context)

    async def handle_ban_reason_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return await self.membres_manager.handle_ban_reason_input(update, context)

    async def handle_danger_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return await self.purge_manager.handle_text_input(update, context)

    # Flux VIP
    async def start_add_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.start_add_vip(update, context)

    async def process_vip_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.process_vip_target_user(update, context)

    async def process_vip_duration_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.process_vip_duration_choice(update, context)

    async def start_remove_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.start_remove_vip(update, context)

    async def process_vip_remove_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.process_vip_remove_choice(update, context)

    async def cancel_vip_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.vip_manager.cancel_vip_action(update, context)

    # Supervision dossiers piégeur
    async def show_staff_dossiers_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, staff_id: int, page: int = 0):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = self.db_manager.get_staff_alias(staff_id)
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.user_id, d.prenom, d.nom, d.age, d.localisation,
                           d.instagram, d.snapchat, d.details, d.prioritaire, d.montant, d.statut,
                           d.is_difficile, d.reussie_substatus, d.date_creation, d.date_modification,
                           ds.date_suivi
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours', '🎯 Assignée (VIP)')
                    ORDER BY ds.date_suivi ASC
                    """,
                    (staff_id,),
                )
                dossiers = cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture dossiers staff %s : %s", staff_id, exc)
            dossiers = []

        if not dossiers:
            msg, kb = users_ui.get_staff_no_dossiers_content(alias, staff_id)
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
            return

        total = len(dossiers)
        page = max(0, min(page, total - 1))
        demande = dossiers[page]

        statut_fmt = self.db_manager.format_statut_display(
            demande.get("statut"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus"),
        )

        text, keyboard = users_ui.format_staff_dossier_card(demande, alias, page, total, staff_id, statut_fmt)
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def handle_admin_remind_staff_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        query = update.callback_query
        if not query:
            return

        parts = data.split("_")
        staff_id = int(parts[4])
        demande_id = int(parts[5])
        page = int(parts[6]) if len(parts) >= 7 else 0

        admin_id = update.effective_user.id
        admin_alias = self.db_manager.get_staff_alias(admin_id)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, prenom FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Dossier introuvable.", show_alert=True)
            return

        req_num = dem["id"]
        prenom = html.escape(str(dem.get("prenom") or "la cible"))
        msg_staff, kb_staff = users_ui.format_admin_reminder_message(admin_alias, req_num, prenom, demande_id)

        try:
            await context.bot.send_message(chat_id=staff_id, text=msg_staff, parse_mode="HTML", reply_markup=kb_staff)
            await query.answer(f"✅ Relance envoyée au piégeur pour le dossier #{req_num} !", show_alert=True)
        except Exception as exc:
            logger.error("Erreur envoi relance admin au piégeur %s : %s", staff_id, exc)
            await query.answer("❌ Erreur lors de la transmission du rappel.", show_alert=True)

        await self.show_staff_dossiers_page(update, context, staff_id, page)

    # Permissions staff & admin
    async def show_staff_permissions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, staff_id: int):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = self.db_manager.get_staff_alias(staff_id)
        perms = self.db_manager.get_staff_permissions(staff_id)
        text, keyboard = users_ui.build_staff_permissions_menu_content(staff_id, alias, perms)
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def handle_set_staff_permission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        query = update.callback_query
        if not query:
            return

        try:
            parts = data.split("_")
            staff_id = int(parts[2])
            action = parts[3]

            if action == "trial" and len(parts) >= 5 and parts[4] == "toggle":
                new_trial = not self.db_manager.is_staff_trial(staff_id)
                self.db_manager.set_staff_trial(staff_id, new_trial)
                await query.answer(f"🧪 Mode à l'essai {'activé' if new_trial else 'désactivé'} !")
                await self.show_staff_permissions_menu(update, context, staff_id)
                return

            if action == "selfprefs" and len(parts) >= 5 and parts[4] == "toggle":
                self.db_manager.toggle_staff_self_prefs(staff_id)
                now_allowed = self.db_manager.can_staff_edit_preferences(staff_id)
                await query.answer(f"Modification des préférences {'débloquée' if now_allowed else 'verrouillée'} !")
                await self.show_staff_permissions_menu(update, context, staff_id)
                return

            cle = f"perm_{action}"
            valeur = "_".join(parts[4:])
            self.db_manager.update_staff_permission(staff_id, cle, valeur)
            await query.answer("✅ Droits staff mis à jour")
            await self.show_staff_permissions_menu(update, context, staff_id)
        except Exception as exc:
            logger.error("Erreur mise à jour permission staff : %s", exc)
            await query.answer("❌ Erreur.", show_alert=True)

    async def show_admin_permissions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = self.db_manager.get_staff_alias(admin_id)
        privs = self.db_manager.get_admin_privileges(admin_id)
        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        is_primary_owner = (int(admin_id) == int(primary_owner_id))

        text, keyboard = users_ui.build_admin_permissions_menu_content(admin_id, alias, privs, is_primary_owner)
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def handle_set_admin_permission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        try:
            parts = data.split("_")
            admin_id = int(parts[2])
            flag = "_".join(parts[3:])

            if flag not in ALLOWED_ADMIN_PERMISSIONS:
                await query.answer("❌ Permission invalide.", show_alert=True)
                return

            primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
            if int(admin_id) == int(primary_owner_id) and flag == "is_owner":
                await query.answer("❌ Impossible de modifier le rôle du propriétaire principal.", show_alert=True)
                return

            self.db_manager.toggle_admin_privilege(admin_id, flag)
            self.config.reload_roles()
            self.db_manager.clear_cache(f"vip_{admin_id}")
            await query.answer("✅ Droits admin mis à jour !")
            await self.show_admin_permissions_menu(update, context, admin_id)
        except Exception as exc:
            logger.error("Erreur bascule droit admin : %s", exc)
            await query.answer("❌ Erreur SQL.", show_alert=True)

    # Délégation gestion staff
    async def staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.staff_ajouter(update, context)

    async def traiter_staff_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.traiter_staff_ajouter(update, context)

    async def handle_recruit_config_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.handle_recruit_config_callback(update, context)

    async def cancel_staff_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.cancel_staff_add(update, context)

    async def staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.staff_supprimer(update, context)

    async def traiter_staff_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.traiter_staff_supprimer(update, context)

    async def confirmer_staff_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.confirmer_staff_suppression(update, context)

    async def cancel_staff_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        return await self.staff_manager.cancel_staff_remove(update, context)

    # Nomination / Révocation Managers
    async def admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END
        await query.answer()

        text, kb = users_ui.get_admin_add_prompt_content()
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)
        return self.WAITING_ADMIN_ID

    async def traiter_admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.WAITING_ADMIN_ID

        user_id = update.effective_user.id
        if not self.config.is_owner(user_id):
            return ConversationHandler.END

        saisie = update.message.text.strip().replace("@", "")
        try:
            with self.db_manager.get_cursor() as cursor:
                if saisie.isdigit():
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (int(saisie),))
                else:
                    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (saisie,))
                u_data = cursor.fetchone()

            if not u_data:
                await update.message.reply_text("❌ Utilisateur introuvable (/start obligatoire).")
                return self.WAITING_ADMIN_ID

            target_id = int(u_data["user_id"])
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (target_id,))
                if cursor.fetchone():
                    await update.message.reply_text("⚠️ Cet utilisateur est déjà Administrateur.")
                    return self.WAITING_ADMIN_ID

            base_alias = u_data.get("first_name") or u_data.get("username") or f"Admin{target_id}"
            alias = str(base_alias)[:20]

            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO admins (
                        user_id, alias, is_owner, is_vip, can_manage_staff, can_manage_vips,
                        can_view_stats, can_manage_delais, can_view_archives, can_monitor_staff,
                        can_ban_users, can_edit_others_demandes, added_by, date_added
                    ) VALUES (%s, %s, FALSE, FALSE, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE, FALSE, %s, NOW())
                    """,
                    (target_id, alias, user_id),
                )

            self.config.add_admin(target_id)
            text, kb = users_ui.build_admin_add_success_content(alias, target_id)
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
            return ConversationHandler.END
        except Exception as exc:
            logger.error("Erreur ajout admin : %s", exc)
            await update.message.reply_text("❌ Erreur technique.")
            return ConversationHandler.END

    async def cancel_admin_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
            msg, kb = self.interface.get_gerer_admins_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
        return ConversationHandler.END

    async def admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END
        await query.answer()

        try:
            primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT user_id, alias, is_owner FROM admins WHERE user_id != %s AND user_id != %s",
                    (update.effective_user.id, primary_owner_id),
                )
                admins = cursor.fetchall()

            text, kb = users_ui.build_admin_remove_list_content(admins)
            if not admins:
                await self._safe_edit_or_send(query, context, text, reply_markup=kb)
                return ConversationHandler.END

            context.user_data["admin_remove_list"] = admins
            await self._safe_edit_or_send(query, context, text, reply_markup=kb)
            return self.WAITING_ADMIN_REMOVE
        except Exception as exc:
            logger.error("Erreur suppression admin : %s", exc)
            return ConversationHandler.END

    async def traiter_admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.WAITING_ADMIN_REMOVE

        choix = update.message.text.strip()
        admins = context.user_data.get("admin_remove_list", [])

        if not choix.isdigit() or int(choix) < 1 or int(choix) > len(admins):
            await update.message.reply_text(f"❌ Numéro hors plage (1 à {len(admins)}) :")
            return self.WAITING_ADMIN_REMOVE

        selected = admins[int(choix) - 1]
        context.user_data["target_admin_to_remove"] = selected
        text, kb = users_ui.get_admin_remove_confirmation_content(selected.get("alias") or selected["user_id"])
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        return self.WAITING_ADMIN_CONFIRMATION

    async def confirmer_admin_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return ConversationHandler.END
        await query.answer()

        selected = context.user_data.pop("target_admin_to_remove", None)
        context.user_data.pop("admin_remove_list", None)
        if not selected:
            return ConversationHandler.END

        target_id = selected["user_id"]
        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        if int(target_id) == int(primary_owner_id):
            await query.answer("❌ Impossible de révoquer le propriétaire principal.", show_alert=True)
            return ConversationHandler.END

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (target_id,))
            self.config.reload_roles()
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_admins")]])
            await self._safe_edit_or_send(query, context, "✅ <b>Administrateur révoqué.</b>", reply_markup=kb)
            return ConversationHandler.END
        except Exception as exc:
            logger.error("Erreur révocation admin : %s", exc)
            return ConversationHandler.END

    async def cancel_admin_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        context.user_data.pop("target_admin_to_remove", None)
        context.user_data.pop("admin_remove_list", None)
        if query:
            await query.answer()
            msg, kb = self.interface.get_gerer_admins_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
        return ConversationHandler.END