"""Gestion de la consultation et du cycle de vie des demandes utilisateur."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class DemandeManager:
    """Gestionnaire d'affichage, de navigation et de vérification des quotas."""

    ACTIVE_STATUSES = ("📨 Reçue", "⏳ En attente", "🔄 En cours", "⚠️ Difficile")

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager
        logger.info("DemandeManager initialisé")

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
        """Gère la pagination des demandes (nav_page_X)."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        await query.answer()
        parts = callback_data.split("_")

        if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
            target_page = int(parts[2])
            await self.show_demande_page(update, context, update.effective_user.id, page=target_page, edit_message=True)
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
        """Affiche une demande à la fois avec navigation dynamique."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, age, localisation,
                           photo_id, statut, prioritaire, montant, date_creation,
                           date_modification, instagram, snapchat, details,
                           admin_en_charge, last_vip_reminder
                    FROM demandes
                    WHERE user_id = %s
                    ORDER BY id DESC
                    """,
                    (int(user_id),),
                )
                demandes = cursor.fetchall()

            if not demandes:
                await self._send_no_requests_message(update, edit_message, user_id)
                return

            total_pages = len(demandes)
            page = max(0, min(page, total_pages - 1))
            demande = demandes[page]

            message = self._format_demande_card(demande, page, total_pages)
            keyboard = self._build_navigation_keyboard(demande, page, total_pages, user_id)

            if edit_message and update.callback_query:
                query = update.callback_query
                if query.message and query.message.photo:
                    chat_id = query.message.chat_id
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                else:
                    await query.edit_message_text(
                        message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
            else:
                target = update.message or (update.callback_query.message if update.callback_query else None)
                if target:
                    await target.reply_text(
                        message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )

        except Exception as exc:
            logger.error("Erreur consultation demandes : %s", exc, exc_info=True)
            await self._send_error_message(update, edit_message)

    def _format_demande_card(self, demande: dict, current_page: int, total_pages: int) -> str:
        """Met en forme la fiche d'une demande avec échappement HTML sécurisé."""
        type_badge = "💎 Prioritaire" if demande.get("prioritaire") else "📝 Standard"
        montant_str = f" - <b>{float(demande['montant']):.2f} €</b>" if demande.get("prioritaire") else ""

        prenom_esc = html.escape(demande.get("prenom") or "")
        nom_esc = html.escape(demande.get("nom") or "")
        nom_complet = f"{prenom_esc} {nom_esc}".strip()
        loc_esc = html.escape(str(demande.get("localisation") or ""))
        statut_esc = html.escape(str(demande.get("statut", "En cours")))

        lignes = [
            f"📋 <b>Demande #{demande.get('request_number', demande['id'])}</b> ({current_page + 1}/{total_pages})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {type_badge}{montant_str}",
            f"📊 <b>Statut :</b> <code>{statut_esc}</code>"
        ]

        admin_id = demande.get("admin_en_charge")
        if admin_id:
            alias = self.db_manager.get_admin_alias(admin_id)
            lignes.append(f"👨‍💼 <b>Référent :</b> {html.escape(alias)}")

        reseaux = []
        if demande.get("instagram"):
            ig = html.escape(str(demande["instagram"]))
            reseaux.append(f"📷 <a href='https://instagram.com/{ig}'>@{ig}</a>")
        if demande.get("snapchat"):
            snap = html.escape(str(demande["snapchat"]))
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{snap}'>{snap}</a>")
        if reseaux:
            lignes.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if demande.get("details"):
            det = str(demande["details"])
            det_short = (det[:150] + "...") if len(det) > 150 else det
            lignes.append(f"💬 <b>Remarque :</b> <i>{html.escape(det_short)}</i>")

        date_str = str(demande.get("date_creation", ""))[:16]
        lignes.append(f"\n📅 <i>Créée le {date_str}</i>")

        return "\n".join(lignes)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int, user_id: int) -> InlineKeyboardMarkup:
        """Génère les boutons de pagination, de modification et d'actions de relance."""
        buttons = []
        demande_id = demande["id"]
        statut = demande.get("statut", "")
        admin_en_charge = demande.get("admin_en_charge")
        is_prio = bool(demande.get("prioritaire"))
        is_vip = self.db_manager.is_user_vip(user_id)

        if statut in ["📨 Reçue", "⏳ En attente"]:
            buttons.append([
                InlineKeyboardButton("✏️ Modifier", callback_data=f"modify_{demande_id}"),
                InlineKeyboardButton("🗑️ Supprimer", callback_data=f"delete_{demande_id}")
            ])

        if admin_en_charge:
            actions_row = []

            if is_vip:
                actions_row.append(
                    InlineKeyboardButton("💬 Contacter mon référent", callback_data=f"vip_contact_admin_{demande_id}")
                )

            if is_vip or is_prio:
                actions_row.append(
                    InlineKeyboardButton("🔔 Relancer (Gratuit)", callback_data=f"remind_admin_free_{demande_id}")
                )
            else:
                actions_row.append(
                    InlineKeyboardButton("🔔 Relancer (1 €)", callback_data=f"remind_admin_pay_{demande_id}")
                )

            buttons.append(actions_row)

        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"nav_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"nav_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        can_create, _ = self.check_creation_quota(user_id)
        btn_creation = (
            InlineKeyboardButton("➕ Nouvelle demande", callback_data="new_demande")
            if can_create
            else InlineKeyboardButton("🔒 Quota atteint", callback_data="quota_reached_info")
        )

        buttons.append([
            btn_creation,
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)

    async def _send_no_requests_message(self, update: Update, edit_message: bool, user_id: int):
        """Message affiché quand aucune demande n'est enregistrée."""
        can_create, _ = self.check_creation_quota(user_id)
        btn_creation = (
            InlineKeyboardButton("➕ Créer une demande", callback_data="new_demande")
            if can_create
            else InlineKeyboardButton("🔒 Quota atteint", callback_data="quota_reached_info")
        )

        text = (
            "📭 <b>Aucune demande active</b>\n\n"
            "Vous n'avez pas encore soumis de demande.\n"
            "Cliquez ci-dessous pour en créer une !"
        )
        keyboard = InlineKeyboardMarkup([
            [btn_creation],
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])

        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            target = update.message or (update.callback_query.message if update.callback_query else None)
            if target:
                await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_error_message(self, update: Update, edit_message: bool):
        """Message en cas de problème de connexion base."""
        text = "❌ <b>Erreur technique</b> lors de la récupération de vos demandes."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
        ])
        if edit_message and update.callback_query:
            query = update.callback_query
            if query.message and query.message.photo:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            target = update.message or (update.callback_query.message if update.callback_query else None)
            if target:
                await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)