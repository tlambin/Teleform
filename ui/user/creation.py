"""ui/user/creation.py
Composants visuels, gabarits textuels, claviers de navigation et alertes pour le tunnel de création de demandes.
Regroupe formulaire_ui et navigation_ui.
"""

import asyncio
import html
import logging
from typing import Any, Dict, List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

NAV_CONFIG = {
    "back_text": "⬅️ Retour",
    "skip_text": "⏭️ Passer",
    "cancel_text": "❌ Annuler",
}


# ==================== UTILITAIRES & URLS ====================

def get_support_url(db_manager) -> str:
    """Génère l'URL directe vers le contact support configuré en base."""
    contact = db_manager.get_support_contact()
    if contact.startswith("@"):
        return f"https://t.me/{contact.lstrip('@')}"
    elif contact.startswith(("http://", "https://")):
        return contact
    return f"https://t.me/{contact}"


# ==================== CLAVIERS DES ÉTAPES DU FORMULAIRE ====================

def get_orientation_keyboard() -> InlineKeyboardMarkup:
    """Clavier de sélection de l'orientation cible."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🫂 HÉTÉRO 🫂", callback_data="ori_hetero")],
        [InlineKeyboardButton("🌈 GAY 🌈", callback_data="ori_gay")],
        [InlineKeyboardButton("💃 BI 🕺", callback_data="ori_bi")],
        [InlineKeyboardButton("❌ ANNULER ❌", callback_data="form_cancel")]
    ])


def get_duplicate_social_keyboard(support_url: str, retry_callback: str) -> InlineKeyboardMarkup:
    """Clavier affiché lors d'une détection de doublon réseau."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 CONTACTER LE SUPPORT 💬", url=support_url)],
        [InlineKeyboardButton("↩️ MODIFIER MA SAISIE ↩️", callback_data=retry_callback)],
        [InlineKeyboardButton("❌ ANNULER LA DEMANDE ❌", callback_data="form_cancel")]
    ])


def get_priority_choice_keyboard(prio_state_id: int) -> InlineKeyboardMarkup:
    """Clavier de choix de la formule prioritaire."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ OUI - PRIORITAIRE", callback_data="priorite_oui"),
            InlineKeyboardButton("📝 NON - STANDARD", callback_data="priorite_non")
        ],
        [InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data=f"form_back_{prio_state_id}")],
        [InlineKeyboardButton("❌ ANNULER ❌", callback_data="form_cancel")]
    ])


def get_vip_assignment_choice_keyboard(choix_admin_state_id: int) -> InlineKeyboardMarkup:
    """Clavier initial pour les membres VIP (choisir un piégeur ou non)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 CHOISIR MON PIÉGEUR 🎯", callback_data="vip_opt_choose")],
        [InlineKeyboardButton("🎲 NE PAS CHOISIR (TOUTE L'ÉQUIPE) 🎲", callback_data="vip_opt_none")],
        [InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data=f"form_back_{choix_admin_state_id}")],
        [InlineKeyboardButton("❌ ANNULER ❌", callback_data="form_cancel")]
    ])


def build_vip_staff_picker(
    equipe: list,
    user_id: int,
    target_ori: str,
    db_manager
) -> InlineKeyboardMarkup:
    """Construit la liste des piégeurs compatibles et disponibles pour le VIP."""
    kb_rows = []
    for member in equipe:
        if int(member["user_id"]) == int(user_id):
            continue

        alias = member.get("alias", f"Staff_{member['user_id']}")
        perms = db_manager.get_staff_permissions(member["user_id"])
        p_ori = perms.get("perm_orientation", "all")

        is_compatible = (
            p_ori in ("all", "bi")
            or p_ori == target_ori
            or (target_ori == "bi" and p_ori in ("hetero", "gay"))
        )

        if is_compatible:
            kb_rows.append([
                InlineKeyboardButton(
                    f"🦈 {alias.upper()} 🦈",
                    callback_data=f"vip_assign_admin_{member['user_id']}"
                )
            ])

    kb_rows.append([InlineKeyboardButton("🎲 NE PAS CHOISIR (TOUTE L'ÉQUIPE) 🎲", callback_data="vip_assign_admin_0")])
    kb_rows.append([InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data="vip_opt_back")])
    kb_rows.append([InlineKeyboardButton("❌ ANNULER ❌", callback_data="form_cancel")])
    return InlineKeyboardMarkup(kb_rows)


# ==================== NAVIGATION DYNAMIQUE (RETOUR / PASSER / ANNULER) ====================

def create_navigation_keyboard(
    current_state: int,
    state_history: dict,
    skippable_fields: set,
    include_skip: bool = False
) -> InlineKeyboardMarkup:
    """Construit le clavier de navigation adapté à l'étape courante."""
    keyboard = []
    action_row = []

    if current_state in state_history:
        action_row.append(
            InlineKeyboardButton(
                NAV_CONFIG["back_text"],
                callback_data=f"form_back_{current_state}",
            )
        )

    if include_skip and current_state in skippable_fields:
        action_row.append(
            InlineKeyboardButton(
                NAV_CONFIG["skip_text"],
                callback_data=f"form_skip_{current_state}",
            )
        )

    if action_row:
        keyboard.append(action_row)

    keyboard.append([
        InlineKeyboardButton(
            NAV_CONFIG["cancel_text"],
            callback_data="form_cancel",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


def create_priority_keyboard(prioritaire_state: int, include_navigation: bool = True) -> InlineKeyboardMarkup:
    """Clavier pour le choix Standard vs Prioritaire (version navigation)."""
    keyboard = [
        [InlineKeyboardButton("⭐ Oui - Prioritaire", callback_data="priorite_oui")],
        [InlineKeyboardButton("📝 Non - Standard", callback_data="priorite_non")],
    ]
    if include_navigation:
        keyboard.append([
            InlineKeyboardButton(
                NAV_CONFIG["back_text"],
                callback_data=f"form_back_{prioritaire_state}",
            ),
            InlineKeyboardButton(
                NAV_CONFIG["cancel_text"],
                callback_data="form_cancel",
            ),
        ])
    return InlineKeyboardMarkup(keyboard)


def create_vip_admin_choice_keyboard(
    equipe: List[Dict[str, Any]],
    target_ori: str,
    choix_admin_state: int,
    db_manager
) -> InlineKeyboardMarkup:
    """Génère la liste dynamique des référents Staff compatibles pour le membre VIP."""
    kb_rows = []

    for member in equipe:
        raw_alias = member.get("alias") or f"Staff_{member['user_id']}"
        perms = db_manager.get_staff_permissions(member["user_id"])
        p_ori = perms.get("perm_orientation", "all")

        is_compatible = (
            p_ori in ("all", "bi")
            or p_ori == target_ori
            or (target_ori == "bi" and p_ori in ("hetero", "gay"))
        )

        if is_compatible:
            kb_rows.append([
                InlineKeyboardButton(
                    f"🦈 {raw_alias}",
                    callback_data=f"vip_assign_admin_{member['user_id']}"
                )
            ])

    kb_rows.append([InlineKeyboardButton("🎲 Premier disponible (Aléatoire)", callback_data="vip_assign_admin_0")])
    kb_rows.append([
        InlineKeyboardButton(NAV_CONFIG["back_text"], callback_data=f"form_back_{choix_admin_state}"),
        InlineKeyboardButton(NAV_CONFIG["cancel_text"], callback_data="form_cancel")
    ])
    return InlineKeyboardMarkup(kb_rows)


def get_mandatory_network_keyboard(snapchat_state: int) -> InlineKeyboardMarkup:
    """Clavier affiché si l'utilisateur tente d'ignorer les deux réseaux."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Retourner à Instagram", callback_data=f"form_back_{snapchat_state}")],
        [InlineKeyboardButton("❌ Annuler la demande", callback_data="form_cancel")]
    ])


def get_back_screens_dict(form, has_insta: bool, target_ori: str) -> dict:
    """Dictionnaire des textes et claviers lors d'un retour arrière sur chaque étape."""
    return {
        form.ORIENTATION: {
            "text": (
                "🎯 <b>Retour — Orientation de la cible</b>\n\n"
                "Quelle est l'<b>orientation de la cible</b> ou le type de piège souhaité ?"
            ),
            "keyboard": get_orientation_keyboard(),
        },
        form.PRENOM: {
            "text": "📝 <b>Retour — Prénom</b>\n\nQuel est son <b>prénom</b> ?",
            "keyboard": create_navigation_keyboard(form.PRENOM, form.state_history, form.skippable_fields),
        },
        form.NOM: {
            "text": "📝 <b>Retour — Nom</b>\n\nSon nom de famille :",
            "keyboard": create_navigation_keyboard(form.NOM, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.AGE: {
            "text": "📝 <b>Retour — Âge</b>\n\nSon âge (18-40 ans) :",
            "keyboard": create_navigation_keyboard(form.AGE, form.state_history, form.skippable_fields),
        },
        form.LOCALISATION: {
            "text": "📝 <b>Retour — Localisation</b>\n\nSa localisation (ville, région ou pays) :",
            "keyboard": create_navigation_keyboard(form.LOCALISATION, form.state_history, form.skippable_fields),
        },
        form.PHOTO: {
            "text": "📝 <b>Retour — Photo</b>\n\n📸 Envoyez une photo :",
            "keyboard": create_navigation_keyboard(form.PHOTO, form.state_history, form.skippable_fields),
        },
        form.INSTAGRAM: {
            "text": "📝 <b>Retour — Instagram</b>\n\nSon profil Instagram :",
            "keyboard": create_navigation_keyboard(form.INSTAGRAM, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.SNAPCHAT: {
            "text": (
                "📝 <b>Retour — Snapchat</b>\n\n"
                + ("Son compte Snapchat (ou passez) :" if has_insta else "⚠️ <b>Au moins un réseau est requis.</b>\nSon compte Snapchat :")
            ),
            "keyboard": create_navigation_keyboard(form.SNAPCHAT, form.state_history, form.skippable_fields, include_skip=has_insta),
        },
        form.DETAILS: {
            "text": "📝 <b>Retour — Détails</b>\n\nDes précisions ou remarques à apporter ?",
            "keyboard": create_navigation_keyboard(form.DETAILS, form.state_history, form.skippable_fields, include_skip=True),
        },
        form.PRIORITAIRE: {
            "text": (
                "📝 <b>Retour — Priorité</b>\n\n"
                "💎 <b>Demande prioritaire ?</b>\n\n"
                "Les demandes prioritaires nécessitent un montant et sont traitées en premier."
            ),
            "keyboard": create_priority_keyboard(form.PRIORITAIRE),
        },
        form.MONTANT: {
            "text": "💰 <b>Retour — Montant</b>\n\nIndiquez le montant (en euros) :",
            "keyboard": create_navigation_keyboard(form.MONTANT, form.state_history, form.skippable_fields),
        },
        form.CHOIX_ADMIN: {
            "text": (
                "⭐ <b>Avantage Membre VIP : Choix du Référent</b>\n\n"
                "Sélectionnez le membre de l'équipe qui prendra personnellement en charge votre demande :"
            ),
            "keyboard": create_vip_admin_choice_keyboard(
                form.db_manager.get_available_staff(),
                target_ori,
                form.CHOIX_ADMIN,
                form.db_manager
            ),
        },
    }


# ==================== ALERTES & BROADCAST ====================

async def send_single_demande_alert(
    context: ContextTypes.DEFAULT_TYPE,
    sid: int,
    alert_text: str,
    alert_kb: InlineKeyboardMarkup,
    photo_id: Optional[str],
    is_silent: bool
):
    """Envoi unitaire d'alerte avec gestion des exceptions."""
    try:
        if photo_id:
            await context.bot.send_photo(
                chat_id=sid,
                photo=photo_id,
                caption=alert_text,
                parse_mode="HTML",
                reply_markup=alert_kb,
                disable_notification=is_silent
            )
        else:
            await context.bot.send_message(
                chat_id=sid,
                text=alert_text,
                parse_mode="HTML",
                reply_markup=alert_kb,
                disable_notification=is_silent
            )
    except Exception as e:
        logger.warning("Impossible d'envoyer l'alerte nouvelle demande à %s : %s", sid, e)


async def send_vip_assignment_alert(
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
    demande_id: int,
    req_num: int,
    nom_complet: str,
    demande: dict
):
    """Envoie l'alerte au piégeur assigné par un membre VIP."""
    prio_icon = "💎" if demande.get("prioritaire") else "📝"
    type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
    montant_str = f" ({demande.get('montant', 0):.2f} €)" if demande.get("prioritaire") else ""
    loc_esc = html.escape(str(demande.get("localisation") or ""))

    label_map = {"hetero": "👩‍❤️‍👨 Hétéro", "gay": "👨‍❤️‍👨 Gay", "bi": "🔄 Bi"}
    ori_str = label_map.get(demande.get("orientation", "hetero"), "Hétéro")

    alert_text = (
        f"👑 <b>NOUVELLE DEMANDE VIP ASSIGNÉE (#{req_num})</b>\n\n"
        f"Un client VIP vous a spécifiquement choisi comme référent pour traiter sa demande :\n\n"
        f"🎯 <b>Cible :</b> {ori_str}\n"
        f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age')} ans)\n"
        f"📍 <b>Localisation :</b> {loc_esc}\n"
        f"🎯 <b>Type :</b> {prio_icon} {type_str}{montant_str}\n\n"
        "<i>Acceptez-vous cette prise en charge ?</i>"
    )
    alert_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ACCEPTER LA MISSION 🎯", callback_data=f"vip_accept_{demande_id}")],
        [InlineKeyboardButton("❌ DÉCLINER LA DEMANDE ❌", callback_data=f"vip_decline_{demande_id}")]
    ])

    try:
        photo_id = demande.get("photo_id")
        if photo_id:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=alert_text,
                parse_mode="HTML",
                reply_markup=alert_kb
            )
        else:
            await context.bot.send_message(
                chat_id=admin_id,
                text=alert_text,
                parse_mode="HTML",
                reply_markup=alert_kb
            )
    except Exception as err:
        logger.warning("Impossible de notifier le piégeur assigné VIP %s : %s", admin_id, err)


async def broadcast_new_demande_alert(
    context: ContextTypes.DEFAULT_TYPE,
    config,
    db_manager,
    demande_id: int,
    req_num: int,
    nom_complet: str,
    demande: dict,
    creator_id: int,
    is_vip: bool = False
):
    """Diffuse en parallèle les alertes d'une nouvelle demande disponible."""
    prio_icon = "💎" if demande.get("prioritaire") else "📝"
    type_str = "Prioritaire" if demande.get("prioritaire") else "Standard"
    montant_str = f" ({demande.get('montant', 0):.2f} €)" if demande.get("prioritaire") else ""
    loc_esc = html.escape(str(demande.get("localisation") or ""))

    label_map = {"hetero": "👩‍❤️‍👨 Hétéro", "gay": "👨‍❤️‍👨 Gay", "bi": "🔄 Bi"}
    target_ori = demande.get("orientation", "hetero")
    ori_str = label_map.get(target_ori, "Hétéro")

    titre = f"🌟 <b>Nouvelle demande VIP disponible #{req_num}</b>" if is_vip else f"🔔 <b>Nouvelle demande disponible #{req_num}</b>"

    alert_text = (
        f"{titre}\n\n"
        f"🎯 <b>Orientation cible :</b> {ori_str}\n"
        f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age')} ans)\n"
        f"📍 <b>Localisation :</b> {loc_esc}\n"
        f"🎯 <b>Type :</b> {prio_icon} {type_str}{montant_str}"
    )
    alert_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ PRENDRE EN CHARGE ⚡", callback_data=f"suivre_demande_{demande_id}")],
        [InlineKeyboardButton("📮 VOIR LES DISPONIBLES 📮", callback_data="demandes_disponibles")]
    ])

    staff_destinataires = config.get_all_staff() or config.get_all_admins()
    tasks = []
    photo_id = demande.get("photo_id")

    for staff_id in staff_destinataires:
        try:
            sid = int(staff_id)
            if sid == int(creator_id) or db_manager.is_staff_paused(sid):
                continue

            perms = db_manager.get_staff_permissions(sid)
            p_ori = perms.get("perm_orientation", "all")

            is_compatible = (
                p_ori in ("all", "bi")
                or p_ori == target_ori
                or (target_ori == "bi" and p_ori in ("hetero", "gay"))
            )
            if not is_compatible:
                continue

            prefs = db_manager.get_admin_preferences(sid)
            notif_mode = prefs.get("notif_new_mode", "sound")
            if notif_mode == "off":
                continue

            is_silent = (notif_mode == "silent")
            tasks.append(
                send_single_demande_alert(
                    context=context,
                    sid=sid,
                    alert_text=alert_text,
                    alert_kb=alert_kb,
                    photo_id=photo_id,
                    is_silent=is_silent
                )
            )
        except Exception as e_prep:
            logger.warning("Erreur préparation notification pour staff %s : %s", staff_id, e_prep)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)