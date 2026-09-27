"""Composants visuels, gabarits textuels et claviers pour les interactions utilisateurs."""

import html
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==================== ADHÉSION OBLIGATOIRE ====================

def get_required_membership_content(sub_url: str) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'invite et les boutons pour l'obligation de rejoindre le groupe."""
    msg_text = (
        "📢 <b>Adhésion requise</b>\n\n"
        "Pour accéder aux services du bot et déposer vos demandes, vous devez obligatoirement rejoindre notre groupe.\n\n"
        "Cliquez sur le bouton ci-dessous pour vous inscrire via le bot dédié, puis cliquez sur <b>Vérifier mon adhésion</b> :"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ S'INSCRIRE AU GROUPE ✍️", url=sub_url)],
        [InlineKeyboardButton("🔄 VÉRIFIER MON ADHÉSION 🔄", callback_data="check_subscription")],
    ])
    return msg_text, keyboard


# ==================== RESTRICTIONS DE SERVICE & QUOTAS ====================

def get_service_disabled_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier quand le service de dépôt est désactivé."""
    text = (
        "🚫 <b>Service temporairement indisponible</b>\n\n"
        "La création et la navigation des demandes sont actuellement désactivées par l'administration."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")
    ]])
    return text, keyboard


def get_quota_reached_content(reason_msg: str) -> tuple[str, InlineKeyboardMarkup]:
    """Clavier proposé lorsque le quota de demandes actives est atteint."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ PASSER VIP ⭐", callback_data="menu_vip_shop")],
        [InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")],
    ])
    return reason_msg, keyboard


# ==================== NÉGOCIATION & ALLOCATION FINANCIÈRE ====================

def format_client_revalorisation_proposal(
    req_num: int,
    prenom: str,
    alias_staff: str,
    nouveau_prix: float,
    current_montant: float,
    demande_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte remise au client avec proposition de revalorisation par le piégeur."""
    client_alert = (
        f"💰 <b>Proposition de revalorisation (Dossier #{req_num})</b>\n\n"
        f"L'opérateur <b>{html.escape(str(alias_staff))}</b> souhaite prendre en charge votre dossier concernant <b>{prenom}</b> !\n\n"
        f"Il vous propose de réaliser la prestation pour <b>{nouveau_prix:.2f} €</b> (au lieu de <code>{current_montant:.2f} €</code>).\n\n"
        "• <b>Accepter :</b> Le dossier sera immédiatement pris en charge sous le statut ⏳ En attente.\n"
        "• <b>Refuser :</b> Votre demande reste active au tarif de base dans les disponibles."
    )
    client_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ ACCEPTER ({nouveau_prix:.2f} €)", callback_data=f"user_accept_remun_prio_{demande_id}"),
        InlineKeyboardButton("❌ REFUSER", callback_data=f"user_refuse_remun_prio_{demande_id}"),
    ]])
    return client_alert, client_kb


def get_std_remun_allocation_prompt(demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite au client pour allouer un tarif à une demande standard."""
    prompt_text = (
        f"💰 <b>Allocation d'un montant (Dossier #{demande_id})</b>\n\n"
        "Indiquez au clavier le <b>montant</b> que vous êtes prêt à allouer pour cette demande (en €) :\n\n"
        "<i>Votre dossier sera automatiquement converti en priorité et proposé aux piégeurs.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="voir_demandes")]])
    return prompt_text, kb


def get_std_remun_refused_content(req_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message actant le refus de rémunérer et l'abandon du dossier standard."""
    text = f"❌ <b>Dossier #{req_num} abandonné et clôturé.</b>\n\nVotre quota de demandes actives a été libéré."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")]])
    return text, kb


# ==================== RAPPELS & LIGNE DIRECTE ====================

def format_admin_reminder_alert(
    req_num: str,
    user_label_esc: str,
    prenom_esc: str,
    tag: str,
    demande_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Notification formelle de relance adressée au piégeur en charge."""
    remind_msg = (
        f"🔔 <b>RAPPEL DEMANDE #{req_num} [{tag}]</b>\n\n"
        f"Le demandeur <b>{user_label_esc}</b> vous relance concernant sa demande pour <b>{prenom_esc}</b>.\n"
        "Merci de consulter vos suivis ou de lui apporter une réponse."
    )
    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💌 OUVRIR MES SUIVIS 💌", callback_data="demandes_suivies")],
        [InlineKeyboardButton("💬 CONTACTER LE DEMANDEUR 💬", callback_data=f"contacter_{demande_id}")],
    ])
    return remind_msg, admin_kb


def get_user_reply_contact_prompt(alias: str, req_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour un message spontané du client vers son référent."""
    contact_text = (
        f"💬 <b>Ligne directe avec votre référent ({html.escape(str(alias))}) — Dossier #{req_num}</b>\n\n"
        "Tapez votre message ou envoyez vos fichiers ci-dessous. Ils lui seront immédiatement transmis :"
    )
    contact_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="cancel_user_reply")]])
    return contact_text, contact_kb


# ==================== ANNULATION & REPRISE DE DOSSIER ====================

def get_reprendre_demande_success_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier confirmant la remise en file d'attente."""
    text = "🔄 <b>Votre demande a été remise en file d'attente !</b>\n\nElle est de nouveau disponible pour toute l'équipe opérationnelle."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 VOIR MES DEMANDES 📋", callback_data="voir_demandes")]])
    return text, kb


def get_archiver_demande_success_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier confirmant le classement sans suite d'une demande abandonnée."""
    text = "🗑️ <b>Demande classée sans suite.</b>\n\nVotre demande a été archivée sous « 🗑️ Supprimée ». Une place vient d'être libérée."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗳️ NOUVELLE DEMANDE 🗳️", callback_data="new_demande")],
        [InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")],
    ])
    return text, kb


def get_client_cancel_prompt(demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie de la raison d'annulation client."""
    prompt_text = (
        f"✍️ <b>Demande d'annulation (Dossier #{demande_id})</b>\n\n"
        "Indiquez au clavier la <b>raison</b> de votre annulation :\n"
        "<i>Elle sera transmise à l'opérateur en charge pour validation.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 RETOUR 🔙", callback_data="voir_demandes")]])
    return prompt_text, kb


def build_staff_cancel_decision_alert(req_num: int, prenom: str, raison: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte remise au piégeur pour décider d'accepter ou refuser l'annulation client."""
    prenom_esc = html.escape(str(prenom or ""))
    raison_esc = html.escape(raison)
    text = (
        f"⚠️ <b>Demande d'annulation (Dossier #{req_num})</b>\n\n"
        f"Le client souhaite annuler pour <b>{prenom_esc}</b>.\n"
        f"<b>Motif :</b> « {raison_esc} »"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ACCEPTER L'ANNULATION", callback_data=f"accept_cancel_{demande_id}"),
        InlineKeyboardButton("❌ REFUSER L'ANNULATION", callback_data=f"refuse_cancel_{demande_id}"),
    ]])
    return text, kb


# ==================== SIGNALEMENT PAR LE STAFF ====================

def build_staff_report_alert(staff_alias: str, staff_id: int, req_num: int, prenom: str, motif: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte envoyée aux superviseurs lorsqu'un opérateur signale une demande disponible."""
    admin_alert = (
        f"🚨 <b>SIGNALEMENT D'UNE DEMANDE DISPONIBLE</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Opérateur :</b> {html.escape(str(staff_alias))} (<code>{staff_id}</code>)\n"
        f"• <b>Dossier :</b> #{req_num} ({prenom})\n"
        f"• <b>Motif :</b>\n« <i>{html.escape(motif)}</i> »"
    )
    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 RÉMUNÉRATION", callback_data=f"dispo_ask_remun_std_{demande_id}"),
            InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"admin_del_dispo_{demande_id}")
        ],
        [InlineKeyboardButton("📄 VOIR LE DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")],
    ])
    return admin_alert, admin_kb