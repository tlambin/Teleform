"""Module de consultation des profils statistiques pour opérateurs (Staff) et demandeurs."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class ProfilsManager:
    """Gestionnaire de rendu des profils de performance (Staff) et d'activité (Demandeur)."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ProfilsManager initialisé avec supervision hiérarchique des demandes")

    def _render_progress_bar(self, rate: float) -> str:
        """Génère une jauge graphique sur 10 blocs."""
        try:
            val = float(rate or 0)
        except (ValueError, TypeError):
            val = 0.0
        filled = int(round(val / 10))
        filled = max(0, min(10, filled))
        empty = 10 - filled
        return f"{'🟩' * filled}{'⬜' * empty}"

    async def _render_clean_view(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
        """Met à jour le message ou supprime la photo existante pour envoyer le profil texte."""
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

    # ==================== ROUTEUR DES CALLBACKS PROFILS ====================

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Aiguille les sous-menus de visualisation des demandes associées aux profils."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        # 1. Menu choix des demandes d'un piégeur
        if data.startswith("staff_view_demandes_"):
            target_staff_id = int(data.replace("staff_view_demandes_", ""))
            await self.show_staff_demandes_menu(query, context, target_staff_id)

        # 2. Listes de dossiers pour un piégeur (suivis vs créés / actifs vs archivés)
        elif data.startswith("staff_list_"):
            parts = data.split("_")
            target_staff_id = int(parts[2])
            category = parts[3]
            page = int(parts[4]) if len(parts) > 4 else 0
            await self.show_staff_demandes_list(query, context, target_staff_id, category, page)

        # 3. Menu choix des demandes d'un utilisateur
        elif data.startswith("user_view_demandes_"):
            parts = data.split("_")
            target_user_id = int(parts[3])
            origin_demande_id = int(parts[4]) if len(parts) > 4 else 0
            await self.show_user_demandes_menu(query, context, target_user_id, origin_demande_id)

        # 4. Listes de demandes pour un client
        elif data.startswith("user_list_"):
            parts = data.split("_")
            target_user_id = int(parts[2])
            origin_demande_id = int(parts[3])
            category = parts[4]
            page = int(parts[5]) if len(parts) > 5 else 0
            await self.show_user_demandes_list(query, context, target_user_id, origin_demande_id, category, page)

        # 5. Consultation d'une archive
        elif data.startswith("archive_view_"):
            payload = data.replace("archive_view_", "")
            if "_back_" in payload:
                parts = payload.split("_back_")
                archive_id = int(parts[0])
                back_callback = parts[1]
            else:
                archive_id = int(payload)
                back_callback = "demandes_archives"
            await self.show_archive_detail(query, context, archive_id, back_callback)

    # ==================== PROFIL OPÉRATEUR / STAFF ====================

    async def show_admin_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int):
        """Affiche la fiche détaillée de performance d'un membre de l'équipe (visible admins ou soi-même)."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        is_owner = self.config.is_owner(user_id)
        is_admin = self.config.is_admin(user_id)

        if user_id != admin_id and not (is_admin or is_owner):
            await query.answer("🔒 Les fiches des piégeurs sont réservées aux administrateurs.", show_alert=True)
            return

        stats = self.db_manager.get_admin_stats(admin_id)
        alias_esc = html.escape(str(stats.get("alias") or f"Membre_{admin_id}"))

        if self.config.is_owner(admin_id):
            date_str = "Direction / Propriétaire"
        else:
            dt_added = stats.get("date_added")
            date_str = dt_added.strftime("%d/%m/%Y") if dt_added and hasattr(dt_added, "strftime") else "Inconnue"

        taux = stats.get("taux_reussite", 0)
        bar = self._render_progress_bar(taux)

        res_label = {"all": "Insta & Snap", "insta": "Insta seul", "snap": "Snap seul"}.get(
            stats.get("perm_reseaux"), str(stats.get("perm_reseaux", "all"))
        )
        typ_label = {"all": "Tous types", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(
            stats.get("perm_type"), str(stats.get("perm_type", "all"))
        )

        montant_total = float(stats.get("montant_total") or 0.0)

        lines = [
            f"🦈 <b>Fiche Piégeur : {alias_esc}</b>",
            f"🆔 ID Telegram : <code>{admin_id}</code>",
            f"📅 Dans l'équipe : <b>{html.escape(date_str)}</b>",
            f"🛡️ Permissions : <i>{html.escape(str(res_label))} | {html.escape(str(typ_label))}</i>\n",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📊 <b>PERFORMANCE OPÉRATIONNELLE</b>\n",
            f"⏳ <b>En cours de traitement :</b> <code>{stats.get('en_cours', 0)}</code>",
            f"✅ <b>Demandes réussies :</b> <code>{stats.get('reussies', 0)}</code>",
            f"❌ <b>Demandes abandonnées :</b> <code>{stats.get('abandonnees', 0)}</code>",
            f"📦 <b>Total demandes clôturées :</b> <code>{stats.get('total_traitees', 0)}</code>\n",
            f"📈 <b>Taux de succès :</b> <b>{taux}%</b>",
            f"{bar}\n",
            "💎 <b>DOSSIERS PRIORITAIRES</b>",
            f"• Demandes prioritaires traitées : <b>{stats.get('prioritaires_traitees', 0)}</b>",
            f"• Volume financier traité : <b>{montant_total:.2f} €</b>"
        ]

        text = "\n".join(lines)
        buttons = [
            [InlineKeyboardButton("📂 Voir ses demandes", callback_data=f"staff_view_demandes_{admin_id}")]
        ]

        if is_owner and user_id != admin_id:
            buttons.append([
                InlineKeyboardButton("🛡️ Modifier ses droits", callback_data=f"perm_staff_{admin_id}"),
                InlineKeyboardButton("🏷️ Renommer", callback_data=f"owner_edit_alias_{admin_id}")
            ])
            buttons.append([InlineKeyboardButton("👥 Retour Équipe Staff", callback_data="gerer_staff")])
        elif (is_admin or is_owner) and user_id != admin_id:
            buttons.append([InlineKeyboardButton("👥 Retour Équipe Staff", callback_data="gerer_staff")])
        else:
            buttons.append([InlineKeyboardButton("🔙 Menu Paramètres", callback_data="parametres")])

        await self._render_clean_view(query, context, text, InlineKeyboardMarkup(buttons))

    # ==================== SOUS-MENUS ET LISTES DEMANDES PIÉGEUR ====================

    async def show_staff_demandes_menu(self, query, context: ContextTypes.DEFAULT_TYPE, staff_id: int):
        alias = self.db_manager.get_staff_alias(staff_id)
        alias_esc = html.escape(str(alias or f"Staff_{staff_id}"))

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM demandes d
                JOIN demandes_suivi ds ON d.id = ds.demande_id
                WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours', '✅ Réussie')
                """,
                (staff_id,)
            )
            cnt_flw_act = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE admin_en_charge = %s", (staff_id,))
            cnt_flw_arch = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM demandes WHERE user_id = %s", (staff_id,))
            cnt_crt_act = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE user_id = %s", (staff_id,))
            cnt_crt_arch = cursor.fetchone()["cnt"]

        text = (
            f"📂 <b>Dossiers associés à {alias_esc}</b>\n\n"
            "Choisissez la catégorie de demandes à consulter :"
        )

        keyboard = [
            [InlineKeyboardButton(f"🔄 Dossiers suivis en cours ({cnt_flw_act})", callback_data=f"staff_list_{staff_id}_flwact_0")],
            [InlineKeyboardButton(f"📦 Dossiers suivis archivés ({cnt_flw_arch})", callback_data=f"staff_list_{staff_id}_flwarch_0")],
            [InlineKeyboardButton(f"📝 Demandes déposées actives ({cnt_crt_act})", callback_data=f"staff_list_{staff_id}_crtact_0")],
            [InlineKeyboardButton(f"🗄️ Demandes déposées archivées ({cnt_crt_arch})", callback_data=f"staff_list_{staff_id}_crtarch_0")],
            [InlineKeyboardButton("↩️ Retour Fiche Piégeur", callback_data=f"profil_admin_{staff_id}")]
        ]

        await self._render_clean_view(query, context, text, InlineKeyboardMarkup(keyboard))

    async def show_staff_demandes_list(self, query, context: ContextTypes.DEFAULT_TYPE, staff_id: int, category: str, page: int = 0):
        alias = self.db_manager.get_staff_alias(staff_id)
        alias_esc = html.escape(str(alias or f"Staff_{staff_id}"))

        limit = 5
        offset = max(0, page * limit)

        titles = {
            "flwact": f"🔄 <b>Dossiers suivis en cours ({alias_esc})</b>",
            "flwarch": f"📦 <b>Dossiers suivis archivés ({alias_esc})</b>",
            "crtact": f"📝 <b>Demandes déposées actives ({alias_esc})</b>",
            "crtarch": f"🗄️ <b>Demandes déposées archivées ({alias_esc})</b>",
        }
        titre = titles.get(category, "Dossiers")
        current_list_callback = f"staff_list_{staff_id}_{category}_{page}"

        items = []
        total = 0

        with self.db_manager.get_cursor() as cursor:
            if category == "flwact":
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours', '✅ Réussie')
                    """,
                    (staff_id,)
                )
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.prenom, d.nom, d.statut, d.prioritaire, d.is_difficile, d.reussie_substatus
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours', '✅ Réussie')
                    ORDER BY d.date_modification DESC
                    LIMIT %s OFFSET %s
                    """,
                    (staff_id, limit, offset)
                )
                items = cursor.fetchall()

            elif category == "flwarch":
                cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE admin_en_charge = %s", (staff_id,))
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT id, original_id, prenom, nom, statut, prioritaire
                    FROM archives WHERE admin_en_charge = %s
                    ORDER BY date_archivage DESC
                    LIMIT %s OFFSET %s
                    """,
                    (staff_id, limit, offset)
                )
                items = cursor.fetchall()

            elif category == "crtact":
                cursor.execute("SELECT COUNT(*) as cnt FROM demandes WHERE user_id = %s", (staff_id,))
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, statut, prioritaire, is_difficile, reussie_substatus
                    FROM demandes WHERE user_id = %s
                    ORDER BY date_creation DESC
                    LIMIT %s OFFSET %s
                    """,
                    (staff_id, limit, offset)
                )
                items = cursor.fetchall()

            elif category == "crtarch":
                cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE user_id = %s", (staff_id,))
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT id, original_id, prenom, nom, statut, prioritaire
                    FROM archives WHERE user_id = %s
                    ORDER BY date_archivage DESC
                    LIMIT %s OFFSET %s
                    """,
                    (staff_id, limit, offset)
                )
                items = cursor.fetchall()

        text_lines = [titre, f"Total : <b>{total}</b> dossier(s)\n"]
        keyboard_rows = []

        if not items:
            text_lines.append("<i>Aucun dossier dans cette catégorie.</i>")
        else:
            for item in items:
                req_num = html.escape(str(item.get("request_number") or item.get("original_id") or item["id"]))
                prenom = html.escape(str(item.get("prenom") or "Inconnu"))
                nom = html.escape(str(item.get("nom") or ""))
                prio_tag = "💎 " if item.get("prioritaire") else ""
                statut_display = html.escape(str(self.db_manager.format_statut_display(
                    item.get("statut", ""),
                    item.get("is_difficile", False),
                    item.get("reussie_substatus")
                )))

                text_lines.append(f"• #{req_num} — {prio_tag}<b>{prenom} {nom}</b> : <code>{statut_display}</code>")

                if category in ("flwact", "crtact"):
                    keyboard_rows.append([
                        InlineKeyboardButton(f"📄 Ouvrir #{req_num} ({prenom})", callback_data=f"retour_texte_{item['id']}_back_{current_list_callback}")
                    ])
                else:
                    keyboard_rows.append([
                        InlineKeyboardButton(f"📦 Archive #{req_num} ({prenom})", callback_data=f"archive_view_{item['id']}_back_{current_list_callback}")
                    ])

        # Pagination
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Précédent", callback_data=f"staff_list_{staff_id}_{category}_{page - 1}"))
        if (offset + limit) < total:
            nav_buttons.append(InlineKeyboardButton("Suivant ➡️", callback_data=f"staff_list_{staff_id}_{category}_{page + 1}"))

        if nav_buttons:
            keyboard_rows.append(nav_buttons)

        keyboard_rows.append([InlineKeyboardButton("↩️ Retour Choix Catégorie", callback_data=f"staff_view_demandes_{staff_id}")])

        await self._render_clean_view(query, context, "\n".join(text_lines), InlineKeyboardMarkup(keyboard_rows))

    # ==================== PROFIL DEMANDEUR / UTILISATEUR ====================

    async def show_user_profile_by_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        if not self.config.is_staff(user_id):
            await query.answer("❌ Réservé aux membres de l'équipe (Staff / Admins).", show_alert=True)
            return

        demande = None
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.date_creation,
                           u.first_name AS user_first_name, u.username AS user_username,
                           u.date_inscription, u.derniere_activite
                    FROM demandes d
                    LEFT JOIN users u ON d.user_id = u.user_id
                    WHERE d.id = %s
                    """,
                    (demande_id,)
                )
                demande = cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur récupération demande #%s : %s", demande_id, exc)

        if not demande:
            await query.answer("❌ Demande introuvable en base.", show_alert=True)
            return

        target_user_id = int(demande["user_id"])
        await self._render_user_profile(query, context, target_user_id, origin_demande_id=demande_id, demande_data=demande)

    async def _render_user_profile(
        self, query, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, origin_demande_id: int = 0, demande_data: dict = None
    ):
        stats = self.db_manager.get_user_stats(target_user_id)

        raw_prenom = (
            (demande_data.get("user_first_name") if demande_data else None)
            or stats.get("prenom")
            or (demande_data.get("user_username") if demande_data else None)
            or f"Utilisateur {target_user_id}"
        )
        prenom_demandeur = html.escape(str(raw_prenom))

        pseudo_val = (demande_data.get("user_username") if demande_data else None) or stats.get("username")
        pseudo = f"@{html.escape(str(pseudo_val))}" if pseudo_val else "Sans @username"

        dt_insc = (demande_data.get("date_inscription") if demande_data else None) or stats.get("date_inscription")
        date_insc = dt_insc.strftime("%d/%m/%Y") if dt_insc and hasattr(dt_insc, "strftime") else "Inconnue"

        dt_act = (demande_data.get("derniere_activite") if demande_data else None) or stats.get("derniere_activite")
        date_act = str(dt_act)[:16] if dt_act else "Inconnue"

        montant_investi = float(stats.get("montant_total_investi") or 0.0)

        lines = [
            f"👤 <b>Fiche Utilisateur : {prenom_demandeur}</b>",
            f"🏷️ Pseudo : {pseudo}",
            f"🆔 ID : <code>{target_user_id}</code>\n",
            f"📅 Inscrit le : <b>{html.escape(date_insc)}</b>",
            f"⏱️ Dernière activité : <i>{html.escape(date_act)}</i>\n",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📋 <b>HISTORIQUE DES DEMANDES</b>\n",
            f"🗳️ <b>Total demandes soumises :</b> <code>{stats.get('total_demandes', 0)}</code>",
            f"⏳ En cours de traitement : <b>{stats.get('en_cours', 0)}</b>",
            f"📨 En attente de prise en charge : <b>{stats.get('en_attente', 0)}</b>",
            f"✅ Terminées avec succès : <b>{stats.get('reussies', 0)}</b>",
            f"❌ Demandes échouées / refusées : <b>{stats.get('abandonnees', 0)}</b>\n",
            f"💎 <b>Demandes payantes :</b> {stats.get('total_prio', 0)} (Total investi : <b>{montant_investi:.2f} €</b>)"
        ]

        text = "\n".join(lines)
        buttons = [
            [InlineKeyboardButton("📋 Voir ses demandes", callback_data=f"user_view_demandes_{target_user_id}_{origin_demande_id}")]
        ]

        if origin_demande_id:
            buttons.append([InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{origin_demande_id}")])
        else:
            buttons.append([InlineKeyboardButton("🔙 Menu Gestion", callback_data="gerer_demandes")])

        await self._render_clean_view(query, context, text, InlineKeyboardMarkup(buttons))

    # ==================== SOUS-MENUS ET LISTES DEMANDES CLIENT ====================

    async def show_user_demandes_menu(self, query, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, origin_demande_id: int):
        viewer_id = query.from_user.id
        is_admin = self.config.is_admin(viewer_id) or self.config.is_owner(viewer_id)

        keyboard = []

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM demandes d
                JOIN demandes_suivi ds ON d.id = ds.demande_id
                WHERE d.user_id = %s AND ds.admin_id = %s
                """,
                (target_user_id, viewer_id)
            )
            cnt_mine = cursor.fetchone()["cnt"]

            keyboard.append([
                InlineKeyboardButton(f"🎯 Demandes dont je m'occupe ({cnt_mine})", callback_data=f"user_list_{target_user_id}_{origin_demande_id}_mine_0")
            ])

            if is_admin:
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM demandes WHERE user_id = %s AND statut IN ('📥 Reçue', '🎯 Assignée (VIP)', '⏳ En attente', '🔄 En cours')",
                    (target_user_id,)
                )
                cnt_all_act = cursor.fetchone()["cnt"]

                cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE user_id = %s", (target_user_id,))
                cnt_all_arch = cursor.fetchone()["cnt"]

                keyboard.append([
                    InlineKeyboardButton(f"🛡️ [Admin] Toutes ses demandes en cours ({cnt_all_act})", callback_data=f"user_list_{target_user_id}_{origin_demande_id}_allact_0")
                ])
                keyboard.append([
                    InlineKeyboardButton(f"🛡️ [Admin] Toutes ses archives ({cnt_all_arch})", callback_data=f"user_list_{target_user_id}_{origin_demande_id}_allarch_0")
                ])

        back_cb = f"profil_demande_{origin_demande_id}" if origin_demande_id else "gerer_demandes"
        keyboard.append([InlineKeyboardButton("↩️ Retour Profil Demandeur", callback_data=back_cb)])

        role_str = "Administrateur (Supervision totale)" if is_admin else "Opérateur (Staff)"
        text = (
            f"📋 <b>Demandes de l'utilisateur</b>\n"
            f"Votre rôle : <i>{html.escape(role_str)}</i>\n\n"
            "Sélectionnez la vue souhaitée :"
        )

        await self._render_clean_view(query, context, text, InlineKeyboardMarkup(keyboard))

    async def show_user_demandes_list(
        self, query, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, origin_demande_id: int, category: str, page: int = 0
    ):
        viewer_id = query.from_user.id
        is_admin = self.config.is_admin(viewer_id) or self.config.is_owner(viewer_id)

        if category in ("allact", "allarch") and not is_admin:
            await query.answer("❌ Consultation globale réservée aux administrateurs.", show_alert=True)
            return

        limit = 5
        offset = max(0, page * limit)

        titles = {
            "mine": "🎯 <b>Demandes de cet utilisateur sous votre charge</b>",
            "allact": "🛡️ <b>Toutes les demandes actives de cet utilisateur</b>",
            "allarch": "🛡️ <b>Toutes les archives de cet utilisateur</b>",
        }
        titre = titles.get(category, "Dossiers")
        current_list_callback = f"user_list_{target_user_id}_{origin_demande_id}_{category}_{page}"

        items = []
        total = 0

        with self.db_manager.get_cursor() as cursor:
            if category == "mine":
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE d.user_id = %s AND ds.admin_id = %s
                    """,
                    (target_user_id, viewer_id)
                )
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.prenom, d.nom, d.statut, d.prioritaire, d.is_difficile, d.reussie_substatus
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE d.user_id = %s AND ds.admin_id = %s
                    ORDER BY d.date_modification DESC
                    LIMIT %s OFFSET %s
                    """,
                    (target_user_id, viewer_id, limit, offset)
                )
                items = cursor.fetchall()

            elif category == "allact":
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM demandes WHERE user_id = %s AND statut IN ('📥 Reçue', '🎯 Assignée (VIP)', '⏳ En attente', '🔄 En cours')",
                    (target_user_id,)
                )
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, statut, prioritaire, is_difficile, reussie_substatus, admin_en_charge
                    FROM demandes
                    WHERE user_id = %s AND statut IN ('📥 Reçue', '🎯 Assignée (VIP)', '⏳ En attente', '🔄 En cours')
                    ORDER BY date_modification DESC
                    LIMIT %s OFFSET %s
                    """,
                    (target_user_id, limit, offset)
                )
                items = cursor.fetchall()

            elif category == "allarch":
                cursor.execute("SELECT COUNT(*) as cnt FROM archives WHERE user_id = %s", (target_user_id,))
                total = cursor.fetchone()["cnt"]

                cursor.execute(
                    """
                    SELECT id, original_id, prenom, nom, statut, prioritaire, admin_en_charge
                    FROM archives WHERE user_id = %s
                    ORDER BY date_archivage DESC
                    LIMIT %s OFFSET %s
                    """,
                    (target_user_id, limit, offset)
                )
                items = cursor.fetchall()

        text_lines = [titre, f"Total : <b>{total}</b> dossier(s)\n"]
        keyboard_rows = []

        if not items:
            text_lines.append("<i>Aucun dossier trouvé dans cette sélection.</i>")
        else:
            for item in items:
                req_num = html.escape(str(item.get("request_number") or item.get("original_id") or item["id"]))
                prenom = html.escape(str(item.get("prenom") or "Inconnu"))
                nom = html.escape(str(item.get("nom") or ""))
                prio_tag = "💎 " if item.get("prioritaire") else ""
                statut_display = html.escape(str(self.db_manager.format_statut_display(
                    item.get("statut", ""),
                    item.get("is_difficile", False),
                    item.get("reussie_substatus")
                )))

                assign_info = ""
                if is_admin and item.get("admin_en_charge"):
                    alias_en_charge = self.db_manager.get_staff_alias(item["admin_en_charge"])
                    assign_info = f" (Par: {html.escape(str(alias_en_charge))})"

                text_lines.append(f"• #{req_num} — {prio_tag}<b>{prenom} {nom}</b> : <code>{statut_display}</code>{assign_info}")

                if category in ("mine", "allact"):
                    keyboard_rows.append([
                        InlineKeyboardButton(f"📄 Ouvrir #{req_num} ({prenom})", callback_data=f"retour_texte_{item['id']}_back_{current_list_callback}")
                    ])
                else:
                    keyboard_rows.append([
                        InlineKeyboardButton(f"📦 Archive #{req_num} ({prenom})", callback_data=f"archive_view_{item['id']}_back_{current_list_callback}")
                    ])

        # Pagination
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Précédent", callback_data=f"user_list_{target_user_id}_{origin_demande_id}_{category}_{page - 1}"))
        if (offset + limit) < total:
            nav_buttons.append(InlineKeyboardButton("Suivant ➡️", callback_data=f"user_list_{target_user_id}_{origin_demande_id}_{category}_{page + 1}"))

        if nav_buttons:
            keyboard_rows.append(nav_buttons)

        keyboard_rows.append([InlineKeyboardButton("↩️ Retour Choix Vue", callback_data=f"user_view_demandes_{target_user_id}_{origin_demande_id}")])

        await self._render_clean_view(query, context, "\n".join(text_lines), InlineKeyboardMarkup(keyboard_rows))

    # ==================== FICHE DÉTAILLÉE D'UNE ARCHIVE ====================

    async def show_archive_detail(self, query, context: ContextTypes.DEFAULT_TYPE, archive_id: int, back_callback: str):
        """Affiche la fiche complète et statique d'une archive avec bouton de retour personnalisé."""
        archive = self.db_manager.get_archive_by_id(archive_id)
        if not archive:
            await query.answer("❌ Archive introuvable.", show_alert=True)
            return

        req_num = html.escape(str(archive.get("original_id", archive["id"])))
        prenom = html.escape(str(archive.get("prenom") or "Non précisé"))
        nom = html.escape(str(archive.get("nom") or ""))
        age = html.escape(str(archive.get("age") or "Non précisé"))
        loc = html.escape(str(archive.get("localisation") or "Non précisée"))
        insta = f"@{html.escape(archive['instagram'].lstrip('@'))}" if archive.get("instagram") else "Aucun"
        snap = html.escape(str(archive.get("snapchat") or "Aucun"))
        details = html.escape(str(archive.get("details") or "Aucun détail complémentaire"))

        dt_arch = archive.get("date_archivage")
        date_arch_str = convert_utc_to_paris(dt_arch).strftime("%d/%m/%Y à %H:%M") if dt_arch else "Inconnue"

        admin_id = archive.get("admin_en_charge")
        admin_alias = self.db_manager.get_staff_alias(admin_id) if admin_id else "Aucun"

        statut_display = html.escape(str(self.db_manager.format_statut_display(
            archive.get("statut", ""),
            archive.get("is_difficile", False),
            archive.get("reussie_substatus")
        )))
        type_str = "💎 Prioritaire (Payante)" if archive.get("prioritaire") else "Standard (Gratuite)"

        text = (
            f"📦 <b>Archive Dossier #{req_num}</b>\n\n"
            f"• <b>Cible :</b> {prenom} {nom} ({age} ans)\n"
            f"• <b>Localisation :</b> {loc}\n"
            f"• <b>Instagram :</b> {insta}\n"
            f"• <b>Snapchat :</b> {snap}\n"
            f"• <b>Type de demande :</b> {html.escape(type_str)}\n"
            f"• <b>Statut final :</b> <code>{statut_display}</code>\n"
            f"• <b>Référent en charge :</b> {html.escape(str(admin_alias))}\n"
            f"• <b>Archivé le :</b> {html.escape(date_arch_str)}\n\n"
            f"📝 <b>Détails / Notes :</b>\n« {details} »"
        )

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Retour à la liste", callback_data=back_callback)
        ]])

        await self._render_clean_view(query, context, text, keyboard)