"""Composants visuels, gabarits textuels et claviers pour la gestion de l'équipe Staff."""

import html
from typing import List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


def format_staff_list_text(staff_members: List[Dict[str, Any]]) -> str:
    """Génère l'affichage textuel de l'ensemble de l'équipe opérationnelle."""
    if not staff_members:
        return "📭 <b>Aucun opérateur dans l'équipe Staff pour le moment.</b>"

    lines = [f"👥 <b>Équipe Staff (Opérateurs)</b> ({len(staff_members)})\n"]
    for st in staff_members:
        raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
        pseudo_esc = html.escape(str(raw_pseudo))
        alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))

        dt_added = st.get("date_added")
        if dt_added:
            date_paris = convert_utc_to_paris(dt_added)
            date_str = date_paris.strftime("%d/%m/%Y à %H:%M")
        else:
            date_str = "Inconnue"

        par_qui = html.escape(str(st.get("nom_ajouteur") or "Direction"))
        status_badge = "⏸️ (En pause)" if st.get("is_paused") else "🟢 (En service)"
        trial_badge = " 🧪 <b>[À l'essai]</b>" if st.get("is_trial") else ""

        lines.append(
            f"• <b>{alias_esc}</b> {status_badge}{trial_badge} ({pseudo_esc})\n"
            f"  ID : <code>{st['user_id']}</code> | Recruté le {date_str} par {par_qui}\n"
        )

    return "\n".join(lines)


def get_staff_add_prompt_content(current_count: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour débuter le recrutement d'un opérateur."""
    text = (
        "👤 <b>Recrutement d'un Opérateur (Staff)</b>\n\n"
        f"Équipe actuelle : <b>{current_count}</b> opérateur(s)\n\n"
        "Envoyez l'<b>ID Telegram</b> ou le <b>@username</b> du compte à recruter :\n\n"
        "<i>(L'utilisateur doit obligatoirement avoir démarré le bot au préalable avec /start)</i>"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_add")
    ]])
    return text, keyboard


def build_recruit_config_content(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Construit l'écran et les boutons de pré-configuration interactive des permissions."""
    target_id = cfg.get("target_id")
    alias_esc = html.escape(str(cfg.get("alias") or ""))
    nom_esc = html.escape(str(cfg.get("first_name") or ""))

    res = cfg.get("reseaux", "all")
    typ = cfg.get("type", "all")
    ori = cfg.get("orientation", "all")
    is_trial = bool(cfg.get("is_trial", True))

    b_res_all = "✅ Tous réseaux" if res == "all" else "Tous réseaux"
    b_res_insta = "✅ Insta" if res == "insta" else "Insta"
    b_res_snap = "✅ Snap" if res == "snap" else "Snap"

    b_typ_all = "✅ Tout type" if typ == "all" else "Tout type"
    b_typ_prio = "✅ 💎 Payantes" if typ == "prio_only" else "💎 Payantes"
    b_typ_std = "✅ 📝 Gratuites" if typ == "standard_only" else "📝 Gratuites"

    b_ori_all = "✅ 🔄 Tous / Bi" if ori in ("all", "bi") else "🔄 Tous / Bi"
    b_ori_h = "✅ Hétéro" if ori == "hetero" else "Hétéro"
    b_ori_g = "✅ Gay" if ori == "gay" else "Gay"

    trial_btn_label = "🧪 À l'essai : ✅ OUI" if is_trial else "🧪 À l'essai : ❌ NON"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(b_res_all, callback_data="cfgadd_res_all"),
            InlineKeyboardButton(b_res_insta, callback_data="cfgadd_res_insta"),
            InlineKeyboardButton(b_res_snap, callback_data="cfgadd_res_snap"),
        ],
        [
            InlineKeyboardButton(b_typ_all, callback_data="cfgadd_typ_all"),
            InlineKeyboardButton(b_typ_prio, callback_data="cfgadd_typ_prio_only"),
            InlineKeyboardButton(b_typ_std, callback_data="cfgadd_typ_standard_only"),
        ],
        [
            InlineKeyboardButton(b_ori_h, callback_data="cfgadd_ori_hetero"),
            InlineKeyboardButton(b_ori_g, callback_data="cfgadd_ori_gay"),
            InlineKeyboardButton(b_ori_all, callback_data="cfgadd_ori_all"),
        ],
        [
            InlineKeyboardButton(trial_btn_label, callback_data="cfgadd_trial_toggle")
        ],
        [
            InlineKeyboardButton("🚀 Valider et recruter", callback_data="cfgadd_confirm_save")
        ],
        [
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_add")
        ]
    ])

    text = (
        f"⚙️ <b>Configuration initiale de l'opérateur</b>\n\n"
        f"👤 <b>Cible :</b> {nom_esc} (ID: <code>{target_id}</code>)\n"
        f"🏷️ <b>Alias provisoire :</b> <code>{alias_esc}</code>\n\n"
        "Ajustez ses autorisations et son mode à l'essai avant d'enregistrer le recrutement :"
    )
    return text, keyboard


def build_recruit_welcome_message(alias: str, is_trial: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Message d'accueil officiel envoyé directement au nouvel opérateur."""
    alias_esc = html.escape(alias)
    trial_notice = (
        "🧪 <b>Période probatoire (À l'essai) :</b>\n"
        "Vous devez mener à bien <b>une première demande test</b> attribuée au hasard pour débloquer l'accès complet à la plateforme.\n\n"
        if is_trial else
        "🟢 <b>Accès complet :</b>\n"
        "Vous avez accès dès maintenant à l'ensemble des demandes disponibles correspondant à vos autorisations.\n\n"
    )

    welcome_msg = (
        "🎉 <b>Bienvenue dans l'équipe opérationnelle (Staff) !</b>\n\n"
        f"🏷️ <b>Votre alias provisoire :</b> <code>{alias_esc}</code>\n\n"
        f"{trial_notice}"
        "⚠️ <b>Pseudonyme officiel :</b> Vous pouvez définir votre alias dès maintenant.\n"
        "<i>Attention : vous ne disposez que d'une seule modification autorisée.</i>\n\n"
        "Cliquez ci-dessous pour démarrer :"
    )
    welcome_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷️ DÉFINIR MON ALIAS", callback_data="modifier_alias")],
        [InlineKeyboardButton("🚀 Menu Principal", callback_data="start_menu")]
    ])
    return welcome_msg, welcome_kb


def build_recruit_admin_summary(cfg: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Récapitulatif envoyé à l'administrateur confirmant l'enregistrement de la recrue."""
    target_id = cfg["target_id"]
    alias_esc = html.escape(cfg["alias"])
    reseaux = cfg["reseaux"]
    typ = cfg["type"]
    orientation = cfg["orientation"]
    is_trial = cfg["is_trial"]

    res_label = {"all": "Tous", "insta": "Instagram", "snap": "Snapchat"}.get(reseaux, reseaux)
    typ_label = {"all": "Tous", "prio_only": "Payantes", "standard_only": "Gratuites"}.get(typ, typ)
    ori_label = {"all": "Tous / Bi", "bi": "Tous / Bi", "hetero": "Hétéro", "gay": "Gay"}.get(orientation, orientation)
    trial_text = "🧪 <b>À l'essai</b> (Demande aléatoire imposée)" if is_trial else "🟢 <b>Confirmé</b> (Accès complet)"

    msg_admin = (
        f"✅ <b>Opérateur recruté et configuré avec succès !</b>\n\n"
        f"👤 <b>Cible :</b> {html.escape(cfg['first_name'])} (ID: <code>{target_id}</code>)\n"
        f"🏷️ <b>Alias :</b> <code>{alias_esc}</code>\n"
        f"🌐 <b>Réseaux :</b> {res_label}\n"
        f"🎯 <b>Type :</b> {typ_label}\n"
        f"🧭 <b>Orientation :</b> {ori_label}\n"
        f"🧪 <b>Statut :</b> {trial_text}"
    )

    kb_confirm = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
    ])
    return msg_admin, kb_confirm


def build_staff_remove_list_content(staff_members: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche la liste numérotée pour la sélection du membre à révoquer."""
    if not staff_members:
        text = "👥 <b>Révocation d'un Opérateur</b>\n\nAucun opérateur révocable n'est configuré actuellement."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Retour", callback_data="gerer_staff")]])
        return text, kb

    lines = [
        "👥 <b>Révocation d'un Opérateur (Staff)</b>\n",
        f"Opérateurs enregistrés : <b>{len(staff_members)}</b>\n"
    ]
    for idx, st in enumerate(staff_members, 1):
        raw_pseudo = f"@{st['username']}" if st.get("username") else (st.get("first_name") or "")
        pseudo_esc = html.escape(str(raw_pseudo))
        alias_esc = html.escape(str(st.get("alias") or f"Staff_{st['user_id']}"))
        date_str = str(st.get("date_added", ""))[:10]
        lines.append(f"{idx}. <b>{alias_esc}</b> ({pseudo_esc}) — ID: <code>{st['user_id']}</code> [{date_str}]")

    lines.append("\nEnvoyez le <b>numéro</b> de l'opérateur à révoquer :")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove")
    ]])
    return "\n".join(lines), keyboard


def build_staff_remove_confirmation_content(selected: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Écran de confirmation avant suppression des accès d'un opérateur."""
    raw_pseudo = f"@{selected['username']}" if selected.get("username") else (selected.get("first_name") or "")
    pseudo_esc = html.escape(str(raw_pseudo))
    alias_esc = html.escape(str(selected.get("alias") or f"Staff_{selected['user_id']}"))

    text = (
        f"⚠️ <b>Confirmation de révocation</b>\n\n"
        f"Êtes-vous certain de vouloir retirer les accès opérationnels à :\n"
        f"• <b>Alias :</b> {alias_esc}\n"
        f"• <b>Profil :</b> {pseudo_esc}\n"
        f"• <b>ID :</b> <code>{selected['user_id']}</code> ?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Confirmer la révocation", callback_data="confirm_staff_remove"),
            InlineKeyboardButton("❌ Annuler", callback_data="cancel_staff_remove")
        ]
    ])
    return text, keyboard


def get_staff_removed_success_content(alias: str, target_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message de succès suite à la révocation d'un opérateur."""
    alias_esc = html.escape(str(alias or f"Staff_{target_id}"))
    text = f"✅ <b>Droits staff retirés avec succès pour {alias_esc}.</b>"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Équipe Staff", callback_data="gerer_staff")],
        [InlineKeyboardButton("🔙 Menu Principal", callback_data="start_menu")]
    ])
    return text, keyboard