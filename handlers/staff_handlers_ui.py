"""Composants visuels, gabarits textuels et claviers pour les opérations Staff."""

import html
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==================== DÉMISSION DU PERSONNEL ====================

def format_demission_owner_notification(alias: str, user_id: int, resume_roles: str) -> str:
    """Notification envoyée au propriétaire lors de la démission d'un membre."""
    alias_esc = html.escape(str(alias))
    return (
        "🚪 <b>DÉMISSION D'UN MEMBRE DE L'ÉQUIPE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Membre :</b> {alias_esc} (<code>{user_id}</code>)\n"
        f"• <b>Fonction(s) quittée(s) :</b> {html.escape(resume_roles)}\n\n"
        "<i>Les autorisations ont été révoquées et les dossiers actifs ont été replacés dans les disponibles.</i>"
    )


def format_demission_user_confirmation(resume_roles: str) -> tuple[str, InlineKeyboardMarkup]:
    """Message de confirmation remis au membre qui démissionne."""
    text = (
        "✅ <b>Démission prise en compte</b>\n\n"
        f"Vous avez démissionné avec succès de vos fonctions : <b>{html.escape(resume_roles)}</b>.\n\n"
        "Merci pour votre contribution au service !"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 RETOUR À L'ACCUEIL", callback_data="start_menu")
    ]])
    return text, kb


# ==================== CONTACT DIRECTION -> PIÉGEUR ====================

def get_admin_contact_staff_prompt(alias_staff: str, req_num: int, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour un message administratif à destination d'un piégeur."""
    text = (
        f"🛡️ <b>Message Direction ➔ Piégeur ({html.escape(str(alias_staff))})</b>\n"
        f"Dossier concerné : <b>#{req_num}</b>\n\n"
        "Tapez votre message ou envoyez vos fichiers ci-dessous :\n"
        "<i>Le message lui sera délivré sous votre alias officiel.</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ]])
    return text, kb


# ==================== MISSIONS ASSIGNÉES VIP ====================

def build_vip_accept_content(req_num: int, prenom_cible: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de prise en charge d'une mission VIP pour l'opérateur."""
    text = (
        f"✅ <b>Mission VIP acceptée (Dossier #{req_num})</b>\n\n"
        f"Vous avez pris en charge le dossier de <b>{html.escape(str(prenom_cible))}</b>.\n"
        "Le dossier est désormais actif sous le statut <b>⏳ En attente</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ VOIR LA DEMANDE", callback_data=f"retour_texte_{demande_id}")],
        [InlineKeyboardButton("💌 MES SUIVIS", callback_data="demandes_suivies")]
    ])
    return text, kb


def format_vip_accept_client_notification(req_num: int, alias: str, prenom_cible: str) -> tuple[str, InlineKeyboardMarkup]:
    """Notification remise au client VIP confirmant l'acceptation de sa demande."""
    text = (
        f"🌟 <b>Votre demande #{req_num} a été acceptée !</b>\n\n"
        f"Votre référent <b>{html.escape(str(alias))}</b> a validé la prise en charge de votre dossier "
        f"pour <b>{html.escape(str(prenom_cible))}</b>.\n\n"
        "Le statut passe en <b>⏳ En attente</b> (premier contact en cours)."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 SUIVRE MA DEMANDE", callback_data="voir_demandes")
    ]])
    return text, kb


def build_vip_decline_content(req_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de refus d'une mission VIP pour l'opérateur."""
    text = (
        f"ℹ️ <b>Demande #{req_num} déclinée</b>\n\n"
        "Le dossier a été replacé dans les <b>demandes disponibles</b> pour le reste de l'équipe."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📮 DEMANDES DISPONIBLES", callback_data="demandes_disponibles")],
        [InlineKeyboardButton("💌 MES SUIVIS", callback_data="demandes_suivies")]
    ])
    return text, kb


def format_vip_decline_client_notification(req_num: int, alias: str, prenom_cible: str) -> tuple[str, InlineKeyboardMarkup]:
    """Notification remise au client VIP indiquant le désistement du référent sollicité."""
    text = (
        f"ℹ️ <b>Mise à jour de votre demande VIP #{req_num}</b>\n\n"
        f"Votre référent sollicité ({html.escape(str(alias))}) n'est malheureusement pas disponible actuellement "
        f"pour prendre en charge le dossier de <b>{html.escape(str(prenom_cible))}</b>.\n\n"
        "Votre demande a été immédiatement transmise à l'ensemble de l'équipe avec priorité absolue !"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 SUIVRE MA DEMANDE", callback_data="voir_demandes")
    ]])
    return text, kb


# ==================== MODE PAUSE ====================

def get_pause_empty_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message d'activation de pause sans dossier en cours."""
    text = (
        "⏸️ <b>Mode pause activé</b>\n\n"
        "• Vous ne recevrez plus aucune notification de nouvelle demande.\n"
        "• Vous n'apparaissez plus dans la liste de sélection VIP.\n"
        "• Vous n'avez aucun dossier actif en attente."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]])
    return text, kb


def get_pause_prompt_content(nb_dossiers: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de décision sur le sort des dossiers lors de la mise en pause."""
    text = (
        f"⏸️ <b>Passage en mode pause</b>\n\n"
        f"Vous avez actuellement <b>{nb_dossiers}</b> demande(s) en cours de traitement.\n"
        "Que souhaitez-vous faire de vos dossiers ?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 CONSERVER MES DOSSIERS EN COURS", callback_data="admin_pause_keep")],
        [InlineKeyboardButton("❌ LIBÉRER ET ABANDONNER MES DOSSIERS", callback_data="admin_pause_release")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]
    ])
    return text, kb


def get_pause_kept_content() -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de pause avec conservation des dossiers."""
    text = (
        "⏸️ <b>Mode pause activé (dossiers conservés)</b>\n\n"
        "• Vos demandes en cours restent assignées à votre compte.\n"
        "• Aucune nouvelle demande ne vous sera attribuée ni notifiée.\n"
        "• Vous pouvez continuer à traiter vos suivis à votre rythme."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]])
    return text, kb


def get_pause_released_content(count_abandoned: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de pause avec libération des dossiers."""
    text = (
        f"⏸️ <b>Mode pause activé</b>\n\n"
        f"• {count_abandoned} dossier(s) libéré(s) et notifiés aux demandeurs.\n"
        "• Vous êtes désormais retiré du service jusqu'à votre reprise."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]])
    return text, kb


def format_pause_abandon_client_notification(req_num: int, alias_esc: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Notification envoyée au demandeur lorsque son référent abandonne son dossier pour pause."""
    msg = (
        f"⚠️ <b>Demande #{req_num} — Référent indisponible</b>\n\n"
        f"Votre référent (<b>{alias_esc}</b>) est actuellement en pause.\n"
        "Sa prise en charge sur votre dossier a donc été interrompue.\n\n"
        "Vous pouvez remettre votre demande dans la file d'attente ou la classer sans suite :"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REPRENDRE MA DEMANDE", callback_data=f"reprendre_demande_{demande_id}")],
        [InlineKeyboardButton("🗑️ ARCHIVER LA DEMANDE", callback_data=f"archiver_demande_{demande_id}")]
    ])
    return msg, kb


def get_resume_service_content() -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation de reprise de service."""
    text = (
        "🟢 <b>Bon retour ! Vous êtes à nouveau en service.</b>\n\n"
        "• Vous recevrez à nouveau les alertes et notifications.\n"
        "• Vous êtes à nouveau sélectionnable par les clients VIP."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")]])
    return text, kb


# ==================== CONTACT DEMANDEUR & CONVERSATION ====================

def build_contact_user_menu(req_num: int, cible_str: str, conv_active: bool, is_bundle: bool, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Menu interactif de configuration de l'échange avec le client."""
    badge_bundle = "✅ OUI" if is_bundle else "❌ NON"

    text = (
        "💬 <b>CONTACTER LE CLIENT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Demande #{req_num}{cible_str}\n\n"
        "<i>Choisissez le type d'échange :</i>\n\n"
        "• <i>Simple : Le client a droit à une seule réponse.</i>\n\n"
        "• <i>Notification : Sans réponse possible.</i>\n\n"
        "• <i>Conversation : Discussion fluide ouverte à plusieurs messages.</i>\n\n"
        "<i>Option Contenu :</i>\n\n"
        "<i>Activez-la si vous souhaitez envoyer du contenu (photos/vidéos)</i>"
    )

    buttons = [
        [
            InlineKeyboardButton("💬 SIMPLE", callback_data=f"contact_mode_{demande_id}_yes"),
            InlineKeyboardButton("🔒 NOTIFICATION", callback_data=f"contact_mode_{demande_id}_no")
        ]
    ]

    if conv_active:
        buttons.append([
            InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION", callback_data=f"contact_close_conv_{demande_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("💬 CONVERSATION", callback_data=f"contact_mode_{demande_id}_conv")
        ])

    buttons.append([
        InlineKeyboardButton(f"📦 AVEC DU CONTENU : {badge_bundle}", callback_data=f"toggle_contact_content_{demande_id}")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ])

    return text, InlineKeyboardMarkup(buttons)


def format_close_conv_client_notification(req_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Notification transmise au client quand l'opérateur ferme la conversation."""
    text = (
        f"ℹ️ <b>Conversation clôturée (Demande #{req_num})</b>\n\n"
        "Votre référent a clôturé la discussion en cours pour ce dossier.\n"
        "Si besoin, vous pouvez consulter vos demandes ci-dessous :"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗂️ MES DEMANDES", callback_data="voir_demandes")
    ]])
    return text, kb


def get_contact_input_prompt(req_num: int, prenom_esc: str, is_content_bundle: bool, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour amorcer l'envoi direct ou groupé."""
    if is_content_bundle:
        text = (
            "📤 <b>ENVOI DU CONTENU GROUPÉ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Demande #{req_num} - {prenom_esc}\n\n"
            "<i>Envoyez vos textes, photos, vidéos ou documents. Un panier se mettra à jour sous chaque envoi.</i>\n\n"
            "<i>Cliquez sur ENVOYER quand vous aurez tout déposé.</i>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 ENVOYER (0 ÉLÉMENT)", callback_data=f"send_batch_{demande_id}")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")]
        ])
    else:
        text = (
            f"💬 <b>Envoi direct (Dossier #{req_num} - {prenom_esc})</b>\n\n"
            "Tapez votre message ou envoyez votre média : il sera <b>transmis instantanément</b> au client."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")
        ]])
    return text, keyboard


def build_basket_status_content(req_num: int, total: int, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Panneau de mise à jour du panier de médias collectés."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🚀 ENVOYER ({total})", callback_data=f"send_batch_{demande_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"cancel_contact_{demande_id}")]
    ])
    text = (
        f"📥 <b>PANIER D'ENVOI : {total} élément{'s' if total > 1 else ''}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Demande #{req_num}\n\n"
        "<i>Déposez la suite de vos fichiers ou cliquez ci-dessous pour expédier l'ensemble :</i>"
    )
    return text, keyboard


def build_direct_message_header(req_num: int, alias_esc: str) -> str:
    """En-tête de message individuel remis au demandeur."""
    return f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\nDe : <b>{alias_esc}</b>\n\n"


def build_batch_message_header(req_num: int, alias_esc: str, corps: str, mode: str, allow_reply: bool) -> str:
    """En-tête de lot remis au demandeur."""
    footer = "\n\n<i>💬 Une conversation directe est ouverte avec votre référent.</i>" if mode == "conv" else ("\n\n<i>Vous pouvez répondre une seule fois ci-dessous.</i>" if allow_reply else "")
    return (
        f"💬 <b>Message de l'équipe (Demande #{req_num})</b>\n"
        f"De : <b>{alias_esc}</b>"
        f"{corps}"
        f"{footer}"
    )


def get_client_reply_keyboard(demande_id: int, admin_id: int) -> InlineKeyboardMarkup:
    """Bouton permettant au demandeur de répondre à l'opérateur."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 RÉPONDRE", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
    ]])


def get_staff_conv_open_confirmation(demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation au staff de l'envoi d'un message avec conversation maintenue ouverte."""
    text = (
        "🚀 <b>Message transmis au demandeur !</b>\n"
        "<i>La conversation reste ouverte. Vous pouvez continuer à écrire ou envoyer des fichiers directement.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION", callback_data=f"contact_close_conv_{demande_id}")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")]
    ])
    return text, kb


def get_batch_sent_success_content(total_items: int, alias_esc: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation d'expédition du lot de fichiers pour le staff."""
    done_text = (
        f"✅ <b>Lot de {total_items} élément{'s' if total_items > 1 else ''} envoyé avec succès !</b>\n"
        f"Transmis sous votre alias : <code>{alias_esc}</code>"
    )
    back_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ]])
    return done_text, back_keyboard


def get_staff_callback_error_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message d'erreur générique lors d'une action staff."""
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_demandes")
    ]])
    return "❌ <b>Erreur technique</b> lors du traitement de l'action opérateur.", kb