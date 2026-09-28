"""ui/admin/system.py
Gabarits visuels, textes et claviers pour la gestion globale et technique :
Maintenance, statut opérationnel On/Off, statistiques, délais, purges et menus système.
"""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

PURGE_LABELS = {
    "archives": "des archives",
    "demandes": "des demandes",
    "users": "des utilisateurs",
    "staff": "du staff",
    "admins": "des administrateurs",
    "config": "de configuration (config)",
    "totale": "TOTALE (de toute la base de données)",
}


# ==================== MENUS SYSTÈME (GESTION CENTRALE) ====================

def build_gerer_bot_menu(demandes_ouvertes: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Menu de contrôle du bot système."""
    etat_badge = "🟢 <b>OUVERTES (Actives)</b>" if demandes_ouvertes else "🔴 <b>SUSPENDUES (Fermées)</b>"
    label_suspension = (
        "❌ SUSPENDRE LES DEMANDES ❌" if demandes_ouvertes else "✅ RÉACTIVER LES DEMANDES ✅"
    )

    message = (
        "🤖 <b>GESTION DU BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>État des demandes :</b> {etat_badge}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Panneau de contrôle système de la plateforme :"
    )
    keyboard = [
        [InlineKeyboardButton(label_suspension, callback_data="bot_toggle_suspension")],
        [
            InlineKeyboardButton("🌡️ QUOTAS", callback_data="menu_limits"),
            InlineKeyboardButton("🎯 CIBLES", callback_data="menu_channels"),
        ],
        [
            InlineKeyboardButton("⏳ DÉLAIS", callback_data="menu_delais"),
            InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="maintenance"),
        ],
        [
            InlineKeyboardButton("🔑 ADHÉSION", callback_data="menu_cfg_group"),
            InlineKeyboardButton("📢 CONTACT", callback_data="menu_cfg_support"),
        ],
        [InlineKeyboardButton("⛔ ZONE DE DANGER ⛔", callback_data="menu_danger_zone")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")],
    ]
    return message, InlineKeyboardMarkup(keyboard)


def build_danger_zone_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Affiche le menu de purge de la zone de danger (Owner only)."""
    text = (
        "🚨 <b>ZONE DE DANGER — PURGE DES DONNÉES</b> 🚨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <b>Attention :</b> Les actions lancées ici effacent immédiatement et définitivement les données ciblées dans MySQL.\n\n"
        "<i>Sélectionnez le lot de données à vider :</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton("📦 VIDER ARCHIVES", callback_data="danger_purge_archives"),
            InlineKeyboardButton("📋 VIDER DEMANDES", callback_data="danger_purge_demandes"),
        ],
        [
            InlineKeyboardButton("👤 VIDER CLIENTS", callback_data="danger_purge_users"),
            InlineKeyboardButton("🦈 VIDER STAFF", callback_data="danger_purge_staff"),
        ],
        [
            InlineKeyboardButton("🛡️ VIDER MANAGERS", callback_data="danger_purge_admins"),
            InlineKeyboardButton("⚙️ VIDER CONFIG", callback_data="danger_purge_config"),
        ],
        [InlineKeyboardButton("💥 PURGE TOTALE 💥", callback_data="danger_purge_totale")],
        [InlineKeyboardButton("⬅️ RETOUR ⬅️", callback_data="gerer_bot")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_group_subscription_config_menu(is_enabled: bool, group_id: int, link: str) -> tuple[str, InlineKeyboardMarkup]:
    """Menu de configuration de l'adhésion obligatoire."""
    statut_badge = "🟢 <b>ACTIVE</b>" if is_enabled else "🔴 <b>DÉSACTIVÉE</b>"
    toggle_btn_label = "🔴 DÉSACTIVER LE CONTRÔLE" if is_enabled else "🟢 ACTIVER LE CONTRÔLE"
    gid_str = f"<code>{group_id}</code>" if group_id != 0 else "<i>Non configuré (0)</i>"

    text = (
        "📢 <b>ADHÉSION OBLIGATOIRE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Si activé, tout utilisateur absent du groupe ne peut pas utiliser le bot.</i>\n\n"
        f"{statut_badge}\n\n"
        f"<b>GROUPE :</b> {gid_str}\n"
        f"<b>LIEN :</b> <code>{html.escape(link)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [
        [InlineKeyboardButton(toggle_btn_label, callback_data="toggle_cfg_group_enabled")],
        [
            InlineKeyboardButton("🆔 GROUPE", callback_data="set_cfg_group_id"),
            InlineKeyboardButton("🔗 LIEN", callback_data="set_cfg_group_link"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_support_config_menu(contact: str) -> tuple[str, InlineKeyboardMarkup]:
    """Menu de configuration du canal support officiel."""
    text = (
        "🎧 <b>CANAL DU SUPPORT OFFICIEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Contact actuel :</b> <code>{html.escape(contact)}</code>\n\n"
        "<i>Ce lien/pseudo est communiqué aux demandeurs en cas d'interrogation ou de blocage.</i>"
    )
    keyboard = [
        [InlineKeyboardButton("✏️ MODIFIER", callback_data="set_cfg_support_contact")],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_channels_menu(hi: bool, hs: bool, gi: bool, gs: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Menu de gestion et d'activation des cibles avec voyants préfixés."""
    def s_badge(val: bool) -> str:
        return "🟢" if val else "🔴"

    message = (
        "🎯 <b>GESTION DES CIBLES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Activer / Désactiver les demandes par cible :\n\n"
        f"{s_badge(hi)} HÉTÉRO - INSTA\n"
        f"{s_badge(hs)} HÉTÉRO - SNAP\n\n"
        f"{s_badge(gi)} GAY - INSTA\n"
        f"{s_badge(gs)} GAY - SNAP\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Les Bi s'orientent selon le réseau concerné.</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"{s_badge(hi)} HÉTÉRO - INSTA", callback_data="toggle_allow_hetero_insta"),
            InlineKeyboardButton(f"{s_badge(hs)} HÉTÉRO - SNAP", callback_data="toggle_allow_hetero_snap"),
        ],
        [
            InlineKeyboardButton(f"{s_badge(gi)} GAY - INSTA", callback_data="toggle_allow_gay_insta"),
            InlineKeyboardButton(f"{s_badge(gs)} GAY - SNAP", callback_data="toggle_allow_gay_snap"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
    ]
    return message, InlineKeyboardMarkup(keyboard)


def build_limits_menu(max_total: int, max_user: int, m_hi: int, m_hs: int, m_gi: int, m_gs: int) -> tuple[str, InlineKeyboardMarkup]:
    """Ajustement des quotas avec contrôle par réseau."""
    def fmt(val: int) -> str:
        return f"<b>{val}</b>" if val > 0 else "<i>Illimité</i>"

    message = (
        "🌡️ <b>GESTION DES QUOTAS :</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 <b>TOTAL :</b> {fmt(max_total)}\n"
        f"👤 <b>CLIENT :</b> {fmt(max_user)}\n\n"
        f"🕺 <b>HÉTÉRO :</b> {m_hi} INSTA | {m_hs} SNAP\n"
        f"🏳️‍🌈 <b>GAY :</b> {m_gi} INSTA | {m_gs} SNAP\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Ajustez via les boutons ou saisissez une valeur précise :</i>"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 TOTAL", callback_data="limit_input_total")],
        [
            InlineKeyboardButton("- 5", callback_data="limit_total_sub5"),
            InlineKeyboardButton("ILLIMITÉ", callback_data="limit_total_0"),
            InlineKeyboardButton("+ 5", callback_data="limit_total_add5"),
        ],
        [InlineKeyboardButton("👤 CLIENT", callback_data="limit_input_user")],
        [
            InlineKeyboardButton("- 1", callback_data="limit_user_sub1"),
            InlineKeyboardButton("DÉFAUT (3)", callback_data="limit_user_3"),
            InlineKeyboardButton("+ 1", callback_data="limit_user_add1"),
        ],
        [
            InlineKeyboardButton("🕺 INSTA", callback_data="limit_input_hetero_insta"),
            InlineKeyboardButton("🕺 SNAP", callback_data="limit_input_hetero_snap"),
        ],
        [
            InlineKeyboardButton("🏳️‍🌈 INSTA", callback_data="limit_input_gay_insta"),
            InlineKeyboardButton("🏳️‍🌈 SNAP", callback_data="limit_input_gay_snap"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
    ]
    return message, InlineKeyboardMarkup(keyboard)


# ==================== STATUT OPÉRATIONNEL & SERVICE ====================

def get_bot_on_content() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🟢 <b>Bot opérationnel</b>\n\n"
        "✅ Les utilisateurs peuvent à nouveau créer des demandes et naviguer librement.\n"
        "📊 Toutes les commandes sont actives."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Suspendre", callback_data="bot_off")],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")],
    ])
    return text, keyboard


def get_bot_off_content() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🔴 <b>Demandes suspendues</b>\n\n"
        "⏸️ Le service de création de demandes est désormais désactivé.\n"
        "🔒 L'équipe conserve ses accès pour traiter et clôturer les dossiers en cours."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Réactiver", callback_data="bot_on")],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")],
    ])
    return text, keyboard


def get_bot_off_confirmation_content() -> tuple[str, InlineKeyboardMarkup]:
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ Confirmer la suspension", callback_data="confirm_bot_off"),
        InlineKeyboardButton("❌ Annuler", callback_data="cancel_bot_off"),
    ]])
    text = (
        "⚠️ <b>Suspension des nouvelles demandes</b>\n\n"
        "Les utilisateurs ne pourront plus créer de demandes jusqu'à la réactivation.\n"
        "Confirmez-vous cette action ?"
    )
    return text, keyboard


def get_bot_maintenance_content() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🛠️ <b>Mode maintenance actif</b>\n\n"
        "⚙️ Le bot est verrouillé pour des interventions techniques.\n"
        "Seuls les comptes de direction sont habilités à exécuter des actions."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Réactiver le service", callback_data="bot_on")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")],
    ])
    return text, keyboard


def build_bot_status_content(is_active: bool, is_maint: bool) -> tuple[str, InlineKeyboardMarkup]:
    if is_maint:
        badge, detail = "🛠️ <b>Maintenance</b>", "Accès restreint à la direction."
    elif is_active:
        badge, detail = "🟢 <b>Actif</b>", "Toutes les fonctions sont opérationnelles pour les utilisateurs."
    else:
        badge, detail = "🔴 <b>Suspendu</b>", "Les utilisateurs ne peuvent plus soumettre de formulaires."

    text = f"📊 <b>Statut Opérationnel du Service</b>\n\n• <b>État :</b> {badge}\n• <b>Détails :</b> {detail}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Activer", callback_data="bot_on"),
            InlineKeyboardButton("🔴 Couper", callback_data="bot_off"),
        ],
        [InlineKeyboardButton("🛠️ Maintenance", callback_data="maintenance")],
        [InlineKeyboardButton("🔙 Gestion Service", callback_data="gerer_bot")],
    ])
    return text, keyboard


# ==================== MAINTENANCE SYSTÈME ====================

def format_maintenance_summary(
    storage_before: float, storage_after: float, demandes_count: int, archives_count: int
) -> tuple[str, InlineKeyboardMarkup]:
    economie = max(0.0, storage_before - storage_after)
    message = (
        "✅ <b>Maintenance terminée avec succès</b>\n\n"
        "💾 <b>Stockage local :</b>\n"
        f"• Avant : {storage_before:.1f} Mo\n"
        f"• Après : {storage_after:.1f} Mo\n"
        f"• Gain : {economie:.1f} Mo\n\n"
        "📊 <b>Base de données :</b>\n"
        f"• Demandes actives : {demandes_count}\n"
        f"• Demandes archivées : {archives_count}\n\n"
        "🧹 Cache mémoire purgé et index optimisés."
    )
    return message, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")]])


# ==================== STATISTIQUES ====================

def format_stats_message(stats: dict) -> str:
    storage = float(stats.get("storage_usage") or 0.0)
    db_size = stats.get("db_stats", {}).get("total_size_mb", 0.0)

    lines = [
        "📈 <b>Tableau de Bord & Statistiques</b>\n",
        "👥 <b>Communauté & Équipe :</b>",
        f"• Inscrits totaux : <b>{stats.get('total_users', 0)}</b>",
        f"• Membres VIP actifs : <b>{stats.get('total_vips', 0)}</b>",
        f"• Opérateurs Staff : <b>{stats.get('total_staff', 0)}</b>",
        f"• Direction & Admins : <b>{stats.get('total_admins', 0)}</b>",
        f"• Actifs (dernières 24h) : <b>{stats.get('active_24h', 0)}</b>",
        f"• Nouveaux (7 derniers jours) : <b>{stats.get('new_7d', 0)}</b>\n",
        "📋 <b>Volume de Demandes :</b>",
        f"• Actives : <b>{stats.get('total_demandes', 0)}</b>",
        f"• Reçues aujourd'hui : <b>{stats.get('demandes_today', 0)}</b>",
        f"• Archivées : <b>{stats.get('total_archives', 0)}</b>",
        f"• Répartition actives : 💎 <b>{stats.get('nb_prio', 0)}</b> prioritaires | 📝 <b>{stats.get('nb_std', 0)}</b> standard",
        f"• Montant cumulé total : <b>{stats.get('total_montant', 0.0):.2f} €</b> (moyenne prio : {stats.get('avg_montant', 0.0):.2f} €)\n",
        "📊 <b>Statuts des demandes en cours :</b>",
    ]
    for s in stats.get("statuts", []):
        lines.append(f"• {s.get('statut', 'Inconnu')} : {s.get('count', 0)}")

    storage_pct = (storage / 512.0) * 100.0 if storage else 0.0
    lines.append("\n💾 <b>Ressources Système :</b>")
    lines.append(f"• Stockage local : <b>{storage:.1f} Mo / 512 Mo</b> ({storage_pct:.1f} %)")
    lines.append(f"• Base de données MySQL : <b>{db_size} Mo</b>")
    return "\n".join(lines)


def build_stats_keyboard(is_owner: bool) -> InlineKeyboardMarkup:
    retour_callback = "gerer_bot" if is_owner else "parametres"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Actualiser", callback_data="bot_stats")],
        [InlineKeyboardButton("🔙 Retour", callback_data=retour_callback)],
    ])


# ==================== DÉLAIS PARAMÉTRABLES ====================

def get_delais_menu_content(hours: int, days: int, pay_days: int, remun_days: int) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⏳ <b>CONFIGURATION DES DÉLAIS DU SYSTÈME</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• 📦 <b>Auto-archivage post-livraison :</b> <code>{hours}h</code>\n"
        f"• 🚚 <b>Rappel livraison (Staff) :</b> <code>{days} jours</code>\n"
        f"• 💰 <b>Rappel impayé (Demandeur) :</b> <code>{pay_days} jours</code>\n"
        f"• ⏳ <b>Délai réponse rémunération :</b> <code>{remun_days} jours</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Cliquez sur une option pour modifier sa valeur :</i>"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"📦 Auto-archivage ({hours}h)", callback_data="cfg_sub_archive_hours"),
            InlineKeyboardButton(f"🚚 Rappel Livraison ({days}j)", callback_data="cfg_sub_reminder_days"),
        ],
        [
            InlineKeyboardButton(f"💰 Rappel Impayé Client ({pay_days}j)", callback_data="cfg_sub_payrem_days"),
            InlineKeyboardButton(f"⏳ Délai Rémunération ({remun_days}j)", callback_data="cfg_sub_remun_days"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="gerer_bot")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def get_archive_hours_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("24h (1j)", 24), callback_data="set_arch_hours_24"),
            InlineKeyboardButton(b_lbl("48h (2j)", 48), callback_data="set_arch_hours_48"),
        ],
        [
            InlineKeyboardButton(b_lbl("72h (3j)", 72), callback_data="set_arch_hours_72"),
            InlineKeyboardButton(b_lbl("168h (7j)", 168), callback_data="set_arch_hours_168"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")],
    ]
    return f"📦 <b>Délai d'auto-archivage</b>\n\nActuel : <b>{current} heures</b> post-livraison.", InlineKeyboardMarkup(keyboard)


def get_reminder_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_rem_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_rem_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_rem_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_rem_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")],
    ]
    return f"🚚 <b>Délai de relance non livré (Staff)</b>\n\nActuel : <b>{current} jours</b>.", InlineKeyboardMarkup(keyboard)


def get_payment_reminder_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_payrem_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_payrem_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_payrem_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_payrem_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")],
    ]
    return f"💰 <b>Fréquence rappel impayé (Demandeur)</b>\n\nActuelle : Tous les <b>{current} jours</b>.", InlineKeyboardMarkup(keyboard)


def get_remun_expiration_days_content(current: int) -> tuple[str, InlineKeyboardMarkup]:
    def b_lbl(name: str, val: int) -> str:
        return f"✅ {name}" if current == val else name

    keyboard = [
        [
            InlineKeyboardButton(b_lbl("3 jours", 3), callback_data="set_remun_days_3"),
            InlineKeyboardButton(b_lbl("5 jours", 5), callback_data="set_remun_days_5"),
        ],
        [
            InlineKeyboardButton(b_lbl("7 jours", 7), callback_data="set_remun_days_7"),
            InlineKeyboardButton(b_lbl("14 jours", 14), callback_data="set_remun_days_14"),
        ],
        [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_delais")],
    ]
    text = (
        "⏳ <b>Délai avant abandon (Non-réponse rémunération)</b>\n\n"
        f"Actuel : <b>{current} jours</b>.\n\n"
        "<i>Passé ce délai sans réponse du demandeur, la demande sera classée sous « ❌ Abandonnée ».</i>"
    )
    return text, InlineKeyboardMarkup(keyboard)


# ==================== PURGES SÉCURISÉES ====================

def get_step1_confirmation_content(target: str) -> tuple[str, InlineKeyboardMarkup]:
    libelle = PURGE_LABELS.get(target, target)
    text = f"🚨 <b>CONFIRMATION REQUISE</b>\n\nÊtes-vous sûr de vouloir effacer la table <b>{libelle}</b> ?\n\nCette action est <b>absolument irréversible</b>."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ OUI, continuer", callback_data=f"danger_confirm_yes_{target}")],
        [InlineKeyboardButton("❌ NON, annuler", callback_data="menu_danger_zone")],
    ])
    return text, kb


def get_step2_text_confirmation_content(target: str) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "✍️ <b>Dernière étape de sécurité</b>\n\n"
        f"Cible : <code>{target}</code>\n\n"
        "Pour valider définitivement la suppression, veuillez <b>taper exactement au clavier le mot</b> :\n"
        "<code>Effacer</code>\n\n"
        "<i>(Envoyez n'importe quel autre message ou cliquez ci-dessous pour annuler).</i>"
    )
    return text, InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_danger_zone")]])


def get_purge_result_content(success: bool, target: str, is_canceled: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    if is_canceled:
        msg = "❌ <b>Suppression annulée :</b> Le mot de confirmation n'était pas exactement 'Effacer'."
    elif success:
        msg = f"✅ <b>Purge de la cible « {target} » exécutée avec succès !</b>\n\nLa base de données a été mise à jour."
    else:
        msg = f"❌ <b>Échec lors de la purge de « {target} ».</b> Consultez les logs d'erreurs."
    return msg, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_danger_zone")]])