"""Module principal de gestion de l'affichage des interactions utilisateurs et demandeurs."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager
from .user.compte import CompteManager
from .user.demande import DemandeManager
from .user.edition import EditionManager
from .user.formulaire import FormulaireManager

logger = logging.getLogger(__name__)


class UserHandlers:
    """Gestionnaire des routes utilisateurs, formulaires, paiements Stars et privilèges VIP."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        self.compte = CompteManager(db_manager, config)
        self.formulaire = FormulaireManager(db_manager, config, self.compte)
        self.demande = DemandeManager(db_manager, config, self.compte)
        self.edition = EditionManager(db_manager, config)
        self._staff_handlers = None

    @property
    def staff_handlers(self):
        """Lazy-loading du gestionnaire opérationnel Staff pour éviter les cycles d'importation."""
        if self._staff_handlers is None:
            from handlers.staff_handlers import StaffHandlers
            self._staff_handlers = StaffHandlers(self.config, self.db_manager)
        return self._staff_handlers

    async def _check_required_membership(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Vérifie si l'utilisateur est membre du groupe obligatoire configuré par l'Owner."""
        user = update.effective_user
        if not user:
            return False

        # Exemptions pour l'équipe opérationnelle et la direction (Owner, Admins, Staff)
        owner_id_db = self.db_manager.get_owner_id()
        if (
            self.config.is_staff(user.id)
            or self.config.is_admin(user.id)
            or self.config.is_owner(user.id)
            or (owner_id_db and int(user.id) == int(owner_id_db))
        ):
            return True

        # Vérifie si le module d'adhésion obligatoire est activé
        if not self.db_manager.is_required_group_enabled():
            return True

        raw_group_id = self.db_manager.get_required_group_id()
        try:
            group_id = int(raw_group_id)
        except (ValueError, TypeError):
            group_id = 0

        if not group_id or group_id == 0:
            return True

        # Correction automatique si le préfixe négatif a été oublié pour un supergroupe
        if group_id > 0 and str(group_id).startswith("100"):
            group_id = -group_id

        telegram_err = None
        user_status = None
        try:
            member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
            user_status = member.status

            # Statuts valides : Créateur, Admin, Membre standard
            if user_status in ("member", "administrator", "creator"):
                return True

            # Membres avec restrictions par défaut dans le supergroupe
            if user_status == "restricted":
                is_in_group = getattr(member, "is_member", True)
                if is_in_group:
                    return True

            logger.info("Utilisateur %s non validé dans le groupe %s (statut : %s)", user.id, group_id, user_status)

        except Exception as exc:
            telegram_err = str(exc)
            logger.error("💥 Erreur get_chat_member (chat_id=%s, user_id=%s) : %s", group_id, user.id, exc)

        # Si l'utilisateur clique sur le bouton de vérification, afficher le détail technique en cas d'échec
        if update.callback_query and update.callback_query.data == "check_subscription":
            if telegram_err:
                await update.callback_query.answer(
                    f"⚠️ Erreur Telegram : {telegram_err[:180]} (Chat ID : {group_id})",
                    show_alert=True
                )
            elif user_status:
                await update.callback_query.answer(
                    f"❌ Non détecté dans le groupe (Statut Telegram : {user_status}). Rejoignez le groupe avant de valider.",
                    show_alert=True
                )

        raw_link = self.db_manager.get_group_subscription_link()
        if raw_link.startswith("@"):
            sub_url = f"https://t.me/{raw_link.lstrip('@')}"
        elif raw_link.startswith("http://") or raw_link.startswith("https://"):
            sub_url = raw_link
        else:
            sub_url = f"https://t.me/{raw_link}"

        msg_text = (
            "📢 <b>Adhésion requise</b>\n\n"
            "Pour accéder aux services du bot et déposer vos demandes, vous devez obligatoirement rejoindre notre groupe.\n\n"
            "Cliquez sur le bouton ci-dessous pour vous inscrire via le bot dédié, puis cliquez sur <b>Vérifier mon adhésion</b> :"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ S'inscrire au groupe", url=sub_url)],
            [InlineKeyboardButton("🔄 Vérifier mon adhésion", callback_data="check_subscription")]
        ])

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
            logger.info("👤 Utilisateur %s vérifié/enregistré en base", user_id)

            if not await self._check_required_membership(update, context):
                return

            welcome_msg, reply_markup = self.interface.get_start_interface(user_id, first_name)

            await update.message.reply_text(
                welcome_msg,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
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

        # 1. Vérification d'adhésion interactive
        if data == "check_subscription":
            if await self._check_required_membership(update, context):
                await query.answer("✅ Merci pour votre adhésion !", show_alert=True)
                welcome_msg, reply_markup = self.interface.get_start_interface(user_id, query.from_user.first_name)
                try:
                    await query.edit_message_text(welcome_msg, parse_mode="HTML", reply_markup=reply_markup)
                except Exception:
                    await query.message.reply_text(welcome_msg, parse_mode="HTML", reply_markup=reply_markup)
            return

        # 2. Contrôle préalable d'adhésion obligatoire
        if not await self._check_required_membership(update, context):
            await query.answer("❌ Adhésion obligatoire non validée.", show_alert=True)
            return

        # 3. Contrôle global du service
        if data.startswith(("form_", "nav_", "new_demande")) and not self.config.are_demandes_enabled():
            await query.answer()
            await query.edit_message_text(
                "🚫 <b>Service temporairement indisponible</b>\n\n"
                "La création et la navigation des demandes sont actuellement désactivées par l'administration.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ]),
            )
            return

        try:
            # Bouton d'information quota atteint
            if data == "quota_reached_info":
                _, reason = self.demande.check_creation_quota(user_id)
                clean_reason = reason.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")[:150]
                await query.answer(clean_reason, show_alert=True)
                return

            # Création d'une nouvelle demande
            elif data == "new_demande":
                await query.answer()
                can_create, reason_msg = self.demande.check_creation_quota(user_id)
                if not can_create:
                    await query.edit_message_text(
                        reason_msg,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⭐ Passer VIP", callback_data="menu_vip_shop")],
                            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                        ]),
                    )
                    return
                await self.formulaire.navigation.handle_form_navigation(update, context)

            # Consultation des archives de l'utilisateur
            elif data == "mes_archives" or data.startswith("user_arch_page_"):
                await self.demande.handle_navigation(update, context, data)
                return

            # Boutique VIP Telegram Stars & Réglages VIP
            elif data == "menu_vip_shop":
                await query.answer()
                is_vip_user = self.db_manager.is_user_vip(user_id)
                msg, kb = self.interface.get_vip_shop_menu(is_vip=is_vip_user)
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
                return

            elif data == "menu_vip_settings" or data.startswith("vip_set_assign_") or data == "vip_pick_auto_staff":
                if data == "menu_vip_settings":
                    await self.compte.show_vip_settings_menu(update, context)
                else:
                    await self.compte.handle_callback_routing(update, context, data)
                return

            elif data == "buy_vip_month":
                await query.answer()
                stars_price = 250
                title = "Abonnement VIP 30 Jours"
                desc = "Accès VIP pendant 30 jours : demandes illimitées, choix du référent et contact direct."
                payload = f"vip_sub_{user_id}_30d"
                prices = [LabeledPrice(label=title, amount=stars_price)]

                await context.bot.send_invoice(
                    chat_id=query.message.chat_id,
                    title=title,
                    description=desc,
                    payload=payload,
                    currency="XTR",
                    prices=prices,
                    provider_token="",
                )
                return

            # ==================== CYCLE RÉMUNÉRATION (DEMANDE STANDARD) ====================
            elif data.startswith("user_accept_remun_std_"):
                await query.answer()
                demande_id = int(data.replace("user_accept_remun_std_", ""))
                context.user_data["waiting_client_std_remun_amount"] = demande_id

                prompt_text = (
                    f"💰 <b>Allocation d'un montant (Dossier #{demande_id})</b>\n\n"
                    "Indiquez au clavier le <b>montant</b> que vous êtes prêt à allouer pour cette demande (en €) :\n\n"
                    "<i>Votre dossier sera automatiquement converti en priorité et proposé aux piégeurs.</i>"
                )
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="voir_demandes")
                ]])
                await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=kb)
                return

            elif data.startswith("user_refuse_remun_std_"):
                await query.answer()
                demande_id = int(data.replace("user_refuse_remun_std_", ""))
                demande = self.db_manager.archiver_demande_annulee(
                    demande_id=demande_id,
                    raison="Refus de rémunération formulé par le demandeur"
                )
                if demande:
                    req_num = demande.get("request_number", demande_id)
                    await query.edit_message_text(
                        f"❌ <b>Dossier #{req_num} abandonné et clôturé.</b>\n\n"
                        "Votre quota de demandes actives a été libéré.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🗂️ Mes demandes", callback_data="voir_demandes")
                        ]])
                    )
                else:
                    await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            # ==================== CYCLE RÉMUNÉRATION (DEMANDE PRIORITAIRE) ====================
            elif data.startswith("user_accept_remun_prio_"):
                await query.answer()
                demande_id = int(data.replace("user_accept_remun_prio_", ""))
                assigned_demande = self.db_manager.accept_proposed_price_and_assign(demande_id)

                if assigned_demande:
                    req_num = assigned_demande.get("request_number", demande_id)
                    nouveau_montant = assigned_demande["nouveau_montant"]
                    staff_id = assigned_demande["staff_id"]
                    staff_alias = self.db_manager.get_staff_alias(staff_id)
                    prenom = html.escape(str(assigned_demande.get("prenom") or ""))

                    await query.edit_message_text(
                        f"🎉 <b>Tarif accepté ({nouveau_montant:.2f} €) !</b>\n\n"
                        f"Votre dossier #{req_num} concernant <b>{prenom}</b> a été pris en charge immédiatement par <b>{html.escape(str(staff_alias))}</b>.\n"
                        "Il est désormais en statut <b>⏳ En attente</b> dans vos demandes en cours.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Consulter mes demandes", callback_data="voir_demandes")
                        ]])
                    )

                    try:
                        alert_staff = (
                            f"🎉 <b>PROPOSITION DE PRIX ACCEPTÉE ! (Dossier #{req_num})</b>\n\n"
                            f"Le demandeur a validé votre tarif de <b>{nouveau_montant:.2f} €</b> pour <b>{prenom}</b>.\n"
                            "Le dossier est maintenant présent dans vos <b>Demandes suivies</b> sous le statut <b>⏳ En attente</b>."
                        )
                        kb_staff = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📄 Ouvrir le dossier", callback_data=f"retour_texte_{demande_id}")],
                            [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
                        ])
                        await context.bot.send_message(
                            chat_id=staff_id,
                            text=alert_staff,
                            parse_mode="HTML",
                            reply_markup=kb_staff
                        )
                    except Exception as err_s:
                        logger.warning("Impossible de notifier le staff de l'acceptation du prix : %s", err_s)
                else:
                    await query.answer("❌ Offre introuvable ou dossier déjà attribué.", show_alert=True)
                return

            elif data.startswith("user_refuse_remun_prio_"):
                await query.answer()
                demande_id = int(data.replace("user_refuse_remun_prio_", ""))

                with self.db_manager.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, request_number, prenom, montant, proposed_price, proposed_by FROM demandes WHERE id = %s",
                        (demande_id,)
                    )
                    dem = cursor.fetchone()

                if dem:
                    req_num = dem.get("request_number", demande_id)
                    staff_id = dem.get("proposed_by")
                    montant_initial = float(dem.get("montant") or 0.0)
                    prenom = html.escape(str(dem.get("prenom") or ""))

                    self.db_manager.clear_demande_proposed_price(demande_id)

                    await query.edit_message_text(
                        f"ℹ️ <b>Proposition refusée.</b>\n\n"
                        f"Votre dossier #{req_num} reste actif en file d'attente à son tarif initial de <b>{montant_initial:.2f} €</b>.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🗂️ Mes demandes", callback_data="voir_demandes")
                        ]])
                    )

                    if staff_id:
                        try:
                            alert_staff = (
                                f"ℹ️ <b>Proposition de prix refusée (Dossier #{req_num})</b>\n\n"
                                f"Le client a décliné votre offre de revalorisation pour <b>{prenom}</b>.\n"
                                f"Le dossier reste disponible dans la file d'attente à <b>{montant_initial:.2f} €</b>."
                            )
                            await context.bot.send_message(
                                chat_id=staff_id,
                                text=alert_staff,
                                parse_mode="HTML",
                                reply_markup=InlineKeyboardMarkup([[
                                    InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")
                                ]])
                            )
                        except Exception as err_s:
                            logger.warning("Impossible de notifier le staff du refus de prix : %s", err_s)
                else:
                    await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            # ==================== CONVERSION EN PRIORITAIRE CLASSIQUE ====================
            elif data.startswith("upgrade_prio_"):
                await query.answer()
                demande_id = int(data.replace("upgrade_prio_", ""))
                context.user_data["waiting_upgrade_prio_amount"] = demande_id

                text_prompt = (
                    f"💎 <b>Conversion en Demande Prioritaire (Dossier #{demande_id})</b>\n\n"
                    "Indiquez au clavier le <b>montant</b> que vous souhaitez allouer à cette demande (en €) :\n"
                    "<i>(Les demandes prioritaires sont examinées et traitées en priorité par l'équipe).</i>"
                )
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="voir_demandes")
                ]])

                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=text_prompt,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                else:
                    try:
                        await query.edit_message_text(text_prompt, parse_mode="HTML", reply_markup=kb)
                    except Exception:
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=text_prompt,
                            parse_mode="HTML",
                            reply_markup=kb
                        )
                return

            # ==================== RÈGLEMENT DEMANDES PRIORITAIRES ====================
            elif data.startswith("pay_stars_prio_"):
                await query.answer()
                demande_id = int(data.replace("pay_stars_prio_", ""))
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, request_number, prenom, montant, paiement_statut, admin_en_charge FROM demandes WHERE id = %s AND user_id = %s",
                        (demande_id, user_id)
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

                stars_amount = max(1, int(montant * 50))
                req_num = dem.get("request_number", demande_id)
                title = f"Règlement Demande #{req_num}"
                desc = f"Paiement de la prestation prioritaire pour {dem.get('prenom', 'la cible')} ({montant:.2f} €)."
                payload = f"prio_pay_{demande_id}_{user_id}"

                await context.bot.send_invoice(
                    chat_id=query.message.chat_id,
                    title=title,
                    description=desc,
                    payload=payload,
                    currency="XTR",
                    prices=[LabeledPrice(label=f"Prestation prioritaire #{req_num}", amount=stars_amount)],
                    provider_token="",
                )
                return

            elif data.startswith("pay_contact_prio_"):
                await query.answer()
                demande_id = int(data.replace("pay_contact_prio_", ""))
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT id, request_number, admin_en_charge, montant, prenom FROM demandes WHERE id = %s AND user_id = %s",
                        (demande_id, user_id)
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
                    admin_alert = (
                        f"💳 <b>Paiement direct demandé (Dossier #{req_num})</b>\n\n"
                        f"Le client <b>{html.escape(u_label)}</b> souhaite convenir du mode de paiement "
                        f"pour le dossier de <b>{html.escape(str(dem.get('prenom') or ''))}</b> (Montant : <b>{montant:.2f} €</b>).\n\n"
                        "Une fois les fonds reçus, validez l'encaissement via le bouton dédié sur votre fiche de suivi."
                    )
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_alert,
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📄 Ouvrir la fiche du dossier", callback_data=f"retour_texte_{demande_id}")]
                        ])
                    )
                except Exception as notif_err:
                    logger.warning("Impossible d'avertir l'opérateur pour paiement alternatif : %s", notif_err)

                contact_text = (
                    f"💬 <b>Paiement avec votre référent ({html.escape(str(alias))}) — Dossier #{req_num}</b>\n\n"
                    f"Montant convenu : <b>{montant:.2f} €</b>\n\n"
                    "Envoyez votre message ci-dessous pour convenir du moyen de règlement souhaité (PayPal, virement, etc.) :\n"
                    "<i>Dès réception des fonds, votre référent validera le paiement et vous transmettra les fichiers.</i>"
                )
                contact_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_user_reply")
                ]])

                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=contact_text,
                        parse_mode="HTML",
                        reply_markup=contact_kb
                    )
                else:
                    await query.edit_message_text(contact_text, parse_mode="HTML", reply_markup=contact_kb)
                return

            # Relance hebdomadaire gratuite
            elif data.startswith("remind_admin_free_"):
                demande_id = int(data.replace("remind_admin_free_", ""))
                can_remind, err_msg = self.db_manager.can_send_demande_reminder(demande_id)
                if not can_remind:
                    await query.answer(f"⚠️ {err_msg}", show_alert=True)
                    return

                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT admin_en_charge FROM demandes WHERE id = %s", (demande_id,))
                    row = cursor.fetchone()

                admin_id = row.get("admin_en_charge") if row else None
                if not admin_id:
                    await query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
                    return

                if self.db_manager.is_staff_paused(admin_id):
                    raw_alias = self.db_manager.get_staff_alias(admin_id)
                    await query.answer(
                        f"⏸️ Votre référent ({raw_alias}) est actuellement en pause. Relance impossible pour le moment.",
                        show_alert=True
                    )
                    return

                await self._dispatch_admin_reminder(update, context, demande_id, is_paid_boost=False)
                return

            # Relance payante
            elif data.startswith("remind_admin_pay_"):
                demande_id = int(data.replace("remind_admin_pay_", ""))
                can_remind, err_msg = self.db_manager.can_send_demande_reminder(demande_id)
                if not can_remind:
                    await query.answer(f"⚠️ {err_msg}", show_alert=True)
                    return

                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT admin_en_charge FROM demandes WHERE id = %s", (demande_id,))
                    row = cursor.fetchone()

                admin_id = row.get("admin_en_charge") if row else None
                if not admin_id:
                    await query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
                    return

                if self.db_manager.is_staff_paused(admin_id):
                    raw_alias = self.db_manager.get_staff_alias(admin_id)
                    await query.answer(
                        f"⏸️ Votre référent ({raw_alias}) est actuellement en pause. Relance impossible pour le moment.",
                        show_alert=True
                    )
                    return

                await query.answer()
                title = f"Rappel Demande #{demande_id}"
                desc = "Relance prioritaire hebdomadaire envoyée directement à votre référent."
                payload = f"remind_pay_{demande_id}_{user_id}"

                await context.bot.send_invoice(
                    chat_id=query.message.chat_id,
                    title=title,
                    description=desc,
                    payload=payload,
                    currency="XTR",
                    prices=[LabeledPrice(label="Relance prioritaire (1 €)", amount=50)],
                    provider_token="",
                )
                return

            # Contacter mon référent
            elif data.startswith(("vip_contact_admin_", "contact_admin_")):
                demande_id = int(data.split("_")[-1])
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT admin_en_charge, request_number FROM demandes WHERE id = %s", (demande_id,))
                    d_row = cursor.fetchone()

                if not d_row or not d_row.get("admin_en_charge"):
                    await query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
                    return

                admin_id = d_row["admin_en_charge"]

                if self.db_manager.is_staff_paused(admin_id):
                    raw_alias = self.db_manager.get_staff_alias(admin_id)
                    await query.answer(
                        f"⏸️ Votre référent ({raw_alias}) est actuellement en pause. Réessayez ultérieurement.",
                        show_alert=True
                    )
                    return

                context.user_data["replying_to_admin"] = {
                    "demande_id": demande_id,
                    "admin_id": admin_id,
                }
                await query.answer()
                req_num = d_row.get("request_number", demande_id)
                alias = self.db_manager.get_staff_alias(admin_id)

                contact_text = (
                    f"💬 <b>Ligne directe avec votre référent ({html.escape(str(alias))}) — Dossier #{req_num}</b>\n\n"
                    "Tapez votre message ou envoyez vos fichiers ci-dessous. Ils lui seront immédiatement transmis :"
                )
                contact_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Annuler", callback_data="cancel_user_reply")
                ]])

                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=contact_text,
                        parse_mode="HTML",
                        reply_markup=contact_kb
                    )
                else:
                    await query.edit_message_text(contact_text, parse_mode="HTML", reply_markup=contact_kb)
                return

            elif data.startswith("vip_assign_admin_") or data.startswith("vip_opt_"):
                await self.formulaire.handle_vip_admin_choice(update, context)
                return

            # Reprise suite à un abandon
            elif data.startswith("reprendre_demande_"):
                await query.answer()
                demande_id = int(data.replace("reprendre_demande_", ""))
                try:
                    with self.db_manager.transaction() as cursor:
                        cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (demande_id,))
                        cursor.execute(
                            """
                            UPDATE demandes
                            SET statut = '📥 Reçue', admin_en_charge = NULL, date_modification = NOW()
                            WHERE id = %s AND user_id = %s
                            """,
                            (demande_id, user_id)
                        )

                    await query.edit_message_text(
                        "🔄 <b>Votre demande a été remise en file d'attente !</b>\n\n"
                        "Elle est de nouveau disponible et visible par toute l'équipe opérationnelle.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("📋 Voir mes demandes", callback_data="voir_demandes")
                        ]])
                    )
                except Exception as exc:
                    logger.error("Erreur remise en dispo demande %s : %s", demande_id, exc)
                    await query.answer("❌ Erreur technique lors de la remise en file d'attente.", show_alert=True)
                return

            # Archivage par l'utilisateur
            elif data.startswith("archiver_demande_"):
                await query.answer()
                demande_id = int(data.replace("archiver_demande_", ""))
                demande = self.db_manager.archiver_demande_supprimee(demande_id, "Abandonnée par le demandeur")
                if demande:
                    await query.edit_message_text(
                        "🗑️ <b>Demande classée sans suite.</b>\n\n"
                        "Votre demande a été archivée sous « 🗑️ Supprimée ». Une place vient d'être libérée dans votre quota.",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🗳️ Nouvelle demande", callback_data="new_demande"),
                            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
                        ]])
                    )
                else:
                    await query.answer("❌ Erreur technique lors de l'archivage.", show_alert=True)
                return

            # Protocole d'annulation client soumis au piégeur
            elif data.startswith("ask_cancel_demande_"):
                await query.answer()
                demande_id = int(data.replace("ask_cancel_demande_", ""))
                context.user_data["waiting_cancel_reason_demande_id"] = demande_id

                prompt_text = (
                    f"✍️ <b>Demande d'annulation (Dossier #{demande_id})</b>\n\n"
                    "Indiquez au clavier la <b>raison</b> de votre annulation :\n"
                    "<i>Elle sera transmise à l'opérateur en charge pour validation.</i>"
                )
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="voir_demandes")]])

                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=prompt_text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                else:
                    await query.edit_message_text(prompt_text, parse_mode="HTML", reply_markup=kb)
                return

            # Décision du piégeur : Acceptation
            elif data.startswith("accept_cancel_"):
                await query.answer()
                demande_id = int(data.replace("accept_cancel_", ""))
                raison = context.user_data.pop(f"cancel_reason_{demande_id}", "Convenance demandeur")
                demande = self.db_manager.archiver_demande_annulee(demande_id, raison)
                if demande:
                    req_num = demande.get("request_number", demande_id)
                    await query.edit_message_text(
                        f"✅ <b>Annulation acceptée.</b> Le dossier #{req_num} est archivé sous le statut « ❌ Annulée ».",
                        parse_mode="HTML"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=demande["user_id"],
                            text=(
                                f"✅ <b>Votre demande d'annulation pour le dossier #{req_num} a été acceptée par l'opérateur.</b>\n"
                                "Le dossier est désormais clôturé et archivé."
                            ),
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                else:
                    await query.answer("❌ Demande introuvable ou déjà traitée.", show_alert=True)
                return

            # Décision du piégeur : Refus
            elif data.startswith("refuse_cancel_"):
                await query.answer()
                demande_id = int(data.replace("refuse_cancel_", ""))
                context.user_data.pop(f"cancel_reason_{demande_id}", None)
                await query.edit_message_text(
                    f"❌ <b>Annulation refusée.</b> Le traitement du dossier #{demande_id} se poursuit.",
                    parse_mode="HTML"
                )
                with self.db_manager.get_cursor() as cursor:
                    cursor.execute("SELECT user_id, request_number FROM demandes WHERE id = %s", (demande_id,))
                    dem = cursor.fetchone()
                if dem:
                    try:
                        await context.bot.send_message(
                            chat_id=dem["user_id"],
                            text=(
                                f"⚠️ <b>Demande d'annulation refusée pour le dossier #{dem.get('request_number', demande_id)}.</b>\n"
                                "Le piège est déjà trop avancé pour être interrompu."
                            ),
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                return

            elif data.startswith("reply_to_admin_"):
                await query.answer()
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except Exception:
                    pass

                parts = data.split("_")
                demande_id = int(parts[3])
                admin_id = int(parts[4])
                context.user_data["replying_to_admin"] = {
                    "demande_id": demande_id,
                    "admin_id": admin_id,
                }
                await query.message.reply_text(
                    "✍️ <b>Tapez votre réponse ou envoyez votre fichier ci-dessous :</b>\n\n"
                    "⚠️ <i>Attention : vous ne disposez que d'une seule réponse autorisée pour ce message.</i>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❌ Annuler", callback_data="cancel_user_reply")
                    ]])
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
            elif data.startswith("cancel_demande_"):
                await query.answer()
                await self._handle_cancel_demande_placeholder(update, data)
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
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Retour au menu", callback_data="start_menu")]
                    ]),
                )
            except Exception:
                pass

    async def _dispatch_admin_reminder(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, is_paid_boost: bool = False
    ):
        """Transmet la notification de rappel à l'opérateur en charge."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT request_number, prenom, user_id, admin_en_charge FROM demandes WHERE id = %s",
                (demande_id,)
            )
            row = cursor.fetchone()

        if not row or not row.get("admin_en_charge"):
            if update.callback_query:
                await update.callback_query.answer("❌ Aucun référent n'est assigné à cette demande.", show_alert=True)
            return

        admin_id = row["admin_en_charge"]
        req_num = html.escape(str(row.get("request_number", demande_id)))
        user = update.effective_user
        user_label = f"@{user.username}" if user.username else user.first_name
        user_label_esc = html.escape(user_label or f"User_{user.id}")
        prenom_esc = html.escape(str(row.get("prenom") or ""))

        if self.db_manager.is_user_vip(user.id):
            tag = "⭐ VIP"
        elif is_paid_boost:
            tag = "⚡ Boost 1 €"
        else:
            tag = "💎 Prioritaire"

        remind_msg = (
            f"🔔 <b>RAPPEL DEMANDE #{req_num} [{tag}]</b>\n\n"
            f"Le demandeur <b>{user_label_esc}</b> vous relance concernant sa demande pour <b>{prenom_esc}</b>.\n"
            "Merci de consulter vos suivis ou de lui apporter une réponse."
        )
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💌 Ouvrir mes suivis", callback_data="demandes_suivies")],
            [InlineKeyboardButton("💬 Contacter le demandeur", callback_data=f"contacter_{demande_id}")]
        ])

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
            "gerer_admins", "admin_ajouter", "admin_supprimer",
            "gerer_staff", "staff_ajouter", "staff_supprimer",
            "gerer_bot", "bot_on", "bot_off", "bot_maintenance",
            "menu_channels", "menu_limits", "gerer_vips", "owner_add_vip", "owner_remove_vip",
            "menu_cfg_group", "toggle_cfg_group_enabled", "set_cfg_group_id", "set_cfg_group_link",
            "menu_cfg_support", "set_cfg_support_contact", "menu_danger_zone"
        }
        if (data in owner_actions or data.startswith("limit_")) and not self.config.is_admin(user_id):
            await query.answer("❌ Accès réservé aux administrateurs.", show_alert=True)
            return

        staff_actions = {
            "gerer_demandes", "demandes_disponibles", "demandes_suivies",
            "modifier_alias", "menu_notifs"
        }
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

        # Gestion synchrone des quotas (RAM + MySQL)
        if data.startswith("limit_"):
            tot = self.config.get_max_total_demandes()
            usr = self.config.get_max_demandes_per_user()

            if data == "limit_total_0":
                self.config.set_max_total_demandes(0)
                self.db_manager.set_config_value("max_total_demandes", "0")
            elif data == "limit_total_add5":
                new_tot = tot + 5
                self.config.set_max_total_demandes(new_tot)
                self.db_manager.set_config_value("max_total_demandes", str(new_tot))
            elif data == "limit_total_sub5":
                new_tot = max(0, tot - 5)
                self.config.set_max_total_demandes(new_tot)
                self.db_manager.set_config_value("max_total_demandes", str(new_tot))

            elif data == "limit_user_3":
                self.config.set_max_demandes_per_user(3)
                self.db_manager.set_config_value("max_demandes_per_user", "3")
            elif data == "limit_user_add1":
                new_usr = usr + 1
                self.config.set_max_demandes_per_user(new_usr)
                self.db_manager.set_config_value("max_demandes_per_user", str(new_usr))
            elif data == "limit_user_sub1":
                new_usr = max(1, usr - 1)
                self.config.set_max_demandes_per_user(new_usr)
                self.db_manager.set_config_value("max_demandes_per_user", str(new_usr))

            elif data == "limit_input_total":
                context.user_data["waiting_limit_input"] = "total"
                await query.edit_message_text(
                    "🔢 Tapez au clavier le <b>nombre total maximum</b> de demandes autorisées (0 = illimité) :",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_limits")]])
                )
                return

            elif data == "limit_input_user":
                context.user_data["waiting_limit_input"] = "user"
                await query.edit_message_text(
                    "🔢 Tapez au clavier le <b>nombre maximum de demandes par personne</b> (0 = illimité) :",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_limits")]])
                )
                return

            elif data in (
                "limit_input_hetero_insta", "limit_input_hetero_snap",
                "limit_input_gay_insta", "limit_input_gay_snap"
            ):
                field = data.replace("limit_input_", "")
                context.user_data["waiting_limit_input"] = field
                labels = {
                    "hetero_insta": "Max Insta Hétéro",
                    "hetero_snap": "Max Snap Hétéro",
                    "gay_insta": "Max Insta Gay",
                    "gay_snap": "Max Snap Gay",
                }
                await query.edit_message_text(
                    f"🔢 Tapez au clavier le <b>{labels.get(field, field)}</b> autorisé (0 = illimité) :",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_limits")]])
                )
                return

            msg, kb = self.interface.get_limits_menu()
            try:
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            except Exception as tg_err:
                if "Message is not modified" not in str(tg_err):
                    logger.warning("Erreur rafraîchissement menu limites : %s", tg_err)
            return

        message, keyboard = self.interface.route_callback(data, user_id, first_name)
        if message and keyboard:
            if query.message and query.message.photo:
                chat_id = query.message.chat_id
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            else:
                await query.edit_message_text(
                    message,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            await query.answer("❌ Action indisponible.", show_alert=True)

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage central des messages texte et médias hors commandes."""
        if not update.message:
            return

        # ==================== SAISIE REVALORISATION TARIF PAR LE STAFF (DEMANDE DISPO PRIO) ====================
        if update.message.text and context.user_data and context.user_data.get("waiting_staff_revalorisation_prix"):
            sess = context.user_data.pop("waiting_staff_revalorisation_prix")
            demande_id = sess["demande_id"]
            current_montant = sess["current_montant"]
            staff_id = sess["staff_id"]
            raw_montant = update.message.text.strip().replace(",", ".").replace("€", "")

            try:
                nouveau_prix = float(raw_montant)
                if nouveau_prix <= current_montant:
                    raise ValueError()
            except ValueError:
                context.user_data["waiting_staff_revalorisation_prix"] = sess
                await update.message.reply_text(
                    f"❌ Veuillez saisir un montant valide strictement supérieur au montant actuel (minimum : <code>{current_montant + 1:.2f} €</code>) :",
                    parse_mode="HTML"
                )
                return

            ok = self.db_manager.set_demande_proposed_price(demande_id, staff_id, nouveau_prix)
            if not ok:
                await update.message.reply_text("❌ Erreur technique lors de l'enregistrement de l'offre.")
                return

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT id, request_number, prenom, user_id FROM demandes WHERE id = %s", (demande_id,))
                dem = cursor.fetchone()

            if dem:
                req_num = dem.get("request_number", demande_id)
                prenom = html.escape(str(dem.get("prenom") or "votre contact"))
                alias_staff = self.db_manager.get_staff_alias(staff_id)

                client_alert = (
                    f"💰 <b>Proposition de revalorisation (Dossier #{req_num})</b>\n\n"
                    f"L'opérateur <b>{html.escape(str(alias_staff))}</b> souhaite prendre en charge votre dossier concernant <b>{prenom}</b> !\n\n"
                    f"Compte tenu de la difficulté de la cible, il vous propose de réaliser la prestation pour un tarif de <b>{nouveau_prix:.2f} €</b> "
                    f"(au lieu de <code>{current_montant:.2f} €</code>).\n\n"
                    "• <b>Accepter :</b> Le dossier sera immédiatement pris en charge par cet opérateur sous le statut ⏳ En attente.\n"
                    "• <b>Refuser :</b> Votre demande reste active au tarif de base dans les disponibles pour le reste de l'équipe."
                )
                client_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"✅ Accepter ({nouveau_prix:.2f} €)", callback_data=f"user_accept_remun_prio_{demande_id}"),
                        InlineKeyboardButton("❌ Refuser", callback_data=f"user_refuse_remun_prio_{demande_id}")
                    ]
                ])

                try:
                    await context.bot.send_message(chat_id=dem["user_id"], text=client_alert, parse_mode="HTML", reply_markup=client_kb)
                    await update.message.reply_text(
                        f"✅ <b>Proposition de {nouveau_prix:.2f} € envoyée au demandeur pour le dossier #{req_num} !</b>\n"
                        "Vous serez notifié dès qu'il aura accepté ou refusé l'offre.",
                        parse_mode="HTML"
                    )
                except Exception as err:
                    logger.error("Erreur envoi proposition tarif client : %s", err)
                    await update.message.reply_text("❌ Impossible de transmettre la proposition au demandeur.")
            return

        # ==================== SAISIE MONTANT RÉMUNÉRATION PAR LE CLIENT (DEMANDE DISPO STANDARD) ====================
        if update.message.text and context.user_data and context.user_data.get("waiting_client_std_remun_amount"):
            demande_id = context.user_data.pop("waiting_client_std_remun_amount")
            raw_montant = update.message.text.strip().replace(",", ".").replace("€", "")

            try:
                montant = float(raw_montant)
                if montant <= 0:
                    raise ValueError()
            except ValueError:
                context.user_data["waiting_client_std_remun_amount"] = demande_id
                await update.message.reply_text(
                    "❌ Veuillez saisir un montant valide supérieur à 0 (ex : <code>15</code> ou <code>25.00</code>) :",
                    parse_mode="HTML"
                )
                return

            user_id = update.effective_user.id
            ok, msg_result = self.db_manager.upgrade_demande_to_prioritaire(demande_id, user_id, montant)

            if ok:
                await update.message.reply_text(
                    f"🎉 <b>Rémunération enregistrée !</b>\n\n"
                    f"Votre dossier #{demande_id} est désormais <b>💎 Prioritaire</b> avec une gratification de <b>{montant:.2f} €</b>.\n"
                    "Il est à présent proposé en priorité à l'ensemble de l'équipe !",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🗂️ Mes demandes", callback_data="voir_demandes")
                    ]])
                )
            else:
                await update.message.reply_text(f"⚠️ {msg_result}")
            return

        # ==================== SIGNALEMENT D'UNE DEMANDE DISPO PAR LE STAFF ====================
        if update.message.text and context.user_data and context.user_data.get("waiting_staff_report_reason"):
            demande_id = context.user_data.pop("waiting_staff_report_reason")
            motif = update.message.text.strip()
            staff_user = update.effective_user
            staff_alias = self.db_manager.get_staff_alias(staff_user.id)
            staff_alias_esc = html.escape(str(staff_alias))
            motif_esc = html.escape(motif)

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT id, request_number, prenom FROM demandes WHERE id = %s", (demande_id,))
                dem = cursor.fetchone()

            if not dem:
                await update.message.reply_text("❌ Demande introuvable.")
                return

            req_num = dem.get("request_number", demande_id)
            prenom = html.escape(str(dem.get("prenom") or ""))

            admin_alert = (
                f"🚨 <b>SIGNALEMENT D'UNE DEMANDE DISPONIBLE</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Opérateur :</b> {staff_alias_esc} (<code>{staff_user.id}</code>)\n"
                f"• <b>Dossier concerné :</b> #{req_num} ({prenom})\n"
                f"• <b>Motif du signalement :</b>\n« <i>{motif_esc}</i> »\n\n"
                "<i>Actions administratives directes :</i>"
            )
            admin_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💰 Rémunération", callback_data=f"dispo_ask_remun_std_{demande_id}"),
                    InlineKeyboardButton("🗑️ Supprimer", callback_data=f"admin_del_dispo_{demande_id}")
                ],
                [InlineKeyboardButton("📄 Voir le dossier", callback_data=f"retour_texte_{demande_id}")]
            ])

            monitors = self.db_manager.get_monitoring_admins()
            for admin_id in monitors:
                try:
                    await context.bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="HTML", reply_markup=admin_kb)
                except Exception:
                    pass

            await update.message.reply_text("✅ <b>Signalement transmis à l'administration avec succès !</b>", parse_mode="HTML")
            return

        # ==================== CONVERSION DEMANDE EN PRIORITAIRE CLASSIQUE ====================
        if update.message.text and context.user_data and context.user_data.get("waiting_upgrade_prio_amount"):
            demande_id = context.user_data.pop("waiting_upgrade_prio_amount")
            raw_montant = update.message.text.strip().replace(",", ".")

            try:
                montant = float(raw_montant)
                if montant <= 0:
                    raise ValueError()
            except ValueError:
                context.user_data["waiting_upgrade_prio_amount"] = demande_id
                await update.message.reply_text(
                    "❌ Veuillez saisir un montant valide supérieur à 0 (ex : <code>15</code> ou <code>20.50</code>) :",
                    parse_mode="HTML"
                )
                return

            user_id = update.effective_user.id
            ok, msg_result = self.db_manager.upgrade_demande_to_prioritaire(demande_id, user_id, montant)

            if ok:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Voir mes demandes", callback_data="voir_demandes")]
                ])
                await update.message.reply_text(
                    f"🎉 <b>Félicitations !</b>\n\nVotre dossier #{demande_id} est désormais <b>💎 Prioritaire</b> avec un montant de <b>{montant:.2f} €</b>.\n"
                    "Nos piégeurs traiteront votre demande en priorité !",
                    parse_mode="HTML",
                    reply_markup=kb
                )

                # Notifications automatiques suite à la conversion
                try:
                    with self.db_manager.get_cursor() as cursor:
                        cursor.execute(
                            "SELECT request_number, prenom, orientation, instagram, snapchat, admin_en_charge FROM demandes WHERE id = %s",
                            (int(demande_id),)
                        )
                        d_info = cursor.fetchone()

                    if d_info:
                        req_num = d_info.get("request_number") or demande_id
                        prenom = html.escape(str(d_info.get("prenom") or "la cible"))
                        admin_id = d_info.get("admin_en_charge")

                        # Cas 1 : La demande est déjà prise en charge -> alerte au référent
                        if admin_id:
                            msg_referent = (
                                f"💎 <b>DEMANDE BOOSTÉE EN PRIORITAIRE !</b>\n\n"
                                f"Le client a converti le dossier <b>#{req_num}</b> ({prenom}) en prioritaire.\n"
                                f"💰 <b>Nouveau montant convenu :</b> <code>{montant:.2f} €</code>"
                            )
                            kb_ref = InlineKeyboardMarkup([
                                [InlineKeyboardButton("📄 Voir le dossier", callback_data=f"retour_texte_{demande_id}")]
                            ])
                            try:
                                await context.bot.send_message(
                                    chat_id=admin_id,
                                    text=msg_referent,
                                    parse_mode="HTML",
                                    reply_markup=kb_ref
                                )
                            except Exception as e_notif:
                                logger.warning("Impossible de notifier le référent %s de l'upgrade : %s", admin_id, e_notif)

                        # Cas 2 : La demande est libre en file d'attente -> diffusion staff
                        else:
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
                                msg_staff = (
                                    f"💎 <b>DEMANDE DEVENUE PRIORITAIRE ! (File d'attente)</b>\n\n"
                                    f"Le dossier <b>#{req_num}</b> ({prenom}) est maintenant prioritaire.\n"
                                    f"💰 <b>Montant proposé :</b> <code>{montant:.2f} €</code>\n\n"
                                    "Disponible immédiatement dans les demandes ouvertes."
                                )
                                kb_staff = InlineKeyboardMarkup([
                                    [InlineKeyboardButton("⚡ Prendre en charge", callback_data=f"suivre_demande_{demande_id}")],
                                    [InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")]
                                ])

                                try:
                                    await context.bot.send_message(
                                        chat_id=st_id,
                                        text=msg_staff,
                                        parse_mode="HTML",
                                        reply_markup=kb_staff,
                                        disable_notification=is_silent
                                    )
                                except Exception:
                                    pass

                except Exception as exc_notif:
                    logger.error("Erreur lors de la diffusion des alertes upgrade prio : %s", exc_notif)

            else:
                await update.message.reply_text(f"⚠️ {msg_result}")
            return

        # ==================== CONFIRMATION ZONE DE DANGER ====================
        if update.message.text and context.user_data and context.user_data.get("waiting_danger_confirmation"):
            if self.config.is_owner(update.effective_user.id):
                target = context.user_data.pop("waiting_danger_confirmation")
                context.user_data.pop("pending_danger_target", None)
                saisie = update.message.text.strip()

                if saisie == "Effacer":
                    owner_id = getattr(self.config, "OWNER_ID", 0) or self.db_manager.get_owner_id()
                    success = self.db_manager.purge_table_data(target, owner_id)
                    if success:
                        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 Zone de Danger", callback_data="menu_danger_zone")]])
                        await update.message.reply_text(
                            f"✅ <b>Purge réussie !</b>\n\nLa table ou cible <code>{target}</code> a été vidée.",
                            parse_mode="HTML",
                            reply_markup=kb
                        )
                    else:
                        await update.message.reply_text("❌ Une erreur SQL est survenue lors de l'exécution de la purge.")
                else:
                    await update.message.reply_text(
                        "❌ Mot de confirmation incorrect. L'opération de purge a été <b>annulée</b>.",
                        parse_mode="HTML"
                    )
                return

        # Saisie d'une configuration Owner (Groupe obligatoire, Lien, ou Contact Support)
        if update.message.text and context.user_data and context.user_data.get("waiting_owner_input"):
            if self.config.is_owner(update.effective_user.id):
                mode = context.user_data.pop("waiting_owner_input")
                txt = update.message.text.strip()
                if mode == "required_group_id":
                    try:
                        gid = int(txt)
                        self.db_manager.set_required_group_id(gid)
                        await update.message.reply_text(f"✅ ID du groupe configuré sur : <code>{gid}</code>", parse_mode="HTML")
                    except ValueError:
                        await update.message.reply_text("❌ L'ID doit être un nombre entier relatif (ex: <code>-1001234567890</code>).")
                    msg, kb = self.interface.get_group_subscription_config_menu()
                    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
                    return

                elif mode == "group_subscription_link":
                    self.db_manager.set_group_subscription_link(txt)
                    await update.message.reply_text(f"✅ Lien/Bot d'inscription configuré sur : <code>{html.escape(txt)}</code>", parse_mode="HTML")
                    msg, kb = self.interface.get_group_subscription_config_menu()
                    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
                    return

                elif mode == "support_contact":
                    self.db_manager.set_support_contact(txt)
                    await update.message.reply_text(f"✅ Contact support mis à jour : <code>{html.escape(txt)}</code>", parse_mode="HTML")
                    msg, kb = self.interface.get_support_config_menu()
                    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
                    return

        # 1. Saisie d'un quota par le propriétaire
        if update.message.text and context.user_data and context.user_data.get("waiting_limit_input"):
            if self.config.is_owner(update.effective_user.id):
                raw = update.message.text.strip()
                if raw.isdigit():
                    mode = context.user_data.pop("waiting_limit_input")
                    val = int(raw)
                    key_map = {
                        "total": "max_total_demandes",
                        "user": "max_demandes_per_user",
                        "hetero_insta": "max_hetero_insta",
                        "hetero_snap": "max_hetero_snap",
                        "gay_insta": "max_gay_insta",
                        "gay_snap": "max_gay_snap",
                    }
                    cfg_key = key_map.get(mode, f"max_{mode}")
                    labels = {
                        "total": "Plafond global",
                        "user": "Plafond par client",
                        "hetero_insta": "Plafond Insta Hétéro",
                        "hetero_snap": "Plafond Snap Hétéro",
                        "gay_insta": "Plafond Insta Gay",
                        "gay_snap": "Plafond Snap Gay",
                    }

                    if mode == "total":
                        self.config.set_max_total_demandes(val)
                    elif mode == "user":
                        self.config.set_max_demandes_per_user(val)

                    self.db_manager.set_config_value(cfg_key, str(val))
                    libelle = "Illimité" if val == 0 else str(val)
                    label_desc = labels.get(mode, "Plafond")
                    await update.message.reply_text(f"✅ {label_desc} défini à : <b>{libelle}</b>", parse_mode="HTML")

                    msg, kb = self.interface.get_limits_menu()
                    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
                    return
                else:
                    await update.message.reply_text("❌ Veuillez saisir un nombre entier positif (ex : 0, 5, 10).")
                    return

        # 2. Admin saisit la raison de suppression d'une demande disponible
        if update.message.text and context.user_data and context.user_data.get("waiting_admin_del_reason"):
            if self.config.is_admin(update.effective_user.id):
                demande_id = context.user_data.pop("waiting_admin_del_reason")
                raison = update.message.text.strip()
                demande = self.db_manager.archiver_demande_supprimee(demande_id, f"Suppression admin : {raison}")
                if demande:
                    req_num = demande.get("request_number", demande_id)
                    await update.message.reply_text(
                        f"✅ <b>Demande #{req_num} supprimée et archivée sous « 🗑️ Supprimée ».</b>",
                        parse_mode="HTML"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=demande["user_id"],
                            text=(
                                f"🗑️ <b>Votre demande #{req_num} a été supprimée par l'administration.</b>\n\n"
                                f"<b>Motif :</b> {html.escape(raison)}"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                else:
                    await update.message.reply_text("❌ Demande introuvable.")
                return

        # 3. Client saisit sa raison d'annulation
        if update.message.text and context.user_data and context.user_data.get("waiting_cancel_reason_demande_id"):
            demande_id = context.user_data.pop("waiting_cancel_reason_demande_id")
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
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Accepter l'annulation", callback_data=f"accept_cancel_{demande_id}")],
                    [InlineKeyboardButton("❌ Refuser l'annulation", callback_data=f"refuse_cancel_{demande_id}")]
                ])
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"⚠️ <b>Demande d'annulation (Dossier #{req_num})</b>\n\n"
                            f"Le client souhaite annuler son dossier pour <b>{html.escape(str(d.get('prenom') or ''))}</b>.\n"
                            f"<b>Motif indiqué :</b> « {html.escape(raison)} »\n\n"
                            "Acceptez-vous d'annuler et d'archiver ce dossier ?"
                        ),
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                    await update.message.reply_text(
                        "📨 <b>Votre demande d'annulation a été transmise à votre piégeur.</b>\n"
                        "Vous serez notifié dès qu'il aura pris sa décision.",
                        parse_mode="HTML"
                    )
                except Exception as exc:
                    logger.error("Impossible de contacter le piégeur pour annulation : %s", exc)
                    await update.message.reply_text("❌ Erreur lors de la transmission au piégeur.")
            else:
                self.db_manager.archiver_demande_annulee(demande_id, raison)
                await update.message.reply_text(
                    f"✅ <b>Votre demande #{req_num} a été annulée et archivée.</b>",
                    parse_mode="HTML"
                )
            return

        # Saisie de la raison d'abandon par un opérateur
        if update.message.text and context.user_data and context.user_data.get("waiting_abandon_reason"):
            await self.staff_handlers.statuts.process_abandon_reason(update, context)
            return

        # Recherche dynamique dans les demandes disponibles
        if update.message.text and context.user_data and context.user_data.get("waiting_dispo_search"):
            await self.staff_handlers.dispo.handle_search_text_input(update, context)
            return

        # Recherche dynamique dans les demandes suivies
        if update.message.text and context.user_data and context.user_data.get("waiting_suivi_search"):
            await self.staff_handlers.suivi.handle_search_text_input(update, context)
            return

        # Collecte des fichiers/messages de l'opérateur en cours d'envoi
        if context.user_data and context.user_data.get("contact_session"):
            if await self.staff_handlers.handle_collect_admin_media(update, context):
                return

        # Réponse du Demandeur vers l'opérateur
        if context.user_data and context.user_data.get("replying_to_admin"):
            await self._handle_user_reply_relay(update, context)
            return

        # Édition d'une demande par l'utilisateur (texte)
        if update.message.text and context.user_data and context.user_data.get("editing"):
            await self.edition.handle_edit_text_input(update, context)
            return

        # Fallback compte utilisateur
        await self.compte.handle_text_messages(update, context)

    async def _handle_user_reply_relay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet la réponse de l'utilisateur vers l'opérateur référent avec notification de surveillance."""
        reply_info = context.user_data.pop("replying_to_admin", None)
        if not reply_info:
            return

        admin_id = reply_info["admin_id"]
        demande_id = reply_info["demande_id"]
        user = update.effective_user
        msg = update.message

        is_vip = self.db_manager.is_user_vip(user.id)
        badge_vip = " ⭐ <b>[VIP]</b>" if is_vip else ""

        user_label = f"@{user.username}" if user.username else f"{user.first_name} (ID : {user.id})"
        user_label_esc = html.escape(user_label)
        user_comment = (msg.caption or msg.text or "").strip()
        corps = f"\n\n« {html.escape(user_comment)} »" if user_comment else ""

        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 Répondre à nouveau", callback_data=f"contacter_{demande_id}"),
                InlineKeyboardButton("📄 Voir la fiche", callback_data=f"retour_texte_{demande_id}")
            ]
        ])

        header_text = (
            f"📩 <b>Message du demandeur{badge_vip} (Demande #{demande_id})</b>\n"
            f"De : {user_label_esc}"
            f"{corps}"
        )

        try:
            if msg.photo or msg.video or msg.document:
                await context.bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id,
                    caption=header_text,
                    parse_mode="HTML",
                    reply_markup=admin_keyboard,
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=header_text,
                    parse_mode="HTML",
                    reply_markup=admin_keyboard,
                )

            # ==================== ALERTE SURVEILLANCE (USER_MSG) ====================
            try:
                monitors = self.db_manager.get_monitoring_admins(action="user_msg")
                alias_staff = self.db_manager.get_staff_alias(admin_id)
                alias_staff_esc = html.escape(str(alias_staff or "Opérateur"))

                alert_text = (
                    f"📩 <b>SURVEILLANCE — RÉPONSE DU DEMANDEUR</b>\n\n"
                    f"• <b>Demandeur :</b> {user_label_esc}{badge_vip}\n"
                    f"• <b>Dossier :</b> #{demande_id}\n"
                    f"• <b>Opérateur :</b> {alias_staff_esc} (<code>{admin_id}</code>)"
                    f"{corps}"
                )
                kb_spy = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 Voir le dossier", callback_data=f"retour_texte_{demande_id}")]
                ])

                for mon_id in monitors:
                    if int(mon_id) not in (int(user.id), int(admin_id)):
                        try:
                            if msg.photo or msg.video or msg.document:
                                await context.bot.copy_message(
                                    chat_id=mon_id,
                                    from_chat_id=msg.chat_id,
                                    message_id=msg.message_id,
                                    caption=alert_text,
                                    parse_mode="HTML",
                                    reply_markup=kb_spy
                                )
                            else:
                                await context.bot.send_message(
                                    chat_id=mon_id,
                                    text=alert_text,
                                    parse_mode="HTML",
                                    reply_markup=kb_spy
                                )
                        except Exception:
                            pass
            except Exception as mon_err:
                logger.warning("Erreur surveillance user_msg : %s", mon_err)

            await msg.reply_text(
                "✅ <b>Votre message a été transmis à votre référent !</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Mes demandes", callback_data="voir_demandes")
                ]])
            )

        except Exception as exc:
            logger.error("Erreur renvoi réponse utilisateur vers staff %s : %s", admin_id, exc)
            await msg.reply_text("❌ Une erreur est survenue lors de la transmission de votre message.")

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Redirige vers l'affichage des demandes du client."""
        await self.demande.voir_demandes(update, context)

    async def _handle_cancel_demande_placeholder(self, update: Update, data: str):
        """Vue temporaire d'annulation de demande."""
        query = update.callback_query
        if not query:
            return

        demande_id = html.escape(str(data.replace("cancel_demande_", "")))
        await query.edit_message_text(
            f"🚧 <b>Annulation de demande</b>\n\n"
            f"L'annulation de la demande n°<code>{demande_id}</code> n'est pas encore activée.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Mes demandes", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")],
            ]),
        )