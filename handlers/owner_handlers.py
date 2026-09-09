"""Module de gestion des fonctions réservées au propriétaire (Owner)."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.interface_manager import InterfaceManager
from utils.maintenance import check_storage_usage, daily_maintenance
from .admin.alias import AliasManager

logger = logging.getLogger(__name__)


class OwnerHandlers:
    """Gestionnaire des opérations système, des statistiques, des admins et des membres VIP."""

    WAITING_ADMIN_ID = 1
    WAITING_ADMIN_REMOVE = 2
    WAITING_CONFIRMATION = 3

    # États pour la gestion VIP
    WAITING_VIP_USER = 10
    WAITING_VIP_DURATION = 11
    WAITING_VIP_REMOVE = 12

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)
        self.alias_manager = AliasManager(db_manager, config)
        logger.info("OwnerHandlers initialisé")

    async def run_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Déclenche la routine de purge et d'optimisation."""
        user = update.effective_user
        if not user or not self.config.is_owner(user.id):
            if update.callback_query:
                await update.callback_query.answer("❌ Accès réservé au propriétaire.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Accès non autorisé.")
            return

        if update.callback_query:
            await update.callback_query.edit_message_text("🔧 <b>Maintenance en cours...</b>", parse_mode="HTML")
        else:
            await update.message.reply_text("🔧 <b>Maintenance en cours...</b>", parse_mode="HTML")

        try:
            storage_before = check_storage_usage()
            daily_maintenance(self.db_manager)
            storage_after = check_storage_usage()

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
                InlineKeyboardButton("🔙 Gestion Bot", callback_data="gerer_bot")
            ]])

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message, parse_mode="HTML", reply_markup=keyboard
                )
            else:
                await update.message.reply_text(message, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur maintenance manuelle: %s", exc, exc_info=True)
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Échec lors de la maintenance.")
            else:
                await update.message.reply_text("❌ Échec lors de la maintenance.")

    async def bot_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active l'acceptation globale des nouvelles demandes."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        self.config.enable_demandes()
        message, keyboard = self.interface.get_gerer_bot_menu()
        await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)

    async def bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Demande confirmation avant de couper la création de demandes."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer l'arrêt", callback_data="confirm_bot_off"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_bot_off")
            ]
        ])
        await query.edit_message_text(
            "⚠️ <b>Suspension des nouvelles demandes</b>\n\n"
            "Les utilisateurs ne pourront plus soumettre de formulaires jusqu'à la réactivation.\n"
            "Confirmez-vous cette action ?",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def confirmer_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre la coupure des demandes."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        self.config.disable_demandes()
        message, keyboard = self.interface.get_gerer_bot_menu()
        await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)

    async def cancel_bot_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la coupure et revient au menu de gestion."""
        query = update.callback_query
        if not query:
            return
        message, keyboard = self.interface.get_gerer_bot_menu()
        await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)

    async def toggle_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bascule d'état via commande /toggle_demandes."""
        if not update.message or not update.effective_user:
            return

        if not self.config.is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Commande réservée au propriétaire.")
            return

        if self.config.are_demandes_enabled():
            self.config.disable_demandes()
            await update.message.reply_text("🚫 <b>Service suspendu :</b> Les utilisateurs ne peuvent plus créer de demandes.", parse_mode="HTML")
        else:
            self.config.enable_demandes()
            await update.message.reply_text("✅ <b>Service actif :</b> Les utilisateurs peuvent à nouveau créer des demandes.", parse_mode="HTML")

    async def handle_owner_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguille les boutons du panneau propriétaire."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        data = query.data or ""
        if data == "bot_on":
            await self.bot_on(update, context)
        elif data == "bot_off":
            await self.bot_off(update, context)
        elif data == "confirm_bot_off":
            await self.confirmer_bot_off(update, context)
        elif data == "cancel_bot_off":
            await self.cancel_bot_off(update, context)
        elif data == "maintenance":
            await self.run_maintenance(update, context)
        elif data == "bot_stats":
            await self.show_statistics(update, context)
        elif data == "gerer_vips":
            msg, kb = self.interface.get_gerer_vips_menu()
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
        elif data.startswith("perm_admin_"):
            admin_target_id = int(data.replace("perm_admin_", ""))
            await self.show_admin_permissions_menu(update, context, admin_target_id)
        elif data.startswith("set_perm_"):
            await self.handle_set_permission(update, context, data)
        elif data.startswith("owner_edit_alias_"):
            admin_target_id = int(data.replace("owner_edit_alias_", ""))
            context.user_data["target_alias_user_id"] = admin_target_id
            await self.alias_manager.modifier_alias(update, context)

    # ==================== GESTION DES PERMISSIONS ADMIN ====================

    async def show_admin_permissions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int):
        """Affiche le panneau de contrôle des permissions pour un administrateur spécifique."""
        query = update.callback_query
        if not query:
            return

        alias = self.db_manager.get_admin_alias(admin_id)
        perms = self.db_manager.get_admin_permissions(admin_id)

        reseau = perms.get("perm_reseaux", "all")
        typ = perms.get("perm_type", "all")

        btn_res_all = "✅ Tous réseaux" if reseau == "all" else "Tous réseaux"
        btn_res_insta = "✅ Insta seul" if reseau == "insta" else "Insta seul"
        btn_res_snap = "✅ Snap seul" if reseau == "snap" else "Snap seul"

        btn_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
        btn_typ_prio = "✅ 💎 Payantes" if typ == "prio_only" else "💎 Payantes"
        btn_typ_std = "✅ 📝 Gratuites" if typ == "standard_only" else "📝 Gratuites"

        keyboard = [
            [
                InlineKeyboardButton(btn_res_all, callback_data=f"set_perm_{admin_id}_reseaux_all"),
                InlineKeyboardButton(btn_res_insta, callback_data=f"set_perm_{admin_id}_reseaux_insta"),
                InlineKeyboardButton(btn_res_snap, callback_data=f"set_perm_{admin_id}_reseaux_snap"),
            ],
            [
                InlineKeyboardButton(btn_typ_all, callback_data=f"set_perm_{admin_id}_type_all"),
                InlineKeyboardButton(btn_typ_prio, callback_data=f"set_perm_{admin_id}_type_prio_only"),
                InlineKeyboardButton(btn_typ_std, callback_data=f"set_perm_{admin_id}_type_standard_only"),
            ],
            [
                InlineKeyboardButton(f"🏷️ Renommer {alias}", callback_data=f"owner_edit_alias_{admin_id}")
            ],
            [
                InlineKeyboardButton("🔙 Équipe d'administration", callback_data="gerer_admins")
            ]
        ]

        reseau_desc = {
            "all": "Instagram & Snapchat",
            "insta": "Instagram uniquement (inclut les demandes avec Insta + Snap)",
            "snap": "Snapchat uniquement (inclut les demandes avec Snap + Insta)"
        }.get(reseau, reseau)

        type_desc = {
            "all": "Prioritaires / Payantes et Standards",
            "prio_only": "Uniquement les demandes payantes (💎 Prioritaires)",
            "standard_only": "Uniquement les demandes gratuites (📝 Standards)"
        }.get(typ, typ)

        text = (
            f"🛡️ <b>Permissions Administrateur : {alias}</b>\n"
            f"🆔 ID : <code>{admin_id}</code>\n\n"
            f"🌐 <b>Périmètre réseaux :</b> {reseau_desc}\n"
            f"🎯 <b>Périmètre demandes :</b> {type_desc}\n\n"
            "<i>Cliquez sur un bouton pour modifier instantanément les accès :</i>"
        )

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_set_permission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Bascule une permission en base et rafraîchit la vue."""
        query = update.callback_query
        if not query:
            return

        parts = data.split("_")
        admin_id = int(parts[2])
        cle = f"perm_{parts[3]}"
        valeur = "_".join(parts[4:])

        self.db_manager.update_admin_permission(admin_id, cle, valeur)
        await query.answer("✅ Permission mise à jour")
        await self.show_admin_permissions_menu(update, context, admin_id)

    # ==================== AJOUT D'ADMINISTRATEUR ====================

    async def admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ouvre le formulaire d'ajout d'administrateur."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM admins")
                admin_count = cursor.fetchone()["count"]

            text = (
                "👤 <b>Ajout d'un Administrateur</b>\n\n"
                f"Équipe actuelle : <b>{admin_count}</b> admin(s)\n\n"
                "Envoyez l'<b>ID Telegram numérique</b> (ex: <code>123456789</code>) "
                "ou le nom d'utilisateur de la personne.\n\n"
                "<i>Attention : Le compte doit obligatoirement avoir démarré le bot au moins une fois (/start).</i>"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_add")
            ]])

            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
            return self.WAITING_ADMIN_ID

        except Exception as exc:
            logger.error("Erreur interface ajout admin: %s", exc)
            return ConversationHandler.END

    async def traiter_admin_ajouter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vérifie l'utilisateur, l'ajoute comme admin, notifie en privé et propose de configurer ses droits."""
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
                user_data = cursor.fetchone()

            if not user_data:
                await update.message.reply_text(
                    f"❌ L'utilisateur <code>{saisie}</code> n'est pas enregistré dans la base.\n"
                    "Il doit impérativement lancer /start avec le bot d'abord.",
                    parse_mode="HTML"
                )
                return self.WAITING_ADMIN_ID

            target_id = user_data["user_id"]

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (target_id,))
                if cursor.fetchone():
                    await update.message.reply_text("⚠️ Cet utilisateur est déjà administrateur.")
                    return self.WAITING_ADMIN_ID

                base_alias = user_data.get("first_name") or user_data.get("username") or f"Admin{target_id}"
                alias = base_alias[:20]

                cursor.execute(
                    """
                    INSERT INTO admins (user_id, alias, added_by, perm_reseaux, perm_type, alias_locked, date_added)
                    VALUES (%s, %s, %s, 'all', 'all', FALSE, NOW())
                    """,
                    (target_id, alias, user_id)
                )

            self.config.add_admin(target_id)
            logger.info("Admin ajouté: %s (%s)", target_id, alias)

            try:
                welcome_msg = (
                    "🎉 <b>Bienvenue dans l'équipe d'administration !</b>\n\n"
                    "Le propriétaire vous a accordé les droits d'accès pour traiter et suivre les demandes.\n\n"
                    f"🏷️ <b>Votre alias provisoire :</b> <code>{alias}</code>\n\n"
                    "⚠️ <b>Important :</b> Vous avez la possibilité de choisir votre propre pseudonyme officiel.\n"
                    "<i>Attention : vous ne disposez que d'<b>une seule modification</b>. Une fois validé, il sera verrouillé.</i>\n\n"
                    "Cliquez ci-dessous pour le définir dès maintenant :"
                )
                welcome_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏷️ DÉFINIR MON ALIAS", callback_data="modifier_alias")],
                    [InlineKeyboardButton("🚀 Accéder au menu principal", callback_data="start_menu")]
                ])
                await context.bot.send_message(
                    chat_id=target_id,
                    text=welcome_msg,
                    parse_mode="HTML",
                    reply_markup=welcome_kb
                )
                logger.info("Notification envoyée à l'admin %s", target_id)
            except Exception as notif_err:
                logger.warning("Notification impossible pour l'admin %s : %s", target_id, notif_err)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡️ Régler ses permissions", callback_data=f"perm_admin_{target_id}")],
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            await update.message.reply_text(
                f"✅ <b>Administrateur ajouté avec succès !</b>\n\n"
                f"👤 <b>Nom :</b> {user_data.get('first_name', '')}\n"
                f"🆔 <b>ID :</b> <code>{target_id}</code>\n"
                f"🏷️ <b>Alias provisoire :</b> <code>{alias}</code>\n\n"
                "Vous pouvez configurer ses permissions de traitement ci-dessous :",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur enregistrement admin: %s", exc, exc_info=True)
            await update.message.reply_text("❌ Une erreur technique est survenue lors de l'ajout.")
            return ConversationHandler.END

    async def cancel_admin_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule l'ajout d'administrateur."""
        query = update.callback_query
        if query:
            message, keyboard = self.interface.get_gerer_admins_menu()
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
        return ConversationHandler.END

    # ==================== SUPPRESSION D'ADMINISTRATEUR ====================

    async def admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des administrateurs révocables."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, alias, date_added
                    FROM admins
                    WHERE user_id != %s
                    ORDER BY date_added DESC
                    """,
                    (update.effective_user.id,)
                )
                admins = cursor.fetchall()

            if not admins:
                await query.edit_message_text(
                    "👥 <b>Révocation d'Administrateur</b>\n\n"
                    "Aucun administrateur supplémentaire n'est configuré.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Retour", callback_data="gerer_admins")
                    ]])
                )
                return ConversationHandler.END

            lines = [
                "👥 <b>Révocation d'Administrateur</b>\n",
                f"Administrateurs révocables : <b>{len(admins)}</b>\n"
            ]
            for idx, adm in enumerate(admins, 1):
                date_str = str(adm.get("date_added", ""))[:10]
                lines.append(f"{idx}. <b>{adm['alias']}</b> — ID: <code>{adm['user_id']}</code> [{date_str}]")

            lines.append("\nEnvoyez le <b>numéro</b> de l'administrateur à révoquer :")

            context.user_data["admins_list"] = admins
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
            ]])

            await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
            return self.WAITING_ADMIN_REMOVE

        except Exception as exc:
            logger.error("Erreur ouverture suppression admin: %s", exc, exc_info=True)
            return ConversationHandler.END

    async def traiter_admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide le choix de l'administrateur à supprimer et demande confirmation."""
        if not update.message or not update.message.text:
            return self.WAITING_ADMIN_REMOVE

        if not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        choix = update.message.text.strip()
        admins_list = context.user_data.get("admins_list", [])

        if not choix.isdigit():
            await update.message.reply_text("❌ Veuillez saisir un numéro valide de la liste :")
            return self.WAITING_ADMIN_REMOVE

        idx = int(choix) - 1
        if idx < 0 or idx >= len(admins_list):
            await update.message.reply_text(f"❌ Numéro invalide. Choisissez entre 1 et {len(admins_list)} :")
            return self.WAITING_ADMIN_REMOVE

        selected = admins_list[idx]
        context.user_data["admin_to_remove"] = selected

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Confirmer la révocation", callback_data="confirm_admin_remove"),
                InlineKeyboardButton("❌ Annuler", callback_data="cancel_admin_remove")
            ]
        ])

        await update.message.reply_text(
            f"⚠️ <b>Confirmation de révocation</b>\n\n"
            f"Voulez-vous vraiment retirer les droits administrateur à :\n"
            f"• <b>Alias :</b> {selected['alias']}\n"
            f"• <b>ID :</b> <code>{selected['user_id']}</code> ?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return self.WAITING_CONFIRMATION

    async def confirmer_admin_suppression(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Supprime l'administrateur de la base de données et du cache."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        selected = context.user_data.pop("admin_to_remove", None)
        context.user_data.pop("admins_list", None)

        if not selected:
            await query.edit_message_text("❌ Erreur : aucun administrateur sélectionné.")
            return ConversationHandler.END

        target_id = selected["user_id"]
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (target_id,))

            self.config.remove_admin(target_id)
            logger.info("Admin %s révoqué par le propriétaire", target_id)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
            await query.edit_message_text(
                f"✅ <b>Droits administrateur révoqués pour {selected['alias']}.</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return ConversationHandler.END

        except Exception as exc:
            logger.error("Erreur révocation admin: %s", exc, exc_info=True)
            await query.edit_message_text("❌ Échec lors de la révocation en base.")
            return ConversationHandler.END

    async def cancel_admin_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Annule la procédure de révocation."""
        query = update.callback_query
        context.user_data.pop("admins_list", None)
        context.user_data.pop("admin_to_remove", None)

        if query:
            message, keyboard = self.interface.get_gerer_admins_menu()
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=keyboard)
        return ConversationHandler.END

    # ==================== GESTION DES MEMBRES VIP (Owner Only) ====================

    async def start_add_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ouvre le dialogue pour promouvoir manuellement un utilisateur en VIP."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        await query.edit_message_text(
            "⭐ <b>Promouvoir un Membre VIP</b>\n\n"
            "Envoyez l'<b>ID numérique</b> ou le <b>@username</b> du compte à promouvoir :",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
        )
        return self.WAITING_VIP_USER

    async def process_vip_target_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Identifie le compte et demande la durée de l'accès VIP."""
        if not update.message or not update.message.text:
            return self.WAITING_VIP_USER

        saisie = update.message.text.strip().replace("@", "")

        try:
            with self.db_manager.get_cursor() as cursor:
                if saisie.isdigit():
                    cursor.execute("SELECT * FROM users WHERE user_id = %s", (int(saisie),))
                else:
                    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s)", (saisie,))
                user_data = cursor.fetchone()

            if not user_data:
                await update.message.reply_text(
                    f"❌ Utilisateur <code>{saisie}</code> introuvable.\n"
                    "Il doit obligatoirement avoir déjà démarré le bot (/start).",
                    parse_mode="HTML"
                )
                return self.WAITING_VIP_USER

            context.user_data["target_vip_user"] = user_data

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ 1 Mois (30 jours)", callback_data="vip_dur_30")],
                [InlineKeyboardButton("⭐ 3 Mois (90 jours)", callback_data="vip_dur_90")],
                [InlineKeyboardButton("👑 À Vie (Illimité)", callback_data="vip_dur_lifetime")],
                [InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]
            ])

            nom_client = user_data.get("first_name") or user_data.get("username") or str(user_data["user_id"])
            await update.message.reply_text(
                f"👤 <b>Compte ciblé :</b> {nom_client} (ID : <code>{user_data['user_id']}</code>)\n\n"
                "Choisissez la durée du statut VIP ou tapez au clavier le <b>nombre de jours</b> souhaité :",
                parse_mode="HTML",
                reply_markup=kb
            )
            return self.WAITING_VIP_DURATION

        except Exception as exc:
            logger.error("Erreur identification VIP cible: %s", exc)
            await update.message.reply_text("❌ Une erreur technique est survenue.")
            return ConversationHandler.END

    async def process_vip_duration_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enregistre le statut VIP suite à un bouton ou une saisie de jours."""
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
                await update.message.reply_text("❌ Veuillez saisir un nombre entier de jours ou utiliser les boutons :")
                context.user_data["target_vip_user"] = target_user
                return self.WAITING_VIP_DURATION

        # Application en base
        self.db_manager.set_user_vip(target_id, is_vip=True, duration_days=duration_days)

        # Notification au client promu
        try:
            type_str = f"pendant {duration_days} jours" if duration_days else "à vie"
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 <b>Félicitations !</b>\n\n"
                    f"Le propriétaire vous a accordé le <b>Statut Membre VIP</b> ({type_str}) !\n\n"
                    "Vos privilèges sont désormais actifs :\n"
                    "• Demandes illimitées sans quotas\n"
                    "• Choix du référent lors de la création\n"
                    "• Contact direct avec l'admin en charge\n"
                    "• Bouton de relance prioritaire hebdomadaire"
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

        dur_txt = f"{duration_days} jours" if duration_days else "À vie"
        succes_msg = f"✅ <b>Statut VIP activé pour {target_user.get('first_name', target_id)}</b> ({dur_txt}) !"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Gestion VIPs", callback_data="gerer_vips")]])

        if update.callback_query:
            await update.callback_query.edit_message_text(succes_msg, parse_mode="HTML", reply_markup=kb)
        elif update.message:
            await update.message.reply_text(succes_msg, parse_mode="HTML", reply_markup=kb)

        return ConversationHandler.END

    async def start_remove_vip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des VIPs actifs pour révocation."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        vips = self.db_manager.get_vip_users_list()
        if not vips:
            await query.edit_message_text(
                "📭 Aucun membre VIP actif à révoquer.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_vips")]])
            )
            return ConversationHandler.END

        lines = ["⭐ <b>Révocation de Membre VIP</b>\n", f"Membres actifs : <b>{len(vips)}</b>\n"]
        for idx, v in enumerate(vips, 1):
            nom = v.get("first_name") or "Utilisateur"
            pseudo = f"(@{v['username']})" if v.get("username") else ""
            lines.append(f"{idx}. <b>{nom}</b> {pseudo} — ID: <code>{v['user_id']}</code>")

        lines.append("\nEnvoyez le <b>numéro</b> de la personne à révoquer :")
        context.user_data["vip_remove_list"] = vips

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="cancel_vip_action")]])
        )
        return self.WAITING_VIP_REMOVE

    async def process_vip_remove_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Valide et supprime le statut VIP de l'utilisateur choisi."""
        if not update.message or not update.message.text:
            return self.WAITING_VIP_REMOVE

        choix = update.message.text.strip()
        vips = context.user_data.pop("vip_remove_list", [])

        if not choix.isdigit():
            await update.message.reply_text("❌ Veuillez saisir un numéro de la liste :")
            context.user_data["vip_remove_list"] = vips
            return self.WAITING_VIP_REMOVE

        idx = int(choix) - 1
        if idx < 0 or idx >= len(vips):
            await update.message.reply_text(f"❌ Numéro hors plage (1 à {len(vips)}) :")
            context.user_data["vip_remove_list"] = vips
            return self.WAITING_VIP_REMOVE

        selected = vips[idx]
        target_id = selected["user_id"]
        self.db_manager.set_user_vip(target_id, is_vip=False)

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="ℹ️ Votre statut Membre VIP a pris fin.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ <b>Statut VIP révoqué pour {selected.get('first_name', target_id)}.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Gestion VIPs", callback_data="gerer_vips")]])
        )
        return ConversationHandler.END

    async def cancel_vip_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Interrompt l'action VIP en cours."""
        context.user_data.pop("target_vip_user", None)
        context.user_data.pop("vip_remove_list", None)
        query = update.callback_query
        if query:
            msg, kb = self.interface.get_gerer_vips_menu()
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
        return ConversationHandler.END

    # ==================== STATISTIQUES ====================

    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les métriques globales du bot, de la base et du stockage local."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM users")
                total_users = cursor.fetchone()["total"]

                cursor.execute("SELECT COUNT(*) AS total FROM users WHERE is_vip = TRUE AND (vip_until IS NULL OR vip_until > NOW())")
                total_vips = cursor.fetchone()["total"]

                cursor.execute("SELECT COUNT(*) AS total FROM demandes")
                total_demandes = cursor.fetchone()["total"]

                cursor.execute("SELECT COUNT(*) AS total FROM archives")
                total_archives = cursor.fetchone()["total"]

                cursor.execute("SELECT COUNT(*) AS total, COALESCE(SUM(montant), 0) AS montant FROM demandes WHERE prioritaire = TRUE")
                prio_row = cursor.fetchone()
                total_prio = prio_row["total"]
                montant_total = float(prio_row["montant"])

                cursor.execute("SELECT statut, COUNT(*) AS count FROM demandes GROUP BY statut ORDER BY count DESC")
                statuts_rows = cursor.fetchall()

            db_stats = self.db_manager.get_database_size()
            storage_usage = check_storage_usage()

            lines = [
                "📈 <b>Statistiques Générales du Bot</b>\n",
                f"👥 <b>Utilisateurs enregistrés :</b> {total_users}",
                f"⭐ <b>Membres VIP actifs :</b> {total_vips}",
                f"📝 <b>Demandes en base :</b> {total_demandes}",
                f"📦 <b>Demandes archivées :</b> {total_archives}",
                f"💎 <b>Demandes prioritaires :</b> {total_prio}",
                f"💰 <b>Montant total cumulé :</b> {montant_total:.2f}€\n",
                "📊 <b>Répartition des statuts :</b>"
            ]

            for s in statuts_rows:
                lines.append(f"• {s['statut']} : {s['count']}")

            lines.append(f"\n💾 <b>Disque local :</b> {storage_usage:.1f} Mo / 512 Mo ({(storage_usage/512)*100:.1f}%)")
            lines.append(f"🗄️ <b>Taille MySQL :</b> {db_stats['total_size_mb']} Mo")

            tables_info = db_stats.get("tables", [])
            if tables_info:
                lines.append("\n📋 <b>Détails des tables :</b>")
                for tbl in tables_info:
                    t_name = tbl.get("table_name") or tbl.get("TABLE_NAME") or "inconnue"
                    s_mb = tbl.get("size_mb", 0)
                    r_cnt = tbl.get("row_count", 0)
                    lines.append(f"• <code>{t_name}</code> : {s_mb} Mo ({r_cnt} lignes)")

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Menu Gestion Bot", callback_data="gerer_bot")
            ]])

            await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur calcul statistiques: %s", exc, exc_info=True)
            await query.edit_message_text(
                "❌ Impossible de charger les statistiques.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Retour", callback_data="gerer_bot")
                ]])
            )