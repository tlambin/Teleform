"""Module de relais des messages du demandeur vers l'opérateur et de surveillance."""

import html
import logging
from telegram import Update
from telegram.ext import ContextTypes
from ui.user import demandes as ui

logger = logging.getLogger(__name__)


class RelaisManager:
    """Gère la retransmission de messages, fichiers et notifications de surveillance."""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def handle_user_reply_relay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Transmet la réponse de l'utilisateur vers son référent avec surveillance et gestion continue."""
        reply_info = context.user_data.pop("replying_to_admin", None)
        if not reply_info:
            return

        admin_id = reply_info["admin_id"]
        demande_id = reply_info["demande_id"]
        user = update.effective_user
        msg = update.message

        is_vip = self.db_manager.is_user_vip(user.id)
        user_comment = (msg.caption or msg.text or "").strip()

        active_convs = context.bot_data.setdefault("active_conversations", {})
        is_conv = (demande_id in active_convs)

        header_text = ui.build_relay_header(user, is_vip, demande_id, user_comment)
        admin_keyboard = ui.build_admin_relay_keyboard(demande_id, is_conv)

        try:
            if msg.photo or msg.video or msg.document:
                await context.bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id,
                    caption=header_text,
                    parse_mode="HTML",
                    reply_markup=admin_keyboard,
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=header_text,
                    parse_mode="HTML",
                    reply_markup=admin_keyboard,
                )

            # Surveillance superviseurs
            badge_vip = " ⭐ <b>[VIP]</b>" if is_vip else ""
            user_label = f"@{user.username}" if user.username else f"{user.first_name} (ID : {user.id})"
            user_label_esc = html.escape(user_label)
            corps = f"\n\n« {html.escape(user_comment)} »" if user_comment else ""

            await self._dispatch_surveillance_alert(context, msg, user, admin_id, demande_id, user_label_esc, badge_vip, corps)

            # Confirmation utilisateur
            client_text, client_kb = ui.get_client_confirmation_content(demande_id, admin_id, is_conv)
            await msg.reply_text(
                client_text,
                parse_mode="HTML",
                reply_markup=client_kb,
            )

        except Exception as exc:
            logger.error("Erreur renvoi réponse utilisateur vers staff %s : %s", admin_id, exc)
            await msg.reply_text("❌ Une erreur est survenue lors de la transmission de votre message.")

    async def _dispatch_surveillance_alert(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        msg,
        user,
        admin_id: int,
        demande_id: int,
        user_label_esc: str,
        badge_vip: str,
        corps: str,
    ):
        """Transmet une copie aux comptes superviseurs abonnés."""
        try:
            monitors = self.db_manager.get_monitoring_admins(action="user_msg")
            alias_staff = self.db_manager.get_staff_alias(admin_id)

            alert_text, kb_spy = ui.build_surveillance_alert(
                user_label_esc=user_label_esc,
                badge_vip=badge_vip,
                demande_id=demande_id,
                alias_staff=alias_staff,
                admin_id=admin_id,
                corps=corps
            )

            for mon_id in monitors:
                if int(mon_id) not in (int(user.id), int(admin_id)):
                    try:
                        if msg.photo or msg.video or msg.document:
                            await context.bot.copy_message(
                                chat_id=mon_id,
                                from_chat_id=msg.chat_id,
                                message_id=msg.message_id,
                                caption=alert_text,
                                parse_mode="HTML",
                                reply_markup=kb_spy,
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=mon_id,
                                text=alert_text,
                                parse_mode="HTML",
                                reply_markup=kb_spy,
                            )
                    except Exception:
                        pass
        except Exception as mon_err:
            logger.warning("Erreur surveillance user_msg : %s", mon_err)