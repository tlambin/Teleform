"""Module de gestion des fonctions réservées au propriétaire (Owner)."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.interface_manager import InterfaceManager
from utils.maintenance import check_storage_usage, daily_maintenance

logger = logging.getLogger(__name__)


class OwnerHandlers:
    """Gestionnaire des opérations système, des statistiques et des droits administrateurs."""

    WAITING_ADMIN_ID = 1
    WAITING_ADMIN_REMOVE = 2
    WAITING_CONFIRMATION = 3

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)
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

        target = update.callback_query if update.callback_query else update.message
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
        """Vérifie l'existence de l'utilisateur et lui accorde les privilèges admin."""
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

                # Attribution de l'alias initial
                base_alias = user_data.get("first_name") or user_data.get("username") or f"Admin{target_id}"
                alias = base_alias[:20]

                cursor.execute(
                    """
                    INSERT INTO admins (user_id, alias, first_name, username, date_added, added_by)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                    """,
                    (target_id, alias, user_data.get("first_name", ""), user_data.get("username", ""), user_id)
                )

            self.config.add_admin(target_id)
            logger.info("Admin ajouté: %s (%s)", target_id, alias)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Gestion Admins", callback_data="gerer_admins")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])

            await update.message.reply_text(
                f"✅ <b>Administrateur ajouté avec succès !</b>\n\n"
                f"👤 <b>Nom :</b> {user_data.get('first_name', '')}\n"
                f"🆔 <b>ID :</b> <code>{target_id}</code>\n"
                f"🏷️ <b>Alias attribué :</b> <code>{alias}</code>",
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

    async def admin_supprimer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche la liste des administrateurs révocables."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return ConversationHandler.END

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, alias, first_name, username, date_added
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
                user_desc = f"@{adm['username']}" if adm.get("username") else adm.get("first_name", "")
                date_str = str(adm.get("date_added", ""))[:10]
                lines.append(f"{idx}. <b>{adm['alias']}</b> ({user_desc}) — ID: <code>{adm['user_id']}</code> [{date_str}]")

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

    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche les métriques globales du bot, de la base et du stockage local."""
        query = update.callback_query
        if not query or not self.config.is_owner(update.effective_user.id):
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM users")
                total_users = cursor.fetchone()["total"]

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
                    # Lecture robuste des clés peu importe la casse
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