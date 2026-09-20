"""Routeur principal des actions et callbacks opérationnels (Staff) avec relais groupé."""

import html
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.ext import ContextTypes
from utils.interface_manager import InterfaceManager

from .staff.alias import AliasManager
from .staff.archives import ArchivesManager
from .staff.contact import ContactManager
from .staff.dispo import DispoManager
from .staff.notifs import NotifsManager
from .staff.photos import PhotosManager
from .staff.profils import ProfilsManager
from .staff.statuts import StatutsManager
from .staff.suivi import SuiviManager

logger = logging.getLogger(__name__)


class StaffHandlers:
    """Gestionnaire central des fonctionnalités opérationnelles de traitement des dossiers (Staff)."""

    def __init__(self, config, db_manager):
        self.config = config
        self.db_manager = db_manager
        self.interface = InterfaceManager(config, db_manager)

        self.suivi = SuiviManager(db_manager, config)
        self.statuts = StatutsManager(db_manager, config)
        self.photos = PhotosManager(db_manager, config)
        self.dispo = DispoManager(db_manager, config)
        self.alias = AliasManager(db_manager, config)
        self.notifs = NotifsManager(db_manager, config)
        self.contact = ContactManager(db_manager, config)
        self.profils = ProfilsManager(db_manager, config)
        self.archives = ArchivesManager(db_manager, config)

    async def _safe_edit_or_reply(self, query, text: str, reply_markup=None, parse_mode="HTML"):
        """Met à jour le message texte ou envoie une nouvelle bulle si le message cible contient une photo."""
        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            try:
                await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
            except Exception:
                if query.message:
                    await query.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)

    async def handle_staff_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Aiguillage sécurisé des callbacks opérationnels (Staff, Admin et Owner)."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        try:
            await query.answer()
        except Exception:
            pass

        user_id = update.effective_user.id
        data = query.data or ""

        if not self.db_manager.is_staff(user_id):
            logger.warning("Tentative d'accès staff refusée pour l'utilisateur %s", user_id)
            return

        try:
            # 0. Décision sur mission assignée VIP (Accepter / Décliner)
            if data.startswith("vip_accept_"):
                demande_id = int(data.replace("vip_accept_", ""))
                await self._handle_vip_accept(query, context, demande_id, user_id)
                return

            elif data.startswith("vip_decline_"):
                demande_id = int(data.replace("vip_decline_", ""))
                await self._handle_vip_decline(query, context, demande_id, user_id)
                return

            # 1. Demandes disponibles, filtres, suppression, proposition de prix et signalement
            elif data == "demandes_disponibles":
                await self.dispo.show_demandes_disponibles(update, context)

            elif (
                data.startswith("dispo_")
                or data.startswith("admin_del_dispo_")
                or data.startswith("admin_propose_prix_")
                or data.startswith("staff_report_dispo_")
            ):
                await self.dispo.handle_callback_routing(update, context, data)

            # 2. Prise en charge d'une demande disponible -> statut "En attente" + notification
            elif data.startswith("suivre_demande_"):
                demande_id = int(data.replace("suivre_demande_", ""))
                await self.dispo.assign_demande_to_admin(update, context, demande_id)

            # 3. Demandes suivies et confirmation de paiement
            elif data == "demandes_suivies":
                await self.suivi.show_demandes_suivies(update, context)

            elif data.startswith("suivi_") or data.startswith("confirm_payment_prio_"):
                await self.suivi.handle_callback_routing(update, context, data)

            # 4. Préférences de notifications et rappels
            elif data == "menu_notifs":
                await self.notifs.show_notifs_menu(update, context)

            elif data.startswith("pref_") or data.startswith("toggle_mon_") or data == "menu_surveillance_notifs":
                await self.notifs.handle_callback_routing(update, context, data)

            # 5. Photos et affichage texte
            elif data.startswith("voir_photo_"):
                await self.photos.voir_photo_demande(update, context)

            elif data.startswith("retour_texte_"):
                await self.photos.retour_texte_demande(update, context)

            # 6. Gestion dynamique des statuts et archivage
            elif data.startswith("change_status_") or data.startswith("mark_treated_menu_"):
                demande_id = int(data.split("_")[-1])
                await self.statuts.show_status_change_menu(update, context, demande_id)

            elif data.startswith("status_"):
                await self.statuts.handle_status_callback(update, context)

            # 7. Archives du service
            elif data == "demandes_archives":
                await self.archives.show_archives(update, context, page=0)

            elif data.startswith("archive_page_"):
                page = int(data.replace("archive_page_", ""))
                await self.archives.show_archives(update, context, page=page)

            # 8. Profils et sous-menus de visualisation des dossiers associés
            elif data.startswith("profil_admin_"):
                target_admin_id = int(data.replace("profil_admin_", ""))
                await self.profils.show_admin_profile(update, context, target_admin_id)

            elif data.startswith("profil_demande_"):
                demande_id = int(data.replace("profil_demande_", ""))
                await self.profils.show_user_profile_by_demande(update, context, demande_id)

            elif (
                data.startswith("staff_view_demandes_")
                or data.startswith("staff_list_")
                or data.startswith("user_view_demandes_")
                or data.startswith("user_list_")
                or data.startswith("archive_view_")
            ):
                await self.profils.handle_callback_routing(update, context, data)

            # 9. Mode pause
            elif data in ("admin_pause_prompt", "admin_pause_keep", "admin_pause_release", "admin_resume"):
                await self._handle_admin_pause(update, context, data)

            # 10. Contact superviseur (Admin/Owner) vers Piégeur
            elif data.startswith("admin_contact_staff_"):
                parts = data.split("_")
                demande_id = int(parts[3])
                target_staff_id = int(parts[4])
                await self._prompt_admin_contact_staff(update, context, demande_id, target_staff_id)

            # 11. Contact du demandeur
            elif data.startswith("contacter_") and not data.startswith("contacter_owner"):
                demande_id = int(data.replace("contacter_", ""))
                await self._prompt_contact_user(update, context, demande_id)

            elif data.startswith("contact_mode_"):
                parts = data.split("_")
                demande_id = int(parts[2])
                allow_reply = (parts[3] == "yes")
                await self._start_contact_input(update, context, demande_id, allow_reply)

            elif data.startswith("send_batch_"):
                demande_id = int(data.replace("send_batch_", ""))
                await self._dispatch_media_batch(update, context, demande_id)

            elif data.startswith("cancel_contact_") and not data.startswith("cancel_contact_owner"):
                demande_id = int(data.replace("cancel_contact_", ""))
                context.user_data.pop("contact_session", None)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{demande_id}")
                ]])
                await self._safe_edit_or_reply(query, "❌ Envoi annulé. Aucun fichier n'a été transmis.", reply_markup=kb)

            else:
                logger.warning("Callback staff non intercepté : %s", data)

        except Exception as exc:
            logger.error("Erreur callback staff '%s' : %s", data, exc, exc_info=True)
            await self._handle_callback_error(query)

    handle_admin_callbacks = handle_staff_callbacks

    # ==================== SUPERVISION ADMIN VERS PIÉGEUR ====================

    async def _prompt_admin_contact_staff(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        """Initialise l'envoi d'un message administratif de supervision vers l'opérateur en charge."""
        query = update.callback_query
        alias_staff = self.db_manager.get_staff_alias(staff_id)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT request_number, prenom FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        req_num = row.get("request_number", demande_id) if row else demande_id

        context.user_data["contact_session"] = {
            "demande_id": demande_id,
            "target_user_id": staff_id,
            "prenom": f"Piégeur ({alias_staff})",
            "req_num": req_num,
            "allow_reply": True,
            "visual_media": [],
            "doc_media": [],
            "text_notes": [],
        }

        text = (
            f"🛡️ <b>Message Direction ➔ Piégeur ({html.escape(str(alias_staff))})</b>\n"
            f"Dossier concerné : <b>#{req_num}</b>\n\n"
            "Envoyez vos instructions, remarques ou fichiers ci-dessous :\n"
            "<i>Le message lui sera délivré sous votre alias officiel.</i>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Valider l'envoi (0 élément)", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("❌ Annuler", callback_data=f"retour_texte_{demande_id}")]
        ])
        await self._safe_edit_or_reply(query, text, reply_markup=kb)

    # ==================== GESTION DE L'ACCEPTATION / REFUS VIP ====================

    async def _handle_vip_accept(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        """Valide la mission assignée par un client VIP."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, request_number, prenom, statut FROM demandes WHERE id = %s",
                (demande_id,)
            )
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        if dem.get("statut") != "🎯 Assignée (VIP)":
            await query.answer("ℹ️ Ce dossier a déjà été traité ou réattribué.", show_alert=True)
            return

        ok = self.db_manager.accept_vip_assigned_demande(demande_id, staff_id)
        if ok:
            req_num = dem.get("request_number", demande_id)
            alias = self.db_manager.get_staff_alias(staff_id)
            prenom_cible = dem.get("prenom", "")

            await query.answer(f"✅ Demande #{req_num} acceptée !", show_alert=False)

            confirm_msg = (
                f"✅ <b>Mission VIP acceptée (Dossier #{req_num})</b>\n\n"
                f"Vous avez pris en charge le dossier de <b>{html.escape(str(prenom_cible))}</b>.\n"
                "Le dossier est désormais actif sous le statut <b>⏳ En attente</b>."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Ouvrir la fiche", callback_data=f"retour_texte_{demande_id}")],
                [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
            ])
            await self._safe_edit_or_reply(query, confirm_msg, reply_markup=kb)

            try:
                vip_user_id = dem["user_id"]
                notif_vip = (
                    f"🌟 <b>Votre demande #{req_num} a été acceptée !</b>\n\n"
                    f"Votre référent <b>{html.escape(str(alias))}</b> a validé la prise en charge de votre dossier "
                    f"pour <b>{html.escape(str(prenom_cible))}</b>.\n\n"
                    "Le statut passe en <b>⏳ En attente</b> (premier contact en cours)."
                )
                await context.bot.send_message(
                    chat_id=vip_user_id,
                    text=notif_vip,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 Suivre ma demande", callback_data="voir_demandes")
                    ]])
                )
            except Exception as e_notif:
                logger.warning("Impossible de notifier le client VIP %s : %s", dem.get("user_id"), e_notif)
        else:
            await query.answer("❌ Erreur technique lors de l'acceptation.", show_alert=True)

    async def _handle_vip_decline(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        """Décline la mission assignée par un client VIP et la replace dans les disponibles."""
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, request_number, prenom, nom, age, localisation, prioritaire, montant, orientation, photo_id, statut FROM demandes WHERE id = %s",
                (demande_id,)
            )
            dem = cursor.fetchone()

        if not dem:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        if dem.get("statut") != "🎯 Assignée (VIP)":
            await query.answer("ℹ️ Ce dossier n'est plus en attente d'assignation.", show_alert=True)
            return

        ok = self.db_manager.decline_vip_assigned_demande(demande_id)
        if ok:
            req_num = dem.get("request_number", demande_id)
            alias = self.db_manager.get_staff_alias(staff_id)
            prenom_cible = dem.get("prenom", "")

            await query.answer("Demande déclinée.", show_alert=False)

            decline_msg = (
                f"ℹ️ <b>Demande #{req_num} déclinée</b>\n\n"
                "Le dossier a été replacé dans les <b>demandes disponibles</b> pour le reste de l'équipe."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📮 Demandes disponibles", callback_data="demandes_disponibles")],
                [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
            ])
            await self._safe_edit_or_reply(query, decline_msg, reply_markup=kb)

            try:
                vip_user_id = dem["user_id"]
                notif_vip = (
                    f"ℹ️ <b>Mise à jour de votre demande VIP #{req_num}</b>\n\n"
                    f"Votre référent sollicité ({html.escape(str(alias))}) n'est malheureusement pas disponible actuellement "
                    f"pour prendre en charge le dossier de <b>{html.escape(str(prenom_cible))}</b>.\n\n"
                    "Votre demande a été immédiatement transmise à l'ensemble de l'équipe avec priorité absolue !"
                )
                await context.bot.send_message(
                    chat_id=vip_user_id,
                    text=notif_vip,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 Suivre ma demande", callback_data="voir_demandes")
                    ]])
                )
            except Exception as e_notif:
                logger.warning("Impossible de notifier le client VIP %s du refus : %s", dem.get("user_id"), e_notif)

            try:
                prenom_esc = html.escape(dem.get("prenom") or "")
                nom_esc = html.escape(dem.get("nom") or "")
                nom_complet = f"{prenom_esc} {nom_esc}".strip()
                from handlers.user.formulaire import FormulaireManager
                form_manager = FormulaireManager(self.db_manager, self.config, None)
                await form_manager._broadcast_new_demande_alert(
                    context=context,
                    demande_id=demande_id,
                    req_num=req_num,
                    nom_complet=nom_complet,
                    demande=dem,
                    creator_id=dem["user_id"],
                    is_vip=True
                )
            except Exception as e_bc:
                logger.warning("Impossible de diffuser la demande déclinée au reste du staff : %s", e_bc)
        else:
            await query.answer("❌ Erreur technique lors du refus.", show_alert=True)

    async def _handle_admin_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Gère les transitions du mode pause de l'opérateur."""
        query = update.callback_query
        admin_id = update.effective_user.id

        if data == "admin_pause_prompt":
            active_demandes = self.db_manager.get_staff_active_demandes(admin_id)
            nb = len(active_demandes)

            if nb == 0:
                self.db_manager.set_staff_pause_status(admin_id, paused=True)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")
                ]])
                await self._safe_edit_or_reply(
                    query,
                    "⏸️ <b>Mode pause activé</b>\n\n"
                    "• Vous ne recevrez plus aucune notification de nouvelle demande.\n"
                    "• Vous n'apparaissez plus dans la liste de sélection VIP.\n"
                    "• Vous n'avez aucun dossier actif en attente.",
                    reply_markup=kb
                )
                return

            text = (
                f"⏸️ <b>Passage en mode pause</b>\n\n"
                f"Vous avez actuellement <b>{nb}</b> demande(s) en cours de traitement.\n"
                "Que souhaitez-vous faire de vos dossiers ?"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📁 Conserver mes dossiers en cours", callback_data="admin_pause_keep")],
                [InlineKeyboardButton("❌ Libérer et abandonner mes dossiers", callback_data="admin_pause_release")],
                [InlineKeyboardButton("🔙 Annuler", callback_data="parametres")]
            ])
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

        elif data == "admin_pause_keep":
            self.db_manager.set_staff_pause_status(admin_id, paused=True)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")
            ]])
            await self._safe_edit_or_reply(
                query,
                "⏸️ <b>Mode pause activé (dossiers conservés)</b>\n\n"
                "• Vos demandes en cours restent assignées à votre compte.\n"
                "• Aucune nouvelle demande ne vous sera attribuée ni notifiée.\n"
                "• Vous pouvez continuer à traiter vos suivis à votre rythme.",
                reply_markup=kb
            )
            return

        elif data == "admin_pause_release":
            abandoned = self.db_manager.abandon_staff_demandes_for_pause(admin_id)
            self.db_manager.set_staff_pause_status(admin_id, paused=True)
            alias = self.db_manager.get_staff_alias(admin_id)
            alias_esc = html.escape(str(alias or f"Staff_{admin_id}"))

            for dem in abandoned:
                try:
                    c_id = dem["user_id"]
                    req_num = html.escape(str(dem.get("request_number") or dem["id"]))
                    msg_client = (
                        f"⚠️ <b>Demande #{req_num} — Référent indisponible</b>\n\n"
                        f"Votre référent (<b>{alias_esc}</b>) est actuellement en pause.\n"
                        "Sa prise en charge sur votre dossier a donc été interrompue.\n\n"
                        "Vous pouvez remettre votre demande dans la file d'attente ou la classer sans suite :"
                    )
                    kb_client = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Reprendre ma demande", callback_data=f"reprendre_demande_{dem['id']}")],
                        [InlineKeyboardButton("🗑️ Archiver la demande", callback_data=f"archiver_demande_{dem['id']}")]
                    ])
                    await context.bot.send_message(chat_id=c_id, text=msg_client, parse_mode="HTML", reply_markup=kb_client)
                except Exception as err:
                    logger.warning("Notification abandon pause impossible pour user %s : %s", dem.get("user_id"), err)

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")
            ]])
            await self._safe_edit_or_reply(
                query,
                f"⏸️ <b>Mode pause activé</b>\n\n"
                f"• {len(abandoned)} dossier(s) libéré(s) et notifiés aux demandeurs.\n"
                "• Vous êtes désormais retiré du service jusqu'à votre reprise.",
                reply_markup=kb
            )
            return

        elif data == "admin_resume":
            self.db_manager.set_staff_pause_status(admin_id, paused=False)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Paramètres", callback_data="parametres")
            ]])
            await self._safe_edit_or_reply(
                query,
                "🟢 <b>Bon retour ! Vous êtes à nouveau en service.</b>\n\n"
                "• Vous recevrez à nouveau les alertes et notifications.\n"
                "• Vous êtes à nouveau sélectionnable par les clients VIP.",
                reply_markup=kb
            )
            return

    async def _prompt_contact_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Demande si l'utilisateur doit pouvoir répondre."""
        query = update.callback_query
        if not query or not update.effective_user:
            return

        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute(
                    "SELECT id, request_number, user_id, prenom FROM demandes WHERE id = %s",
                    (demande_id,)
                )
                row = cursor.fetchone()

            if not row:
                return

            req_num = html.escape(str(row.get("request_number", row["id"])))
            prenom_esc = html.escape(str(row.get("prenom") or ""))

            text = (
                f"💬 <b>Contacter le demandeur</b> (Dossier #{req_num} - {prenom_esc})\n\n"
                "Souhaitez-vous autoriser le demandeur à répondre à cet envoi ?"
            )
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💬 Oui (avec bouton réponse)", callback_data=f"contact_mode_{demande_id}_yes"),
                    InlineKeyboardButton("🔒 Non (informatif / clôture)", callback_data=f"contact_mode_{demande_id}_no")
                ],
                [InlineKeyboardButton("❌ Annuler", callback_data=f"retour_texte_{demande_id}")]
            ])

            await self._safe_edit_or_reply(query, text, reply_markup=keyboard)

        except Exception as exc:
            logger.error("Erreur prompt contact utilisateur : %s", exc)

    async def _start_contact_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, allow_reply: bool):
        """Initialise la session de collecte de messages et fichiers."""
        query = update.callback_query
        if not query:
            return

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, request_number, user_id, prenom FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        if not row:
            return

        req_num = html.escape(str(row.get("request_number", row["id"])))
        prenom_esc = html.escape(str(row.get("prenom") or ""))

        context.user_data["contact_session"] = {
            "demande_id": demande_id,
            "target_user_id": row["user_id"],
            "prenom": row["prenom"],
            "req_num": row.get("request_number", row["id"]),
            "allow_reply": allow_reply,
            "visual_media": [],
            "doc_media": [],
            "text_notes": [],
        }

        mode_str = "💬 Réponse autorisée (1 fois)" if allow_reply else "🔒 Message informatif (réponse bloquée)"
        text = (
            f"📦 <b>Session d'envoi (Demande #{req_num} - {prenom_esc})</b>\n"
            f"Mode : <b>{mode_str}</b>\n\n"
            "Envoyez vos photos, vidéos, documents ou messages texte (en un seul envoi ou plusieurs).\n\n"
            "<i>Tous vos éléments seront conservés et transmis en groupe quand vous validerez.</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Valider et envoyer le lot (0 élément)", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_contact_{demande_id}")]
        ])

        await self._safe_edit_or_reply(query, text, reply_markup=keyboard)

    async def handle_collect_admin_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Collecte les fichiers sans spammer la conversation, en mettant à jour un statut propre."""
        msg = update.message
        if not msg:
            return False

        session = context.user_data.get("contact_session")
        if not session:
            return False

        demande_id = session["demande_id"]
        caption = (msg.caption or "").strip()

        if msg.photo:
            file_id = msg.photo[-1].file_id
            session["visual_media"].append({"type": "photo", "file_id": file_id, "caption": caption})
        elif msg.video:
            file_id = msg.video.file_id
            session["visual_media"].append({"type": "video", "file_id": file_id, "caption": caption})
        elif msg.document:
            file_id = msg.document.file_id
            session["doc_media"].append({"file_id": file_id, "caption": caption})
        elif msg.text:
            session["text_notes"].append(msg.text.strip())

        total = len(session["visual_media"]) + len(session["doc_media"]) + len(session["text_notes"])

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🚀 Envoyer tout le lot ({total} élément{'s' if total > 1 else ''})", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("❌ Annuler tout", callback_data=f"cancel_contact_{demande_id}")]
        ])

        status_text = (
            f"📥 <b>Panier d'envoi mis à jour : {total} élément{'s' if total > 1 else ''} prêt{'s' if total > 1 else ''}</b>\n\n"
            "Vous pouvez encore déposer d'autres fichiers ou cliquer ci-dessous pour expédier l'ensemble :"
        )

        last_status_msg_id = session.get("last_status_msg_id")
        if last_status_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=msg.chat_id,
                    message_id=last_status_msg_id,
                    text=status_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return True
            except Exception:
                pass

        sent_msg = await msg.reply_text(
            status_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        session["last_status_msg_id"] = sent_msg.message_id
        return True

    async def _dispatch_media_batch(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        """Envoie l'ensemble du lot au destinataire, valide la livraison et envoie une copie miroir aux superviseurs autorisés."""
        query = update.callback_query
        session = context.user_data.pop("contact_session", None)

        if not session or session.get("demande_id") != demande_id:
            return

        admin_id = update.effective_user.id
        target_user_id = session["target_user_id"]
        req_num = html.escape(str(session["req_num"]))
        allow_reply = session["allow_reply"]
        raw_alias = self.db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"
        alias_esc = html.escape(str(raw_alias))

        visuals = session["visual_media"]
        docs = session["doc_media"]
        texts = session["text_notes"]

        if not visuals and not docs and not texts:
            context.user_data["contact_session"] = session
            return

        if query:
            await self._safe_edit_or_reply(query, "⏳ Transmission du lot en cours...")

        combined_text = "\n".join([html.escape(t) for t in texts])
        corps = f"\n\n« {combined_text} »" if combined_text else ""
        footer = "\n\n<i>Vous pouvez répondre une seule fois ci-dessous.</i>" if allow_reply else ""

        header_text = (
            f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\n"
            f"De : <b>{alias_esc}</b>"
            f"{corps}"
            f"{footer}"
        )

        user_keyboard = None
        if allow_reply:
            user_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Répondre", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
            ]])

        try:
            if visuals:
                for i in range(0, len(visuals), 10):
                    batch = visuals[i:i + 10]
                    media_group = []
                    for idx, item in enumerate(batch):
                        item_caption = header_text if (i == 0 and idx == 0) else (html.escape(item["caption"]) if item.get("caption") else None)
                        if item["type"] == "photo":
                            media_group.append(InputMediaPhoto(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))
                        elif item["type"] == "video":
                            media_group.append(InputMediaVideo(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))

                    if len(media_group) == 1:
                        single = media_group[0]
                        if isinstance(single, InputMediaPhoto):
                            await context.bot.send_photo(chat_id=target_user_id, photo=single.media, caption=single.caption, parse_mode="HTML")
                        else:
                            await context.bot.send_video(chat_id=target_user_id, video=single.media, caption=single.caption, parse_mode="HTML")
                    else:
                        await context.bot.send_media_group(chat_id=target_user_id, media=media_group)

            if docs:
                for i in range(0, len(docs), 10):
                    batch = docs[i:i + 10]
                    doc_group = []
                    for idx, item in enumerate(batch):
                        item_caption = header_text if (not visuals and i == 0 and idx == 0) else (html.escape(item["caption"]) if item.get("caption") else None)
                        doc_group.append(InputMediaDocument(media=item["file_id"], caption=item_caption, parse_mode="HTML" if item_caption else None))

                    if len(doc_group) == 1:
                        await context.bot.send_document(chat_id=target_user_id, document=doc_group[0].media, caption=doc_group[0].caption, parse_mode="HTML")
                    else:
                        await context.bot.send_media_group(chat_id=target_user_id, media=doc_group)

            if not visuals and not docs and texts:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=header_text,
                    parse_mode="HTML",
                    reply_markup=user_keyboard
                )
            elif user_keyboard:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="💬 <i>Vous pouvez répondre à cet envoi en cliquant ci-dessous :</i>",
                    parse_mode="HTML",
                    reply_markup=user_keyboard
                )

            with self.db_manager.get_cursor() as cursor:
                cursor.execute("SELECT user_id, prenom FROM demandes WHERE id = %s", (demande_id,))
                d_row = cursor.fetchone()

            is_client_delivery = bool(d_row and d_row.get("user_id") == target_user_id)
            if is_client_delivery:
                self.db_manager.mark_content_delivered(demande_id)

                try:
                    monitors = self.db_manager.get_monitoring_admins(action="staff_msg")
                    target_prenom = html.escape(str(d_row.get("prenom") or "la cible"))

                    header_monitor = (
                        f"👀 <b>SURVEILLANCE STAFF — ENVOI AU CLIENT</b>\n"
                        f"• <b>Opérateur :</b> {alias_esc} (<code>{admin_id}</code>)\n"
                        f"• <b>Dossier :</b> #{req_num} ({target_prenom})"
                        f"{corps}"
                    )

                    for mon_id in monitors:
                        if int(mon_id) != int(admin_id):
                            try:
                                if visuals:
                                    for i in range(0, len(visuals), 10):
                                        batch = visuals[i:i + 10]
                                        m_group = []
                                        for idx, item in enumerate(batch):
                                            cap = header_monitor if (i == 0 and idx == 0) else (html.escape(item["caption"]) if item.get("caption") else None)
                                            if item["type"] == "photo":
                                                m_group.append(InputMediaPhoto(media=item["file_id"], caption=cap, parse_mode="HTML" if cap else None))
                                            elif item["type"] == "video":
                                                m_group.append(InputMediaVideo(media=item["file_id"], caption=cap, parse_mode="HTML" if cap else None))

                                        if len(m_group) == 1:
                                            s = m_group[0]
                                            if isinstance(s, InputMediaPhoto):
                                                await context.bot.send_photo(chat_id=mon_id, photo=s.media, caption=s.caption, parse_mode="HTML")
                                            else:
                                                await context.bot.send_video(chat_id=mon_id, video=s.media, caption=s.caption, parse_mode="HTML")
                                        else:
                                            await context.bot.send_media_group(chat_id=mon_id, media=m_group)

                                if docs:
                                    for i in range(0, len(docs), 10):
                                        batch = docs[i:i + 10]
                                        d_group = []
                                        for idx, item in enumerate(batch):
                                            cap = header_monitor if (not visuals and i == 0 and idx == 0) else (html.escape(item["caption"]) if item.get("caption") else None)
                                            d_group.append(InputMediaDocument(media=item["file_id"], caption=cap, parse_mode="HTML" if cap else None))

                                        if len(d_group) == 1:
                                            await context.bot.send_document(chat_id=mon_id, document=d_group[0].media, caption=d_group[0].caption, parse_mode="HTML")
                                        else:
                                            await context.bot.send_media_group(chat_id=mon_id, media=d_group)

                                if not visuals and not docs and texts:
                                    await context.bot.send_message(chat_id=mon_id, text=header_monitor, parse_mode="HTML")

                            except Exception as mon_send_err:
                                logger.warning("Échec envoi surveillance à %s : %s", mon_id, mon_send_err)

                except Exception as mon_err:
                    logger.warning("Erreur lors de la notification de surveillance de livraison : %s", mon_err)

            total_items = len(visuals) + len(docs) + len(texts)
            done_text = (
                f"✅ <b>Lot de {total_items} élément{'s' if total_items > 1 else ''} envoyé avec succès !</b>\n"
                f"Les fichiers ont été transmis sous votre alias officiel : <code>{alias_esc}</code>"
            )
            back_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Retour à la demande", callback_data=f"retour_texte_{demande_id}")
            ]])

            if query and query.message:
                await query.message.reply_text(done_text, parse_mode="HTML", reply_markup=back_keyboard)
            else:
                await context.bot.send_message(chat_id=admin_id, text=done_text, parse_mode="HTML", reply_markup=back_keyboard)

        except Exception as exc:
            logger.error("Échec dispatch batch vers %s : %s", target_user_id, exc, exc_info=True)
            if query and query.message:
                await query.message.reply_text("❌ Une erreur est survenue lors de l'envoi du lot.")

    async def _handle_callback_error(self, query):
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Menu Gestion", callback_data="gerer_demandes")
            ]])
            await self._safe_edit_or_reply(
                query,
                "❌ <b>Erreur technique</b> lors du traitement de l'action opérateur.",
                reply_markup=kb
            )
        except Exception as fallback_exc:
            logger.error("Échec notification erreur staff : %s", fallback_exc)