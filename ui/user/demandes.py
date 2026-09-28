"""ui/user/demandes.py
Composants visuels, fiches, claviers, formulaires d'édition et relais messagerie des demandes.
Regroupe demande_ui, edition_ui et relais_ui.
"""

from datetime import datetime
import html
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import Validators, convert_utc_to_paris


# ==================== UTILITAIRES DE FORMATAGE ====================

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


# ==================== FICHES DES DEMANDES (ACTIVES & ARCHIVES) ====================

def format_demande_card(demande: dict, current_page: int, total_pages: int, db_manager) -> str:
    """Formate la fiche côté utilisateur avec liens sociaux interactifs."""
    num_client = total_pages - current_page

    is_prio = bool(demande.get("prioritaire"))
    titre = (
        f"💎  <b>Demande Prioritaire #{num_client} ({current_page + 1}/{total_pages})</b>"
        if is_prio
        else f"📝  <b>Demande Standard #{num_client} ({current_page + 1}/{total_pages})</b>"
    )

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    age_str = f"  •  {html.escape(str(demande['age']))} ans" if demande.get("age") is not None else ""

    ori_raw = str(demande.get("orientation") or "").strip().lower()
    ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
    ori_label = html.escape(ori_map.get(ori_raw, "Non précisée"))
    loc = html.escape(str(demande.get("localisation") or "Lieu non précisé").strip())

    lines = [
        titre,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤  <b>{nom_complet}{age_str}</b>",
        f"📍  {ori_label} de {loc}",
    ]

    if demande.get("details"):
        det = html.escape(str(demande["details"]).strip())
        lines.append(f"💬  <i>{det}</i>")

    if is_prio:
        montant = float(demande.get("montant") or 0.0)
        lines.append(f"💰  <b>{montant:.2f} €</b>")

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

    statut_label = html.escape(str(db_manager.format_statut_display(
        demande.get("statut", "📥 Reçue"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus"),
    )))
    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{statut_label}</b> • ")

    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{html.escape(format_datetime_fr(dt_mod))}</i>")

    if is_prio:
        p_statut = demande.get("paiement_statut", "non_requis")
        if p_statut == "paye":
            lines.append("\n🟢 <b>Réglé et validé</b>")
        elif p_statut == "en_attente":
            lines.append("\n🟡 <b>En attente de règlement</b>")

    admin_id = demande.get("admin_en_charge")
    if admin_id:
        alias = html.escape(str(db_manager.get_staff_alias(admin_id) or "Opérateur"))
        lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")
        dt_suivi = demande.get("date_modification")
        if dt_suivi:
            lines.append(f"<b>Depuis le :</b> <i>{html.escape(format_datetime_fr(dt_suivi))}</i>")

    dt_crea = demande.get("date_creation")
    lines.append("\n───────  <b>INFOS</b>  ───────")
    lines.append(f"<b>Déposé le :</b>  {html.escape(format_datetime_fr(dt_crea))}")

    ancien_alias = demande.get("ancien_admin_alias")
    raw_reason = demande.get("raison_abandon")
    if ancien_alias or raw_reason:
        alias_str = html.escape(str(ancien_alias or "Opérateur"))
        reason_str = clean_reason_text(raw_reason)
        dt_abandon = demande.get("date_modification")
        date_abandon_str = html.escape(format_datetime_fr(dt_abandon)) if dt_abandon else "Date inconnue"

        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        lines.append("❌ Abandonné")
        lines.append(f"{alias_str} le {date_abandon_str}")
        lines.append(f"<b>Raison :</b> {reason_str}")

    return "\n".join(lines)


def format_user_archive_card(item: dict, page: int, total: int, db_manager) -> str:
    """Formate la fiche d'une archive pour la vue du demandeur avec numérotation propre."""
    num_archive_client = total - page

    prenom_esc = html.escape(str(item.get("prenom") or ""))
    nom_esc = html.escape(str(item.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    loc_esc = html.escape(str(item.get("localisation") or "Non précisée"))
    age_str = f"  •  {html.escape(str(item['age']))} ans" if item.get("age") is not None else ""

    is_prio = bool(item.get("prioritaire"))
    titre = (
        f"💎  <b>Demande Prioritaire #{num_archive_client} ({page + 1}/{total})</b>"
        if is_prio
        else f"📝  <b>Demande Standard #{num_archive_client} ({page + 1}/{total})</b>"
    )

    lines = [
        titre,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤  <b>{nom_complet}{age_str}</b>",
        f"📍  {loc_esc}",
    ]

    if item.get("details"):
        det_esc = html.escape(str(item["details"]).strip())
        lines.append(f"💬  <i>{det_esc}</i>")

    if is_prio:
        montant = float(item.get("montant") or 0.0)
        lines.append(f"💰  <b>{montant:.2f} €</b>")

    reseaux = []
    if item.get("instagram"):
        raw_ig = str(item["instagram"]).strip().lstrip("@")
        ig_esc = html.escape(raw_ig)
        reseaux.append(f'• <b>Instagram :</b> <a href="https://instagram.com/{ig_esc}">@{ig_esc}</a>')
    if item.get("snapchat"):
        raw_snap = str(item["snapchat"]).strip().lstrip("@")
        snap_esc = html.escape(raw_snap)
        reseaux.append(f'• <b>Snapchat :</b> <a href="https://snapchat.com/add/{snap_esc}">{snap_esc}</a>')

    if reseaux:
        lines.append("\n🌐  <b>SES RÉSEAUX</b>")
        lines.extend(reseaux)

    statut_label = html.escape(str(item.get("statut") or "Archivée"))
    dt_arch = item.get("date_archivage")

    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{statut_label}</b> • ")
    if dt_arch:
        lines.append(f" <i>{html.escape(format_datetime_fr(dt_arch))}</i>")

    dt_crea = item.get("date_creation")
    lines.append("\n───────  <b>INFOS</b>  ───────")
    lines.append(f"<b>Déposé le :</b>  {html.escape(format_datetime_fr(dt_crea))}")

    statut_raw = str(item.get("statut") or "").lower()
    admin_charge = item.get("admin_en_charge")
    alias_admin = html.escape(str(db_manager.get_staff_alias(admin_charge) if admin_charge else "Direction"))

    lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
    if "supprim" in statut_raw:
        dt_ev = item.get("date_archivage") or item.get("date_modification")
        date_ev_str = html.escape(format_datetime_fr(dt_ev)) if dt_ev else "Date inconnue"
        raw_reason = item.get("raison_abandon") or item.get("details")
        raison = clean_reason_text(raw_reason)

        lines.append("🗑️ Supprimée")
        lines.append(f"{alias_admin} le {date_ev_str}")
        lines.append(f"<b>Raison :</b> {raison}")

    elif "abandon" in statut_raw or "annul" in statut_raw:
        dt_ev = item.get("date_archivage") or item.get("date_modification")
        date_ev_str = html.escape(format_datetime_fr(dt_ev)) if dt_ev else "Date inconnue"
        raw_reason = item.get("raison_abandon") or item.get("details")
        raison = clean_reason_text(raw_reason)

        label_hist = "❌ Abandonnée" if "abandon" in statut_raw else "❌ Annulée"
        lines.append(label_hist)
        lines.append(f"{alias_admin} le {date_ev_str}")
        lines.append(f"<b>Raison :</b> {raison}")
    else:
        montant = float(item.get("montant") or 0.0)
        montant_str = f" ({montant:.2f} €)" if montant > 0 else ""
        dt_ev = item.get("date_livraison") or item.get("date_archivage") or item.get("date_modification")
        date_ev_str = html.escape(format_datetime_fr(dt_ev)) if dt_ev else "Date inconnue"

        lines.append(f"✅ Réussie{montant_str}")
        lines.append(f"{alias_admin} le {date_ev_str}")

    return "\n".join(lines)


# ==================== CLAVIERS DE CONSULTATION ====================

def build_navigation_keyboard(
    demande: dict,
    page: int,
    total: int,
    user_id: int,
    can_create: bool,
    nb_archives: int,
    db_manager
) -> InlineKeyboardMarkup:
    """Génère les boutons de 'Mes Demandes' selon la maquette et les règles métiers."""
    buttons = []
    demande_id = demande["id"]
    admin_en_charge = demande.get("admin_en_charge")
    statut_raw = str(demande.get("statut") or "").strip()
    is_prio = bool(demande.get("prioritaire"))
    is_vip = db_manager.is_user_vip(user_id)
    is_active = statut_raw not in ["✅ Réussie", "❌ Annulée", "❌ Abandonnée"]

    if not is_prio and is_active:
        buttons.append([
            InlineKeyboardButton("💎 PASSER PRIORITAIRE 💎", callback_data=f"upgrade_prio_{demande_id}")
        ])

    if is_prio and is_active and not admin_en_charge:
        buttons.append([
            InlineKeyboardButton("💰 MODIFIER LE PRIX 💰", callback_data=f"modify_{demande_id}")
        ])

    if is_prio and is_active and admin_en_charge:
        buttons.append([
            InlineKeyboardButton("💰 AUGMENTER LE PRIX 💰", callback_data=f"modify_{demande_id}")
        ])

    if is_active and not admin_en_charge:
        buttons.append([
            InlineKeyboardButton("✏️ MODIFIER", callback_data=f"modify_{demande_id}"),
            InlineKeyboardButton("🗑️ SUPPRIMER", callback_data=f"delete_{demande_id}"),
        ])

    if admin_en_charge and is_active:
        contact_btn = InlineKeyboardButton("💬 CONTACT", callback_data=f"vip_contact_admin_{demande_id}")
        if is_vip or is_prio:
            relance_btn = InlineKeyboardButton("🛎️ RELANCER (Gratuit)", callback_data=f"remind_admin_free_{demande_id}")
        else:
            relance_btn = InlineKeyboardButton("🛎️ RELANCER (1€)", callback_data=f"remind_admin_pay_{demande_id}")
        buttons.append([contact_btn, relance_btn])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ PRÉCÉDENTE", callback_data=f"nav_page_{page - 1}"))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("SUIVANTE ➡️", callback_data=f"nav_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    btn_creer = (
        InlineKeyboardButton("🗳️ CRÉER", callback_data="new_demande")
        if can_create
        else InlineKeyboardButton("🔒 PLEIN", callback_data="quota_reached_info")
    )
    btn_archives = InlineKeyboardButton(f"📦 ARCHIVES ({nb_archives})", callback_data="mes_archives")
    buttons.append([btn_creer, btn_archives])

    buttons.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")
    ])

    return InlineKeyboardMarkup(buttons)


def build_user_archive_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    """Construit la barre de navigation pour les archives client."""
    buttons = []
    nav_row = []

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Précédent", callback_data=f"user_arch_page_{page - 1}"))
    if page < total - 1:
        nav_row.append(InlineKeyboardButton("Suivant ➡️", callback_data=f"user_arch_page_{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("📋 Mes demandes actives", callback_data="voir_demandes"),
        InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu"),
    ])
    return InlineKeyboardMarkup(buttons)


def build_no_requests_keyboard(can_create: bool, nb_archives: int) -> InlineKeyboardMarkup:
    """Construit le clavier affiché lorsqu'aucun dossier actif n'existe."""
    btn_creation = (
        InlineKeyboardButton("➕ Créer une demande", callback_data="new_demande")
        if can_create
        else InlineKeyboardButton("🔒 Quota atteint", callback_data="quota_reached_info")
    )
    btn_archives = InlineKeyboardButton(f"📦 Mes archives ({nb_archives})", callback_data="mes_archives")
    return InlineKeyboardMarkup([
        [btn_creation],
        [btn_archives],
        [InlineKeyboardButton("🔙 Menu principal", callback_data="start_menu")],
    ])


# ==================== ÉDITION & SUPPRESSION ====================

def build_modify_menu_content(demande: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Génère l'interface des champs modifiables selon le statut du dossier."""
    prenom_esc = html.escape(demande.get("prenom") or "")
    nom_esc = html.escape(demande.get("nom") or "")
    nom_complet = f"{prenom_esc} {nom_esc}".strip()
    loc_esc = html.escape(str(demande.get("localisation") or ""))
    req_num = html.escape(str(demande.get("request_number", demande["id"])))
    statut = demande.get("statut", "")
    is_prio = bool(demande.get("prioritaire"))
    montant = float(demande.get("montant") or 0.0)
    d_id = demande["id"]

    is_en_cours = statut in ("⏳ En attente", "🔄 En cours")
    keyboard = []

    if is_en_cours:
        text = (
            f"✏️ <b>Revalorisation du dossier n°{req_num}</b>\n\n"
            f"👤 <b>Cible :</b> {nom_complet} ({demande.get('age', '?')} ans)\n"
            f"💎 <b>Tarif actuel :</b> <b>{montant:.2f} €</b>\n"
            f"📊 <b>Statut :</b> <code>{statut}</code>\n\n"
            "Le dossier est déjà en cours de traitement. Vous pouvez uniquement <b>augmenter</b> "
            "le montant proposé à votre piégeur pour motiver ou accélérer le résultat :"
        )
        keyboard.append([InlineKeyboardButton(f"💰 Rehausser le tarif (Actuel: {montant:.2f} €)", callback_data=f"edit_montant_{d_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Retour aux demandes", callback_data="voir_demandes")])
    else:
        text = (
            f"✏️ <b>Modifier la demande n°{req_num}</b>\n\n"
            f"👤 <b>Identité :</b> {nom_complet} ({demande.get('age', '?')} ans)\n"
            f"📍 <b>Localisation :</b> {loc_esc}\n"
        )
        if is_prio:
            text += f"💎 <b>Gratification :</b> <b>{montant:.2f} €</b>\n"

        text += "\nSélectionnez la donnée à modifier :"

        keyboard.extend([
            [
                InlineKeyboardButton("👤 Prénom", callback_data=f"edit_prenom_{d_id}"),
                InlineKeyboardButton("📝 Nom", callback_data=f"edit_nom_{d_id}"),
            ],
            [
                InlineKeyboardButton("🎂 Âge", callback_data=f"edit_age_{d_id}"),
                InlineKeyboardButton("📍 Ville", callback_data=f"edit_localisation_{d_id}"),
            ],
            [
                InlineKeyboardButton("📷 Instagram", callback_data=f"edit_instagram_{d_id}"),
                InlineKeyboardButton("👻 Snapchat", callback_data=f"edit_snapchat_{d_id}"),
            ],
            [InlineKeyboardButton("💬 Remarques / Détails", callback_data=f"edit_details_{d_id}")],
        ])

        if is_prio:
            keyboard.append([InlineKeyboardButton(f"💰 Modifier le tarif ({montant:.2f} €)", callback_data=f"edit_montant_{d_id}")])

        keyboard.extend([
            [InlineKeyboardButton("🗑️ Supprimer la demande", callback_data=f"delete_{d_id}")],
            [InlineKeyboardButton("🔙 Retour aux demandes", callback_data="voir_demandes")],
        ])

    return text, InlineKeyboardMarkup(keyboard)


def build_edit_prompt_content(
    field_name: str,
    demande_id: int,
    demande: dict,
    allowed_fields: dict
) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche les instructions de saisie pour le champ sélectionné."""
    field_label = allowed_fields.get(field_name, field_name)

    if field_name == "montant":
        montant_actuel = float(demande.get("montant") or 0.0)
        statut = demande.get("statut", "")
        is_en_cours = statut in ("⏳ En attente", "🔄 En cours")

        if is_en_cours:
            consigne = (
                f"• Montant minimum actuel : <b>{montant_actuel:.2f} €</b>\n\n"
                "<i>Ce dossier étant déjà pris en charge, le montant ne peut qu'être augmenté.</i>"
            )
        else:
            consigne = (
                f"• Montant actuel : <b>{montant_actuel:.2f} €</b>\n\n"
                "<i>Vous pouvez ajuster librement le tarif proposé (à la hausse ou à la baisse, supérieur à 0).</i>"
            )

        text = (
            f"💰 <b>Modifier le tarif de la demande #{demande_id}</b>\n\n"
            f"{consigne}\n\n"
            "Tapez votre nouveau tarif (en euros) par message texte :"
        )
    else:
        help_text = Validators.get_validation_help(field_name)
        text = (
            f"✏️ <b>Modification : {html.escape(field_label)}</b>\n\n"
            f"{help_text}\n\n"
            "Envoyez votre nouvelle valeur par message texte :"
        )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_edit")
    ]])
    return text, keyboard


def build_delete_confirmation_content(demande: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Affiche l'écran d'avertissement avant suppression."""
    prenom_esc = html.escape(demande.get("prenom") or "")
    nom_esc = html.escape(demande.get("nom") or "")
    nom_complet = f"{prenom_esc} {nom_esc}".strip()
    req_num = html.escape(str(demande.get("request_number", demande["id"])))

    text = (
        f"⚠️ <b>Confirmation de suppression</b>\n\n"
        f"Demande n°<b>{req_num}</b> ({nom_complet})\n\n"
        "Cette action est irréversible. Confirmez-vous la suppression ?"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Confirmer la suppression", callback_data=f"confirm_delete_{demande['id']}")],
        [InlineKeyboardButton("❌ Annuler", callback_data=f"modify_{demande['id']}")]
    ])
    return text, keyboard


# ==================== RELAIS MESSAGERIE & SURVEILLANCE ====================

def build_relay_header(user, is_vip: bool, demande_id: int, user_comment: str) -> str:
    """Génère l'en-tête du message transmis au référent."""
    badge_vip = " ⭐ <b>[VIP]</b>" if is_vip else ""
    user_label = f"@{user.username}" if user.username else f"{user.first_name} (ID : {user.id})"
    user_label_esc = html.escape(user_label)
    corps = f"\n\n« {html.escape(user_comment)} »" if user_comment else ""

    return (
        f"📩 <b>Message du demandeur{badge_vip} (Demande #{demande_id})</b>\n"
        f"De : {user_label_esc}"
        f"{corps}"
    )


def build_admin_relay_keyboard(demande_id: int, is_conv: bool) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions pour le piégeur recevant la réponse."""
    if is_conv:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 RÉPONDRE 💬", callback_data=f"contacter_{demande_id}")],
            [InlineKeyboardButton("🔒 CLÔTURER LA CONVERSATION 🔒", callback_data=f"contact_close_conv_{demande_id}")],
        ])
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 RÉPONDRE À NOUVEAU", callback_data=f"contacter_{demande_id}"),
        InlineKeyboardButton("📄 VOIR LA FICHE", callback_data=f"retour_texte_{demande_id}"),
    ]])


def get_client_confirmation_content(demande_id: int, admin_id: int, is_conv: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier de confirmation envoyés au demandeur."""
    if is_conv:
        text = (
            "✅ <b>Message transmis à votre référent !</b>\n\n"
            "<i>La conversation reste ouverte. Cliquez ci-dessous si vous souhaitez ajouter un autre message ou document :</i>"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 ENVOYER UN AUTRE MESSAGE 💬", callback_data=f"reply_to_admin_{demande_id}_{admin_id}")
        ]])
    else:
        text = "✅ <b>Votre message a été transmis à votre référent !</b>"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")
        ]])
    return text, kb


def build_surveillance_alert(
    user_label_esc: str,
    badge_vip: str,
    demande_id: int,
    alias_staff: str,
    admin_id: int,
    corps: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte et clavier pour les superviseurs lors de la réception d'un message client."""
    alias_staff_esc = html.escape(str(alias_staff or "Opérateur"))
    text = (
        f"📩 <b>SURVEILLANCE — RÉPONSE DU DEMANDEUR</b>\n\n"
        f"• <b>Demandeur :</b> {user_label_esc}{badge_vip}\n"
        f"• <b>Dossier :</b> #{demande_id}\n"
        f"• <b>Opérateur :</b> {alias_staff_esc} (<code>{admin_id}</code>)"
        f"{corps}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 VOIR LE DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")
    ]])
    return text, kb