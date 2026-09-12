"""Module de gestion, filtrage dynamique et recherche des demandes disponibles."""

import html
import logging
import random
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes
from .notifs import NotifsManager

logger = logging.getLogger(__name__)


class DispoManager:
    """Gestionnaire des demandes non assignées avec filtrage, recherche et prise en charge."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        self.notifs_manager = NotifsManager(db_manager, config)
        logger.info("DispoManager initialisé")

    def _get_active_filters(self, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Récupère ou initialise les filtres de la session utilisateur."""
        if "dispo_filters" not in context.user_data:
            context.user_data["dispo_filters"] = {
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

        # 1. Prise en charge d'une demande
        if data.startswith("suivre_demande_"):
            demande_id = int(data.replace("suivre_demande_", ""))
            await self.assign_demande_to_admin(update, context, demande_id)
            return

        # 2. Menu filtres
        if data == "dispo_filters_menu":
            await self.show_filters_menu(update, context)
            return

        # 3. Bascule Filtre Réseaux
        elif data.startswith("dispo_filter_net_"):
            val = data.replace("dispo_filter_net_", "")
            filters["reseau"] = val
            await self.show_filters_menu(update, context)
            return

        # 4. Bascule Filtre Âge
        elif data.startswith("dispo_filter_age_"):
            val = data.replace("dispo_filter_age_", "")
            filters["age_range"] = val
            await self.show_filters_menu(update, context)
            return

        # 5. Bascule Filtre Priorité
        elif data.startswith("dispo_filter_type_"):
            val = data.replace("dispo_filter_type_", "")
            filters["type_demande"] = val
            await self.show_filters_menu(update, context)
            return

        # 6. Reset Filtres
        elif data == "dispo_filter_reset":
            context.user_data["dispo_filters"] = {
                "reseau": "all",
                "age_range": "all",
                "type_demande": "all",
                "search": None,
            }
            await self.show_filters_menu(update, context)
            return

        # 7. Lancement de la recherche textuelle
        elif data == "dispo_search_prompt":
            context.user_data["waiting_dispo_search"] = True
            msg = (
                "🔍 <b>Recherche dans les demandes</b>\n\n"
                "Tapez un mot-clé (prénom, ville, identifiant Instagram/Snapchat ou détail) :"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler la recherche", callback_data="dispo_cancel_search")
            ]])
            await self._render_clean_text(query, context, msg, keyboard)
            return

        # 8. Annulation ou réinitialisation de la recherche
        elif data == "dispo_cancel_search":
            context.user_data.pop("waiting_dispo_search", None)
            await self.show_demandes_disponibles_page(update, context, page=0)
            return

        elif data == "dispo_clear_search":
            filters["search"] = None
            await self.show_demandes_disponibles_page(update, context, page=0)
            return

        # 9. Pioche aléatoire
        elif data == "dispo_random":
            await self.show_random_demande(update, context)
            return

        # 10. Pagination standard
        elif data.startswith("dispo_prev_") or data.startswith("dispo_next_"):
            parts = data.split("_")
            curr = int(parts[2])
            page = max(0, curr - 1) if "prev" in data else curr + 1
            await self.show_demandes_disponibles_page(update, context, page=page)

    async def assign_demande_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Prend en charge la demande : bascule à '⏳ En attente' et avertit le demandeur."""
        query = update.callback_query
        admin_id = update.effective_user.id

        if not self.config.is_admin(admin_id):
            await query.answer("❌ Action réservée aux administrateurs.", show_alert=True)
            return

        try:
            with self.db_manager.transaction() as cursor:
                # Vérifier si la demande est encore libre
                cursor.execute(
                    """
                    SELECT id, user_id, request_number, prenom, statut, admin_en_charge
                    FROM demandes WHERE id = %s FOR UPDATE
                    """,
                    (demande_id,)
                )
                demande = cursor.fetchone()

                if not demande:
                    await query.answer("❌ Demande introuvable.", show_alert=True)
                    return

                if demande.get("admin_en_charge"):
                    await query.answer("⚠️ Cette demande est déjà prise en charge par un autre admin.", show_alert=True)
                    await self.show_demandes_disponibles_page(update, context, page=0)
                    return

                # Bascule du statut vers ⏳ En attente
                nouveau_statut = "⏳ En attente"
                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = %s,
                        admin_en_charge = %s,
                        is_difficile = FALSE,
                        reussie_substatus = NULL,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (nouveau_statut, admin_id, demande_id)
                )

                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), 'active')
                    ON DUPLICATE KEY UPDATE 
                        admin_id = VALUES(admin_id),
                        derniere_action = NOW(),
                        statut_suivi = 'active'
                    """,
                    (demande_id, admin_id)
                )

            admin_alias = self.db_manager.get_admin_alias(admin_id)
            req_num = demande.get("request_number", demande_id)

            # Notification au demandeur
            await self.notifs_manager.send_status_update_notification(
                context=context,
                user_id=demande["user_id"],
                demande_id=demande["id"],
                request_number=req_num,
                prenom_cible=demande.get("prenom"),
                old_status=demande.get("statut", "📥 Reçue"),
                new_status=nouveau_statut,
                is_difficile=False,
                reussie_substatus=None,
                admin_alias=admin_alias,
            )

            await query.answer(f"✅ Demande #{req_num} prise en charge !", show_alert=False)

            # Redirection vers les demandes suivies
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Aller à mes demandes suivies", callback_data="demandes_suivies")],
                [InlineKeyboardButton("📮 Continuer dans disponibles", callback_data="demandes_disponibles")]
            ])
            success_msg = (
                f"🎉 <b>Prise en charge validée !</b>\n\n"
                f"La demande <b>#{req_num}</b> est passée en statut <b>⏳ En attente</b>.\n"
                f"Le demandeur a été notifié avec l'explication du statut."
            )
            await self._render_clean_text(query, context, success_msg, keyboard)

        except Exception as exc:
            logger.error("Erreur prise en charge demande %s : %s", demande_id, exc, exc_info=True)
            await query.answer("❌ Erreur lors de la prise en charge.", show_alert=True)

    async def handle_search_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Récupère le texte de recherche saisi par l'admin."""
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
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
            await update.message.reply_text(
                "🔍 Aucun résultat ne correspond à votre recherche.",
                reply_markup=keyboard
            )
            return

        total = len(demandes)
        demande = demandes[0]
        text_card = self._format_demande_card(demande, 0, total, context)
        keyboard = self._build_navigation_keyboard(demande, 0, total)
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

        net = filters["reseau"]
        net_all = "✅ Tous" if net == "all" else "Tous"
        net_insta = "✅ Insta" if net == "insta" else "Insta"
        net_snap = "✅ Snap" if net == "snap" else "Snap"
        net_both = "✅ Les 2" if net == "both" else "Les 2"

        age = filters["age_range"]
        age_all = "✅ Tous âges" if age == "all" else "Tous"
        age_18 = "✅ 18-25" if age == "18_25" else "18-25"
        age_26 = "✅ 26-35" if age == "26_35" else "26-35"
        age_36 = "✅ 36+" if age == "36_plus" else "36+"

        typ = filters["type_demande"]
        typ_all = "✅ Tout type" if typ == "all" else "Tout"
        typ_prio = "✅ 💎 Prio" if typ == "prio" else "💎 Prio"
        typ_std = "✅ 📝 Standard" if typ == "standard" else "📝 Standard"

        keyboard = [
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
                InlineKeyboardButton("🚀 Appliquer et voir les résultats", callback_data="demandes_disponibles")
            ]
        ]

        search_info = f"« {html.escape(filters['search'])} »" if filters["search"] else "<i>Aucun</i>"
        text = (
            "⚙️ <b>Filtres des demandes disponibles</b>\n\n"
            f"• <b>Réseaux :</b> {html.escape(net.upper())}\n"
            f"• <b>Âge :</b> {html.escape(age)}\n"
            f"• <b>Type :</b> {html.escape(typ)}\n"
            f"• <b>Mot-clé :</b> {search_info}\n\n"
            "<i>Cliquez sur un bouton pour modifier le filtre, puis appliquez :</i>"
        )

        await self._render_clean_text(query, context, text, InlineKeyboardMarkup(keyboard))

    def _fetch_filtered_demandes(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
        """Exécute la requête SQL dynamique selon les permissions de l'admin et les filtres choisis."""
        filters = self._get_active_filters(context)

        join_params = [int(user_id)]
        sql_where = [
            "ds.demande_id IS NULL",
            "d.admin_en_charge IS NULL",
            "d.statut = '📥 Reçue'"
        ]
        where_params = []

        # 1. Permissions admin
        perms = self.db_manager.get_admin_permissions(user_id)
        p_reseau = perms.get("perm_reseaux", "all")
        p_type = perms.get("perm_type", "all")

        if p_reseau == "insta":
            sql_where.append("d.instagram IS NOT NULL AND d.instagram != ''")
        elif p_reseau == "snap":
            sql_where.append("d.snapchat IS NOT NULL AND d.snapchat != ''")

        if p_type == "prio_only":
            sql_where.append("d.prioritaire = 1")
        elif p_type == "standard_only":
            sql_where.append("d.prioritaire = 0")

        # 2. Filtres session
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
            ORDER BY d.prioritaire DESC, d.date_creation DESC
        """

        full_params = tuple(join_params + where_params)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(query_sql, full_params)
            return cursor.fetchall()

    async def show_demandes_disponibles_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche la page courante parmi les demandes filtrées."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        user_id = update.effective_user.id
        demandes = self._fetch_filtered_demandes(user_id, context)

        if not demandes:
            msg = (
                "📮 <b>Demandes Disponibles</b>\n\n"
                "🔍 Aucune demande ne correspond à vos permissions ou filtres actuels."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Modifier les filtres", callback_data="dispo_filters_menu")],
                [InlineKeyboardButton("🔄 Réinitialiser filtres", callback_data="dispo_filter_reset")],
                [InlineKeyboardButton("💌 Mes Suivis", callback_data="demandes_suivies")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
            await self._render_clean_text(query, context, msg, keyboard)
            return

        total = len(demandes)
        page = max(0, min(page, total - 1))
        demande = demandes[page]

        text_card = self._format_demande_card(demande, page, total, context)
        keyboard = self._build_navigation_keyboard(demande, page, total)
        photo_id = demande.get("photo_id")

        if photo_id:
            await self._render_photo(query, context, photo_id, text_card, keyboard)
        else:
            await self._render_clean_text(query, context, text_card, keyboard)

    async def show_random_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sélectionne et affiche une demande au hasard parmi le lot actif."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        demandes = self._fetch_filtered_demandes(update.effective_user.id, context)
        if not demandes:
            await query.answer("❌ Aucune demande disponible pour le tirage.", show_alert=True)
            return

        random_page = random.randint(0, len(demandes) - 1)
        await query.answer(f"🎲 Pioche : #{demandes[random_page].get('request_number', demandes[random_page]['id'])}")
        await self.show_demandes_disponibles_page(update, context, page=random_page)

    async def _render_photo(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, keyboard: InlineKeyboardMarkup):
        """Met à jour l'affichage avec photo via context.bot."""
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
        """Gère l'affichage en mode texte (sans photo ou menus)."""
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

    def _format_demande_card(self, demande: dict, page: int, total: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Formate la fiche avec échappement HTML strict."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_val = float(demande.get("montant") or 0.0)
        montant_str = f" ({montant_val:.2f}€)" if demande.get("prioritaire") else ""

        prenom_esc = html.escape(str(demande.get("prenom") or ""))
        nom_esc = html.escape(str(demande.get("nom") or ""))
        nom_complet = f"{prenom_esc} {nom_esc}".strip()
        loc_esc = html.escape(str(demande.get("localisation") or "Non précisée"))
        
        statut_label = self.db_manager.format_statut_display(
            demande.get("statut", "📥 Reçue"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus")
        )
        statut_esc = html.escape(statut_label)
        req_num = html.escape(str(demande.get("request_number", demande["id"])))

        if demande.get("username"):
            demandeur = f"@{html.escape(demande['username'])}"
        elif demande.get("user_first_name"):
            demandeur = html.escape(demande["user_first_name"])
        else:
            demandeur = f"User {demande['user_id']}"

        date_str = str(demande.get("date_creation", ""))[:16]

        lines = [
            f"📮 <b>Demande disponible #{req_num}</b> ({page + 1}/{total})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)",
            f"📍 <b>Localisation :</b> {loc_esc}",
            f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
            f"📊 <b>Statut :</b> <code>{statut_esc}</code>",
            f"🙋 <b>Demandeur :</b> {demandeur}"
        ]

        if demande.get("raison_abandon"):
            lines.append(
                f"\n⚠️ <b>HISTORIQUE - TENTATIVE(S) PRÉCÉDENTE(S) :</b>\n"
                f"{html.escape(str(demande['raison_abandon']))}"
            )

        reseaux = []
        if demande.get("instagram"):
            ig = html.escape(str(demande["instagram"]))
            reseaux.append(f"📷 <a href='https://instagram.com/{ig}'>@{ig}</a>")
        if demande.get("snapchat"):
            snap = html.escape(str(demande["snapchat"]))
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{snap}'>{snap}</a>")
        if reseaux:
            lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if demande.get("details"):
            det = str(demande["details"])
            det_court = (det[:140] + "...") if len(det) > 140 else det
            lines.append(f"💬 <b>Détails :</b> <i>{html.escape(det_court)}</i>")

        f = self._get_active_filters(context)
        active_tags = []
        if f["reseau"] != "all":
            active_tags.append(f"🌐 {html.escape(f['reseau'])}")
        if f["age_range"] != "all":
            active_tags.append(f"🎂 {html.escape(f['age_range'])}")
        if f["search"]:
            active_tags.append(f"🔎 «{html.escape(f['search'])}»")

        if active_tags:
            lines.append(f"\n🏷️ <i>Filtres : {' | '.join(active_tags)}</i>")
        else:
            lines.append(f"\n📅 <i>Reçue le {date_str}</i>")

        return "\n".join(lines)

    def _build_navigation_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit le clavier d'actions enrichi avec Filtres, Aléatoire et Profil Demandeur."""
        demande_id = demande["id"]
        buttons = [
            [
                InlineKeyboardButton("❤️ Prendre en charge", callback_data=f"suivre_demande_{demande_id}"),
                InlineKeyboardButton("🎲 Au hasard", callback_data="dispo_random")
            ],
            [
                InlineKeyboardButton("👤 Profil Demandeur", callback_data=f"profil_demande_{demande_id}")
            ]
        ]

        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"dispo_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"dispo_next_{page}"))

        if nav_row:
            buttons.append(nav_row)

        buttons.append([
            InlineKeyboardButton("⚙️ Filtres / Recherche", callback_data="dispo_filters_menu"),
            InlineKeyboardButton("💌 Mes Suivis", callback_data="demandes_suivies")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)