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

logger = logging.getLogger(__name__)

# Liste blanche stricte des permissions admin modifiables dans la table 'admins'
ALLOWED_ADMIN_PERMISSIONS = frozenset({
    "can_manage_staff",
    "can_manage_vips",
    "can_view_stats",
    "can_manage_delais",
    "can_view_archives",
    "can_monitor_staff",
    "is_vip",
    "is_owner",
})


class AdminHandlers:
    """Gestionnaire des opérations système, de la gouvernance (Admins/Staff), des stats et des VIPs."""

    # États pour l'ajout/suppression Staff
    WAITING_STAFF_ID = 1
    WAITING_STAFF_CONFIG = 2
    WAITING_STAFF_REMOVE = 3
    WAITING_STAFF_CONFIRMATION = 4

    # États pour l'ajout/suppression Admin (Owner only)
    WAITING_ADMIN_ID = 5
    WAITING_ADMIN_REMOVE = 6
    WAITING_ADMIN_CONFIRMATION = 7

    # États pour la gestion VIP
    WAITING_VIP_USER = 10
    WAITING_VIP_DURATION = 11
    WAITING_VIP_REMOVE = 12

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)
        self.alias_manager = AliasManager(db_manager, config)
        self.archives_manager = ArchivesManager(db_manager, config)

        # Sous-gestionnaires dédiés
        self.config_manager = ConfigManager(db_manager, config)
        self.stats_manager = StatsManager(db_manager, config)
        self.bot_manager = BotManager(db_manager, config, self.interface)
        self.staff_manager = StaffManager(db_manager, config, self.interface)

        logger.info("AdminHandlers initialisé avec architecture RBAC, support Archives Générales et Surveillance Staff.")

    async def _safe_edit_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
        """Met à jour le message ou envoie un message texte propre."""
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
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )

    # ==================== MAINTENANCE ET SERVICE ====================

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
            # Appels asynchrones non-bloquants
            storage_before = await check_storage_usage()
            await daily_maintenance(self.db_manager)
            storage_after = await check_storage_usage()

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM demandes")
                demandes_count = cursor.fetchone()["count"]

                cursor.execute("SELECT COUNT(*) AS count FROM archives")
                archives_count = cursor.fetchone()["count"]

            economie = max(0.0, storage_before - storage_after)
            message = (
                "✅ <b>Maintenance terminée avec succès</b>\n\n"
                "💾 <b>Stockage local :</b>\n"
                f"• Avant : {storage_before:.1f} Mo\n"
                f"• Après : {storage_after:.1f} Mo\n"
                f"• Gain : {economie:.1f} Mo\n\n"
                "📊 <b>Base de données :</b>\n"
                f"• Demandes actives : {demandes_count}\n"
                f"• Demandes archivées : {archives_count}\n\n"
                "🧹 Cache mémoire purgé et index optimisés."
            )

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")
            ]])

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
        """Active l'acceptation globale des demandes."""
        await self.bot_manager.bot_on(update, context)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Demande confirmation avant suspension du service."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        await query.answer()
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer la suspension", callback_data="confirm_bot_off"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_bot_off")
            ]
        ])
        text = (
            "⚠️ <b>Suspension des nouvelles demandes</b>\n\n"
            "Les utilisateurs ne pourront plus créer de demandes jusqu'à la réactivation.\n"
            "Confirmez-vous cette action ?"
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=keyboard)

    async def confirmer_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre la suspension."""
        await self.bot_manager.bot_off(update, context)

    async def cancel_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return
        await query.answer()
        message, keyboard = self.interface.get_gerer_bot_menu()
        await self._safe_edit_or_send(query, context, message, reply_markup=keyboard)

    async def toggle_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande rapide /toggle_demandes."""
        if not update.message or not update.effective_user:
            return

        if not self.config.is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Commande réservée aux propriétaires.")
            return

        if self.config.are_demandes_enabled():
            self.config.disable_demandes()
            await update.message.reply_text("🚫 <b>Service suspendu :</b> Création bloquée.", parse_mode="HTML")
        else:
            self.config.enable_demandes()
            await update.message.reply_text("✅ <b>Service actif :</b> Création autorisée.", parse_mode="HTML")

    # ==================== ROUTAGE CALLBACKS ADMIN & OWNER ====================

    async def handle_admin_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguille toutes les actions d'administration (Owner et Managers)."""
        query = update.callback_query
        if not query:
            return

        user_id = update.effective_user.id
        data = query.data or ""

        # 1. Gestion des modes de paiement acceptés
        if data == "staff_payment_settings" and (self.config.is_staff(user_id) or self.config.is_admin(user_id) or self.config.is_owner(user_id)):
            await query.answer()
            text_menu, kb_menu = self.interface.get_staff_payment_settings_menu(user_id)
            await self._safe_edit_or_send(query, context, text_menu, reply_markup=kb_menu)
            return

        if data.startswith("toggle_pay_staff_") and (self.config.is_staff(user_id) or self.config.is_admin(user_id) or self.config.is_owner(user_id)):
            method = data.replace("toggle_pay_staff_", "")
            ok, msg_err = self.db_manager.toggle_staff_payment_method(user_id, method)
            if not ok:
                await query.answer(f"⚠️ {msg_err}", show_alert=True)
                return
            await query.answer("✅ Option mise à jour !")
            text_menu, kb_menu = self.interface.get_staff_payment_settings_menu(user_id)
            await self._safe_edit_or_send(query, context, text_menu, reply_markup=kb_menu)
            return

        # 2. Vérification des droits administrateur pour le reste
        if not self.config.is_admin(user_id):
            await query.answer("❌ Accès non autorisé.", show_alert=True)
            return

        privs = self.db_manager.get_admin_privileges(user_id)
        is_owner = privs.get("is_owner", False) or self.config.is_owner(user_id)

        # Actions Service (Owner only)
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

        # Adhésion Obligatoire au Groupe (Owner only)
        elif data == "menu_cfg_group" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_group_subscription_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "toggle_cfg_group_enabled" and is_owner:
            new_state = self.db_manager.toggle_required_group_enabled()
            status_txt = "activée" if new_state else "désactivée"
            await query.answer(f"Obligation d'adhésion {status_txt} !")
            msg, kb = self.interface.get_group_subscription_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "set_cfg_group_id" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "required_group_id"
            await query.edit_message_text(
                "🆔 <b>Entrez le Chat ID numérique du groupe obligatoire</b> (ex: <code>-1001234567890</code>) :\n\n"
                "<i>Assurez-vous que le bot est bien présent dans ce groupe en tant qu'administrateur.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_group")]])
            )

        elif data == "set_cfg_group_link" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "group_subscription_link"
            await query.edit_message_text(
                "🔗 <b>Entrez le nom du bot ou l'URL t.me d'inscription</b> (ex: <code>@parascriptionbot</code> ou <code>https://t.me/...</code>) :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_group")]])
            )

        # Contact Support (Owner only)
        elif data == "menu_cfg_support" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_support_config_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data == "set_cfg_support_contact" and is_owner:
            await query.answer()
            context.user_data["waiting_owner_input"] = "support_contact"
            await query.edit_message_text(
                "🎧 <b>Entrez le @username ou le lien du support</b> (ex: <code>@ContactParaBot</code> ou <code>https://t.me/ContactParaBot</code>) :",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_cfg_support")]])
            )

        # ==================== ZONE DE DANGER (PURGES - OWNER ONLY) ====================
        elif data == "menu_danger_zone" and is_owner:
            await query.answer()
            context.user_data.pop("waiting_danger_confirmation", None)
            context.user_data.pop("pending_danger_target", None)
            msg, kb = self.interface.get_danger_zone_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        elif data.startswith("danger_purge_") and is_owner:
            await query.answer()
            target = data.replace("danger_purge_", "")
            context.user_data["pending_danger_target"] = target

            labels = {
                "archives": "des archives",
                "demandes": "des demandes",
                "users": "des utilisateurs",
                "staff": "du staff",
                "admins": "des administrateurs",
                "totale": "TOTALE (de toute la base de données)",
            }
            libelle = labels.get(target, target)

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ OUI, continuer", callback_data=f"danger_confirm_yes_{target}")],
                [InlineKeyboardButton("❌ NON, annuler", callback_data="menu_danger_zone")]
            ])
            text_confirm = (
                f"🚨 <b>CONFIRMATION REQUISE</b>\n\n"
                f"Êtes-vous sûr de vouloir effacer la table <b>{libelle}</b> ?\n\n"
                "Cette action est <b>absolument irréversible</b>."
            )
            await self._safe_edit_or_send(query, context, text_confirm, reply_markup=kb)

        elif data.startswith("danger_confirm_yes_") and is_owner:
            await query.answer()
            target = data.replace("danger_confirm_yes_", "")
            context.user_data["waiting_danger_confirmation"] = target

            text_step2 = (
                "✍️ <b>Dernière étape de sécurité</b>\n\n"
                f"Cible : <code>{target}</code>\n\n"
                "Pour valider définitivement la suppression, veuillez <b>taper exactement au clavier le mot</b> :\n"
                "<code>Effacer</code>\n\n"
                "<i>(Envoyez n'importe quel autre message ou cliquez ci-dessous pour annuler).</i>"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_danger_zone")]])
            await self._safe_edit_or_send(query, context, text_step2, reply_markup=kb)

        # Statistiques
        elif data == "bot_stats" and privs.get("can_view_stats", True):
            await self.stats_manager.show_general_stats(update, context)

        # VIPs
        elif data == "gerer_vips" and privs.get("can_manage_vips", True):
            await query.answer()
            msg, kb = self.interface.get_gerer_vips_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        # Archives Générales (Owner ou Admin avec permission)
        elif data == "admin_global_archives":
            await self.archives_manager.show_archives(update, context, page=0, is_global=True)

        elif data.startswith("global_arch_page_"):
            try:
                page = int(data.replace("global_arch_page_", ""))
            except ValueError:
                page = 0
            await self.archives_manager.show_archives(update, context, page=page, is_global=True)

        # Gestion Staff
        elif data == "gerer_staff" and privs.get("can_manage_staff", True):
            await query.answer()
            msg, kb = self.interface.get_gerer_staff_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        # Consultation des dossiers d'un piégeur spécifique
        elif data.startswith("staff_view_demandes_") and privs.get("can_manage_staff", True):
            parts = data.split("_")
            target_staff_id = int(parts[3])
            page = int(parts[4]) if len(parts) >= 5 else 0
            await self.show_staff_dossiers_page(update, context, target_staff_id, page)

        # Relance d'un piégeur par un admin sur un dossier
        elif data.startswith("admin_remind_staff_demande_") and privs.get("can_manage_staff", True):
            await self.handle_admin_remind_staff_demande(update, context, data)

        # Gestion Admins (Owner only)
        elif data == "gerer_admins" and is_owner:
            await query.answer()
            msg, kb = self.interface.get_gerer_admins_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)

        # Menus Canaux & Orientations combinés (Owner only)
        elif data == "menu_channels" and is_owner:
            await self.config_manager.show_channels_menu(update, context)
        elif data.startswith("toggle_allow_") and is_owner:
            key_name = data.replace("toggle_", "")
            await self.config_manager.toggle_channel_setting(update, context, key_name)

        # Délais, Auto-Archivage et Rappels
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

        # Permissions Staff (Réseau, Type, Orientation, Verrouillage Préférences, Mode à l'essai)
        elif data.startswith("perm_staff_") and privs.get("can_manage_staff", True):
            try:
                target_id = int(data.replace("perm_staff_", ""))
                await self.show_staff_permissions_menu(update, context, target_id)
            except Exception:
                pass
        elif data.startswith("set_permstaff_") and privs.get("can_manage_staff", True):
            await self.handle_set_staff_permission(update, context, data)

        # Permissions Admin (Owner only)
        elif data.startswith("perm_admin_") and is_owner:
            try:
                target_id = int(data.replace("perm_admin_", ""))
                await self.show_admin_permissions_menu(update, context, target_id)
            except Exception:
                pass
        elif data.startswith("set_permadmin_") and is_owner:
            await self.handle_set_admin_permission(update, context, data)

    # ==================== CONSULTATION DES DOSSIERS D'UN PIÉGEUR PAR L'ADMIN ====================

    async def show_staff_dossiers_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, staff_id: int, page: int = 0):
        """Affiche les demandes actives d'un membre du staff fiche par fiche avec options de relance."""
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = html.escape(str(self.db_manager.get_staff_alias(staff_id)))

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
                    (staff_id,)
                )
                dossiers = cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur lecture dossiers staff %s : %s", staff_id, exc)
            dossiers = []

        if not dossiers:
            msg = (
                f"📂 <b>Dossiers de {alias}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📭 Cet opérateur n'a aucune demande en cours de traitement pour le moment."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Contacter le piégeur", callback_data=f"admin_contact_staff_{staff_id}")],
                [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")]
            ])
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
            return

        total = len(dossiers)
        page = max(0, min(page, total - 1))
        demande = dossiers[page]
        demande_id = demande["id"]
        req_num = demande.get("request_number", demande_id)

        nom_cible = f"{html.escape(str(demande.get('prenom') or ''))} {html.escape(str(demande.get('nom') or ''))}".strip() or "Non renseigné"
        statut_fmt = self.db_manager.format_statut_display(
            demande.get("statut"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus")
        )

        prio_tag = f"💎 Prioritaire ({float(demande.get('montant') or 0.0):.2f} €)" if demande.get("prioritaire") else "📝 Standard"
        date_prise = str(demande.get("date_suivi") or demande.get("date_creation"))[:16]

        text = (
            f"📂 <b>Dossiers de {alias} ({page + 1}/{total})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Dossier :</b> #{req_num}\n"
            f"• <b>Cible :</b> <b>{nom_cible}</b>\n"
            f"• <b>Formule :</b> {prio_tag}\n"
            f"• <b>Statut actuel :</b> <code>{html.escape(str(statut_fmt))}</code>\n"
            f"• <b>Prise en charge :</b> <i>{date_prise}</i>\n"
            f"• <b>Demandeur :</b> <code>{demande['user_id']}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Actions administratives sur ce dossier :</i>"
        )

        buttons = [
            [InlineKeyboardButton("🔔 RELANCER LE PIÉGEUR", callback_data=f"admin_remind_staff_demande_{staff_id}_{demande_id}_{page}")],
            [
                InlineKeyboardButton("💬 CONTACTER LE PIÉGEUR", callback_data=f"admin_contact_staff_{staff_id}"),
                InlineKeyboardButton("👤 CONTACTER LE CLIENT", callback_data=f"contacter_{demande_id}")
            ]
        ]

        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"staff_view_demandes_{staff_id}_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"staff_view_demandes_{staff_id}_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_staff")])

        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(buttons))

    async def handle_admin_remind_staff_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Envoie un rappel ciblé de l'administrateur au piégeur pour un dossier précis."""
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
            cursor.execute("SELECT id, request_number, prenom FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Dossier introuvable.", show_alert=True)
            return

        req_num = dem.get("request_number", demande_id)
        prenom = html.escape(str(dem.get("prenom") or "la cible"))

        msg_staff = (
            f"🔔 <b>RAPPEL DE LA DIRECTION / ADMINISTRATION</b>\n\n"
            f"L'administrateur <b>{html.escape(str(admin_alias))}</b> vous relance concernant le dossier <b>#{req_num}</b> ({prenom}).\n\n"
            "👉 Merci de faire le point sur ce dossier dans vos suivis et de finaliser la démarche."
        )
        kb_staff = InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Ouvrir la fiche du dossier", callback_data=f"retour_texte_{demande_id}")],
            [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
        ])

        try:
            await context.bot.send_message(chat_id=staff_id, text=msg_staff, parse_mode="HTML", reply_markup=kb_staff)
            await query.answer(f"✅ Relance envoyée au piégeur pour le dossier #{req_num} !", show_alert=True)
        except Exception as exc:
            logger.error("Erreur envoi relance admin au piégeur %s : %s", staff_id, exc)
            await query.answer("❌ Erreur lors de la transmission du rappel.", show_alert=True)

        await self.show_staff_dossiers_page(update, context, staff_id, page)

    # ==================== PERMISSIONS STAFF (OPÉRATEURS) ====================

    async def show_staff_permissions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, staff_id: int):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = html.escape(str(self.db_manager.get_staff_alias(staff_id)))
        perms = self.db_manager.get_staff_permissions(staff_id)
        reseau = perms.get("perm_reseaux", "all")
        typ = perms.get("perm_type", "all")
        ori = perms.get("perm_orientation", "all")
        allow_self = bool(perms.get("allow_self_prefs", True))
        is_trial = bool(perms.get("is_trial", False))

        b_res_all = "✅ Tous réseaux" if reseau == "all" else "Tous réseaux"
        b_res_insta = "✅ Insta seul" if reseau == "insta" else "Insta seul"
        b_res_snap = "✅ Snap seul" if reseau == "snap" else "Snap seul"

        b_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
        b_typ_prio = "✅ 💎 Payantes" if typ == "prio_only" else "💎 Payantes"
        b_typ_std = "✅ 📝 Gratuites" if typ == "standard_only" else "📝 Gratuites"

        b_ori_all = "✅ 🔄 Tous / Bi" if ori in ("all", "bi") else "🔄 Tous / Bi"
        b_ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
        b_ori_g = "✅ Gay" if ori == "gay" else "Gay"

        trial_btn_label = "🧪 À l'essai : ✅ OUI" if is_trial else "🧪 À l'essai : ❌ NON"
        self_prefs_label = "🔒 Bloquer ses réglages cibles" if allow_self else "🔓 Débloquer ses réglages cibles"

        keyboard = [
            [
                InlineKeyboardButton(b_res_all, callback_data=f"set_permstaff_{staff_id}_reseaux_all"),
                InlineKeyboardButton(b_res_insta, callback_data=f"set_permstaff_{staff_id}_reseaux_insta"),
                InlineKeyboardButton(b_res_snap, callback_data=f"set_permstaff_{staff_id}_reseaux_snap"),
            ],
            [
                InlineKeyboardButton(b_typ_all, callback_data=f"set_permstaff_{staff_id}_type_all"),
                InlineKeyboardButton(b_typ_prio, callback_data=f"set_permstaff_{staff_id}_type_prio_only"),
                InlineKeyboardButton(b_typ_std, callback_data=f"set_permstaff_{staff_id}_type_standard_only"),
            ],
            [
                InlineKeyboardButton(b_ori_h, callback_data=f"set_permstaff_{staff_id}_orientation_hetero"),
                InlineKeyboardButton(b_ori_g, callback_data=f"set_permstaff_{staff_id}_orientation_gay"),
                InlineKeyboardButton(b_ori_all, callback_data=f"set_permstaff_{staff_id}_orientation_all"),
            ],
            [
                InlineKeyboardButton(self_prefs_label, callback_data=f"set_permstaff_{staff_id}_selfprefs_toggle")
            ],
            [
                InlineKeyboardButton(trial_btn_label, callback_data=f"set_permstaff_{staff_id}_trial_toggle")
            ],
            [InlineKeyboardButton("🔙 Équipe Staff", callback_data="gerer_staff")]
        ]

        text = (
            f"🛡️ <b>Permissions Opérateur : {alias}</b>\n"
            f"🆔 ID : <code>{staff_id}</code>\n\n"
            "Ajustez les dossiers auxquels ce membre a accès (Réseaux, Type, Orientation),\n"
            "verrouillez sa capacité à modifier ses préférences, ou réglez sa <b>période d'essai</b> :"
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_set_staff_permission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        query = update.callback_query
        if not query:
            return

        try:
            parts = data.split("_")
            staff_id = int(parts[2])
            action = parts[3]

            if action == "trial" and len(parts) >= 5 and parts[4] == "toggle":
                curr_trial = self.db_manager.is_staff_trial(staff_id)
                new_trial = not curr_trial
                self.db_manager.set_staff_trial(staff_id, new_trial)
                status_txt = "activé" if new_trial else "désactivé"
                await query.answer(f"🧪 Mode à l'essai {status_txt} !")
                await self.show_staff_permissions_menu(update, context, staff_id)
                return

            if action == "selfprefs" and len(parts) >= 5 and parts[4] == "toggle":
                self.db_manager.toggle_staff_self_prefs(staff_id)
                now_allowed = self.db_manager.can_staff_edit_preferences(staff_id)
                status_txt = "débloquée (autonome)" if now_allowed else "verrouillée (bloqué)"
                await query.answer(f"Modification des préférences {status_txt} !")
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

    # ==================== PERMISSIONS ADMIN (MANAGERS & CO-OWNERS) ====================

    async def show_admin_permissions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int):
        query = update.callback_query
        if not query:
            return
        await query.answer()

        alias = html.escape(str(self.db_manager.get_staff_alias(admin_id)))
        privs = self.db_manager.get_admin_privileges(admin_id)

        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        is_primary_owner = (int(admin_id) == int(primary_owner_id))

        st_staff = "✅ OUI" if privs.get("can_manage_staff") else "❌ NON"
        st_vips = "✅ OUI" if privs.get("can_manage_vips") else "❌ NON"
        st_stats = "✅ OUI" if privs.get("can_view_stats") else "❌ NON"
        st_delais = "✅ OUI" if privs.get("can_manage_delais") else "❌ NON"
        st_archives = "✅ OUI" if privs.get("can_view_archives") else "❌ NON"
        st_monitor = "✅ OUI" if privs.get("can_monitor_staff") else "❌ NON"
        st_vip_status = "✅ OUI" if privs.get("is_vip") else "❌ NON"
        st_owner = "👑 CO-GÉRANT" if privs.get("is_owner") else "🛡️ MANAGER"

        keyboard = [
            [
                InlineKeyboardButton(f"Gérer Staff : {st_staff}", callback_data=f"set_permadmin_{admin_id}_can_manage_staff"),
                InlineKeyboardButton(f"Gérer VIPs : {st_vips}", callback_data=f"set_permadmin_{admin_id}_can_manage_vips"),
            ],
            [
                InlineKeyboardButton(f"Voir Stats : {st_stats}", callback_data=f"set_permadmin_{admin_id}_can_view_stats"),
                InlineKeyboardButton(f"Régler Délais : {st_delais}", callback_data=f"set_permadmin_{admin_id}_can_manage_delais"),
            ],
            [
                InlineKeyboardButton(f"Archives Générales : {st_archives}", callback_data=f"set_permadmin_{admin_id}_can_view_archives"),
                InlineKeyboardButton(f"Surveillance Staff : {st_monitor}", callback_data=f"set_permadmin_{admin_id}_can_monitor_staff"),
            ],
            [
                InlineKeyboardButton(f"⭐ Accès VIP : {st_vip_status}", callback_data=f"set_permadmin_{admin_id}_is_vip"),
            ],
        ]

        if not is_primary_owner:
            keyboard.append([
                InlineKeyboardButton(f"Rôle Suprême : {st_owner}", callback_data=f"set_permadmin_{admin_id}_is_owner"),
            ])

        keyboard.append([InlineKeyboardButton("🔙 Liste Managers", callback_data="gerer_admins")])

        text = (
            f"⚙️ <b>Droits Administrateur : {alias}</b>\n"
            f"🆔 ID : <code>{admin_id}</code>\n\n"
            + ("⚠️ <i>Ceci est le Propriétaire principal (Intouchable).</i>\n\n" if is_primary_owner else "")
            + "Activez ou désactivez les responsabilités et privilèges de ce compte :"
        )
        await self._safe_edit_or_send(query, context, text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_set_admin_permission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        try:
            parts = data.split("_")
            admin_id = int(parts[2])
            flag = "_".join(parts[3:])

            # Validation stricte par liste blanche
            if flag not in ALLOWED_ADMIN_PERMISSIONS:
                logger.warning("Tentative de modification d'une permission admin invalide : '%s' par user %s", flag, update.effective_user.id)
                await query.answer("❌ Permission invalide.", show_alert=True)
                return

            primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
            if int(admin_id) == int(primary_owner_id) and flag == "is_owner":
                await query.answer("❌ Impossible de modifier le rôle du propriétaire principal.", show_alert=True)
                return

            with self.db_manager.transaction() as cursor:
                cursor.execute(f"UPDATE admins SET `{flag}` = NOT `{flag}` WHERE user_id = %s", (admin_id,))

            self.config.reload_roles()
            self.db_manager.clear_cache(f"vip_{admin_id}")
            await query.answer("✅ Droits admin mis à jour !")
            await self.show_admin_permissions_menu(update, context, admin_id)
        except Exception as exc:
            logger.error("Erreur bascule droit admin : %s", exc)
            await query.answer("❌ Erreur SQL.", show_alert=True)

    # ==================== RECRUTEMENT / RÉVOCATION STAFF ====================

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

    # ==================== NOMINATION / RÉVOCATION ADMINS (OWNER ONLY) ====================

    async def admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END
        await query.answer()

        text = (
            "🛡️ <b>Nomination d'un Administrateur (Manager)</b>\n\n"
            "Envoyez l'<b>ID Telegram numérique</b> ou le nom d'utilisateur de la personne :"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")]])
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
                    INSERT INTO admins (user_id, alias, is_owner, is_vip, can_manage_staff, can_manage_vips, can_view_stats, can_manage_delais, can_view_archives, can_monitor_staff, added_by, date_added)
                    VALUES (%s, %s, FALSE, FALSE, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, %s, NOW())
                    """,
                    (target_id, alias, user_id)
                )

            self.config.add_admin(target_id)
            alias_esc = html.escape(alias)

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Régler ses privilèges", callback_data=f"perm_admin_{target_id}")],
                [InlineKeyboardButton("🛡️ Liste Managers", callback_data="gerer_admins")]
            ])
            await update.message.reply_text(f"✅ <b>Manager nommé :</b> <code>{alias_esc}</code> ({target_id})", parse_mode="HTML", reply_markup=kb)
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
                    (update.effective_user.id, primary_owner_id)
                )
                admins = cursor.fetchall()

            if not admins:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")]])
                await self._safe_edit_or_send(query, context, "📭 Aucun administrateur révocable.", reply_markup=kb)
                return ConversationHandler.END

            lines = ["🛡️ <b>Révocation d'un Administrateur</b>\n"]
            for idx, adm in enumerate(admins, 1):
                badge = "👑 [Co-Owner]" if adm.get("is_owner") else "🛡️ [Manager]"
                alias_esc = html.escape(str(adm.get("alias") or adm['user_id']))
                lines.append(f"{idx}. {badge} <b>{alias_esc}</b> (<code>{adm['user_id']}</code>)")

            lines.append("\nEnvoyez le <b>numéro</b> de l'administrateur à révoquer :")
            context.user_data["admin_remove_list"] = admins
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")]])
            await self._safe_edit_or_send(query, context, "\n".join(lines), reply_markup=kb)
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

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer", callback_data="confirm_admin_remove"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
            ]
        ])
        alias_esc = html.escape(str(selected.get("alias") or selected['user_id']))
        await update.message.reply_text(f"⚠️ Retirer les droits administrateur à <b>{alias_esc}</b> ?", parse_mode="HTML", reply_markup=kb)
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
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Liste Managers", callback_data="gerer_admins")]])
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

    # ==================== GESTION DES MEMBRES VIP ====================

    async def start_add_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return ConversationHandler.END
        await query.answer()

        text = "⭐ <b>Promouvoir un Membre VIP</b>\n\nEnvoyez l'<b>ID numérique</b> ou le <b>@username</b> du compte :"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
        await self._safe_edit_or_send(query, context, text, reply_markup=kb)
        return self.WAITING_VIP_USER

    async def process_vip_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.WAITING_VIP_USER

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
                return self.WAITING_VIP_USER

            context.user_data["target_vip_user"] = u_data
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ 1 Mois (30 jours)", callback_data="vip_dur_30")],
                [InlineKeyboardButton("⭐ 3 Mois (90 jours)", callback_data="vip_dur_90")],
                [InlineKeyboardButton("👑 À Vie (Illimité)", callback_data="vip_dur_lifetime")],
                [InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]
            ])
            nom = html.escape(str(u_data.get("first_name") or u_data.get("username") or u_data["user_id"]))
            await update.message.reply_text(f"👤 Cible : <b>{nom}</b>\n\nChoisissez la durée ou tapez le nombre de jours :", parse_mode="HTML", reply_markup=kb)
            return self.WAITING_VIP_DURATION
        except Exception as exc:
            logger.error("Erreur cible VIP : %s", exc)
            return ConversationHandler.END

    async def process_vip_duration_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        target_user = context.user_data.pop("target_vip_user", None)
        if not target_user:
            return ConversationHandler.END

        target_id = target_user["user_id"]
        duration_days = None

        if update.callback_query:
            query = update.callback_query
            await query.answer()
            data = query.data
            if data == "vip_dur_30":
                duration_days = 30
            elif data == "vip_dur_90":
                duration_days = 90
            elif data == "vip_dur_lifetime":
                duration_days = None
        elif update.message and update.message.text:
            text = update.message.text.strip()
            if text.isdigit() and int(text) > 0:
                duration_days = int(text)
            else:
                await update.message.reply_text("❌ Entrez un nombre de jours valide ou utilisez les boutons :")
                context.user_data["target_vip_user"] = target_user
                return self.WAITING_VIP_DURATION

        self.db_manager.set_user_vip(target_id, is_vip=True, duration_days=duration_days)

        try:
            type_str = f"pendant {duration_days} jours" if duration_days else "à vie"
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 <b>Félicitations ! Votre accès VIP ({type_str}) est activé !</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

        dur_txt = f"{duration_days} jours" if duration_days else "À vie"
        succes_msg = f"✅ Statut VIP activé pour {target_user.get('first_name', target_id)} ({dur_txt}) !"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Gestion VIPs", callback_data="gerer_vips")]])

        if update.callback_query:
            await self._safe_edit_or_send(update.callback_query, context, succes_msg, reply_markup=kb)
        elif update.message:
            await update.message.reply_text(succes_msg, parse_mode="HTML", reply_markup=kb)

        return ConversationHandler.END

    async def start_remove_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return ConversationHandler.END
        await query.answer()

        vips = self.db_manager.get_vip_users_list()
        if not vips:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_vips")]])
            await self._safe_edit_or_send(query, context, "📭 Aucun membre VIP actif.", reply_markup=kb)
            return ConversationHandler.END

        lines = ["⭐ <b>Révocation Membre VIP</b>\n"]
        for idx, v in enumerate(vips, 1):
            nom = html.escape(str(v.get("first_name") or "Utilisateur"))
            lines.append(f"{idx}. <b>{nom}</b> (<code>{v['user_id']}</code>)")

        lines.append("\nEnvoyez le <b>numéro</b> de la personne à révoquer :")
        context.user_data["vip_remove_list"] = vips
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
        await self._safe_edit_or_send(query, context, "\n".join(lines), reply_markup=kb)
        return self.WAITING_VIP_REMOVE

    async def process_vip_remove_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return self.WAITING_VIP_REMOVE

        choix = update.message.text.strip()
        vips = context.user_data.pop("vip_remove_list", [])

        if not choix.isdigit() or int(choix) < 1 or int(choix) > len(vips):
            await update.message.reply_text(f"❌ Numéro invalide (1 à {len(vips)}) :")
            context.user_data["vip_remove_list"] = vips
            return self.WAITING_VIP_REMOVE

        selected = vips[int(choix) - 1]
        self.db_manager.set_user_vip(selected["user_id"], is_vip=False)

        await update.message.reply_text(
            f"✅ <b>Statut VIP révoqué pour {selected.get('first_name', selected['user_id'])}.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Gestion VIPs", callback_data="gerer_vips")]])
        )
        return ConversationHandler.END

    async def cancel_vip_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.pop("target_vip_user", None)
        context.user_data.pop("vip_remove_list", None)
        query = update.callback_query
        if query:
            await query.answer()
            msg, kb = self.interface.get_gerer_vips_menu()
            await self._safe_edit_or_send(query, context, msg, reply_markup=kb)
        return ConversationHandler.END