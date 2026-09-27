"""Composants visuels, fiches de mise à jour et claviers de gestion des statuts."""

import html
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.validators import convert_utc_to_paris


def build_status_change_keyboard(demande_id: int, current_status: str, is_diff: bool) -> InlineKeyboardMarkup:
    """Construit le clavier principal de progression de statut selon les règles de gestion."""
    keyboard = []

    # 1. Dossier réussi : aucune régression possible vers En attente ou En cours
    if current_status == "✅ Réussie":
        keyboard.append([
            InlineKeyboardButton("✅ MODIFIER SOUS-STATUT RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])

    # 2. Dossier en cours : Réussie ou Abandonner (pas de retour en attente)
    elif current_status == "🔄 En cours":
        keyboard.append([
            InlineKeyboardButton("✅ RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}"),
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])
        diff_label = "⚠️ DIFFICILE : OUI" if is_diff else "⚠️ DIFFICILE : NON"
        keyboard.append([
            InlineKeyboardButton(diff_label, callback_data=f"status_toggle_diff_{demande_id}")
        ])

    # 3. Dossier en attente / Assignée VIP : En cours, Réussie ou Abandonner
    else:
        keyboard.append([
            InlineKeyboardButton("🔄 EN COURS", callback_data=f"status_apply_{demande_id}_encours")
        ])
        diff_label = "⚠️ DIFFICILE : OUI" if is_diff else "⚠️ DIFFICILE : NON"
        keyboard.append([
            InlineKeyboardButton(diff_label, callback_data=f"status_toggle_diff_{demande_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("✅ RÉUSSIE", callback_data=f"status_sub_reussie_{demande_id}"),
            InlineKeyboardButton("❌ ABANDONNER", callback_data=f"status_prompt_abandon_{demande_id}")
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ RETOUR", callback_data=f"retour_texte_{demande_id}")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_reussie_suboptions_keyboard(demande_id: int) -> InlineKeyboardMarkup:
    """Clavier de choix du sous-statut Active ou Terminée."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 ACTIVE 🟢", callback_data=f"status_apply_reussie_{demande_id}_active"),
            InlineKeyboardButton("❎ TERMINÉE ❎", callback_data=f"status_apply_reussie_{demande_id}_terminee")
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data=f"change_status_{demande_id}")]
    ])


def build_demande_card_keyboard(demande: dict) -> InlineKeyboardMarkup:
    """Construit le clavier d'actions sur la vue de suivi après modification de statut."""
    demande_id = demande["id"]
    is_reussie = (demande.get("statut") == "✅ Réussie")
    has_delivered = bool(demande.get("has_delivered_content", False))
    is_prio = bool(demande.get("prioritaire"))
    paiement_statut = demande.get("paiement_statut", "non_requis")

    buttons = [
        [InlineKeyboardButton("📌 CHANGER LE STATUT 📌", callback_data=f"change_status_{demande_id}")],
        [
            InlineKeyboardButton("👤 PROFIL", callback_data=f"profil_demande_{demande_id}"),
            InlineKeyboardButton("💬 CONTACT", callback_data=f"contacter_{demande_id}")
        ]
    ]

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

    buttons.append([
        InlineKeyboardButton("🔍 TRIER", callback_data="suivi_sort_menu"),
        InlineKeyboardButton("📮 DISPO", callback_data="demandes_disponibles")
    ])
    buttons.append([InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")])

    return InlineKeyboardMarkup(buttons)


def format_demande_suivi_text(demande: dict, db_manager) -> str:
    """Génère le texte complet de la fiche suivi mis à jour (mutualisé message texte et légende photo)."""
    real_id = html.escape(str(demande.get("request_number") or demande["id"]))
    is_prio = bool(demande.get("prioritaire"))
    titre = f"💎  <b>Demande Prioritaire #{real_id}</b>" if is_prio else f"📝  <b>Demande Standard #{real_id}</b>"

    prenom_esc = html.escape(str(demande.get("prenom") or ""))
    nom_esc = html.escape(str(demande.get("nom") or ""))
    nom_complet = f"{prenom_esc} {nom_esc}".strip() or "Identité non précisée"
    age_str = f"  •  {html.escape(str(demande['age']))} ans" if demande.get("age") is not None else ""

    ori_map = {"hetero": "Hétéro", "gay": "Gay", "bi": "Bi"}
    ori_label = html.escape(ori_map.get(str(demande.get("orientation") or "").lower(), "Non précisée"))
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

    statut_label = db_manager.format_statut_display(
        demande.get("statut", "⏳ En attente"),
        demande.get("is_difficile", False),
        demande.get("reussie_substatus")
    )
    lines.append("\n───────  <b>STATUT</b>  ──────")
    lines.append(f" • <b>{html.escape(str(statut_label))}</b> • ")

    def fmt_dt(val):
        if not val:
            return ""
        try:
            return convert_utc_to_paris(val).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(val)[:16]

    dt_mod = demande.get("date_modification")
    if dt_mod:
        lines.append(f" <i>{html.escape(fmt_dt(dt_mod))}</i>")

    if is_prio:
        p_statut = demande.get("paiement_statut", "non_requis")
        if p_statut == "paye":
            lines.append("\n🟢 <b>Réglé et validé</b>")
        elif p_statut == "en_attente":
            lines.append("\n🟡 <b>En attente de règlement</b>")

    admin_id = demande.get("admin_en_charge")
    if admin_id:
        alias = html.escape(str(db_manager.get_staff_alias(admin_id) or f"Staff_{admin_id}"))
        lines.append(f"\n<b>Géré par :</b> <b>{alias}</b>")

    lines.append("\n───────  <b>INFOS</b>  ───────")
    dt_crea = demande.get("date_creation")
    lines.append(f"<b>Déposé le :</b>  {html.escape(fmt_dt(dt_crea))}")

    demandeur = f"@{html.escape(demande['username'])}" if demande.get("username") else (
        html.escape(str(demande.get("user_first_name") or f"User {demande['user_id']}"))
    )
    lines.append(f"<b>Par :</b>  {demandeur} (<code>{demande['user_id']}</code>)")

    ancien_alias = demande.get("ancien_admin_alias")
    raw_reason = demande.get("raison_abandon")
    if ancien_alias or raw_reason:
        alias_str = html.escape(str(ancien_alias or "Opérateur"))
        clean_r = re.sub(r"<[^>]+>", "", str(raw_reason or "Non précisée")).strip()
        lines.append("\n─────  <b>HISTORIQUE</b>  ─────")
        lines.append("❌ Abandonné")
        lines.append(f"{alias_str} le {html.escape(fmt_dt(demande.get('date_modification')))}")
        lines.append(f"<b>Raison :</b> {html.escape(clean_r)}")

    return "\n".join(lines)


def build_reussie_active_notice(req_num: str, prenom: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour une demande passée en Réussie Active."""
    text = (
        f"💡 <b>Rappel de suivi (Demande #{req_num})</b>\n\n"
        f"Le statut a été passé en <b>Réussie (Active)</b>.\n"
        f"D'autres contenus peuvent être obtenus sur <b>{prenom}</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Contacter le demandeur", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_prio_wait_payment_notice(req_num: str, montant: float, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour une demande prioritaire en attente d'encaissement."""
    text = (
        f"💎 <b>Demande prioritaire #{req_num} réussie !</b>\n\n"
        f"Montant alloué : <b>{montant:.2f} €</b>\n\n"
        "⏳ <b>En attente du règlement du client :</b>\n"
        "Le demandeur a reçu les options de paiement (Stars Telegram ou contact direct).\n\n"
        "• Si le client règle par Stars, vous serez notifié instantanément.\n"
        "• S'il vous contacte pour un autre moyen de paiement (PayPal, virement, etc.), "
        "vous pourrez valider la réception des fonds via le bouton <b>« 💰 VALIDER LE PAIEMENT 💰 »</b> sur votre fiche de suivi.\n\n"
        "<i>Conservez vos fichiers : vous pourrez les envoyer dès que le paiement sera validé.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Échanger avec le client", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("📄 Ouvrir la fiche du dossier", callback_data=f"retour_texte_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_delivery_required_notice(req_num: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur rappelant l'envoi obligatoire de contenu."""
    text = (
        f"⚠️ <b>Action requise (Demande #{req_num})</b>\n\n"
        "La demande a été déclarée <b>Réussie (Terminée)</b>.\n\n"
        "👉 Vous devez <b>obligatoirement envoyer le contenu obtenu</b> à l'utilisateur.\n"
        "<i>Le bouton d'archivage sera débloqué dès votre premier envoi (et la demande s'auto-archivera sous le délai configuré).</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Transmettre le contenu maintenant", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb


def build_ready_to_archive_notice(req_num: str, demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Message et boutons envoyés à l'opérateur pour un dossier prêt à archiver manuellement."""
    text = (
        f"📦 <b>Dossier #{req_num} prêt pour l'archivage</b>\n\n"
        "Le contenu a bien été livré. Vous pouvez archiver ce dossier immédiatement pour clore la fiche, "
        "ou le laisser s'archiver automatiquement."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 ARCHIVER LE DOSSIER 📦", callback_data=f"status_archive_now_{demande_id}")],
        [InlineKeyboardButton("💌 Mes suivis", callback_data="demandes_suivies")]
    ])
    return text, kb