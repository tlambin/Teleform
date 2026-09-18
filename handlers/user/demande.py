"""Gestion de la consultation et du cycle de vie des demandes utilisateur."""

from datetime import datetime
import html
import logging
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


def format_datetime_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA HH:MM."""
    if not val:
        return "?"
    if hasattr(val, "strftime"):
        return convert_utc_to_paris(val).strftime("%d/%m/%Y %H:%M")
    try:
        dt = datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S")
        return convert_utc_to_paris(dt).strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    try:
        parts = str(val)[:10].split("-")
        time_part = str(val)[11:16] if len(str(val)) >= 16 else "00:00"
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]} {time_part}"
    except Exception:
        pass
    return str(val)[:16]


def clean_reason_text(raw_reason: str) -> str:
    """Nettoie les balises HTML, puces et préfixes de nom déjà enregistrés dans le motif."""
    if not raw_reason:
        return "Non précisée"
    clean = str(raw_reason).strip()
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = re.sub(r"^[•\-\*]\s*", "", clean)
    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0].strip().split()) <= 3:
            clean = parts[1].strip()
    clean = clean.strip(" «»\"'")
    return html.escape(clean) if clean else "Non précisée"


class DemandeManager:
    """Gestionnaire d'affichage, de navigation et de vérification des quotas."""

    ACTIVE_STATUSES = ("📥 Reçue", "⏳ En attente", "🔄 En cours")

    def __init__(self, db_manager, config, account_manager):
        self.db_manager = db_manager
        self.config = config
        self.account_manager = account_manager
        logger.info("DemandeManager initialisé avec charte graphique unifiée et support RBAC")

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
                    "🚫 <b>SERVICE SATURÉ</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Le plafond global des demandes en cours sur la plateforme est atteint.\n\n"
                    "<i>Veuillez patienter ou réessayer un peu plus tard.</i>"
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
                    "⚠️ <b>QUOTA PERSONNEL ATTEINT</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"Vous avez déjà <b>{user_actif}/{max_user}</b> demande(s) actives en traitement.\n\n"
                    "Attendez qu'un dossier se termine pour en créer un autre.\n\n"
                    "⭐ <i>Le statut VIP permet d'ouvrir des demandes en illimité.</i>"
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
                           admin_en_charge, ancien_admin_alias, raison_abandon,
                           last_vip_reminder, paiement_statut
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
        """Formate la fiche côté utilisateur avec numérotation propre et calibrage strict des traits."""
        num_client = total_pages - current_page

        is_prio = bool(demande.get("prioritaire"))
        titre = f"💎  <b>Demande Prioritaire #{num_client} ({current_page + 1}/{total_pages})</b>" if is_prio else f"📝  <b>Demande Standard #{num_client} ({current_page + 1}/{total_pages})</b>"

        prenom_esc = html.escape(str(demande.get("prenom") or ""))
        nom_esc = html.escape(str(demande.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
        age_str = f"  •  {demande['age']} ans" if demande.get("age") is not None else ""

        ori_raw = str(demande.get("orientation") or "").strip().lower()
        ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
        ori_label = ori_map.get(ori_raw, "Non précisée")
        loc = html.escape(str(demande.get("localisation") or "Lieu non précisé").strip())

        lines = [
            titre,
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👤  <b>{nom_complet}{age_str}</b>",
            f"📍  {ori_label} de {loc}"
        ]

        if demande.get("details"):
            det = html.escape(str(demande["details"]).strip())
            lines.append(f"💬  <i>{det}</i>")

        if is_prio:
            montant = float(demande.get("montant") or 0.0)
            lines.append(f"💰  <b>{montant:.2f} €</b>")

        # Réseaux sociaux
        reseaux = []
        if demande.get("instagram"):
            ig = html.escape(str(demande["instagram"]).strip().lstrip("@"))
            reseaux.append(f"• <b>Instagram :</b> @{ig}")
        if demande.get("snapchat"):
            snap = html.escape(str(demande["snapchat"]).strip().lstrip("@"))
            reseaux.append(f"• <b>Snapchat :</b> {snap}")

        if reseaux:
            lines.append("\n🌐  <b>SES RÉSEAUX</b>")
            lines.extend(reseaux)

        # Bloc STATUT
        statut_label = self.db_manager.format_statut_display(
            demande.get("statut", "📥 Reçue"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus")
        )
        lines.append("\n───────  <b>STATUT</b>  ──────")
        lines.append(f" • <b>{html.escape(statut_label)}</b> • ")

        dt_mod = demande.get("date_modification")
        if dt_mod:
            lines.append(f" <i>{format_datetime_fr(dt_mod)}</i>")

        if is_prio:
            p_statut = demande.get("paiement_statut", "non_requis")
            if p_statut == "paye":
                lines.append("\n🟢 <b>Réglé et validé</b>")
            elif p_statut == "en_attente":
                lines.append("\n🟡 <b>En attente de règlement</b>")

        # Gestionnaire (affiché uniquement si assigné)
        admin_id = demande.get("admin_en_charge")
        if admin_id:
            alias = html.escape(str(self.db_manager.get_staff_alias(admin_id) or "Opérateur"))
            lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")
            dt_suivi = demande.get("date_modification")
            if dt_suivi:
                lines.append(f"<b>Depuis le :</b> <i>{format_datetime_fr(dt_suivi)}</i>")

        # Bloc INFOS
        lines.append("\n───────  <b>INFOS</b>  ───────")
        dt_crea = demande.get("date_creation")
        lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

        # Bloc HISTORIQUE (si abandon préalable)
        ancien_alias = demande.get("ancien_admin_alias")
        raw_reason = demande.get("raison_abandon")
        if ancien_alias or raw_reason:
            alias_str = html.escape(str(ancien_alias or "Opérateur"))
            reason_str = clean_reason_text(raw_reason)
            dt_abandon = demande.get("date_modification")
            date_abandon_str = format_datetime_fr(dt_abandon) if dt_abandon else "Date inconnue"

            lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
            lines.append("❌ Abandonné")
            lines.append(f"{alias_str} le {date_abandon_str}")
            lines.append(f"<b>Raison :</b> {reason_str}")

        return "\n".join(lines)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int, user_id: int) -> InlineKeyboardMarkup:
        """Génère les boutons de 'Mes Demandes' selon la maquette et les règles métiers."""
        buttons = []
        demande_id = demande["id"]
        admin_en_charge = demande.get("admin_en_charge")
        statut_raw = str(demande.get("statut") or "").strip()
        is_prio = bool(demande.get("prioritaire"))
        is_vip = self.db_manager.is_user_vip(user_id)
        is_active = statut_raw not in ["✅ Réussie", "❌ Annulée", "❌ Abandonnée"]

        # 1. 💎 PASSER PRIORITAIRE 💎 (si standard active)
        if not is_prio and is_active:
            buttons.append([
                InlineKeyboardButton("💎 PASSER PRIORITAIRE 💎", callback_data=f"upgrade_prio_{demande_id}")
            ])

        # 2. 💰 MODIFIER LE PRIX 💰 (si prio active non assignée)
        if is_prio and is_active and not admin_en_charge:
            buttons.append([
                InlineKeyboardButton("💰 MODIFIER LE PRIX 💰", callback_data=f"modify_{demande_id}")
            ])

        # 3. 💰 AUGMENTER LE PRIX 💰 (si prio active déjà assignée)
        if is_prio and is_active and admin_en_charge:
            buttons.append([
                InlineKeyboardButton("💰 AUGMENTER LE PRIX 💰", callback_data=f"modify_{demande_id}")
            ])

        # 4. ✏️ MODIFIER | 🗑️ SUPPRIMER (uniquement non assignée)
        if is_active and not admin_en_charge:
            buttons.append([
                InlineKeyboardButton("✏️ MODIFIER", callback_data=f"modify_{demande_id}"),
                InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"delete_{demande_id}")
            ])

        # 5. 💬 CONTACT | 🛎️ RELANCER (dès qu'assigné)
        if admin_en_charge and is_active:
            contact_btn = InlineKeyboardButton("💬 CONTACT", callback_data=f"vip_contact_admin_{demande_id}")
            if is_vip or is_prio:
                relance_btn = InlineKeyboardButton("🛎️ RELANCER (Gratuit)", callback_data=f"remind_admin_free_{demande_id}")
            else:
                relance_btn = InlineKeyboardButton("🛎️ RELANCER (1€)", callback_data=f"remind_admin_pay_{demande_id}")
            buttons.append([contact_btn, relance_btn])

        # 6. ⬅️ PRÉCÉDENTE | SUIVANTE ➡️
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"nav_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"nav_page_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

        # 7. 🗳️ CRÉER | 📦 ARCHIVES (X)
        can_create, _ = self.check_creation_quota(user_id)
        btn_creer = (
            InlineKeyboardButton("🗳️ CRÉER", callback_data="new_demande")
            if can_create
            else InlineKeyboardButton("🔒 PLEIN", callback_data="quota_reached_info")
        )
        nb_archives = self.db_manager.get_archives_count(user_id=user_id)
        btn_archives = InlineKeyboardButton(f"📦 ARCHIVES ({nb_archives})", callback_data="mes_archives")
        buttons.append([btn_creer, btn_archives])

        # 8. ⬅️ RETOUR
        buttons.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
        ])

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
                "📦 <b>MES ARCHIVES PERSONNELLES</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Vous n'avez actuellement aucun dossier archivé.\n\n"
                "<i>Les demandes finalisées ou annulées apparaîtront ici automatiquement.</i>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Voir mes demandes actives", callback_data="voir_demandes")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
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
        """Formate la fiche d'une archive pour la vue du demandeur avec numérotation propre."""
        num_archive_client = total - page

        prenom_esc = html.escape(str(item.get("prenom") or ""))
        nom_esc = html.escape(str(item.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
        loc_esc = html.escape(str(item.get("localisation") or "Non précisée"))
        age_str = f"  •  {item['age']} ans" if item.get("age") is not None else ""

        is_prio = bool(item.get("prioritaire"))
        titre = f"💎  <b>Demande Prioritaire #{num_archive_client} ({page + 1}/{total})</b>" if is_prio else f"📝  <b>Demande Standard #{num_archive_client} ({page + 1}/{total})</b>"

        lines = [
            titre,
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👤  <b>{nom_complet}{age_str}</b>",
            f"📍  {loc_esc}"
        ]

        if item.get("details"):
            det_esc = html.escape(str(item["details"]).strip())
            lines.append(f"💬  <i>{det_esc}</i>")

        if is_prio:
            montant = float(item.get("montant") or 0.0)
            lines.append(f"💰  <b>{montant:.2f} €</b>")

        # Réseaux
        reseaux = []
        if item.get("instagram"):
            ig = html.escape(str(item["instagram"]).strip().lstrip("@"))
            reseaux.append(f"• <b>Instagram :</b> @{ig}")
        if item.get("snapchat"):
            snap = html.escape(str(item["snapchat"]).strip().lstrip("@"))
            reseaux.append(f"• <b>Snapchat :</b> {snap}")

        if reseaux:
            lines.append("\n🌐  <b>SES RÉSEAUX</b>")
            lines.extend(reseaux)

        # Bloc STATUT
        statut_label = html.escape(str(item.get("statut") or "Archivée"))
        dt_arch = item.get("date_archivage")

        lines.append("\n───────  <b>STATUT</b>  ──────")
        lines.append(f" • <b>{statut_label}</b> • ")
        if dt_arch:
            lines.append(f" <i>{format_datetime_fr(dt_arch)}</i>")

        # Bloc INFOS
        dt_crea = item.get("date_creation")
        lines.append("\n───────  <b>INFOS</b>  ───────")
        lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

        # Bloc HISTORIQUE
        statut_raw = str(item.get("statut") or "").lower()
        admin_charge = item.get("admin_en_charge")
        alias_admin = html.escape(str(self.db_manager.get_staff_alias(admin_charge) if admin_charge else "Opérateur"))

        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        if "abandon" in statut_raw or "annul" in statut_raw:
            dt_ev = item.get("date_archivage") or item.get("date_modification")
            date_ev_str = format_datetime_fr(dt_ev) if dt_ev else "Date inconnue"
            raw_reason = item.get("raison_abandon") or item.get("details")
            raison = clean_reason_text(raw_reason)

            lines.append("❌ Abandonné")
            lines.append(f"{alias_admin} le {date_ev_str}")
            lines.append(f"<b>Raison :</b> {raison}")
        else:
            montant = float(item.get("montant") or 0.0)
            montant_str = f" ({montant:.2f} €)" if montant > 0 else ""
            dt_ev = item.get("date_livraison") or item.get("date_archivage") or item.get("date_modification")
            date_ev_str = format_datetime_fr(dt_ev) if dt_ev else "Date inconnue"

            lines.append(f"✅ Réussie{montant_str}")
            lines.append(f"{alias_admin} le {date_ev_str}")

        return "\n".join(lines)

    def _build_user_archive_keyboard(self, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit la barre de navigation pour les archives client."""
        buttons = []
        nav_row = []

        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédent", callback_data=f"user_arch_page_{page - 1}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivant ➡️", callback_data=f"user_arch_page_{page + 1}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([
            InlineKeyboardButton("📋 Mes demandes actives", callback_data="voir_demandes"),
            InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")
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
            "📭 <b>AUCUN DOSSIER ACTIF</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Vous n'avez aucune demande en cours de traitement pour le moment.\n\n"
            "<i>Créez votre première demande ou consultez vos archives :</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [btn_creation],
            [btn_archives],
            [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
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
            [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
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