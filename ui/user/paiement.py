"""ui/user/paiement.py
Composants visuels, gabarits textuels et claviers pour les paiements, conversions tarifaires et négociations.
"""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ==================== TELEGRAM STARS (FACTURES) ====================

def get_vip_invoice_details(user_id: int) -> dict:
    """Paramètres de facturation Stars pour l'abonnement VIP 30 jours."""
    return {
        "title": "Abonnement VIP 30 Jours",
        "description": "Accès VIP pendant 30 jours : demandes illimitées, choix du référent et contact direct.",
        "payload": f"vip_sub_{user_id}_30d",
        "stars_price": 250,
    }


def get_prio_invoice_details(
    demande_id: int,
    req_num: int,
    prenom: str,
    montant: float,
    user_id: int,
) -> dict:
    """Paramètres de facturation Stars pour le règlement d'une demande prioritaire."""
    return {
        "title": f"Règlement Demande #{req_num}",
        "description": f"Paiement de la prestation prioritaire pour {prenom} ({montant:.2f} €).",
        "payload": f"prio_pay_{demande_id}_{user_id}",
        "label": f"Prestation prioritaire #{req_num}",
        "stars_amount": max(1, int(montant * 50)),
    }


def get_paid_reminder_invoice_details(demande_id: int, user_id: int) -> dict:
    """Paramètres de facturation Stars pour un rappel hebdomadaire payant."""
    return {
        "title": f"Rappel Demande #{demande_id}",
        "description": "Relance prioritaire hebdomadaire envoyée directement à votre référent.",
        "payload": f"remind_pay_{demande_id}_{user_id}",
        "label": "Relance prioritaire (1 €)",
        "stars_amount": 50,
    }


# ==================== CONFIRMATIONS D'ENCAISSEMENT STARS ====================

def get_vip_success_content() -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier de confirmation d'abonnement VIP 30 jours validé."""
    merci_msg = (
        "🎉 <b>Félicitations ! Votre abonnement VIP 30 Jours est activé !</b>\n\n"
        "Vos privilèges exclusifs sont disponibles immédiatement :\n"
        "• 🚀 <b>Demandes illimitées</b> sans aucune restriction de quota\n"
        "• 🎯 <b>Choix de votre référent</b> parmi l'équipe lors de la création\n"
        "• 💬 <b>Ligne directe</b> avec l'opérateur en charge de vos demandes\n"
        "• 🔔 <b>Relance prioritaire hebdomadaire gratuite</b> sur chacune de vos fiches\n\n"
        "Merci pour votre confiance !"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗳️ CRÉER UNE DEMANDE VIP 🗳️", callback_data="new_demande")],
        [InlineKeyboardButton("🔙 MENU PRINCIPAL 🔙", callback_data="start_menu")],
    ])
    return merci_msg, kb


def get_prio_paid_client_content(req_num: str) -> tuple[str, InlineKeyboardMarkup]:
    """Message et clavier de confirmation de règlement transmis au client."""
    merci_msg = (
        f"🎉 <b>Paiement reçu avec succès pour la demande #{req_num} !</b>\n\n"
        "Votre règlement en Stars a été validé. Votre référent a été averti et va procéder "
        "à la transmission de vos contenus dans les plus brefs délais."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 CONSULTER MES DEMANDES 📋", callback_data="voir_demandes")
    ]])
    return merci_msg, kb


def build_prio_paid_admin_alert(
    req_num: str,
    prenom_cible: str,
    montant: float,
    demande_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte remise au piégeur en charge suite à l'encaissement Stars."""
    admin_alert = (
        f"💰 <b>RÈGLEMENT CONFIRMÉ (Demande #{req_num})</b>\n\n"
        f"Le client a réglé la prestation prioritaire pour <b>{prenom_cible}</b> ({montant:.2f} €) via Stars Telegram.\n\n"
        "👉 Vous pouvez désormais transmettre les fichiers obtenus au client."
    )
    alert_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 TRANSMETTRE LE CONTENU MAINTENANT 💬", callback_data=f"contacter_{demande_id}")],
        [InlineKeyboardButton("💌 OUVRIR MES SUIVIS 💌", callback_data="demandes_suivies")],
    ])
    return admin_alert, alert_kb


# ==================== PAIEMENT DIRECT ====================

def build_direct_payment_alert_for_admin(
    req_num: int,
    u_label: str,
    prenom: str,
    montant: float,
    demande_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte envoyée au piégeur quand le client sollicite un paiement alternatif."""
    text = (
        f"💳 <b>Paiement direct demandé (Dossier #{req_num})</b>\n\n"
        f"Le client <b>{html.escape(u_label)}</b> souhaite convenir du mode de paiement "
        f"pour le dossier de <b>{html.escape(str(prenom or ''))}</b> (Montant : <b>{montant:.2f} €</b>).\n\n"
        "Une fois les fonds reçus, validez l'encaissement via le bouton dédié sur votre fiche de suivi."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 OUVRIR LA FICHE DU DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")]
    ])
    return text, kb


def build_direct_payment_client_prompt(
    alias: str,
    req_num: int,
    montant: float,
) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie envoyée au client pour engager la discussion de paiement direct avec le staff."""
    text = (
        f"💬 <b>Paiement avec votre référent ({html.escape(str(alias))}) — Dossier #{req_num}</b>\n\n"
        f"Montant convenu : <b>{montant:.2f} €</b>\n\n"
        "Envoyez votre message ci-dessous pour convenir du moyen de règlement souhaité (PayPal, virement, etc.) :\n"
        "<i>Dès réception des fonds, votre référent validera le paiement et vous transmettra les fichiers.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="cancel_user_reply")]])
    return text, kb


# ==================== REVALORISATION DU PRIX PAR LE STAFF ====================

def build_accept_remun_prio_content(
    req_num: int,
    nouveau_montant: float,
    staff_alias: str,
    prenom: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """Message au client confirmant son acceptation de la contre-proposition de prix."""
    text = (
        f"🎉 <b>Tarif accepté ({nouveau_montant:.2f} €) !</b>\n\n"
        f"Votre dossier #{req_num} concernant <b>{prenom}</b> a été pris en charge immédiatement par <b>{html.escape(str(staff_alias))}</b>.\n"
        "Il est désormais en statut <b>⏳ En attente</b> dans vos demandes en cours."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 CONSULTER MES DEMANDES 📋", callback_data="voir_demandes")
    ]])
    return text, kb


def build_accept_remun_staff_alert(
    req_num: int,
    nouveau_montant: float,
    prenom: str,
    demande_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte au staff notifiant que le client accepte son nouveau prix."""
    text = (
        f"🎉 <b>PROPOSITION DE PRIX ACCEPTÉE ! (Dossier #{req_num})</b>\n\n"
        f"Le demandeur a validé votre tarif de <b>{nouveau_montant:.2f} €</b> pour <b>{prenom}</b>.\n"
        "Le dossier est maintenant présent dans vos <b>Demandes suivies</b> sous le statut <b>⏳ En attente</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 OUVRIR LE DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")],
        [InlineKeyboardButton("💌 MES SUIVIS 💌", callback_data="demandes_suivies")],
    ])
    return text, kb


def build_refuse_remun_prio_content(
    req_num: int,
    montant_initial: float,
) -> tuple[str, InlineKeyboardMarkup]:
    """Message au client actant le refus de la revalorisation proposée."""
    text = (
        f"ℹ️ <b>Proposition refusée.</b>\n\n"
        f"Votre dossier #{req_num} reste actif en file d'attente à son tarif initial de <b>{montant_initial:.2f} €</b>."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗂️ MES DEMANDES 🗂️", callback_data="voir_demandes")
    ]])
    return text, kb


def build_refuse_remun_staff_alert(
    req_num: int,
    prenom: str,
    montant_initial: float,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte au staff notifiant le refus de sa proposition de prix."""
    text = (
        f"ℹ️ <b>Proposition de prix refusée (Dossier #{req_num})</b>\n\n"
        f"Le client a décliné votre offre de revalorisation pour <b>{prenom}</b>.\n"
        f"Le dossier reste disponible dans la file d'attente à <b>{montant_initial:.2f} €</b>."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📮 DEMANDES DISPONIBLES 📮", callback_data="demandes_disponibles")
    ]])
    return text, kb


# ==================== UPGRADE STANDARD ➔ PRIORITAIRE ====================

def get_upgrade_prio_prompt_content(demande_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Invite de saisie pour convertir une demande en prioritaire."""
    text = (
        f"💎 <b>Conversion en Demande Prioritaire (Dossier #{demande_id})</b>\n\n"
        "Indiquez au clavier le <b>montant</b> que vous souhaitez allouer à cette demande (en €) :\n"
        "<i>(Les demandes prioritaires sont examinées et traitées en priorité par l'équipe).</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ ANNULER ❌", callback_data="voir_demandes")]])
    return text, kb


def build_upgrade_prio_success_content(demande_id: int, montant: float) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation au client de la conversion prioritaire."""
    text = (
        f"🎉 <b>Félicitations !</b>\n\nVotre dossier #{demande_id} est désormais <b>💎 Prioritaire</b> avec un montant de <b>{montant:.2f} €</b>.\n"
        "Nos piégeurs traiteront votre demande en priorité !"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 VOIR MES DEMANDES 📋", callback_data="voir_demandes")]])
    return text, kb


def build_upgrade_referent_alert(
    req_num: int,
    prenom: str,
    montant: float,
    demande_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte au référent déjà assigné suite au boost prioritaire du client."""
    text = (
        f"💎 <b>DEMANDE BOOSTÉE EN PRIORITAIRE !</b>\n\n"
        f"Le client a converti le dossier <b>#{req_num}</b> ({prenom}) en prioritaire.\n"
        f"💰 <b>Nouveau montant convenu :</b> <code>{montant:.2f} €</code>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📄 VOIR LE DOSSIER 📄", callback_data=f"retour_texte_{demande_id}")
    ]])
    return text, kb


def build_upgrade_broadcast_alert(
    req_num: int,
    prenom: str,
    montant: float,
    demande_id: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """Alerte diffusée à la file générale des piégeurs après passage en prioritaire."""
    text = (
        f"💎 <b>DEMANDE DEVENUE PRIORITAIRE ! (File d'attente)</b>\n\n"
        f"Le dossier <b>#{req_num}</b> ({prenom}) est maintenant prioritaire.\n"
        f"💰 <b>Montant proposé :</b> <code>{montant:.2f} €</code>\n\n"
        "Disponible immédiatement dans les demandes ouvertes."
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚡ PRENDRE EN CHARGE", callback_data=f"suivre_demande_{demande_id}"),
        InlineKeyboardButton("📮 DEMANDES DISPO", callback_data="demandes_disponibles"),
    ]])
    return text, kb