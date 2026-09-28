"""Constructeur des menus et interfaces pour l'équipe opérationnelle (Staff)."""

import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class StaffKeyboards:
    """Génère les vues des dossiers suivis, profils opérateurs, modes de règlement et démissions."""

    def __init__(self, config, db_manager, role_resolver):
        self.config = config
        self.db_manager = db_manager
        self._get_user_role = role_resolver

    def get_gerer_demandes_menu(self, user_id: int):
        """Affiche le menu de gestion des demandes avec compteurs dynamiques."""
        counts = self.db_manager.get_staff_demandes_counts(user_id)
        nb_dispo = counts.get("dispo", 0)
        nb_suivies = counts.get("suivies", 0)
        nb_archives = counts.get("archives", 0)

        message = (
            "📋 <b>Gestion des demandes</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Accédez aux dossiers selon leur niveau d'assignation :"
        )
        keyboard = [
            [InlineKeyboardButton(f"📮 DISPONIBLE ({nb_dispo})", callback_data="demandes_disponibles")],
            [InlineKeyboardButton(f"💌 SUIVIES ({nb_suivies})", callback_data="demandes_suivies")],
            [InlineKeyboardButton(f"📦 ARCHIVÉES ({nb_archives})", callback_data="demandes_archives")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="start_menu")],
        ]
        return message, InlineKeyboardMarkup(keyboard)

    def get_mon_profil_menu(self, user_id: int):
        """Construit le sous-menu individuel 'MON PROFIL'."""
        user_role = self._get_user_role(user_id)
        is_admin = user_role in ["admin", "owner"]
        is_paused = self.db_manager.is_staff_paused(user_id)
        alias = self.db_manager.get_staff_alias(user_id) or f"Membre_{user_id}"

        primary_owner_id = self.db_manager.get_owner_id() or getattr(self.config, "OWNER_ID", 0)
        is_primary_owner = (int(user_id) == int(primary_owner_id))
        statut_dispo = "⏸️ <b>En pause</b>" if is_paused else "🟢 <b>En service</b>"

        message = (
            "👤 <b>MON PROFIL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Identité :</b> <code>{html.escape(str(alias))}</code>\n"
            f"• <b>Disponibilité :</b> {statut_dispo}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Gérez vos paramètres individuels :"
        )
        keyboard = [
            [InlineKeyboardButton("🔔 NOTIFICATIONS 🔔", callback_data="menu_notifs")],
            [InlineKeyboardButton("🎯 MES CRITÈRES 🎯", callback_data="staff_self_prefs")],
        ]

        if is_admin or self.db_manager.can_staff_edit_alias(user_id):
            keyboard.append([
                InlineKeyboardButton("🏷️ MODIFIER MON ALIAS 🏷️", callback_data="modifier_alias")
            ])

        keyboard.append([
            InlineKeyboardButton("💰 MOYENS DE PAIEMENT 💰", callback_data="staff_payment_settings")
        ])

        if is_paused:
            keyboard.append([
                InlineKeyboardButton("▶️ REPRENDRE LE SERVICE ▶️", callback_data="admin_resume")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("⏸️ SE METTRE EN PAUSE ⏸️", callback_data="admin_pause_prompt")
            ])

        if (user_role in ["staff", "admin"]) or (user_role == "owner" and not is_primary_owner):
            keyboard.append([
                InlineKeyboardButton("❌ DÉMISSIONNER ❌", callback_data="menu_demission")
            ])

        keyboard.append([
            InlineKeyboardButton("🧮 MES STATS", callback_data=f"profil_admin_{user_id}"),
            InlineKeyboardButton("📦 MES ARCHIVES", callback_data="demandes_archives"),
        ])
        keyboard.append([
            InlineKeyboardButton("⬅️ RETOUR", callback_data="parametres")
        ])

        return message, InlineKeyboardMarkup(keyboard)

    def get_demission_choice_menu(self):
        """Affiche le choix de démission pour un membre cumulant Admin et Piégeur."""
        text = (
            "❌ <b>CHOIX DE DÉMISSION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Vous occupez actuellement deux fonctions dans l'équipe :\n"
            "• 🧠 <b>Administrateur</b>\n"
            "• 🎣 <b>Piégeur</b>\n\n"
            "<i>De quel rôle souhaitez-vous démissionner ?</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("🧠 ADMIN 🧠", callback_data="demission_confirm_admin"),
                InlineKeyboardButton("🎣 PIÉGEUR 🎣", callback_data="demission_confirm_staff"),
            ],
            [InlineKeyboardButton("🧠 LES DEUX 🎣", callback_data="demission_confirm_all")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_demission_confirm_menu(self, scope: str):
        """Demande une confirmation claire avant d'acter la démission."""
        if scope == "admin":
            role_label = "de l'<b>Administration</b>"
            warning = "Vous perdrez l'accès aux panneaux de gestion et de surveillance."
        elif scope == "staff":
            role_label = "de l'équipe des <b>Piégeurs</b>"
            warning = "Vos demandes en cours seront immédiatement libérées et remises dans la file."
        else:
            role_label = "de <b>toutes vos fonctions</b> (Admin & Piégeur)"
            warning = "Vous redeviendrez simple utilisateur. Vos dossiers actifs seront libérés."

        text = (
            "⚠️ <b>CONFIRMATION DE DÉMISSION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Êtes-vous certain de vouloir démissionner {role_label} ?\n\n"
            f"<i>{warning}</i>\n\n"
            "Cette action prend effet immédiatement."
        )
        keyboard = [
            [InlineKeyboardButton("⚠️ OUI, DÉMISSIONNER", callback_data=f"demission_exec_{scope}")],
            [InlineKeyboardButton("⬅️ ANNULER", callback_data="menu_mon_profil")],
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_staff_self_preferences_menu(self, user_id: int):
        """Menu interactif de configuration des critères de l'opérateur."""
        can_edit = self.db_manager.can_staff_edit_preferences(user_id)
        perms = self.db_manager.get_staff_permissions(user_id)

        reseau = str(perms.get("perm_reseaux") or "all").lower()
        typ = str(perms.get("perm_type") or "all").lower()
        ori = str(perms.get("perm_orientation") or "hetero").lower()

        # --- TEXTE DU RÉCAPITULATIF ---
        if reseau == "insta":
            txt_res = "🌆 Insta"
        elif reseau == "snap":
            txt_res = "👻 Snap"
        else:
            txt_res = "🌆 Insta + 👻 Snap"

        if ori == "hetero":
            txt_ori = "🫂 Hétéro"
        elif ori == "gay":
            txt_ori = "🌈 Gay"
        else:
            txt_ori = "🫂 Hétéro + 🌈 Gay"

        if typ == "standard_only":
            txt_typ = "🧾 Standard"
        elif typ == "prio_only":
            txt_typ = "💎 Prioritaire"
        else:
            txt_typ = "🧾 Standard + 💎 Prioritaire"

        text = (
            "🎯 <b>CHOIX DE MES CRITÈRES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Configurez vos critères en un clic.\n\n"
            f"• <b>Réseaux :</b> {txt_res}\n"
            f"• <b>Orientation :</b> {txt_ori}\n"
            f"• <b>Type :</b> {txt_typ}\n\n"
            "<i>Modifiez votre sélection avec les boutons ci-dessous :</i>"
        )

        if not can_edit:
            text += "\n\n🔒 <i>Vos critères sont actuellement verrouillés par l'administration.</i>"

        # --- LABELS DYNAMIQUES DU CLAVIER (Coche en remplacement d'icône) ---
        prefix = "self_pref" if can_edit else "self_pref_locked"

        btn_res_insta = "✅ INSTA" if reseau == "insta" else "🌆 INSTA"
        btn_res_all = "✅ LES 2" if reseau == "all" else "LES 2"
        btn_res_snap = "✅ SNAP" if reseau == "snap" else "👻 SNAP"

        btn_ori_h = "✅ HÉTÉRO" if ori == "hetero" else "🫂 HÉTÉRO"
        btn_ori_all = "✅ LES 2" if ori in ("all", "bi") else "LES 2"
        btn_ori_g = "✅ GAY" if ori == "gay" else "🌈 GAY"

        btn_typ_std = "✅ STANDARD" if typ == "standard_only" else "🧾 STANDARD"
        btn_typ_all = "✅ LES 2" if typ == "all" else "LES 2"
        btn_typ_prio = "✅ PRIORITAIRE" if typ == "prio_only" else "💎 PRIORITAIRE"

        keyboard = [
            # Rangée 1 : Réseaux
            [
                InlineKeyboardButton(btn_res_insta, callback_data=f"{prefix}_res_insta"),
                InlineKeyboardButton(btn_res_all, callback_data=f"{prefix}_res_all"),
                InlineKeyboardButton(btn_res_snap, callback_data=f"{prefix}_res_snap"),
            ],
            # Rangée 2 : Orientation
            [
                InlineKeyboardButton(btn_ori_h, callback_data=f"{prefix}_ori_hetero"),
                InlineKeyboardButton(btn_ori_all, callback_data=f"{prefix}_ori_all"),
                InlineKeyboardButton(btn_ori_g, callback_data=f"{prefix}_ori_gay"),
            ],
            # Rangée 3 : Formule / Type
            [
                InlineKeyboardButton(btn_typ_std, callback_data=f"{prefix}_type_standard_only"),
                InlineKeyboardButton(btn_typ_all, callback_data=f"{prefix}_type_all"),
                InlineKeyboardButton(btn_typ_prio, callback_data=f"{prefix}_type_prio_only"),
            ],
            # Rangée 4 : Retour vers Mon Profil
            [
                InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")
            ],
        ]

        return text, InlineKeyboardMarkup(keyboard)

    def get_staff_payment_settings_menu(self, staff_id: int):
        """Affiche le menu de configuration des moyens de paiement."""
        methods = self.db_manager.get_staff_payment_methods(staff_id)
        accept_stars = bool(methods.get("accept_stars", True))
        accept_direct = bool(methods.get("accept_direct", True))

        # --- TEXTE D'ÉTAT DYNAMIQUE ---
        st_stars = "✅ Activé" if accept_stars else "❌ Désactivé"
        st_direct = "✅ Activé" if accept_direct else "❌ Désactivé"

        text = (
            "💰 <b>MOYENS DE PAIEMENT ACCEPTÉS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Définissez vos méthodes de règlement proposées pour les demandes prioritaires :\n\n"
            f"• <b>Telegram Stars :</b> {st_stars}\n"
            f"• <b>Paiement direct :</b> {st_direct}\n"
            "(Paypal, unlockt, etc...)\n\n"
            "⚠️ <i>Vous devez conserver au minimum un moyen de paiement actif.</i>\n\n"
            "<i>Modifiez votre sélection avec les boutons ci-dessous :</i>"
        )

        # --- ÉTIQUETTES DES BOUTONS ---
        btn_stars = f"⭐ TELEGRAM STARS {'✅' if accept_stars else '❌'}"
        btn_direct = f"💸 PAIEMENT DIRECT {'✅' if accept_direct else '❌'}"

        keyboard = [
            [InlineKeyboardButton(btn_stars, callback_data="toggle_pay_staff_accept_stars")],
            [InlineKeyboardButton(btn_direct, callback_data="toggle_pay_staff_accept_direct")],
            [InlineKeyboardButton("⬅️ RETOUR", callback_data="menu_mon_profil")],
        ]

        return text, InlineKeyboardMarkup(keyboard)