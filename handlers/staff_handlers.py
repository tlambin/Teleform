"""Routeur principal des actions et callbacks opérationnels (Staff) avec relais groupé."""

import asyncio
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
from . import staff_handlers_ui as ui

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

    async def show_demande_detail_unified(self, update_or_query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, back_callback: str = "demandes_suivies"):
        """Aiguille intelligemment vers la vraie vue Disponible ou Suivie selon le statut du dossier."""
        query = update_or_query if hasattr(update_or_query, "data") else getattr(update_or_query, "callback_query", None)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT statut, admin_en_charge FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if not dem:
            if query:
                await query.answer("❌ Dossier introuvable.", show_alert=True)
            return

        statut = dem.get("statut", "")

        if statut in ("📥 Reçue", "🎯 Assignée (VIP)") and not dem.get("admin_en_charge"):
            if hasattr(self.dispo, "show_single_dispo"):
                await self.dispo.show_single_dispo(query, context, demande_id, back_callback=back_callback)
            else:
                await self.suivi.show_single_demande(query, context, demande_id, back_callback=back_callback)
        else:
            await self.suivi.show_single_demande(query, context, demande_id, back_callback=back_callback)

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

        # Gestion des flux de démission
        if data in ("menu_demission", "demission_confirm_admin", "demission_confirm_staff", "demission_confirm_all"):
            text, kb = self.interface.route_callback(data, user_id, update.effective_user.first_name)
            if text and kb:
                await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

        elif data.startswith("demission_exec_"):
            scope = data.replace("demission_exec_", "")
            await self._handle_staff_demission(update, context, user_id, scope)
            return

        if not self.db_manager.is_staff(user_id):
            logger.warning("Tentative d'accès staff refusée pour l'utilisateur %s", user_id)
            return

        try:
            # 0. Décision sur mission assignée VIP
            if data.startswith("vip_accept_"):
                demande_id = int(data.replace("vip_accept_", ""))
                await self._handle_vip_accept(query, context, demande_id, user_id)
                return

            elif data.startswith("vip_decline_"):
                demande_id = int(data.replace("vip_decline_", ""))
                await self._handle_vip_decline(query, context, demande_id, user_id)
                return

            # 1. Demandes disponibles
            elif data == "demandes_disponibles":
                await self.dispo.show_demandes_disponibles(update, context)

            elif (
                data.startswith("dispo_")
                or data.startswith("admin_del_dispo_")
                or data.startswith("admin_propose_prix_")
                or data.startswith("staff_report_dispo_")
            ):
                await self.dispo.handle_callback_routing(update, context, data)

            # 2. Prise en charge
            elif data.startswith("suivre_demande_"):
                demande_id = int(data.replace("suivre_demande_", ""))
                await self.dispo.assign_demande_to_admin(update, context, demande_id)

            # 3. Demandes suivies
            elif data == "demandes_suivies":
                await self.suivi.show_demandes_suivies(update, context)

            elif data.startswith("suivi_") or data.startswith("confirm_payment_prio_"):
                await self.suivi.handle_callback_routing(update, context, data)

            # 4. Préférences de notifications
            elif data == "menu_notifs":
                await self.notifs.show_notifs_menu(update, context)

            elif data.startswith("pref_") or data.startswith("toggle_mon_") or data == "menu_surveillance_notifs":
                await self.notifs.handle_callback_routing(update, context, data)

            # 5. Photos et affichage unifié
            elif data.startswith("voir_photo_"):
                await self.photos.voir_photo_demande(update, context)

            elif data.startswith("retour_texte_"):
                parts = data.split("_")
                demande_id = int(parts[2])
                back_cb = "demandes_suivies"
                if "_back_" in data:
                    back_cb = data.split("_back_")[1]
                await self.show_demande_detail_unified(query, context, demande_id, back_callback=back_cb)

            # 6. Gestion dynamique des statuts
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

            # 8. Profils
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

            # 10. Contact superviseur vers Piégeur
            elif data.startswith("admin_contact_staff_"):
                parts = data.split("_")
                demande_id = int(parts[3])
                target_staff_id = int(parts[4])
                await self._prompt_admin_contact_staff(update, context, demande_id, target_staff_id)

            # 11. Contact du demandeur
            elif data.startswith("toggle_contact_content_"):
                demande_id = int(data.replace("toggle_contact_content_", ""))
                cle = f"contact_with_content_{demande_id}"
                context.user_data[cle] = not context.user_data.get(cle, False)
                await self._prompt_contact_user(update, context, demande_id)

            elif data.startswith("contacter_") and not data.startswith("contacter_owner") and not data.startswith("contacter_archive_"):
                demande_id = int(data.replace("contacter_", ""))
                await self._prompt_contact_user(update, context, demande_id)

            elif data.startswith("contact_mode_"):
                parts = data.split("_")
                demande_id = int(parts[2])
                mode_choice = parts[3]
                await self._start_contact_input(update, context, demande_id, mode_choice)

            elif data.startswith("contact_close_conv_"):
                demande_id = int(data.replace("contact_close_conv_", ""))
                await self._close_conversation(update, context, demande_id)

            elif data.startswith("send_batch_"):
                demande_id = int(data.replace("send_batch_", ""))
                await self._dispatch_media_batch(update, context, demande_id)

            elif data.startswith("cancel_contact_") and not data.startswith("cancel_contact_owner"):
                demande_id = int(data.replace("cancel_contact_", ""))
                context.user_data.pop("contact_session", None)
                await self.show_demande_detail_unified(query, context, demande_id)

            else:
                logger.warning("Callback staff non intercepté : %s", data)

        except Exception as exc:
            logger.error("Erreur callback staff '%s' : %s", data, exc, exc_info=True)
            await self._handle_callback_error(query)

    handle_admin_callbacks = handle_staff_callbacks

    # ==================== DÉMISSION DU PERSONNEL ====================

    async def _handle_staff_demission(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, scope: str):
        """Traite la démission d'un membre selon le périmètre sélectionné."""
        query = update.callback_query
        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)

        if int(user_id) == int(primary_owner_id):
            if query:
                await query.answer("❌ Le propriétaire principal ne peut pas démissionner.", show_alert=True)
            return

        alias = self.db_manager.get_staff_alias(user_id) or f"Membre_{user_id}"
        details_demission = []

        try:
            with self.db_manager.transaction() as cursor:
                if scope in ("staff", "all"):
                    abandoned = self.db_manager.abandon_staff_demandes_for_pause(user_id)
                    cursor.execute("DELETE FROM staff WHERE user_id = %s", (int(user_id),))
                    details_demission.append(f"Piégeur ({len(abandoned)} dossier(s) libéré(s))")

                if scope in ("admin", "all"):
                    cursor.execute("DELETE FROM admins WHERE user_id = %s AND is_owner = FALSE", (int(user_id),))
                    details_demission.append("Administrateur")

            self.db_manager.clear_cache(f"is_staff_{user_id}")
            self.db_manager.clear_cache(f"is_admin_{user_id}")
            self.db_manager.clear_cache(f"alias_{user_id}")
            self.db_manager.clear_cache(f"perm_{user_id}")
            self.config.reload_roles()

            resume_roles = " et ".join(details_demission)
            logger.info("🚪 Démission enregistrée pour %s (%s) : %s", alias, user_id, resume_roles)

            if primary_owner_id and int(primary_owner_id) != int(user_id):
                try:
                    notif_owner = ui.format_demission_owner_notification(alias, user_id, resume_roles)
                    await context.bot.send_message(
                        chat_id=primary_owner_id,
                        text=notif_owner,
                        parse_mode="HTML"
                    )
                except Exception as err_notif:
                    logger.warning("Échec notification démission à l'Owner : %s", err_notif)

            msg_confirm, kb = ui.format_demission_user_confirmation(resume_roles)
            await self._safe_edit_or_reply(query, msg_confirm, reply_markup=kb)

        except Exception as exc:
            logger.error("Erreur lors de la démission de %s : %s", user_id, exc, exc_info=True)
            if query:
                await query.answer("❌ Erreur technique lors du traitement de votre démission.", show_alert=True)

    # ==================== SUPERVISION ADMIN VERS PIÉGEUR ====================

    async def _prompt_admin_contact_staff(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        query = update.callback_query
        alias_staff = self.db_manager.get_staff_alias(staff_id)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, prenom FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        req_num = row["id"] if row else demande_id

        context.user_data["contact_session"] = {
            "demande_id": demande_id,
            "target_user_id": staff_id,
            "prenom": f"Piégeur ({alias_staff})",
            "req_num": req_num,
            "mode": "yes",
            "allow_reply": True,
            "is_content_bundle": False,
            "visual_media": [],
            "doc_media": [],
            "text_notes": [],
        }

        text, kb = ui.get_admin_contact_staff_prompt(alias_staff, req_num, demande_id)
        await self._safe_edit_or_reply(query, text, reply_markup=kb)

    # ==================== GESTION DE L'ACCEPTATION / REFUS VIP ====================

    async def _handle_vip_accept(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, prenom, statut FROM demandes WHERE id = %s",
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
            req_num = dem["id"]
            alias = self.db_manager.get_staff_alias(staff_id)
            prenom_cible = dem.get("prenom", "")

            await query.answer(f"✅ Demande #{req_num} acceptée !", show_alert=False)

            confirm_msg, kb = ui.build_vip_accept_content(req_num, prenom_cible, demande_id)
            await self._safe_edit_or_reply(query, confirm_msg, reply_markup=kb)

            try:
                vip_user_id = dem["user_id"]
                notif_vip, notif_kb = ui.format_vip_accept_client_notification(req_num, alias, prenom_cible)
                await context.bot.send_message(
                    chat_id=vip_user_id,
                    text=notif_vip,
                    parse_mode="HTML",
                    reply_markup=notif_kb
                )
            except Exception as e_notif:
                logger.warning("Impossible de notifier le client VIP %s : %s", dem.get("user_id"), e_notif)
        else:
            await query.answer("❌ Erreur technique lors de l'acceptation.", show_alert=True)

    async def _handle_vip_decline(self, query, context: ContextTypes.DEFAULT_TYPE, demande_id: int, staff_id: int):
        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, prenom, nom, age, localisation, prioritaire, montant, orientation, photo_id, statut FROM demandes WHERE id = %s",
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
            req_num = dem["id"]
            alias = self.db_manager.get_staff_alias(staff_id)
            prenom_cible = dem.get("prenom", "")

            await query.answer("Demande déclinée.", show_alert=False)

            decline_msg, kb = ui.build_vip_decline_content(req_num)
            await self._safe_edit_or_reply(query, decline_msg, reply_markup=kb)

            try:
                vip_user_id = dem["user_id"]
                notif_vip, notif_kb = ui.format_vip_decline_client_notification(req_num, alias, prenom_cible)
                await context.bot.send_message(
                    chat_id=vip_user_id,
                    text=notif_vip,
                    parse_mode="HTML",
                    reply_markup=notif_kb
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
        query = update.callback_query
        admin_id = update.effective_user.id

        if data == "admin_pause_prompt":
            active_demandes = self.db_manager.get_staff_active_demandes(admin_id)
            nb = len(active_demandes)

            if nb == 0:
                self.db_manager.set_staff_pause_status(admin_id, paused=True)
                text, kb = ui.get_pause_empty_content()
                await self._safe_edit_or_reply(query, text, reply_markup=kb)
                return

            text, kb = ui.get_pause_prompt_content(nb)
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

        elif data == "admin_pause_keep":
            self.db_manager.set_staff_pause_status(admin_id, paused=True)
            text, kb = ui.get_pause_kept_content()
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

        elif data == "admin_pause_release":
            abandoned = self.db_manager.abandon_staff_demandes_for_pause(admin_id)
            self.db_manager.set_staff_pause_status(admin_id, paused=True)
            alias = self.db_manager.get_staff_alias(admin_id)
            alias_esc = html.escape(str(alias or f"Staff_{admin_id}"))

            for dem in abandoned:
                try:
                    c_id = dem["user_id"]
                    req_num = dem["id"]
                    msg_client, kb_client = ui.format_pause_abandon_client_notification(req_num, alias_esc, dem["id"])
                    await context.bot.send_message(chat_id=c_id, text=msg_client, parse_mode="HTML", reply_markup=kb_client)
                except Exception as err:
                    logger.warning("Notification abandon pause impossible pour user %s : %s", dem.get("user_id"), err)

            text, kb = ui.get_pause_released_content(len(abandoned))
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

        elif data == "admin_resume":
            self.db_manager.set_staff_pause_status(admin_id, paused=False)
            text, kb = ui.get_resume_service_content()
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
            return

    # ==================== CONTACT DEMANDEUR ET MODE CONVERSATION ====================

    def _is_conv_open(self, context: ContextTypes.DEFAULT_TYPE, demande_id: int) -> bool:
        active_convs = context.bot_data.setdefault("active_conversations", {})
        return demande_id in active_convs

    async def _prompt_contact_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        query = update.callback_query
        if not query or not update.effective_user:
            return

        try:
            await query.answer()
        except Exception:
            pass

        with self.db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, prenom FROM demandes WHERE id = %s",
                (demande_id,)
            )
            row = cursor.fetchone()

        if not row:
            await query.answer("❌ Demande introuvable.", show_alert=True)
            return

        req_num = row["id"]
        prenom_esc = html.escape(str(row.get("prenom") or ""))
        cible_str = f" - {prenom_esc}" if prenom_esc else ""

        is_bundle = context.user_data.get(f"contact_with_content_{demande_id}", False)
        conv_active = self._is_conv_open(context, demande_id)

        text, keyboard = ui.build_contact_user_menu(req_num, cible_str, conv_active, is_bundle, demande_id)

        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await self._safe_edit_or_reply(query, text, reply_markup=keyboard)

    async def _close_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        query = update.callback_query
        active_convs = context.bot_data.setdefault("active_conversations", {})
        active_convs.pop(demande_id, None)

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, user_id, prenom FROM demandes WHERE id = %s", (demande_id,))
            dem = cursor.fetchone()

        if dem:
            req_num = dem["id"]
            try:
                msg_client, kb_client = ui.format_close_conv_client_notification(req_num)
                await context.bot.send_message(chat_id=dem["user_id"], text=msg_client, parse_mode="HTML", reply_markup=kb_client)
            except Exception as e_notif:
                logger.warning("Notification fermeture conversation impossible pour user %s : %s", dem.get("user_id"), e_notif)

        await query.answer("🔒 Conversation clôturée avec succès.", show_alert=True)
        await self.show_demande_detail_unified(query, context, demande_id)

    async def _start_contact_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int, mode_choice: str):
        query = update.callback_query
        if not query:
            return

        with self.db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, user_id, prenom FROM demandes WHERE id = %s", (demande_id,))
            row = cursor.fetchone()

        if not row:
            return

        req_num = row["id"]
        prenom_esc = html.escape(str(row.get("prenom") or ""))

        is_content_bundle = context.user_data.pop(f"contact_with_content_{demande_id}", False)
        allow_reply = (mode_choice in ("yes", "conv"))

        context.user_data["contact_session"] = {
            "demande_id": demande_id,
            "target_user_id": row["user_id"],
            "prenom": row["prenom"],
            "req_num": row["id"],
            "mode": mode_choice,
            "allow_reply": allow_reply,
            "is_content_bundle": is_content_bundle,
            "visual_media": [],
            "doc_media": [],
            "text_notes": [],
        }

        text, keyboard = ui.get_contact_input_prompt(req_num, prenom_esc, is_content_bundle, demande_id)
        await self._safe_edit_or_reply(query, text, reply_markup=keyboard)

    async def handle_collect_admin_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        msg = update.message
        if not msg:
            return False

        session = context.user_data.get("contact_session")
        if not session:
            return False

        demande_id = session["demande_id"]
        target_user_id = session["target_user_id"]
        is_bundle = session.get("is_content_bundle", False)
        mode = session.get("mode", "yes")
        allow_reply = session.get("allow_reply", False)
        admin_id = update.effective_user.id
        raw_alias = self.db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"
        alias_esc = html.escape(str(raw_alias))
        req_num = session.get("req_num", demande_id)
        caption = (msg.caption or "").strip()

        # Envoi direct (unitaire)
        if not is_bundle:
            if mode != "conv":
                context.user_data.pop("contact_session", None)
            else:
                active_convs = context.bot_data.setdefault("active_conversations", {})
                active_convs[demande_id] = {
                    "admin_id": admin_id,
                    "user_id": target_user_id,
                }

            header_text = ui.build_direct_message_header(req_num, alias_esc)
            client_kb = ui.get_client_reply_keyboard(demande_id, admin_id) if allow_reply else None

            try:
                if msg.photo or msg.video or msg.document:
                    full_caption = f"{header_text}« {html.escape(caption)} »" if caption else header_text.strip()
                    await context.bot.copy_message(
                        chat_id=target_user_id,
                        from_chat_id=msg.chat_id,
                        message_id=msg.message_id,
                        caption=full_caption,
                        parse_mode="HTML",
                        reply_markup=client_kb
                    )
                elif msg.text:
                    full_text = f"{header_text}« {html.escape(msg.text.strip())} »"
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=full_text,
                        parse_mode="HTML",
                        reply_markup=client_kb
                    )

                self.db_manager.mark_content_delivered(demande_id)

                if mode == "conv":
                    staff_confirm_text, staff_confirm_kb = ui.get_staff_conv_open_confirmation(demande_id)
                    await msg.reply_text(staff_confirm_text, parse_mode="HTML", reply_markup=staff_confirm_kb)
                else:
                    kb_done = InlineKeyboardMarkup([[
                        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
                    ]])
                    await msg.reply_text("✅ <b>Message transmis directement au demandeur !</b>", parse_mode="HTML", reply_markup=kb_done)
                return True

            except Exception as exc:
                logger.error("Erreur transmission directe staff -> client : %s", exc)
                await msg.reply_text("❌ Échec lors de la transmission du message.")
                return True

        # Envoi en lot
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

        session["update_seq"] = session.get("update_seq", 0) + 1
        current_seq = session["update_seq"]

        await asyncio.sleep(1.0)
        if session.get("update_seq") != current_seq:
            return True

        status_msg_ids = session.setdefault("status_msg_ids", [])
        for mid in status_msg_ids:
            try:
                await context.bot.delete_message(chat_id=msg.chat_id, message_id=mid)
            except Exception:
                pass
        status_msg_ids.clear()

        total = len(session["visual_media"]) + len(session["doc_media"]) + len(session["text_notes"])
        status_text, keyboard = ui.build_basket_status_content(req_num, total, demande_id)

        new_status_msg = await msg.reply_text(status_text, parse_mode="HTML", reply_markup=keyboard)
        status_msg_ids.append(new_status_msg.message_id)
        return True

    async def _dispatch_media_batch(self, update: Update, context: ContextTypes.DEFAULT_TYPE, demande_id: int):
        query = update.callback_query
        session = context.user_data.pop("contact_session", None)

        if not session or session.get("demande_id") != demande_id:
            return

        admin_id = update.effective_user.id
        target_user_id = session["target_user_id"]
        req_num = session["req_num"]
        mode = session.get("mode", "yes")
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

        if mode == "conv":
            active_convs = context.bot_data.setdefault("active_conversations", {})
            active_convs[demande_id] = {
                "admin_id": admin_id,
                "user_id": target_user_id,
            }

        combined_text = "\n".join([html.escape(t) for t in texts])
        corps = f"\n\n« {combined_text} »" if combined_text else ""
        header_text = ui.build_batch_message_header(req_num, alias_esc, corps, mode, allow_reply)
        user_keyboard = ui.get_client_reply_keyboard(demande_id, admin_id) if allow_reply else None

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
                await context.bot.send_message(chat_id=target_user_id, text=header_text, parse_mode="HTML", reply_markup=user_keyboard)
            elif user_keyboard:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="💬 <i>Vous pouvez répondre à cet envoi en cliquant ci-dessous :</i>",
                    parse_mode="HTML",
                    reply_markup=user_keyboard
                )

            self.db_manager.mark_content_delivered(demande_id)

            total_items = len(visuals) + len(docs) + len(texts)
            done_text, back_keyboard = ui.get_batch_sent_success_content(total_items, alias_esc, demande_id)

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
            text, kb = ui.get_staff_callback_error_content()
            await self._safe_edit_or_reply(query, text, reply_markup=kb)
        except Exception as fallback_exc:
            logger.error("Échec notification erreur staff : %s", fallback_exc)