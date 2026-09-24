"""Module de gestion, filtrage et tri dynamique des demandes suivies par les opérateurs (Staff)."""

from datetime import datetime
import html
import logging
import re
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Update,
)
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

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


class SuiviManager:
    """Gestionnaire des demandes prises en charge avec tri multicritère et confirmation de paiement."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("SuiviManager initialisé avec charte graphique unifiée, confirmation de paiement et surveillance")

    def _get_sort_settings(self, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """Récupère ou initialise les réglages de tri et filtre de suivi."""
        if "suivi_settings" not in context.user_data:
            context.user_data["suivi_settings"] = {
                "sort_by": "date_suivi",
                "order": "DESC",
                "search": None,
            }
        return context.user_data["suivi_settings"]

    def _format_archive_countdown(self, demande: dict) -> str:
        """Calcule et renvoie la mention visuelle du compte à rebours d'archivage dynamique."""
        if demande.get("statut") != "✅ Réussie" or demande.get("reussie_substatus") != "terminee":
            return ""

        if not demande.get("has_delivered_content"):
            return "⏳ <b>Clôture :</b> <i>En attente d'expédition du contenu</i>"

        hours_setting = self.db_manager.get_auto_archive_hours()
        date_liv = demande.get("date_livraison")
        if not date_liv:
            return f"📦 <b>Auto-archivage :</b> programmé sous {hours_setting}h"

        try:
            if isinstance(date_liv, str):
                date_liv = datetime.strptime(date_liv[:19], "%Y-%m-%d %H:%M:%S")
            diff_hours = (datetime.now() - date_liv).total_seconds() / 3600.0
            hours_left = max(0, int(hours_setting - diff_hours))

            if hours_left > 0:
                return f"📦 <b>Auto-archivage :</b> dans ~{hours_left}h (Contenu livré)"
            return "📦 <b>Auto-archivage :</b> <i>imminent...</i>"
        except Exception:
            return f"📦 <b>Auto-archivage :</b> programmé sous {hours_setting}h"

    async def show_demandes_suivies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Point d'entrée principal."""
        await self.show_demandes_suivies_page(update, context, page=0)

    async def handle_callback_routing(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Routeur des callbacks internes au suivi (pagination, tris, recherche, validation paiement)."""
        query = update.callback_query
        if not query:
            return

        settings = self._get_sort_settings(context)

        # 1. Fenêtre de confirmation d'encaissement (Prompt)
        if data.startswith("confirm_payment_prio_") and not data.startswith("confirm_payment_prio_exec_"):
            demande_id = int(data.replace("confirm_payment_prio_", ""))
            await self._prompt_confirm_payment(query, context, demande_id)
            return

        # 2. Exécution confirmée du paiement
        elif data.startswith("confirm_payment_prio_exec_"):
            demande_id = int(data.replace("confirm_payment_prio_exec_", ""))
            await self._execute_confirm_payment(update, context, demande_id)
            return

        # 3. Menu de tri
        elif data == "suivi_sort_menu":
            await self.show_sort_menu(update, context)
            return

        # 4. Changement de critère de tri
        elif data.startswith("suivi_set_sort_"):
            critere = data.replace("suivi_set_sort_", "")
            if settings["sort_by"] == critere:
                settings["order"] = "ASC" if settings["order"] == "DESC" else "DESC"
            else:
                settings["sort_by"] = critere
                settings["order"] = "ASC" if critere in ("nom", "age", "statut") else "DESC"
            await self.show_sort_menu(update, context)
            return

        # 5. Réinitialisation
        elif data == "suivi_sort_reset":
            context.user_data["suivi_settings"] = {
                "sort_by": "date_suivi",
                "order": "DESC",
                "search": None,
            }
            await self.show_sort_menu(update, context)
            return

        # 6. Recherche
        elif data == "suivi_search_prompt":
            context.user_data["waiting_suivi_search"] = True
            msg = (
                "🔍 <b>RECHERCHE DANS VOS SUIVIS</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Tapez un terme au clavier (nom, prénom, ville, réseau, détail) :"
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

        # 7. Pagination
        elif data.startswith("suivi_prev_") or data.startswith("suivi_next_"):
            parts = data.split("_")
            curr = int(parts[2])
            page = max(0, curr - 1) if "prev" in data else curr + 1
            await self.show_demandes_suivies_page(update, context, page=page)

    async def _prompt_confirm_payment(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Affiche la fenêtre intermédiaire de confirmation avant validation définitive."""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, prenom, nom, montant, user_id
                    FROM demandes WHERE id = %s
                    """,
                    (demande_id,)
                )
                dem = cursor.fetchone()

            if not dem:
                await query.answer("❌ Demande introuvable.", show_alert=True)
                return

            real_id = dem["id"]
            prenom_esc = html.escape(str(dem.get("prenom") or ""))
            montant_val = float(dem.get("montant") or 0.0)

            prompt_text = (
                f"💳 <b>CONFIRMATION D'ENCAISSEMENT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Dossier :</b> #{real_id}\n"
                f"• <b>Cible :</b> {prenom_esc}\n"
                f"• <b>Montant :</b> <code>{montant_val:.2f} €</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Confirmez-vous avoir reçu l'intégralité du règlement ?\n\n"
                "<i>Cette action avertira le client et débloquera l'envoi des contenus.</i>"
            )

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmer l'encaissement", callback_data=f"confirm_payment_prio_exec_{demande_id}")],
                [InlineKeyboardButton("❌ Annuler", callback_data=f"retour_texte_{demande_id}")]
            ])

            if query.message and query.message.photo:
                try:
                    await query.edit_message_caption(
                        caption=prompt_text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                except Exception:
                    await query.message.reply_text(
                        text=prompt_text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
            else:
                try:
                    await query.edit_message_text(
                        text=prompt_text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                except Exception:
                    if query.message:
                        await query.message.reply_text(
                            text=prompt_text,
                            parse_mode="HTML",
                            reply_markup=kb
                        )

        except Exception as exc:
            logger.error("Erreur affichage prompt confirmation paiement : %s", exc, exc_info=True)
            await query.answer("❌ Erreur technique.", show_alert=True)

    async def _execute_confirm_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Valide la réception des fonds hors Stars, notifie le client et alerte les superviseurs."""
        query = update.callback_query
        staff_id = update.effective_user.id

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, request_number, prenom, montant, admin_en_charge
                FROM demandes WHERE id = %s
                """,
                (demande_id,)
            )
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        if dem.get("admin_en_charge") and int(dem["admin_en_charge"]) != int(staff_id) and not self.config.is_owner(staff_id):
            await query.answer("❌ Seul l'opérateur en charge peut valider ce paiement.", show_alert=True)
            return

        ok = self.db_manager.set_demande_paiement_statut(demande_id, "paye")
        if ok:
            real_id = dem["id"]
            alias = self.db_manager.get_staff_alias(staff_id)
            alias_esc = html.escape(str(alias))
            prenom_esc = html.escape(str(dem.get("prenom") or "la cible"))
            montant_val = float(dem.get("montant") or 0.0)

            await query.answer(f"✅ Paiement du dossier #{real_id} validé !", show_alert=True)

            try:
                msg_client = (
                    f"💳 <b>PAIEMENT CONFIRMÉ (Dossier #{real_id})</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Votre référent <b>{alias_esc}</b> a validé la réception de votre règlement.\n\n"
                    "<i>L'envoi de vos contenus est désormais débloqué !</i>"
                )
                await context.bot.send_message(
                    chat_id=dem["user_id"],
                    text=msg_client,
                    parse_mode="HTML"
                )
            except Exception as e_notif:
                logger.warning("Impossible de notifier le client %s de la validation paiement : %s", dem["user_id"], e_notif)

            try:
                monitors = self.db_manager.get_monitoring_admins(action="reussite")
                alert_pay = (
                    f"💰 <b>SURVEILLANCE STAFF — PAIEMENT ENCAISSÉ</b>\n\n"
                    f"• <b>Opérateur :</b> {alias_esc} (<code>{staff_id}</code>)\n"
                    f"• <b>Dossier :</b> #{real_id} ({prenom_esc})\n"
                    f"• <b>Montant encaissé :</b> <code>{montant_val:.2f} €</code>\n"
                    f"• <b>Mode :</b> Règlement direct validé."
                )
                kb_mon = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 Ouvrir la fiche", callback_data=f"retour_texte_{demande_id}")]
                ])

                for mon_id in monitors:
                    if int(mon_id) != int(staff_id):
                        try:
                            await context.bot.send_message(
                                chat_id=mon_id,
                                text=alert_pay,
                                parse_mode="HTML",
                                reply_markup=kb_mon
                            )
                        except Exception:
                            pass
            except Exception as mon_err:
                logger.warning("Erreur surveillance encaissement staff : %s", mon_err)

            await self.show_demandes_suivies_page(update, context, page=0)
        else:
            await query.answer("❌ Erreur technique lors de la validation du paiement.", show_alert=True)

    async def handle_search_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Récupère la saisie textuelle pour filtrer les suivis."""
        if not update.message or not update.message.text:
            return

        query_text = update.message.text.strip()
        context.user_data.pop("waiting_suivi_search", None)
        settings = self._get_sort_settings(context)
        settings["search"] = query_text

        await update.message.reply_text(
            f"🔎 Filtre appliqué sur vos suivis : « <b>{html.escape(query_text)}</b> »",
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
                [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")],
                [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
            ])
            await update.message.reply_text("🔍 Aucun suivi ne correspond à votre recherche.", reply_markup=keyboard)
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
                InlineKeyboardButton(btn_label("📝 Date dépôt", "date_creation"), callback_data="suivi_set_sort_date_creation"),
            ],
            [
                InlineKeyboardButton(btn_label("👤 Nom", "nom"), callback_data="suivi_set_sort_nom"),
                InlineKeyboardButton(btn_label("🎂 Âge", "age"), callback_data="suivi_set_sort_age"),
            ],
            [
                InlineKeyboardButton(btn_label("💰 Tarif", "montant"), callback_data="suivi_set_sort_montant"),
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
            "date_creation": "Date de création du dossier",
            "nom": "Nom / Prénom",
            "age": "Âge",
            "montant": "Tarif / Don",
            "statut": "Statut opérationnel",
        }.get(sb, sb)

        sens_str = "Croissant" if settings["order"] == "ASC" else "Décroissant"
        search_str = f"« {html.escape(settings['search'])} »" if settings["search"] else "<i>Aucun</i>"

        text = (
            "⚙️ <b>TRI & FILTRAGE DES SUIVIS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Critère actif :</b> {html.escape(nom_critere)} ({sens_str} {order_arrow})\n"
            f"• <b>Recherche :</b> {search_str}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<i>Sélectionnez un critère pour basculer son sens ou appliquer :</i>"
        )
        await self._render_clean_text(query, context, text, InlineKeyboardMarkup(keyboard))

    def _fetch_sorted_suivis(self, admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
        """Exécute la requête SQL avec tri dynamique sécurisé en incluant toutes les demandes assignées."""
        settings = self._get_sort_settings(context)
        sb = settings["sort_by"]
        order = settings["order"] if settings["order"] in ("ASC", "DESC") else "DESC"

        col_map = {
            "date_suivi": "ds.date_suivi",
            "date_creation": "d.date_creation",
            "age": "d.age",
            "montant": "d.montant",
            "statut": "d.statut",
            "nom": "d.prenom",
        }
        sort_column = col_map.get(sb, "ds.date_suivi")

        sql_where = [
            "d.admin_en_charge = %s"
        ]
        params = [admin_id]

        if settings["search"]:
            pat = f"%{settings['search']}%"
            sql_where.append(
                "(d.prenom LIKE %s OR d.nom LIKE %s OR d.localisation LIKE %s "
                "OR d.instagram LIKE %s OR d.snapchat LIKE %s OR d.details LIKE %s)"
            )
            params.extend([pat] * 6)

        query_sql = f"""
            SELECT d.*, d.user_id AS user_id, u.username, u.first_name AS user_first_name,
                   COALESCE(ds.date_suivi, d.date_modification) AS date_suivi
            FROM demandes d
            LEFT JOIN demandes_suivi ds ON d.id = ds.demande_id AND ds.admin_id = %s
            LEFT JOIN users u ON d.user_id = u.user_id
            WHERE {' AND '.join(sql_where)}
            ORDER BY d.prioritaire DESC, {sort_column} {order}
        """

        full_params = tuple([admin_id] + params)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(query_sql, full_params)
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
                    "💌 <b>MES DOSSIERS SUIVIS</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔍 Aucun suivi ne correspond à « {html.escape(settings['search'])} »."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧹 Effacer la recherche", callback_data="suivi_clear_search")],
                    [InlineKeyboardButton("⚙️ Options de tri", callback_data="suivi_sort_menu")],
                    [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
                ])
            else:
                msg = (
                    "💌 <b>MES DOSSIERS SUIVIS</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "❤️ Vous n'avez aucune demande active en cours de traitement."
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")],
                    [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")]
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
            logger.warning("Recréation photo suivi suite à : %s", err)
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
        """Gère le mode texte pur en supprimant la photo si nécessaire."""
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

    def _format_suivi_card(self, demande: dict, page: int, total: int, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Formate la fiche du dossier suivi par le staff avec liens sociaux cliquables."""
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

        # Réseaux sociaux cliquables
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

        # Bloc Statut
        statut_label = self.db_manager.format_statut_display(
            demande.get("statut", "⏳ En attente"),
            demande.get("is_difficile", False),
            demande.get("reussie_substatus")
        )
        lines.append("\n───────  <b>STATUT</b>  ──────")
        lines.append(f" • <b>{html.escape(statut_label)}</b> • ")
        dt_mod = demande.get("date_modification")
        if dt_mod:
            lines.append(f" <i>{format_datetime_fr(dt_mod)}</i>")

        # Statut du paiement
        if is_prio:
            p_statut = demande.get("paiement_statut", "non_requis")
            if p_statut == "paye":
                lines.append("\n🟢 <b>Réglé et validé</b>")
            elif p_statut == "en_attente":
                lines.append("\n🟡 <b>En attente de règlement</b>")

        # Gestionnaire (toujours présent en suivi)
        admin_id = demande.get("admin_en_charge")
        if admin_id:
            alias = html.escape(str(self.db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"))
            lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")

        dt_suivi = demande.get("date_suivi")
        if dt_suivi:
            lines.append(f"<b>Depuis le :</b> <i>{format_datetime_fr(dt_suivi)}</i>")

        # Bloc Infos
        lines.append("\n───────  <b>INFOS</b>  ───────")
        dt_crea = demande.get("date_creation")
        lines.append(f"<b>Déposé le :</b>  {format_datetime_fr(dt_crea)}")

        demandeur = f"@{html.escape(demande['username'])}" if demande.get("username") else (
            html.escape(str(demande.get("user_first_name") or f"User {demande['user_id']}"))
        )
        lines.append(f"<b>Par :</b>  {demandeur} (<code>{demande['user_id']}</code>)")

        # Bloc HISTORIQUE (si abandon antérieur)
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

        archive_badge = self._format_archive_countdown(demande)
        if archive_badge:
            lines.append(f"\n{archive_badge}")

        return "\n".join(lines)

    def _build_suivi_keyboard(self, demande: dict, page: int, total: int) -> InlineKeyboardMarkup:
        """Construit le clavier des demandes suivies selon la maquette exacte."""
        demande_id = demande["id"]
        statut_raw = str(demande.get("statut") or "").strip()
        is_reussie = (statut_raw == "✅ Réussie")
        is_prio = bool(demande.get("prioritaire"))
        paiement_statut = demande.get("paiement_statut", "non_requis")
        has_delivered = bool(demande.get("has_delivered_content", False))

        buttons = [
            # 1. 📌 CHANGER LE STATUT 📌
            [InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")],
            # 2. 👤 PROFIL | 💬 CONTACT
            [
                InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
                InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
            ]
        ]

        # 3. 💰 VALIDER LE PAIEMENT 💰 (si prio + réussie + en attente)
        if is_prio and is_reussie and paiement_statut == "en_attente":
            buttons.append([
                InlineKeyboardButton("💰 VALIDER LE PAIEMENT 💰", callback_data=f"confirm_payment_prio_{demande_id}")
            ])

        # 4. Alternance dynamique : ENVOYER LE CONTENU ou ARCHIVER LE DOSSIER
        if is_reussie:
            if not is_prio or paiement_statut == "paye":
                if has_delivered:
                    buttons.append([
                        InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")
                    ])
                else:
                    buttons.append([
                        InlineKeyboardButton("📤 ENVOYER LE CONTENU 📤", callback_data=f"contacter_{demande_id}")
                    ])

        # 5. ⬅️ PRÉCÉDENTE | SUIVANTE ➡️
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"suivi_prev_{page}"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"suivi_next_{page}"))
        if nav_row:
            buttons.append(nav_row)

        # 6. 🔍 TRIER | 📮 DISPO
        buttons.append([
            InlineKeyboardButton("🔍 TRIER", callback_data="suivi_sort_menu"),
            InlineKeyboardButton("📮 DISPO", callback_data="demandes_disponibles")
        ])

        # 7. ⬅️ RETOUR
        buttons.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
        ])

        return InlineKeyboardMarkup(buttons)

    async def show_single_demande(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, back_callback: str = "demandes_suivies"):
        """Affiche la fiche complète officielle d'une demande unitaire (avec photo et permissions adaptées)."""
        viewer_id = query.from_user.id
        is_owner = self.config.is_owner(viewer_id)
        is_admin = self.config.is_admin(viewer_id) or is_owner

        privs = self.db_manager.get_admin_privileges(viewer_id) if is_admin else {}
        can_edit_all = is_owner or bool(privs.get("can_edit_others_demandes"))

        demande = None
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT d.*, u.username, u.first_name AS user_first_name,
                       COALESCE(ds.date_suivi, d.date_modification) AS date_suivi
                FROM demandes d
                LEFT JOIN demandes_suivi ds ON d.id = ds.demande_id
                LEFT JOIN users u ON d.user_id = u.user_id
                WHERE d.id = %s
                LIMIT 1
                """,
                (demande_id,)
            )
            demande = cursor.fetchone()

        if not demande:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        text_card = self._format_suivi_card(demande, 0, 1, context)

        admin_en_charge = demande.get("admin_en_charge")
        is_assigned_to_viewer = (admin_en_charge == viewer_id)

        buttons = []

        # 1. Mode Opérateur complet (Assigné à soi-même, Owner ou Admin avec permission spéciale)
        if is_assigned_to_viewer or can_edit_all:
            statut_raw = str(demande.get("statut") or "").strip()
            is_reussie = (statut_raw == "✅ Réussie")
            is_prio = bool(demande.get("prioritaire"))
            paiement_statut = demande.get("paiement_statut", "non_requis")
            has_delivered = bool(demande.get("has_delivered_content", False))

            buttons.append([InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")])
            buttons.append([
                InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
                InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
            ])

            if is_prio and is_reussie and paiement_statut == "en_attente":
                buttons.append([
                    InlineKeyboardButton("💰 VALIDER LE PAIEMENT 💰", callback_data=f"confirm_payment_prio_{demande_id}")
                ])

            if is_reussie:
                if not is_prio or paiement_statut == "paye":
                    if has_delivered:
                        buttons.append([
                            InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")
                        ])
                    else:
                        buttons.append([
                            InlineKeyboardButton("📤 ENVOYER LE CONTENU 📤", callback_data=f"contacter_{demande_id}")
                        ])

        # 2. Mode Supervision / Lecture seule
        else:
            buttons.append([
                InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}")
            ])
            if admin_en_charge:
                buttons.append([
                    InlineKeyboardButton("🛡️ CONTACTER LE PIÉGEUR", callback_data=f"admin_contact_staff_{demande_id}_{admin_en_charge}")
                ])

        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=back_callback)])
        keyboard = InlineKeyboardMarkup(buttons)

        photo_id = demande.get("photo_id")
        if photo_id:
            await self._render_photo(query, context, photo_id, text_card, keyboard)
        else:
            await self._render_clean_text(query, context, text_card, keyboard)