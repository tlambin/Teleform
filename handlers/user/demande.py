"""Gestion de la consultation et du cycle de vie des demandes utilisateur."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class DemandeManager:
    """Gestionnaire d'affichage, de navigation et de vérification des quotas."""

    ACTIVE_STATUSES = ("📥 Reçue", "⏳ En attente", "🔄 En cours")

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager
        logger.info("DemandeManager initialisé avec support Annulation, Archives, Rehausse Tarif, Conversion Prioritaire et Filtrage Paiements")

    def check_creation_quota(self, user_id: int) -> tuple[bool, str]:
        """Contrôle les plafonds global et individuel avant création (contourné pour VIP)."""
        if self.db_manager.is_user_vip(user_id):
            return True, ""

        placeholders = ", ".join(["%s"] * len(self.ACTIVE_STATUSES))
        status_filter = f"statut IN ({placeholders})"

        # 1. Quota global
        max_total = self.config.get_max_total_demandes()
        if max_total > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM demandes WHERE {status_filter}",
                    self.ACTIVE_STATUSES,
                )
                row = cursor.fetchone()
                total_actif = row["total"] if row else 0

            if total_actif >= max_total:
                return False, (
                    "🚫 <b>Service complet</b>\n\n"
                    "Le plafond global de demandes simultanées sur la plateforme a été atteint.\n"
                    "Merci de réessayer un peu plus tard."
                )

        # 2. Quota individuel
        max_user = self.config.get_max_demandes_per_user()
        if max_user > 0:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS count_user FROM demandes WHERE user_id = %s AND {status_filter}",
                    (int(user_id), *self.ACTIVE_STATUSES),
                )
                row = cursor.fetchone()
                user_actif = row["count_user"] if row else 0

            if user_actif >= max_user:
                return False, (
                    "⚠️ <b>Limite atteinte</b>\n\n"
                    f"Vous avez déjà <b>{user_actif}/{max_user}</b> demande(s) en cours de traitement.\n"
                    "Attendez qu'une de vos demandes soit finalisée avant d'en ouvrir une nouvelle.\n\n"
                    "<i>⭐ Devenez membre VIP pour débloquer les demandes illimitées !</i>"
                )

        return True, ""

    async def voir_demandes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée pour afficher les demandes de l'utilisateur."""
        user = update.effective_user
        if not user:
            return

        if update.callback_query:
            await update.callback_query.answer()
            await self.show_demande_page(update, context, user.id, page=0, edit_message=True)
        else:
            await self.account_manager.ensure_user_registered(update)
            await self.show_demande_page(update, context, user.id, page=0, edit_message=False)

    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Gère la pagination des demandes actives et des archives."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        parts = callback_data.split("_")

        # 1. Pagination des demandes actives (nav_page_X)
        if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
            target_page = int(parts[2])
            await self.show_demande_page(update, context, update.effective_user.id, page=target_page, edit_message=True)

        # 2. Pagination des archives client (user_arch_page_X)
        elif len(parts) >= 4 and parts[1] == "arch" and parts[2] == "page" and parts[3].isdigit():
            target_page = int(parts[3])
            await self.show_user_archive_page(update, context, update.effective_user.id, page=target_page)

        # 3. Accès direct aux archives client
        elif callback_data == "mes_archives":
            await self.show_user_archive_page(update, context, update.effective_user.id, page=0)

        else:
            await self.voir_demandes(update, context)

    async def show_demande_page(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        page: int = 0,
        edit_message: bool = True
    ):
        """Affiche une demande à la fois avec sa photo obligatoire et sa pagination."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM demandes WHERE user_id = %s", (int(user_id),))
                count_res = cursor.fetchone()
                total_pages = count_res["total"] if count_res else 0

                if total_pages == 0:
                    await self._send_no_requests_message(update, context, edit_message, user_id)
                    return

                page = max(0, min(page, total_pages - 1))

                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, age, localisation,
                           photo_id, statut, is_difficile, reussie_substatus,
                           prioritaire, montant, date_creation,
                           date_modification, instagram, snapchat, details,
                           admin_en_charge, last_vip_reminder, paiement_statut
                    FROM demandes
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1 OFFSET %s
                    """,
                    (int(user_id), page),
                )
                demande = cursor.fetchone()

            if not demande:
                await self._send_no_requests_message(update, context, edit_message, user_id)
                return

            caption_text = self._format_demande_card(demande, page, total_pages)
            keyboard = self._build_navigation_keyboard(demande, page, total_pages, user_id)
            photo_id = demande.get("photo_id")
            chat_id = update.effective_chat.id if update.effective_chat else None

            if edit_message and update.callback_query and update.callback_query.message:
                query = update.callback_query

                if query.message.photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=photo_id, caption=caption_text, parse_mode="HTML"),
                        reply_markup=keyboard,
                    )
                else:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    if chat_id:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo_id,
                            caption=caption_text,
                            parse_mode="HTML",
                            reply_markup=keyboard,
                        )
            else:
                if chat_id:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_id,
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )

        except Exception as exc:
            logger.error("Erreur consultation demandes : %s", exc, exc_info=True)
            await self._send_error_message(update, context, edit_message)

    def _format_demande_card(self, demande: dict, current_page: int, total_pages: int) -> str:
        """Met en forme la fiche d'une demande avec échappement HTML sécurisé."""
        type_badge = "💎 Prioritaire" if demande.get("prioritaire") else "📝 Standard"

        montant = float(demande.get("montant") or 0.0)
        montant_str = f" - <b>{montant:.2f} €</b>" if demande.get("prioritaire") else ""

        prenom_esc = html.escape(demande.get("prenom") or "")
        nom_esc = html.escape(demande.get("nom") or "")
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Non renseigné"
        loc_esc = html.escape(str(demande.get("localisation") or "Non précisée"))

        statut_label = self.db_manager.format_statut_display(
            demande.get("statut", "📥 Reçue"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus")
        )
        statut_esc = html.escape(statut_label)
        age_str = demande.get("age") if demande.get("age") is not None else "?"

        lignes = [
            f"📋 <b>Demande #{demande.get('request_number', demande['id'])}</b> ({current_page + 1}/{total_pages})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({age_str} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {type_badge}{montant_str}",
            f"📊 <b>Statut :</b> <code>{statut_esc}</code>"
        ]

        admin_id = demande.get("admin_en_charge")
        if admin_id:
            alias = self.db_manager.get_staff_alias(admin_id)
            lignes.append(f"👨‍💼 <b>Référent :</b> {html.escape(alias or 'Opérateur en charge')}")

        reseaux = []
        if demande.get("instagram"):
            ig = html.escape(str(demande["instagram"]))
            reseaux.append(f"📷 <a href='https://instagram.com/{ig}'>@{ig}</a>")
        if demande.get("snapchat"):
            snap = html.escape(str(demande["snapchat"]))
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{snap}'>{snap}</a>")
        if reseaux:
            lines_str = " | ".join(reseaux)
            lignes.append(f"🌐 <b>Réseaux :</b> {lines_str}")

        if demande.get("details"):
            det = str(demande["details"])
            det_short = (det[:150] + "...") if len(det) > 150 else det
            lignes.append(f"💬 <b>Remarque :</b> <i>{html.escape(det_short)}</i>")

        dt_crea = demande.get("date_creation")
        crea_str = convert_utc_to_paris(dt_crea).strftime("%d/%m/%Y à %H:%M") if dt_crea else "?"
        lignes.append(f"\n📅 <i>Créée le {crea_str}</i>")

        return "\n".join(lignes)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int, user_id: int) -> InlineKeyboardMarkup:
        """Génère les boutons d'actions selon le statut et les méthodes de paiement configurées."""
        buttons = []
        demande_id = demande["id"]
        admin_en_charge = demande.get("admin_en_charge")
        statut_raw = str(demande.get("statut") or "").strip()
        is_prio = bool(demande.get("prioritaire"))
        is_vip = self.db_manager.is_user_vip(user_id)
        montant = float(demande.get("montant") or 0.0)
        paiement_statut = demande.get("paiement_statut")

        # 1. Demande terminée en attente de règlement : options selon les préférences du piégeur
        if statut_raw == "✅ Réussie" and is_prio and paiement_statut == "en_attente":
            methods = (
                self.db_manager.get_staff_payment_methods(admin_en_charge)
                if admin_en_charge
                else {"accept_stars": True, "accept_direct": True}
            )
            pay_row = []
            if methods.get("accept_stars", True):
                pay_row.append(InlineKeyboardButton("⭐ Payer en Stars", callback_data=f"pay_stars_prio_{demande_id}"))
            if methods.get("accept_direct", True):
                pay_row.append(InlineKeyboardButton("💬 Convenir du règlement", callback_data=f"pay_contact_prio_{demande_id}"))

            if pay_row:
                buttons.append(pay_row)

        # 2. Conversion en Prioritaire pour les demandes Standard encore ouvertes
        if not is_prio and statut_raw not in ["✅ Réussie", "❌ Annulée", "❌ Abandonnée"]:
            buttons.append([
                InlineKeyboardButton("💎 Passer en Prioritaire", callback_data=f"upgrade_prio_{demande_id}")
            ])

        # 3. Actions sur le dossier selon son avancement
        if not admin_en_charge and ("reçue" in statut_raw.lower() or "recue" in statut_raw.lower()):
            # Demande NON prise en charge : Modification complète et Suppression directe
            buttons.append([
                InlineKeyboardButton("✏️ Modifier", callback_data=f"modify_{demande_id}"),
                InlineKeyboardButton("🗑️ Supprimer", callback_data=f"delete_{demande_id}")
            ])
        elif statut_raw not in ["✅ Réussie", "❌ Annulée", "❌ Abandonnée"]:
            # Demande PRISE EN CHARGE (en attente ou en cours)
            action_row = [
                InlineKeyboardButton("❌ Demander l'annulation", callback_data=f"ask_cancel_demande_{demande_id}")
            ]
            if is_prio:
                action_row.insert(0, InlineKeyboardButton(f"💰 Rehausser le tarif ({montant:.2f} €)", callback_data=f"modify_{demande_id}"))
            buttons.append(action_row)

        # 4. Boutons de contact et de relance si un opérateur est assigné
        if admin_en_charge:
            contact_btn = InlineKeyboardButton("💬 Contacter mon référent", callback_data=f"vip_contact_admin_{demande_id}")
            if is_vip or is_prio:
                relance_btn = InlineKeyboardButton("🔔 Relancer (Gratuit)", callback_data=f"remind_admin_free_{demande_id}")
            else:
                relance_btn = InlineKeyboardButton("🔔 Relancer (1 €)", callback_data=f"remind_admin_pay_{demande_id}")
            buttons.append([contact_btn, relance_btn])

        # 5. Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"nav_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"nav_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        # 6. Actions complémentaires
        can_create, _ = self.check_creation_quota(user_id)
        btn_creation = (
            InlineKeyboardButton("➕ Nouvelle demande", callback_data="new_demande")
            if can_create
            else InlineKeyboardButton("🔒 Quota atteint", callback_data="quota_reached_info")
        )

        nb_archives = self.db_manager.get_archives_count(user_id=user_id)
        btn_archives = InlineKeyboardButton(f"📦 Mes archives ({nb_archives})", callback_data="mes_archives")

        buttons.append([btn_creation, btn_archives])
        buttons.append([InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")])

        return InlineKeyboardMarkup(buttons)

    # ==================== GESTION DES ARCHIVES CLIENT ====================

    async def show_user_archive_page(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        page: int = 0
    ):
        """Affiche les demandes archivées propres à l'utilisateur."""
        query = update.callback_query
        total_archives = self.db_manager.get_archives_count(user_id=user_id)

        if total_archives == 0:
            msg = (
                "📦 <b>Mes Archives</b>\n\n"
                "Vous n'avez actuellement aucune demande archivée.\n"
                "Les demandes finalisées, clôturées ou annulées apparaîtront ici."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Voir mes demandes actives", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
            if query:
                if query.message and query.message.photo:
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=msg,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                else:
                    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            return

        page = max(0, min(page, total_archives - 1))
        archive_item = self.db_manager.get_archives_page(page=page, user_id=user_id)
        if not archive_item:
            return

        caption_text = self._format_user_archive_card(archive_item, page, total_archives)
        keyboard = self._build_user_archive_keyboard(page, total_archives)
        photo_id = archive_item.get("photo_id")
        chat_id = update.effective_chat.id if update.effective_chat else None

        if query and query.message:
            if query.message.photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_id, caption=caption_text, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
            else:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_id,
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
        else:
            if chat_id:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

    def _format_user_archive_card(self, item: dict, page: int, total: int) -> str:
        """Formate la fiche d'une archive pour la vue du demandeur."""
        prenom_esc = html.escape(str(item.get("prenom") or ""))
        nom_esc = html.escape(str(item.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Non renseigné"
        loc_esc = html.escape(str(item.get("localisation") or "Non précisée"))
        statut_esc = html.escape(str(item.get("statut") or "Archivée"))
        num = item.get("original_id") or item.get("id")

        type_badge = "💎 Prioritaire" if item.get("prioritaire") else "📝 Standard"

        dt_crea = item.get("date_creation")
        crea_str = convert_utc_to_paris(dt_crea).strftime("%d/%m/%Y") if dt_crea else "?"

        dt_arch = item.get("date_archivage")
        arch_str = convert_utc_to_paris(dt_arch).strftime("%d/%m/%Y") if dt_arch else "?"

        lines = [
            f"📦 <b>Archive dossier #{num}</b> ({page + 1}/{total})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({item.get('age', '?')} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {type_badge}",
            f"📊 <b>Statut final :</b> <code>{statut_esc}</code>",
        ]

        admin_charge = item.get("admin_en_charge")
        if admin_charge:
            alias = self.db_manager.get_staff_alias(admin_charge)
            lines.append(f"👨‍💼 <b>Traité par :</b> {html.escape(alias or 'Opérateur')}")
        else:
            lines.append("👨‍💼 <b>Traité par :</b> <i>Équipe support</i>")

        if item.get("details"):
            det_esc = html.escape(str(item["details"]))
            lines.append(f"📝 <b>Détails / Note :</b> {det_esc}")

        lines.extend([
            f"\n📅 <i>Déposée le : {crea_str}</i>",
            f"🗄️ <i>Archivée le : {arch_str}</i>",
        ])
        return "\n".join(lines)

    def _build_user_archive_keyboard(self, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit la barre de navigation pour les archives client."""
        buttons = []
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"user_arch_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"user_arch_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([
            InlineKeyboardButton("📋 Retour à mes demandes", callback_data="voir_demandes"),
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])
        return InlineKeyboardMarkup(buttons)

    async def _send_no_requests_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool, user_id: int):
        """Message affiché quand aucune demande n'est enregistrée."""
        can_create, _ = self.check_creation_quota(user_id)
        btn_creation = (
            InlineKeyboardButton("➕ Créer une demande", callback_data="new_demande")
            if can_create
            else InlineKeyboardButton("🔒 Quota atteint", callback_data="quota_reached_info")
        )

        nb_archives = self.db_manager.get_archives_count(user_id=user_id)
        btn_archives = InlineKeyboardButton(f"📦 Mes archives ({nb_archives})", callback_data="mes_archives")

        text = (
            "📭 <b>Aucune demande active</b>\n\n"
            "Vous n'avez pas encore soumis de demande.\n"
            "Cliquez ci-dessous pour en créer une ou consultez votre historique :"
        )
        keyboard = InlineKeyboardMarkup([
            [btn_creation],
            [btn_archives],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])

        chat_id = update.effective_chat.id if update.effective_chat else None

        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_error_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool):
        """Message en cas de problème de connexion base."""
        text = "❌ <b>Erreur technique</b> lors de la récupération de vos demandes."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        chat_id = update.effective_chat.id if update.effective_chat else None

        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                if chat_id:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)