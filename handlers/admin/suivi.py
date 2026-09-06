"""Module de gestion, filtrage et tri dynamique des demandes suivies par les administrateurs."""

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class SuiviManager:
    """Gestionnaire des demandes prises en charge avec tri multicritère et recherche."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("SuiviManager initialisé")

    def _get_sort_settings(self, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Récupère ou initialise les réglages de tri et filtre de suivi."""
        if "suivi_settings" not in context.user_data:
            context.user_data["suivi_settings"] = {
                "sort_by": "date_suivi",  # 'date_suivi', 'date_creation', 'age', 'montant', 'statut', 'nom'
                "order": "DESC",           # 'ASC' ou 'DESC'
                "search": None,
            }
        return context.user_data["suivi_settings"]

    async def show_demandes_suivies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée principal."""
        await self.show_demandes_suivies_page(update, context, page=0)

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Routeur des callbacks internes au suivi (pagination, tris, recherche)."""
        query = update.callback_query
        if not query:
            return

        settings = self._get_sort_settings(context)

        # 1. Menu de tri
        if data == "suivi_sort_menu":
            await self.show_sort_menu(update, context)
            return

        # 2. Changement de critère de tri
        elif data.startswith("suivi_set_sort_"):
            critere = data.replace("suivi_set_sort_", "")
            if settings["sort_by"] == critere:
                # Alterne l'ordre si on reclique sur le même critère
                settings["order"] = "ASC" if settings["order"] == "DESC" else "DESC"
            else:
                settings["sort_by"] = critere
                # Ordre par défaut selon la nature de la colonne
                settings["order"] = "ASC" if critere in ("nom", "age", "statut") else "DESC"
            await self.show_sort_menu(update, context)
            return

        # 3. Réinitialisation
        elif data == "suivi_sort_reset":
            context.user_data["suivi_settings"] = {
                "sort_by": "date_suivi",
                "order": "DESC",
                "search": None,
            }
            await self.show_sort_menu(update, context)
            return

        # 4. Recherche
        elif data == "suivi_search_prompt":
            context.user_data["waiting_suivi_search"] = True
            msg = (
                "🔍 <b>Recherche dans vos suivis</b>\n\n"
                "Tapez un terme (nom, prénom, ville, réseau, détail) :"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Annuler", callback_data="suivi_cancel_search")
            ]])
            await self._render_clean_text(query, context, msg, keyboard)
            return

        elif data == "suivi_cancel_search":
            context.user_data.pop("waiting_suivi_search", None)
            await self.show_demandes_suivies_page(update, context, page=0)
            return

        elif data == "suivi_clear_search":
            settings["search"] = None
            await self.show_demandes_suivies_page(update, context, page=0)
            return

        # 5. Pagination
        elif data.startswith("suivi_prev_") or data.startswith("suivi_next_"):
            parts = data.split("_")
            curr = int(parts[2])
            page = max(0, curr - 1) if "prev" in data else curr + 1
            await self.show_demandes_suivies_page(update, context, page=page)

    async def handle_search_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Récupère la saisie textuelle pour filtrer les suivis."""
        if not update.message or not update.message.text:
            return

        query_text = update.message.text.strip()
        context.user_data.pop("waiting_suivi_search", None)
        settings = self._get_sort_settings(context)
        settings["search"] = query_text

        await update.message.reply_text(
            f"🔎 Recherche appliquée sur les suivis : « <b>{query_text}</b> »",
            parse_mode="HTML"
        )
        await self._render_first_page_from_message(update, context)

    async def _render_first_page_from_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gère l'affichage initial après soumission de recherche texte."""
        admin_id = update.effective_user.id
        demandes = self._fetch_sorted_suivis(admin_id, context)

        if not demandes:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🧹 Effacer la recherche", callback_data="suivi_clear_search")],
                [InlineKeyboardButton("🔙 Mes Suivis", callback_data="demandes_suivies")],
                [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
            ])
            await update.message.reply_text("🔍 Aucun suivi ne correspond à cette recherche.", reply_markup=keyboard)
            return

        total = len(demandes)
        demande = demandes[0]
        text_card = self._format_suivi_card(demande, 0, total, context)
        keyboard = self._build_suivi_keyboard(demande, 0, total)
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

    async def show_sort_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Affiche le menu de sélection du tri."""
        query = update.callback_query
        settings = self._get_sort_settings(context)
        sb = settings["sort_by"]
        order_arrow = "⬆️" if settings["order"] == "ASC" else "⬇️"

        def btn_label(name: str, key: str) -> str:
            return f"✅ {name} {order_arrow}" if sb == key else name

        keyboard = [
            [
                InlineKeyboardButton(btn_label("📅 Date suivi", "date_suivi"), callback_data="suivi_set_sort_date_suivi"),
                InlineKeyboardButton(btn_label("📝 Date demande", "date_creation"), callback_data="suivi_set_sort_date_creation"),
            ],
            [
                InlineKeyboardButton(btn_label("👤 Nom", "nom"), callback_data="suivi_set_sort_nom"),
                InlineKeyboardButton(btn_label("🎂 Âge", "age"), callback_data="suivi_set_sort_age"),
            ],
            [
                InlineKeyboardButton(btn_label("💰 Prix / Don", "montant"), callback_data="suivi_set_sort_montant"),
                InlineKeyboardButton(btn_label("📊 Statut", "statut"), callback_data="suivi_set_sort_statut"),
            ],
            [
                InlineKeyboardButton("🔍 Rechercher par mot-clé", callback_data="suivi_search_prompt"),
                InlineKeyboardButton("🔄 Réinitialiser", callback_data="suivi_sort_reset"),
            ],
            [
                InlineKeyboardButton("🚀 Appliquer et afficher", callback_data="demandes_suivies")
            ]
        ]

        nom_critere = {
            "date_suivi": "Date de prise en charge",
            "date_creation": "Date de création de la demande",
            "nom": "Nom / Prénom",
            "age": "Âge",
            "montant": "Montant / Priorité",
            "statut": "Statut de traitement",
        }.get(sb, sb)

        sens_str = "Croissant" if settings["order"] == "ASC" else "Décroissant"
        search_str = f"« {settings['search']} »" if settings["search"] else "<i>Aucun</i>"

        text = (
            "⚙️ <b>Options de tri & recherche (Demandes Suivies)</b>\n\n"
            f"• <b>Tri actuel :</b> {nom_critere} ({sens_str} {order_arrow})\n"
            f"• <b>Recherche :</b> {search_str}\n\n"
            "<i>Cliquez sur un critère pour l'activer ou inverser son ordre :</i>"
        )
        await self._render_clean_text(query, context, text, InlineKeyboardMarkup(keyboard))

    def _fetch_sorted_suivis(self, admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
        """Exécute la requête SQL avec tri dynamique sécurisé."""
        settings = self._get_sort_settings(context)
        sb = settings["sort_by"]
        order = settings["order"] if settings["order"] in ("ASC", "DESC") else "DESC"

        # Mapping strict des colonnes autorisées
        col_map = {
            "date_suivi": "ds.date_suivi",
            "date_creation": "d.date_creation",
            "age": "d.age",
            "montant": "d.montant",
            "statut": "d.statut",
            "nom": "d.prenom",
        }
        sort_column = col_map.get(sb, "ds.date_suivi")

        sql_where = ["ds.admin_id = %s"]
        params = [admin_id]

        if settings["search"]:
            pat = f"%{settings['search']}%"
            sql_where.append(
                "(d.prenom LIKE %s OR d.nom LIKE %s OR d.localisation LIKE %s "
                "OR d.instagram LIKE %s OR d.snapchat LIKE %s OR d.details LIKE %s)"
            )
            params.extend([pat] * 6)

        query_sql = f"""
            SELECT d.*, u.username, u.first_name AS user_first_name,
                   ds.date_suivi, ds.notes_admin
            FROM demandes d
            JOIN demandes_suivi ds ON d.id = ds.demande_id
            JOIN users u ON d.user_id = u.user_id
            WHERE {' AND '.join(sql_where)}
            ORDER BY d.prioritaire DESC, {sort_column} {order}
        """

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(query_sql, tuple(params))
            return cursor.fetchall()

    async def show_demandes_suivies_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Affiche la page courante parmi les suivis triés."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        admin_id = update.effective_user.id
        demandes = self._fetch_sorted_suivis(admin_id, context)

        if not demandes:
            settings = self._get_sort_settings(context)
            if settings["search"]:
                msg = (
                    "💌 <b>Mes Demandes Suivies</b>\n\n"
                    f"🔍 Aucun suivi ne correspond au filtre « {settings['search']} »."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧹 Effacer la recherche", callback_data="suivi_clear_search")],
                    [InlineKeyboardButton("⚙️ Options de tri", callback_data="suivi_sort_menu")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])
            else:
                msg = (
                    "💌 <b>Mes Demandes Suivies</b>\n\n"
                    "❤️ Vous ne prenez en charge aucune demande actuellement."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📮 Demandes Disponibles", callback_data="demandes_disponibles")],
                    [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
                ])

            await self._render_clean_text(query, context, msg, keyboard)
            return

        total = len(demandes)
        page = max(0, min(page, total - 1))
        demande = demandes[page]

        text_card = self._format_suivi_card(demande, page, total, context)
        keyboard = self._build_suivi_keyboard(demande, page, total)
        photo_id = demande.get("photo_id")

        if photo_id:
            await self._render_photo(query, context, photo_id, text_card, keyboard)
        else:
            await self._render_clean_text(query, context, text_card, keyboard)

    async def suivre_demande(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Assigne une demande disponible à l'administrateur connecté."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        admin_id = update.effective_user.id
        if not self.config.is_admin(admin_id):
            return

        demande_id = int(query.data.replace("suivre_demande_", ""))

        try:
            with self.db_manager.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), 'active')
                    ON DUPLICATE KEY UPDATE 
                        admin_id = VALUES(admin_id),
                        derniere_action = NOW(),
                        statut_suivi = 'active'
                    """,
                    (demande_id, admin_id),
                )
                cursor.execute(
                    """
                    UPDATE demandes 
                    SET statut = '🔄 En cours', admin_en_charge = %s, date_modification = NOW()
                    WHERE id = %s
                    """,
                    (admin_id, demande_id),
                )

            await query.answer("✅ Demande prise en charge !")
            await self.show_demandes_suivies_page(update, context, page=0)

        except Exception as exc:
            logger.error("Erreur prise en charge demande #%s: %s", demande_id, exc, exc_info=True)
            await query.answer("❌ Erreur lors de la prise en charge.", show_alert=True)

    async def _render_photo(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, keyboard: InlineKeyboardMarkup):
        """Affiche ou remplace la photo sans casser la vue."""
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
            logger.warning("Recréation photo suivi suite à: %s", err)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    async def _render_clean_text(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
        """Gère le mode texte pur."""
        is_current_photo = bool(query.message and query.message.photo)

        if is_current_photo:
            chat_id = query.message.chat_id
            await query.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )

    def _format_suivi_card(self, demande: dict, page: int, total: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Formate la fiche avec rappel du tri actif."""
        priorite_icon = "💎" if demande.get("prioritaire") else "📝"
        type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
        montant_str = f" ({float(demande['montant']):.2f}€)" if demande.get("prioritaire") else ""
        nom_complet = f"{demande['prenom']} {demande.get('nom') or ''}".strip()

        demandeur = f"@{demande['username']}" if demande.get("username") else (demande.get("user_first_name") or f"User {demande['user_id']}")
        date_crea_str = str(demande.get("date_creation", ""))[:16]
        date_suivi_str = str(demande.get("date_suivi", ""))[:16]

        lines = [
            f"💌 <b>Demande suivie #{demande.get('request_number', demande['id'])}</b> ({page + 1}/{total})\n",
            f"👤 <b>Identité :</b> {nom_complet} ({demande['age']} ans)",
            f"📍 <b>Localisation :</b> {demande['localisation']}",
            f"🎯 <b>Type :</b> {priorite_icon} {type_str}{montant_str}",
            f"📊 <b>Statut :</b> <code>{demande.get('statut')}</code>",
            f"🙋 <b>Demandeur :</b> {demandeur}"
        ]

        reseaux = []
        if demande.get("instagram"):
            reseaux.append(f"📷 <a href='https://instagram.com/{demande['instagram']}'>@{demande['instagram']}</a>")
        if demande.get("snapchat"):
            reseaux.append(f"👻 <a href='https://snapchat.com/add/{demande['snapchat']}'>{demande['snapchat']}</a>")
        if reseaux:
            lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if demande.get("details"):
            det = demande["details"]
            det_court = (det[:140] + "...") if len(det) > 140 else det
            lines.append(f"💬 <b>Détails :</b> <i>{det_court}</i>")

        # Indicateur de tri actif
        s = self._get_sort_settings(context)
        label_sort = {
            "date_suivi": "date suivi",
            "date_creation": "date demande",
            "age": "âge",
            "montant": "prix",
            "statut": "statut",
            "nom": "nom",
        }.get(s["sort_by"], s["sort_by"])
        arrow = "⬆️" if s["order"] == "ASC" else "⬇️"

        tags = [f"{label_sort} {arrow}"]
        if s["search"]:
            tags.append(f"«{s['search']}»")

        lines.append(f"\n🏷️ <i>Tri : {' | '.join(tags)} | Suivie le {date_suivi_str}</i>")
        return "\n".join(lines)

    def _build_suivi_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Clavier avec actions, pagination et menu de tri."""
        demande_id = demande["id"]
        buttons = []

        # Actions principales
        buttons.append([
            InlineKeyboardButton("🔄 Statut", callback_data=f"change_status_{demande_id}"),
            InlineKeyboardButton("💬 Contacter", callback_data=f"contacter_{demande_id}"),
        ])

        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"suivi_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"suivi_next_{page}"))

        if nav_row:
            buttons.append(nav_row)

        # Tris et navigation
        buttons.append([
            InlineKeyboardButton("⚙️ Trier / Rechercher", callback_data="suivi_sort_menu"),
            InlineKeyboardButton("📮 Disponibles", callback_data="demandes_disponibles")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)