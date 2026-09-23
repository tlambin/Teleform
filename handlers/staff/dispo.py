"""Module de gestion, filtrage dynamique et recherche des demandes disponibles avec support de la période d'essai."""

from datetime import datetime
import html
import logging
import random
import re
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris
from .notifs import NotifsManager

logger = logging.getLogger(__name__)


def format_date_fr(val) -> str:
    """Convertit une date ou un timestamp au format strict JJ/MM/AAAA."""
    if not val:
        return "?"
    if hasattr(val, "strftime"):
        return convert_utc_to_paris(val).strftime("%d/%m/%Y")
    try:
        dt = datetime.strptime(str(val)[:19], "%Y-%m-%d %H:%M:%S")
        return convert_utc_to_paris(dt).strftime("%d/%m/%Y")
    except Exception:
        pass
    try:
        parts = str(val)[:10].split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(val)[:10]


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


class DispoManager:
    """Gestionnaire des demandes non assignées avec filtrage, recherche et prise en charge."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        self.notifs_manager = NotifsManager(db_manager, config)
        logger.info("DispoManager initialisé avec disposition conforme et indicateur de rémunération")

    def _get_active_filters(self, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Récupère ou initialise les filtres de la session utilisateur."""
        if "dispo_filters" not in context.user_data:
            context.user_data["dispo_filters"] = {
                "orientation": "all",
                "reseau": "all",
                "age_range": "all",
                "type_demande": "all",
                "search": None,
            }
        return context.user_data["dispo_filters"]

    async def show_demandes_disponibles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée principal."""
        await self.show_demandes_disponibles_page(update, context, page=0)

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Aiguillage des actions spécifiques à la vue disponibles."""
        query = update.callback_query
        if not query:
            return

        filters = self._get_active_filters(context)
        user_id = update.effective_user.id
        is_admin = self.db_manager.is_admin(user_id)
        is_trial = self.db_manager.is_staff_trial(user_id)

        # 0. Information proposition de rémunération déjà en attente
        if data == "dispo_remun_pending_info":
            await query.answer("⏳ Une demande de rémunération a déjà été transmise au client. En attente de sa réponse.", show_alert=True)
            return

        # 1. Prise en charge d'une demande
        if data.startswith("suivre_demande_"):
            demande_id = int(data.replace("suivre_demande_", ""))
            await self.assign_demande_to_admin(update, context, demande_id)
            return

        # 2. Suppression administrative (Admin / Owner)
        elif data.startswith("admin_del_dispo_"):
            if not is_admin:
                await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
                return

            demande_id = int(data.replace("admin_del_dispo_", ""))
            context.user_data["waiting_admin_del_reason"] = demande_id

            msg = (
                f"🗑️ <b>SUPPRESSION DU DOSSIER #{demande_id}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Indiquez au clavier le <b>motif de suppression</b> (non-conformité, cible introuvable, etc.) :\n\n"
                "<i>Ce motif sera consigné dans l'archive sous le statut « 🗑️ Supprimée » et notifié au client.</i>"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="demandes_disponibles")
            ]])
            await self._render_clean_text(query, context, msg, kb)
            return

        # 3. Rémunération : Demande Standard (Admin/Owner -> Solliciter rémunération au client)
        elif data.startswith("dispo_ask_remun_std_"):
            if not is_admin:
                await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
                return

            demande_id = int(data.replace("dispo_ask_remun_std_", ""))
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id, request_number, prenom, user_id FROM demandes WHERE id = %s",
                    (demande_id,)
                )
                dem = cursor.fetchone()

            if not dem:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            req_num = dem.get("request_number", demande_id)
            prenom = html.escape(str(dem.get("prenom") or "votre contact"))
            client_id = dem["user_id"]
            days_exp = self.db_manager.get_remun_expiration_days()

            text_client = (
                f"💰 <b>Proposition de prise en charge (Dossier #{req_num})</b>\n\n"
                f"L'équipe a examiné votre demande concernant <b>{prenom}</b>.\n"
                "En raison de la complexité du profil, ce dossier nécessite une <b>rémunération</b> "
                "pour être pris en charge par nos piégeurs.\n\n"
                "Acceptez-vous d'allouer une gratification pour cette demande ?\n\n"
                "• <b>Oui :</b> Vous choisirez le montant que vous souhaitez allouer.\n"
                f"• <b>Non (ou sans réponse sous {days_exp} jours) :</b> Votre demande sera abandonnée et votre quota sera libéré."
            )
            kb_client = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Oui, allouer un montant", callback_data=f"user_accept_remun_std_{demande_id}"),
                    InlineKeyboardButton("❌ Non, abandonner", callback_data=f"user_refuse_remun_std_{demande_id}")
                ]
            ])

            try:
                self.db_manager.set_demande_proposed_price(demande_id, proposed_by=user_id, amount=None)
                await context.bot.send_message(
                    chat_id=client_id,
                    text=text_client,
                    parse_mode="HTML",
                    reply_markup=kb_client
                )
                await query.answer("✅ Demande de rémunération transmise au client !", show_alert=True)
                await self.show_demandes_disponibles_page(update, context, page=0)
            except Exception as err:
                logger.error("Erreur envoi demande rémunération client : %s", err)
                await query.answer("❌ Erreur lors de l'envoi au demandeur.", show_alert=True)
            return

        # 4. Rémunération : Demande Prioritaire (Staff habilité -> Proposer une plus grosse somme)
        elif data.startswith("dispo_ask_remun_prio_"):
            perms = self.db_manager.get_staff_permissions(user_id)
            can_prio = (perms.get("perm_type") in ("all", "prio_only") or is_admin)
            if not can_prio:
                await query.answer("❌ Vous n'avez pas la permission de traiter les dossiers prioritaires.", show_alert=True)
                return

            demande_id = int(data.replace("dispo_ask_remun_prio_", ""))
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id, request_number, prenom, montant FROM demandes WHERE id = %s",
                    (demande_id,)
                )
                dem = cursor.fetchone()

            if not dem:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            montant_actuel = float(dem.get("montant") or 0.0)
            context.user_data["waiting_staff_revalorisation_prix"] = {
                "demande_id": demande_id,
                "current_montant": montant_actuel,
                "staff_id": user_id
            }

            msg = (
                f"💰 <b>REVALORISATION DU TARIF (Dossier #{demande_id})</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Tarif actuel :</b> <code>{montant_actuel:.2f} €</code>\n\n"
                "Indiquez au clavier le <b>nouveau montant</b> que vous réclamez pour traiter ce dossier\n"
                f"(strictement supérieur à <code>{montant_actuel:.2f} €</code>) :\n\n"
                "<i>Le client recevra la proposition. S'il accepte, le dossier vous sera automatiquement assigné.</i>"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="demandes_disponibles")
            ]])
            await self._render_clean_text(query, context, msg, kb)
            return

        # 5. Signaler une demande (Staff standard non-admin)
        elif data.startswith("staff_report_dispo_"):
            demande_id = int(data.replace("staff_report_dispo_", ""))
            context.user_data["waiting_staff_report_reason"] = demande_id

            msg = (
                f"⚠️ <b>SIGNALER LA DEMANDE #{demande_id}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Indiquez au clavier la <b>raison de votre signalement</b> aux administrateurs\n"
                "(ex : <i>« Demande irréalisable sans rémunération »</i>, <i>« Compte inaccessible »</i>, etc.) :"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="demandes_disponibles")
            ]])
            await self._render_clean_text(query, context, msg, kb)
            return

        if is_trial and (data.startswith("dispo_") or data == "dispo_filters_menu"):
            await query.answer("🔒 Période d'essai : vous devez traiter la demande assignée au hasard.", show_alert=True)
            return

        # 6. Menu filtres
        elif data == "dispo_filters_menu":
            await self.show_filters_menu(update, context)
            return

        # 7. Bascule Filtre Orientation
        elif data.startswith("dispo_filter_ori_"):
            val = data.replace("dispo_filter_ori_", "")
            filters["orientation"] = val
            await self.show_filters_menu(update, context)
            return

        # 8. Bascule Filtre Réseaux
        elif data.startswith("dispo_filter_net_"):
            val = data.replace("dispo_filter_net_", "")
            filters["reseau"] = val
            await self.show_filters_menu(update, context)
            return

        # 9. Bascule Filtre Âge
        elif data.startswith("dispo_filter_age_"):
            val = data.replace("dispo_filter_age_", "")
            filters["age_range"] = val
            await self.show_filters_menu(update, context)
            return

        # 10. Bascule Filtre Priorité
        elif data.startswith("dispo_filter_type_"):
            val = data.replace("dispo_filter_type_", "")
            filters["type_demande"] = val
            await self.show_filters_menu(update, context)
            return

        # 11. Reset Filtres
        elif data == "dispo_filter_reset":
            context.user_data["dispo_filters"] = {
                "orientation": "all",
                "reseau": "all",
                "age_range": "all",
                "type_demande": "all",
                "search": None,
            }
            await self.show_filters_menu(update, context)
            return

        # 12. Recherche textuelle
        elif data == "dispo_search_prompt":
            context.user_data["waiting_dispo_search"] = True
            msg = (
                "🔍 <b>RECHERCHE DANS LES DISPONIBLES</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Tapez un mot-clé (prénom, ville, identifiant ou détail) :"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler la recherche", callback_data="dispo_cancel_search")
            ]])
            await self._render_clean_text(query, context, msg, keyboard)
            return

        elif data == "dispo_cancel_search":
            context.user_data.pop("waiting_dispo_search", None)
            await self.show_demandes_disponibles_page(update, context, page=0)
            return

        elif data == "dispo_clear_search":
            filters["search"] = None
            await self.show_demandes_disponibles_page(update, context, page=0)
            return

        # 13. Pioche aléatoire
        elif data == "dispo_random":
            await self.show_random_demande(update, context)
            return

        # 14. Pagination standard
        elif data.startswith("dispo_prev_") or data.startswith("dispo_next_"):
            parts = data.split("_")
            curr = int(parts[2])
            page = max(0, curr - 1) if "prev" in data else curr + 1
            await self.show_demandes_disponibles_page(update, context, page=page)

    async def assign_demande_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Prend en charge la demande avec verrouillage atomique sans gap lock (UPDATE puis INSERT)."""
        query = update.callback_query
        staff_id = update.effective_user.id

        if not self.db_manager.is_staff(staff_id):
            await query.answer("❌ Action réservée aux membres de l'équipe (Staff).", show_alert=True)
            return

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, request_number, prenom, statut, admin_en_charge, orientation
                    FROM demandes WHERE id = %s FOR UPDATE
                    """,
                    (demande_id,)
                )
                demande = cursor.fetchone()

                if not demande:
                    await query.answer("❌ Demande introuvable.", show_alert=True)
                    return

                if int(demande["user_id"]) == int(staff_id):
                    await query.answer("🚫 Vous ne pouvez pas prendre en charge votre propre demande !", show_alert=True)
                    return

                if demande.get("admin_en_charge"):
                    await query.answer("⚠️ Cette demande est déjà prise en charge par un autre opérateur.", show_alert=True)
                    await self.show_demandes_disponibles_page(update, context, page=0)
                    return

                perms = self.db_manager.get_staff_permissions(staff_id)
                p_ori = perms.get("perm_orientation", "all")
                target_ori = demande.get("orientation", "hetero")

                is_compatible = (
                    p_ori in ("all", "bi")
                    or p_ori == target_ori
                    or (target_ori == "bi" and p_ori in ("hetero", "gay"))
                )
                if not is_compatible:
                    await query.answer("❌ Vos permissions d'orientation ne vous permettent pas de prendre ce dossier.", show_alert=True)
                    return

                nouveau_statut = "⏳ En attente"
                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = %s,
                        admin_en_charge = %s,
                        is_difficile = FALSE,
                        reussie_substatus = NULL,
                        proposed_price = NULL,
                        proposed_by = NULL,
                        remun_asked_at = NULL,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (nouveau_statut, staff_id, demande_id)
                )

                # Pattern anti-deadlock : UPDATE puis INSERT si la ligne de suivi n'existait pas encore
                cursor.execute(
                    """
                    UPDATE demandes_suivi
                    SET admin_id = %s, derniere_action = NOW(), statut_suivi = 'active'
                    WHERE demande_id = %s
                    """,
                    (staff_id, demande_id)
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                        VALUES (%s, %s, NOW(), NOW(), 'active')
                        """,
                        (demande_id, staff_id)
                    )

            staff_alias = self.db_manager.get_staff_alias(staff_id)
            real_id = demande["id"]

            await self.notifs_manager.send_status_update_notification(
                context=context,
                user_id=demande["user_id"],
                demande_id=demande["id"],
                request_number=real_id,
                prenom_cible=demande.get("prenom"),
                old_status=demande.get("statut", "📥 Reçue"),
                new_status=nouveau_statut,
                is_difficile=False,
                reussie_substatus=None,
                admin_alias=staff_alias,
            )

            try:
                monitors = self.db_manager.get_monitoring_admins(action="prise_en_charge")
                target_prenom = html.escape(str(demande.get("prenom") or "la cible"))
                alias_esc = html.escape(str(staff_alias))

                alert_text = (
                    f"👀 <b>SURVEILLANCE STAFF — PRISE EN CHARGE</b>\n\n"
                    f"• <b>Opérateur :</b> {alias_esc} (<code>{staff_id}</code>)\n"
                    f"• <b>Dossier :</b> #{real_id} ({target_prenom})\n"
                    f"• <b>Statut :</b> <code>⏳ En attente</code>"
                )
                kb_monitor = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 Ouvrir la fiche", callback_data=f"retour_texte_{demande_id}")]
                ])

                for mon_id in monitors:
                    if int(mon_id) != int(staff_id):
                        try:
                            await context.bot.send_message(
                                chat_id=mon_id,
                                text=alert_text,
                                parse_mode="HTML",
                                reply_markup=kb_monitor
                            )
                        except Exception:
                            pass
            except Exception as mon_err:
                logger.warning("Erreur notification surveillance staff : %s", mon_err)

            await query.answer(f"✅ Demande #{real_id} prise en charge !", show_alert=False)

            is_trial = self.db_manager.is_staff_trial(staff_id)
            trial_notice = "\n\n🧪 <i>Ce dossier constitue votre test d'intégration. Menez-le à bien pour valider votre accès complet !</i>" if is_trial else ""

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Aller à mes suivis", callback_data="demandes_suivies")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            success_msg = (
                f"🎉 <b>PRISE EN CHARGE VALIDÉE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"La demande <b>#{real_id}</b> est passée en statut <b>⏳ En attente</b>.\n"
                f"Le demandeur a été notifié de votre attribution.{trial_notice}"
            )
            await self._render_clean_text(query, context, success_msg, keyboard)

        except Exception as exc:
            logger.error("Erreur prise en charge demande %s : %s", demande_id, exc, exc_info=True)
            await query.answer("❌ Erreur lors de la prise en charge.", show_alert=True)

    async def handle_search_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Récupère le texte de recherche saisi par le membre."""
        if not update.message or not update.message.text:
            return

        search_str = update.message.text.strip()
        context.user_data.pop("waiting_dispo_search", None)
        filters = self._get_active_filters(context)
        filters["search"] = search_str

        await update.message.reply_text(
            f"🔎 Filtre de recherche appliqué : « <b>{html.escape(search_str)}</b> »",
            parse_mode="HTML"
        )
        await self._render_first_page_from_message(update, context)

    async def _render_first_page_from_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Envoie la page 0 suite à un message texte."""
        user_id = update.effective_user.id
        demandes = self._fetch_filtered_demandes(user_id, context)

        if not demandes:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🧹 Effacer la recherche", callback_data="dispo_clear_search")],
                [InlineKeyboardButton("⚙️ Menu Filtres", callback_data="dispo_filters_menu")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            await update.message.reply_text(
                "🔍 Aucun résultat ne correspond à votre recherche.",
                reply_markup=keyboard
            )
            return

        total = len(demandes)
        demande = demandes[0]
        text_card = self._format_demande_card(demande, 0, total, context)
        keyboard = self._build_navigation_keyboard(demande, 0, total, user_id)
        photo_id = demande.get("photo_id")

        if photo_id:
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=photo_id,
                caption=text_card,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=text_card,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

    async def show_filters_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le panneau interactif de réglage des filtres."""
        query = update.callback_query
        filters = self._get_active_filters(context)

        ori = filters.get("orientation", "all")
        ori_all = "✅ Toutes" if ori == "all" else "Toutes"
        ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
        ori_g = "✅ Gay" if ori == "gay" else "Gay"
        ori_bi = "✅ Bi" if ori == "bi" else "Bi"

        net = filters["reseau"]
        net_all = "✅ Tous" if net == "all" else "Tous"
        net_insta = "✅ Insta" if net == "insta" else "Insta"
        net_snap = "✅ Snap" if net == "snap" else "Snap"
        net_both = "✅ Les 2" if net == "both" else "Les 2"

        age = filters["age_range"]
        age_all = "✅ Tous âges" if age == "all" else "Tous âges"
        age_18 = "✅ 18-25" if age == "18_25" else "18-25"
        age_26 = "✅ 26-35" if age == "26_35" else "26-35"
        age_36 = "✅ 36+" if age == "36_plus" else "36+"

        typ = filters["type_demande"]
        typ_all = "✅ Tout type" if typ == "all" else "Tout type"
        typ_prio = "✅ 💎 Prio" if typ == "prio" else "💎 Prio"
        typ_std = "✅ 📝 Standard" if typ == "standard" else "📝 Standard"

        keyboard = [
            [
                InlineKeyboardButton(ori_all, callback_data="dispo_filter_ori_all"),
                InlineKeyboardButton(ori_h, callback_data="dispo_filter_ori_hetero"),
                InlineKeyboardButton(ori_g, callback_data="dispo_filter_ori_gay"),
                InlineKeyboardButton(ori_bi, callback_data="dispo_filter_ori_bi"),
            ],
            [
                InlineKeyboardButton(net_all, callback_data="dispo_filter_net_all"),
                InlineKeyboardButton(net_insta, callback_data="dispo_filter_net_insta"),
                InlineKeyboardButton(net_snap, callback_data="dispo_filter_net_snap"),
                InlineKeyboardButton(net_both, callback_data="dispo_filter_net_both"),
            ],
            [
                InlineKeyboardButton(age_all, callback_data="dispo_filter_age_all"),
                InlineKeyboardButton(age_18, callback_data="dispo_filter_age_18_25"),
                InlineKeyboardButton(age_26, callback_data="dispo_filter_age_26_35"),
                InlineKeyboardButton(age_36, callback_data="dispo_filter_age_36_plus"),
            ],
            [
                InlineKeyboardButton(typ_all, callback_data="dispo_filter_type_all"),
                InlineKeyboardButton(typ_prio, callback_data="dispo_filter_type_prio"),
                InlineKeyboardButton(typ_std, callback_data="dispo_filter_type_standard"),
            ],
            [
                InlineKeyboardButton("🔍 Rechercher par mot-clé", callback_data="dispo_search_prompt"),
                InlineKeyboardButton("🔄 Réinitialiser", callback_data="dispo_filter_reset"),
            ],
            [
                InlineKeyboardButton("🚀 Appliquer les filtres", callback_data="demandes_disponibles")
            ]
        ]

        search_info = f"« {html.escape(filters['search'])} »" if filters["search"] else "<i>Aucun</i>"
        text = (
            "⚙️ <b>FILTRES DES DEMANDES DISPONIBLES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Orientation :</b> {html.escape(ori.upper())}\n"
            f"• <b>Réseaux :</b> {html.escape(net.upper())}\n"
            f"• <b>Âge :</b> {html.escape(age)}\n"
            f"• <b>Formule :</b> {html.escape(typ.upper())}\n"
            f"• <b>Mot-clé :</b> {search_info}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Modifiez les options puis cliquez sur « Appliquer » :</i>"
        )

        await self._render_clean_text(query, context, text, InlineKeyboardMarkup(keyboard))

    def _fetch_filtered_demandes(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
        """Exécute la requête SQL dynamique selon les permissions du staff, les filtres et l'anti-auto-prise avec tri configuré."""
        filters = self._get_active_filters(context)

        join_params = [int(user_id)]
        sql_where = [
            "ds.demande_id IS NULL",
            "d.admin_en_charge IS NULL",
            "d.statut = '📥 Reçue'",
            "d.user_id != %s"
        ]
        where_params = [int(user_id)]

        perms = self.db_manager.get_staff_permissions(user_id)
        p_reseau = perms.get("perm_reseaux", "all")
        p_type = perms.get("perm_type", "all")
        p_ori = perms.get("perm_orientation", "all")

        if p_ori == "hetero":
            sql_where.append("d.orientation IN ('hetero', 'bi')")
        elif p_ori == "gay":
            sql_where.append("d.orientation IN ('gay', 'bi')")

        if p_reseau == "insta":
            sql_where.append("d.instagram IS NOT NULL AND d.instagram != ''")
        elif p_reseau == "snap":
            sql_where.append("d.snapchat IS NOT NULL AND d.snapchat != ''")

        if p_type == "prio_only":
            sql_where.append("d.prioritaire = 1")
        elif p_type == "standard_only":
            sql_where.append("d.prioritaire = 0")

        if filters.get("orientation") and filters["orientation"] != "all":
            sql_where.append("d.orientation = %s")
            where_params.append(filters["orientation"])

        if filters["reseau"] == "insta":
            sql_where.append("d.instagram IS NOT NULL AND d.instagram != ''")
        elif filters["reseau"] == "snap":
            sql_where.append("d.snapchat IS NOT NULL AND d.snapchat != ''")
        elif filters["reseau"] == "both":
            sql_where.append("d.instagram IS NOT NULL AND d.instagram != '' AND d.snapchat IS NOT NULL AND d.snapchat != ''")

        if filters["age_range"] == "18_25":
            sql_where.append("d.age BETWEEN 18 AND 25")
        elif filters["age_range"] == "26_35":
            sql_where.append("d.age BETWEEN 26 AND 35")
        elif filters["age_range"] == "36_plus":
            sql_where.append("d.age >= 36")

        if filters["type_demande"] == "prio":
            sql_where.append("d.prioritaire = 1")
        elif filters["type_demande"] == "standard":
            sql_where.append("d.prioritaire = 0")

        if filters["search"]:
            pattern = f"%{filters['search']}%"
            sql_where.append(
                "(d.prenom LIKE %s OR d.nom LIKE %s OR d.localisation LIKE %s "
                "OR d.instagram LIKE %s OR d.snapchat LIKE %s OR d.details LIKE %s)"
            )
            where_params.extend([pattern] * 6)

        query_sql = f"""
            SELECT d.*, d.user_id AS user_id, u.username, u.first_name AS user_first_name
            FROM demandes d
            LEFT JOIN users u ON d.user_id = u.user_id
            LEFT JOIN demandes_suivi ds ON d.id = ds.demande_id AND ds.admin_id = %s
            WHERE {' AND '.join(sql_where)}
            ORDER BY 
                d.prioritaire DESC,
                CASE WHEN d.prioritaire = 1 THEN d.montant END DESC,
                d.date_creation ASC
        """

        full_params = tuple(join_params + where_params)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(query_sql, full_params)
            return cursor.fetchall()

    async def show_demandes_disponibles_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche la page courante ou l'assignation aléatoire unique en cas de période d'essai."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        is_trial = self.db_manager.is_staff_trial(user_id)

        # ==================== RESTRICTION PÉRIODE D'ESSAI ====================
        if is_trial:
            active_demandes = self.db_manager.get_staff_active_demandes(user_id)
            if active_demandes:
                d = active_demandes[0]
                real_id = d["id"]
                msg = (
                    "🧪 <b>PÉRIODE D'ESSAI EN COURS</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Vous avez déjà un dossier test en cours de traitement (<b>Dossier #{real_id}</b>).\n\n"
                    "<i>Finalisez cette demande pour débloquer l'accès complet à la file générale.</i>"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💌 Ouvrir mes suivis", callback_data="demandes_suivies")],
                    [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
                ])
                await self._render_clean_text(query, context, msg, kb)
                return

            demande = self.db_manager.get_random_demande_for_trial(user_id)
            if not demande:
                msg = (
                    "🧪 <b>PÉRIODE D'ESSAI EN COURS</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🔍 Aucune demande compatible n'est disponible pour le moment pour votre test.\n\n"
                    "<i>Merci de vous reconnecter un peu plus tard.</i>"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Réessayer", callback_data="demandes_disponibles")],
                    [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
                ])
                await self._render_clean_text(query, context, msg, kb)
                return

            text_card = self._format_trial_demande_card(demande)
            demande_id = demande["id"]
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❤️ PRENDRE EN CHARGE ❤️", callback_data=f"suivre_demande_{demande_id}")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            photo_id = demande.get("photo_id")
            if photo_id:
                await self._render_photo(query, context, photo_id, text_card, keyboard)
            else:
                await self._render_clean_text(query, context, text_card, keyboard)
            return

        # ==================== ACCÈS STANDARD ====================
        demandes = self._fetch_filtered_demandes(user_id, context)

        if not demandes:
            msg = (
                "📮 <b>DEMANDES DISPONIBLES</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔍 Aucun dossier ne correspond à vos permissions ou filtres actuels."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Modifier les filtres", callback_data="dispo_filters_menu")],
                [InlineKeyboardButton("🔄 Réinitialiser filtres", callback_data="dispo_filter_reset")],
                [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            await self._render_clean_text(query, context, msg, keyboard)
            return

        total = len(demandes)
        page = max(0, min(page, total - 1))
        demande = demandes[page]

        text_card = self._format_demande_card(demande, page, total, context)
        keyboard = self._build_navigation_keyboard(demande, page, total, user_id)
        photo_id = demande.get("photo_id")

        if photo_id:
            await self._render_photo(query, context, photo_id, text_card, keyboard)
        else:
            await self._render_clean_text(query, context, text_card, keyboard)

    async def show_random_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sélectionne et affiche une demande au hasard."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        demandes = self._fetch_filtered_demandes(update.effective_user.id, context)
        if not demandes:
            await query.answer("❌ Aucune demande disponible pour le tirage.", show_alert=True)
            return

        random_page = random.randint(0, len(demandes) - 1)
        await query.answer(f"🎲 Dossier sélectionné : #{demandes[random_page]['id']}")
        await self.show_demandes_disponibles_page(update, context, page=random_page)

    async def _render_photo(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, keyboard: InlineKeyboardMarkup):
        """Affiche ou met à jour la photo."""
        is_current_photo = bool(query.message and query.message.photo)
        chat_id = query.message.chat_id

        try:
            if is_current_photo:
                new_media = InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML")
                await query.edit_message_media(media=new_media, reply_markup=keyboard)
            else:
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        except Exception as err:
            logger.warning("Recréation photo dispo suite à : %s", err)
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    async def _render_clean_text(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
        """Affiche du texte en supprimant l'ancienne photo si existante."""
        is_current_photo = bool(query.message and query.message.photo)

        if is_current_photo:
            chat_id = query.message.chat_id
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )

    def _format_trial_demande_card(self, demande: dict) -> str:
        """Formate la fiche d'une demande pour un membre à l'essai avec liens sociaux cliquables."""
        label_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
        ori_label = label_map.get(demande.get("orientation", "hetero"), "Hétéro")

        prenom_esc = html.escape(str(demande.get("prenom") or ""))
        nom_esc = html.escape(str(demande.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
        age_str = f"  •  {demande['age']} ans" if demande.get("age") is not None else ""
        loc_esc = html.escape(str(demande.get("localisation") or "Lieu non précisé"))
        real_id = demande["id"]

        is_prio = bool(demande.get("prioritaire"))
        titre = f"💎  <b>Demande Prioritaire #{real_id}</b>" if is_prio else f"📝  <b>Demande Standard #{real_id}</b>"

        lines = [
            titre,
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👤  <b>{nom_complet}{age_str}</b>",
            f"📍  {ori_label} de {loc_esc}"
        ]

        if demande.get("details"):
            det = html.escape(str(demande["details"]).strip())
            lines.append(f"💬  <i>{det}</i>")

        if is_prio:
            montant_val = float(demande.get("montant") or 0.0)
            lines.append(f"💰  <b>{montant_val:.2f} €</b>")

        # Réseaux sociaux avec liens cliquables
        reseaux = []
        if demande.get("instagram"):
            raw_ig = str(demande["instagram"]).strip().lstrip("@")
            ig_esc = html.escape(raw_ig)
            reseaux.append(f'• <b>Instagram :</b> <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
        if demande.get("snapchat"):
            raw_snap = str(demande["snapchat"]).strip().lstrip("@")
            snap_esc = html.escape(raw_snap)
            reseaux.append(f'• <b>Snapchat :</b> <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

        if reseaux:
            lines.append("\n🌐  <b>SES RÉSEAUX</b>")
            lines.extend(reseaux)

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

        lines.append("\n───────  <b>INFOS</b>  ───────")
        dt_crea = demande.get("date_creation")
        lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

        # Historique d'abandon
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

    def _format_demande_card(self, demande: dict, page: int, total: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Formate la fiche d'une demande disponible pour le staff avec liens sociaux cliquables."""
        real_id = demande["id"]
        is_prio = bool(demande.get("prioritaire"))
        titre = f"💎  <b>Demande Prioritaire #{real_id} ({page + 1}/{total})</b>" if is_prio else f"📝  <b>Demande Standard #{real_id} ({page + 1}/{total})</b>"

        prenom_esc = html.escape(str(demande.get("prenom") or ""))
        nom_esc = html.escape(str(demande.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
        age_str = f"  •  {demande['age']} ans" if demande.get("age") is not None else ""

        ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
        ori_label = ori_map.get(str(demande.get("orientation") or "").lower(), "Non précisée")
        loc = html.escape(str(demande.get("localisation") or "Lieu non précisé"))

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
            montant_val = float(demande.get("montant") or 0.0)
            lines.append(f"💰  <b>{montant_val:.2f} €</b>")

        # Réseaux sociaux avec liens cliquables
        reseaux = []
        if demande.get("instagram"):
            raw_ig = str(demande["instagram"]).strip().lstrip("@")
            ig_esc = html.escape(raw_ig)
            reseaux.append(f'• <b>Instagram :</b> <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
        if demande.get("snapchat"):
            raw_snap = str(demande["snapchat"]).strip().lstrip("@")
            snap_esc = html.escape(raw_snap)
            reseaux.append(f'• <b>Snapchat :</b> <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

        if reseaux:
            lines.append("\n🌐  <b>SES RÉSEAUX</b>")
            lines.extend(reseaux)

        # Statut opérationnel
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

        # Mention de rémunération sollicitée
        remun_asked_at = demande.get("remun_asked_at")
        if remun_asked_at:
            lines.append(f" ⏳ <i>Rémunération sollicitée le {format_date_fr(remun_asked_at)}</i>")

        # Infos dossier & Demandeur
        lines.append("\n───────  <b>INFOS</b>  ───────")
        dt_crea = demande.get("date_creation")
        lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

        demandeur = f"@{html.escape(demande['username'])}" if demande.get("username") else (
            html.escape(str(demande.get("user_first_name") or f"User {demande['user_id']}"))
        )
        lines.append(f"<b>Par :</b>  {demandeur} (<code>{demande['user_id']}</code>)")

        # Bloc HISTORIQUE
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

        # Filtres actifs
        f = self._get_active_filters(context)
        active_tags = []
        if f.get("orientation") and f["orientation"] != "all":
            active_tags.append(f"🎯 {f['orientation']}")
        if f.get("reseau") and f["reseau"] != "all":
            active_tags.append(f"🌐 {f['reseau']}")
        if f.get("age_range") and f["age_range"] != "all":
            active_tags.append(f"🎂 {f['age_range']}")
        if f.get("search"):
            active_tags.append(f"🔎 «{f['search']}»")

        if active_tags:
            lines.append(f"\n🏷️ <i>Filtres : {' • '.join(active_tags)}</i>")

        return "\n".join(lines)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int, user_id: int) -> InlineKeyboardMarkup:
        """Construit le clavier des demandes disponibles selon la maquette exacte avec bouton RÉMUNÉRATION dynamique."""
        demande_id = demande["id"]
        is_admin = self.db_manager.is_admin(user_id)
        is_prio = bool(demande.get("prioritaire"))
        is_remun_asked = bool(demande.get("remun_asked_at"))

        buttons = [
            # 1. ❤️ PRENDRE EN CHARGE ❤️
            [InlineKeyboardButton("❤️ PRENDRE EN CHARGE ❤️", callback_data=f"suivre_demande_{demande_id}")]
        ]

        # 2. 👤 PROFIL | 🗑️ SUPPRIMER (Admin) OU 👤 PROFIL | ⚠️ SIGNALER (Staff)
        row_profil = [InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}")]
        if is_admin:
            row_profil.append(InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"admin_del_dispo_{demande_id}"))
        else:
            row_profil.append(InlineKeyboardButton("⚠️ SIGNALER", callback_data=f"staff_report_dispo_{demande_id}"))
        buttons.append(row_profil)

        # 3. 💰 RÉMUNÉRATION 💰 ou ⏳ RÉMUNÉRATION DEMANDÉE
        perms = self.db_manager.get_staff_permissions(user_id)
        can_handle_prio = (perms.get("perm_type") in ("all", "prio_only") or is_admin)

        if is_remun_asked:
            buttons.append([
                InlineKeyboardButton("⏳ RÉMUNÉRATION DEMANDÉE", callback_data="dispo_remun_pending_info")
            ])
        else:
            if not is_prio and is_admin:
                buttons.append([
                    InlineKeyboardButton("💰 RÉMUNÉRATION 💰", callback_data=f"dispo_ask_remun_std_{demande_id}")
                ])
            elif is_prio and can_handle_prio:
                buttons.append([
                    InlineKeyboardButton("💰 RÉMUNÉRATION 💰", callback_data=f"dispo_ask_remun_prio_{demande_id}")
                ])

        # 4. ⬅️ PRÉCÉDENTE | SUIVANTE ➡️
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"dispo_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"dispo_next_{page}"))
        if nav_row:
            buttons.append(nav_row)

        # 5. 🔍 TRIER | 🎲 AU HASARD
        buttons.append([
            InlineKeyboardButton("🔍 TRIER", callback_data="dispo_filters_menu"),
            InlineKeyboardButton("🎲 AU HASARD", callback_data="dispo_random")
        ])

        # 6. ⬅️ RETOUR
        buttons.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)