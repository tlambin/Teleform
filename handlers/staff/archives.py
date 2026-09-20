"""Module de consultation des demandes archivées pour l'équipe Staff et Administration."""

import html
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import ContextTypes
from utils.validators import convert_utc_to_paris

logger = logging.getLogger(__name__)


class ArchivesManager:
    """Gestionnaire d'affichage et de navigation dans les archives (personnelles ou générales)."""

    def __init__(self, db_manager, config):
        self.db_manager = db_manager
        self.config = config
        logger.info("ArchivesManager initialisé avec support double vue (personnelle & générale)")

    async def _safe_edit_media_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, photo_id: str, caption: str, reply_markup):
        """Met à jour une photo existante ou envoie une nouvelle bulle photo proprement."""
        if query.message and query.message.photo:
            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML"),
                    reply_markup=reply_markup,
                )
                return
            except Exception:
                pass

        if query.message:
            try:
                await query.message.delete()
            except Exception:
                pass

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    async def _safe_edit_text_or_send(self, query, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup):
        """Met à jour un message texte ou supprime l'ancienne photo pour réémettre du texte."""
        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            try:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except Exception:
                if query.message:
                    await query.message.reply_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )

    async def show_archives(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0, is_global: bool = False):
        """Affiche les archives personnelles de l'opérateur ou les archives générales pour les admins."""
        query = update.callback_query
        user = update.effective_user
        if not user:
            return

        user_id = user.id

        # Contrôle des droits
        if is_global:
            privs = self.db_manager.get_admin_privileges(user_id)
            if not (self.db_manager.is_owner(user_id) or privs.get("can_view_archives", False)):
                if query:
                    await query.answer("❌ Vous n'avez pas la permission de consulter les archives générales.", show_alert=True)
                return
            admin_target = None
        else:
            if not self.config.is_staff(user_id):
                if query:
                    await query.answer("❌ Accès réservé au personnel opérationnel.", show_alert=True)
                return
            admin_target = user_id

        total = self.db_manager.get_archives_count(admin_id=admin_target)
        back_cb = "parametres" if is_global else "gerer_demandes"
        back_label = "⬅️ RETOUR"

        if total == 0:
            if is_global:
                msg = "📭 <b>Archives Générales</b>\n\nAucun dossier archivé enregistré sur la plateforme."
            else:
                msg = "📭 <b>Mes Dossiers Clôturés</b>\n\nVous n'avez pas encore finalisé ou archivé de demande."

            kb = InlineKeyboardMarkup([[InlineKeyboardButton(back_label, callback_data=back_cb)]])
            if query:
                await self._safe_edit_text_or_send(query, context, msg, kb)
            else:
                await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
            return

        page = max(0, min(page, total - 1))
        demande = self.db_manager.get_archives_page(page=page, admin_id=admin_target)
        if not demande:
            return

        caption = self._format_archive_card(demande, page, total, is_global=is_global)
        kb = self._build_archive_keyboard(page, total, is_global=is_global)
        photo_id = demande.get("photo_id")

        if query:
            if photo_id:
                await self._safe_edit_media_or_send(query, context, photo_id, caption, kb)
            else:
                await self._safe_edit_text_or_send(query, context, caption, kb)
        else:
            if photo_id:
                await update.message.reply_photo(photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                await update.message.reply_text(caption, parse_mode="HTML", reply_markup=kb)

    def _format_archive_card(self, item: dict, page: int, total: int, is_global: bool = False) -> str:
        """Formate la fiche d'une demande archivée avec liens sociaux cliquables."""
        prenom = html.escape(str(item.get("prenom") or ""))
        nom = html.escape(str(item.get("nom") or ""))
        complet = f"{prenom} {nom}".strip() or "Non renseigné"
        loc = html.escape(str(item.get("localisation") or "Non précisée"))
        statut = html.escape(str(item.get("statut") or "Archivée"))
        orig_id = item.get("original_id") or item.get("id") or "?"
        age = item.get("age") or "?"

        type_badge = "💎 Prioritaire" if item.get("prioritaire") else "📝 Standard"
        montant_str = f" ({item.get('montant', 0):.2f} €)" if item.get("prioritaire") else ""

        dt_crea = item.get("date_creation")
        crea_str = convert_utc_to_paris(dt_crea).strftime("%d/%m/%Y à %H:%M") if dt_crea else "?"

        dt_arch = item.get("date_archivage")
        arch_str = convert_utc_to_paris(dt_arch).strftime("%d/%m/%Y à %H:%M") if dt_arch else "?"

        titre = "📦 <b>Archives Générales</b>" if is_global else "📦 <b>Mon Archive Dossier</b>"
        lines = [
            f"{titre} #{orig_id} ({page + 1}/{total})\n",
            f"👤 <b>Cible :</b> {complet} ({age} ans)",
            f"📍 <b>Localisation :</b> {loc}",
            f"🎯 <b>Type :</b> {type_badge}{montant_str}",
            f"📊 <b>Statut de clôture :</b> <code>{statut}</code>",
        ]

        if is_global:
            admin_charge = item.get("admin_en_charge")
            if admin_charge:
                alias = self.db_manager.get_staff_alias(admin_charge)
                lines.append(f"👨‍💼 <b>Traité par :</b> {html.escape(alias or str(admin_charge))}")
            else:
                lines.append("👨‍💼 <b>Traité par :</b> <i>Non spécifié</i>")

        # Liens sociaux interactifs
        reseaux = []
        if item.get("instagram"):
            raw_ig = str(item["instagram"]).strip().lstrip("@")
            ig_esc = html.escape(raw_ig)
            reseaux.append(f'📷 <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
        if item.get("snapchat"):
            raw_snap = str(item["snapchat"]).strip().lstrip("@")
            snap_esc = html.escape(raw_snap)
            reseaux.append(f'👻 <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

        if reseaux:
            lines.append(f"🌐 <b>Réseaux :</b> {' | '.join(reseaux)}")

        if item.get("details"):
            det = html.escape(str(item["details"]))
            lines.append(f"💬 <b>Remarques :</b> <i>{det[:200]}</i>")

        lines.append(f"\n📅 <i>Créée le {crea_str}</i>")
        lines.append(f"🗄️ <i>Archivée le {arch_str}</i>")

        return "\n".join(lines)

    def _build_archive_keyboard(self, page: int, total: int, is_global: bool = False) -> InlineKeyboardMarkup:
        """Génère la barre de navigation dans les archives."""
        prefix = "global_arch_page_" if is_global else "archive_page_"
        back_cb = "parametres" if is_global else "gerer_demandes"

        buttons = []
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Précédente", callback_data=f"{prefix}{page - 1}"))
        if page < total - 1:
            nav.append(InlineKeyboardButton("Suivante ➡️", callback_data=f"{prefix}{page + 1}"))

        if nav:
            buttons.append(nav)

        buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data=back_cb)])
        return InlineKeyboardMarkup(buttons)