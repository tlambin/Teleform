"""Dépôt de gestion du cycle de vie des demandes, propositions de prix et relances."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DemandeRepository:
    """Méthodes opérationnelles relatives aux dossiers de demandes avec transactions sécurisées."""

    @staticmethod
    def format_statut_display(statut: str, is_difficile: bool = False, reussie_substatus: Optional[str] = None) -> str:
        clean_statut = str(statut or "").strip()
        if clean_statut == "🎯 Assignée (VIP)":
            return "🎯 Assignée (VIP)"

        if clean_statut in ("⏳ En attente", "🔄 En cours"):
            if is_difficile:
                return f"{clean_statut} ⚠️ (Difficile)"
            return clean_statut

        if clean_statut == "✅ Réussie":
            if reussie_substatus == "terminee":
                return "✅ Réussie (Terminée)"
            return "✅ Réussie (Active)"

        return clean_statut

    def check_social_duplicate(self, instagram: Optional[str] = None, snapchat: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        active_statuses = ("📥 Reçue", "🎯 Assignée (VIP)", "⏳ En attente", "🔄 En cours")
        placeholders = ", ".join(["%s"] * len(active_statuses))

        try:
            with self.get_cursor() as cursor:
                if instagram:
                    clean_insta = instagram.strip().lstrip("@")
                    cursor.execute(
                        f"""
                        SELECT id, request_number, instagram FROM demandes
                        WHERE instagram = %s AND statut IN ({placeholders})
                        LIMIT 1
                        """,
                        (clean_insta, *active_statuses)
                    )
                    row = cursor.fetchone()
                    if row:
                        return True, f"@{clean_insta}"

                if snapchat:
                    clean_snap = snapchat.strip()
                    cursor.execute(
                        f"""
                        SELECT id, request_number, snapchat FROM demandes
                        WHERE snapchat = %s AND statut IN ({placeholders})
                        LIMIT 1
                        """,
                        (clean_snap, *active_statuses)
                    )
                    row = cursor.fetchone()
                    if row:
                        return True, clean_snap

            return False, None
        except Exception as exc:
            logger.error("Erreur vérification doublon réseau : %s", exc)
            return False, None

    def get_channel_combination_active_count(self, orientation: str, reseau: str) -> int:
        active_statuses = ("📥 Reçue", "🎯 Assignée (VIP)", "⏳ En attente", "🔄 En cours")
        placeholders = ", ".join(["%s"] * len(active_statuses))
        res_col = "instagram" if "insta" in reseau.lower() else "snapchat"

        query = f"""
            SELECT COUNT(*) AS total
            FROM demandes
            WHERE statut IN ({placeholders})
              AND orientation = %s
              AND {res_col} IS NOT NULL
              AND {res_col} != ''
        """
        params = list(active_statuses) + [orientation.lower()]

        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return int(row["total"]) if row and row.get("total") else 0
        except Exception as exc:
            logger.error("Erreur comptage combinaison canal (%s, %s) : %s", orientation, reseau, exc)
            return 0

    def get_demandes_disponibles(
        self,
        staff_id: int,
        orientation_filter: Optional[str] = None,
        reseau_filter: Optional[str] = None,
        type_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT id, request_number, user_id, prenom, nom, age, localisation,
                   photo_id, instagram, snapchat, details, prioritaire, montant,
                   statut, orientation, proposed_price, proposed_by, remun_asked_at, date_creation
            FROM demandes
            WHERE statut = '📥 Reçue'
              AND user_id != %s
        """
        params: List[Any] = [int(staff_id)]

        if orientation_filter and orientation_filter != "all":
            if orientation_filter == "bi":
                query += " AND orientation = 'bi'"
            else:
                query += " AND (orientation = %s OR orientation = 'bi')"
                params.append(orientation_filter)

        if reseau_filter == "insta":
            query += " AND instagram IS NOT NULL AND instagram != ''"
        elif reseau_filter == "snap":
            query += " AND snapchat IS NOT NULL AND snapchat != ''"

        if type_filter == "prio_only":
            query += " AND prioritaire = TRUE"
        elif type_filter == "standard_only":
            query += " AND prioritaire = FALSE"

        query += """
            ORDER BY
                prioritaire DESC,
                CASE WHEN prioritaire = 1 THEN montant END DESC,
                date_creation ASC
        """

        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur récupération demandes disponibles staff %s : %s", staff_id, exc)
            return []

    def toggle_demande_difficile(self, demande_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    "UPDATE demandes SET is_difficile = NOT is_difficile, date_modification = NOW() WHERE id = %s",
                    (int(demande_id),)
                )
                cursor.execute("SELECT is_difficile FROM demandes WHERE id = %s", (int(demande_id),))
                row = cursor.fetchone()
                res = bool(row["is_difficile"]) if row else False

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return res
        except Exception as exc:
            logger.error("Erreur bascule statut difficile pour demande %s : %s", demande_id, exc)
            return False

    def update_demande_statut(self, demande_id: int, nouveau_statut: str, reussie_substatus: Optional[str] = None) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute("SELECT prioritaire, montant FROM demandes WHERE id = %s FOR UPDATE", (int(demande_id),))
                current_d = cursor.fetchone()
                if not current_d:
                    return False

                is_prio = bool(current_d.get("prioritaire"))
                montant = float(current_d.get("montant") or 0.0)

                if nouveau_statut == "✅ Réussie":
                    sub = reussie_substatus if reussie_substatus in ("active", "terminee") else "active"
                    init_paiement = "en_attente" if (is_prio and montant > 0) else "non_requis"
                    cursor.execute(
                        """
                        UPDATE demandes
                        SET statut = %s,
                            is_difficile = FALSE,
                            reussie_substatus = %s,
                            paiement_statut = CASE
                                WHEN paiement_statut = 'paye' THEN 'paye'
                                ELSE %s
                            END,
                            date_modification = NOW()
                        WHERE id = %s
                        """,
                        (nouveau_statut, sub, init_paiement, int(demande_id))
                    )
                elif nouveau_statut in ("⏳ En attente", "🔄 En cours", "🎯 Assignée (VIP)"):
                    cursor.execute(
                        """
                        UPDATE demandes
                        SET statut = %s,
                            reussie_substatus = NULL,
                            date_modification = NOW()
                        WHERE id = %s
                        """,
                        (nouveau_statut, int(demande_id))
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE demandes
                        SET statut = %s,
                            is_difficile = FALSE,
                            reussie_substatus = NULL,
                            date_modification = NOW()
                        WHERE id = %s
                        """,
                        (nouveau_statut, int(demande_id))
                    )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True
        except Exception as exc:
            logger.error("Erreur mise à jour statut demande %s : %s", demande_id, exc)
            return False

    def mark_content_delivered(self, demande_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE demandes
                    SET has_delivered_content = TRUE,
                        date_livraison = COALESCE(date_livraison, NOW()),
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (int(demande_id),)
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()
        except Exception as exc:
            logger.error("Erreur marquage livraison demande %s : %s", demande_id, exc)

    # ==================== OFFRES TARIFAIRES & PAIEMENTS ====================

    def set_demande_proposed_price(self, demande_id: int, proposed_by: Optional[int], amount: Optional[float] = None) -> bool:
        try:
            val_montant = round(float(amount), 2) if amount is not None else None
            p_by = int(proposed_by) if proposed_by is not None else None
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE demandes
                    SET proposed_price = %s,
                        proposed_by = %s,
                        remun_asked_at = NOW(),
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (val_montant, p_by, int(demande_id))
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True
        except Exception as exc:
            logger.error("Erreur enregistrement proposition de prix demande %s : %s", demande_id, exc)
            return False

    def clear_demande_proposed_price(self, demande_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE demandes
                    SET proposed_price = NULL,
                        proposed_by = NULL,
                        remun_asked_at = NULL,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (int(demande_id),)
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True
        except Exception as exc:
            logger.error("Erreur effacement proposition de prix demande %s : %s", demande_id, exc)
            return False

    def accept_proposed_price_and_assign(self, demande_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT id, request_number, user_id, prenom, montant, proposed_price, proposed_by
                    FROM demandes
                    WHERE id = %s FOR UPDATE
                    """,
                    (int(demande_id),)
                )
                dem = cursor.fetchone()
                if not dem or not dem.get("proposed_price") or not dem.get("proposed_by"):
                    return None

                staff_id = int(dem["proposed_by"])
                nouveau_prix = float(dem["proposed_price"])

                cursor.execute(
                    """
                    UPDATE demandes
                    SET montant = %s,
                        prioritaire = TRUE,
                        statut = '⏳ En attente',
                        admin_en_charge = %s,
                        proposed_price = NULL,
                        proposed_by = NULL,
                        remun_asked_at = NULL,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (nouveau_prix, staff_id, int(demande_id))
                )

                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), 'active')
                    ON DUPLICATE KEY UPDATE admin_id = VALUES(admin_id), derniere_action = NOW(), statut_suivi = 'active'
                    """,
                    (int(demande_id), staff_id)
                )

                dem["nouveau_montant"] = nouveau_prix
                dem["staff_id"] = staff_id

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return dem
        except Exception as exc:
            logger.error("Erreur acceptation et assignation offre prix demande %s : %s", demande_id, exc)
            return None

    def set_demande_paiement_statut(self, demande_id: int, statut_paiement: str) -> bool:
        valid_statuts = ("non_requis", "en_attente", "paye")
        if statut_paiement not in valid_statuts:
            logger.error("Statut paiement invalide : %s", statut_paiement)
            return False

        try:
            with self.transaction() as cursor:
                cursor.execute(
                    "UPDATE demandes SET paiement_statut = %s, date_modification = NOW() WHERE id = %s",
                    (statut_paiement, int(demande_id))
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            logger.info("Statut paiement demande #%s défini à '%s'", demande_id, statut_paiement)
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour statut paiement demande %s : %s", demande_id, exc)
            return False

    def is_demande_paid(self, demande_id: int) -> bool:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT prioritaire, paiement_statut FROM demandes WHERE id = %s", (int(demande_id),))
                row = cursor.fetchone()
                if not row:
                    return False
                if not row.get("prioritaire"):
                    return True
                return row.get("paiement_statut") == "paye"
        except Exception as exc:
            logger.error("Erreur vérification statut paiement demande %s : %s", demande_id, exc)
            return False

    def update_demande_montant(self, demande_id: int, nouveau_montant: float) -> Tuple[bool, str]:
        try:
            nouveau_montant = round(float(nouveau_montant), 2)
            if nouveau_montant <= 0:
                return False, "Le montant doit être strictement supérieur à 0."

            with self.transaction() as cursor:
                cursor.execute("SELECT prioritaire, montant, statut FROM demandes WHERE id = %s FOR UPDATE", (int(demande_id),))
                dem = cursor.fetchone()
                if not dem:
                    return False, "Demande introuvable."

                if not dem.get("prioritaire"):
                    return False, "Cette demande n'est pas prioritaire."

                statut_actuel = dem.get("statut")
                statuts_autorises = ("📥 Reçue", "🎯 Assignée (VIP)", "⏳ En attente", "🔄 En cours")
                if statut_actuel not in statuts_autorises:
                    return False, f"Impossible de modifier le montant pour une demande avec le statut '{statut_actuel}'."

                montant_actuel = float(dem.get("montant") or 0.0)
                if statut_actuel in ("⏳ En attente", "🔄 En cours") and nouveau_montant <= montant_actuel:
                    return False, f"La demande est déjà prise en charge : vous ne pouvez qu'augmenter le tarif (minimum : {montant_actuel:.2f} €)."

                cursor.execute(
                    "UPDATE demandes SET montant = %s, date_modification = NOW() WHERE id = %s",
                    (nouveau_montant, int(demande_id))
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True, f"Montant mis à jour à {nouveau_montant:.2f} €."
        except Exception as exc:
            logger.error("Erreur modification montant demande %s : %s", demande_id, exc)
            return False, "Erreur technique lors de la mise à jour."

    def upgrade_demande_to_prioritaire(self, demande_id: int, user_id: int, montant: float) -> Tuple[bool, str]:
        try:
            val_montant = round(float(montant), 2)
            if val_montant <= 0:
                return False, "Le montant doit être supérieur à 0 €."

            uid = int(user_id)
            is_management = (
                (hasattr(self, "is_owner") and self.is_owner(uid))
                or (hasattr(self, "is_admin") and self.is_admin(uid))
                or (hasattr(self, "is_staff") and self.is_staff(uid))
            )

            with self.transaction() as cursor:
                if is_management:
                    cursor.execute("SELECT id, user_id, statut, prioritaire FROM demandes WHERE id = %s FOR UPDATE", (int(demande_id),))
                else:
                    cursor.execute(
                        "SELECT id, user_id, statut, prioritaire FROM demandes WHERE id = %s AND user_id = %s FOR UPDATE",
                        (int(demande_id), uid)
                    )

                dem = cursor.fetchone()
                if not dem:
                    return False, "Demande introuvable ou vous n'avez pas l'autorisation sur ce dossier."

                if dem.get("prioritaire"):
                    return False, "Cette demande est déjà prioritaire."

                statuts_autorises = ("📥 Reçue", "🎯 Assignée (VIP)", "⏳ En attente", "🔄 En cours")
                if dem.get("statut") not in statuts_autorises:
                    return False, f"Ce dossier ne peut plus être converti avec le statut '{dem.get('statut')}'."

                cursor.execute(
                    """
                    UPDATE demandes
                    SET prioritaire = TRUE,
                        montant = %s,
                        proposed_price = NULL,
                        proposed_by = NULL,
                        remun_asked_at = NULL,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (val_montant, int(demande_id))
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True, f"Demande convertie en prioritaire ({val_montant:.2f} €)."
        except Exception as exc:
            logger.error("Erreur conversion demande prioritaire %s : %s", demande_id, exc)
            return False, "Erreur technique lors de la conversion."

    def accept_vip_assigned_demande(self, demande_id: int, staff_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM demandes
                    WHERE id = %s AND (statut = '🎯 Assignée (VIP)' OR statut = '📥 Reçue')
                    FOR UPDATE
                    """,
                    (int(demande_id),)
                )
                if not cursor.fetchone():
                    return False

                cursor.execute(
                    """
                    UPDATE demandes
                    SET statut = '⏳ En attente',
                        admin_en_charge = %s,
                        date_modification = NOW()
                    WHERE id = %s
                    """,
                    (int(staff_id), int(demande_id))
                )

                cursor.execute(
                    """
                    INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                    VALUES (%s, %s, NOW(), NOW(), 'active')
                    ON DUPLICATE KEY UPDATE admin_id = VALUES(admin_id), derniere_action = NOW(), statut_suivi = 'active'
                    """,
                    (int(demande_id), int(staff_id))
                )

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True
        except Exception as exc:
            logger.error("Erreur acceptation demande assignée VIP #%s par staff %s : %s", demande_id, staff_id, exc)
            return False

    def decline_vip_assigned_demande(self, demande_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute(
                    "UPDATE demandes SET statut = '📥 Reçue', admin_en_charge = NULL, date_modification = NOW() WHERE id = %s",
                    (int(demande_id),)
                )
                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (int(demande_id),))

            if hasattr(self, "clear_cache"):
                self.clear_cache()

            return True
        except Exception as exc:
            logger.error("Erreur refus demande assignée VIP #%s : %s", demande_id, exc)
            return False

    # ==================== RAPPELS CRON / PERIODIQUES ====================

    def get_paid_undelivered_demandes_for_reminder(self) -> List[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.prenom, d.nom, d.montant, ds.admin_id
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE d.statut = '✅ Réussie'
                      AND d.prioritaire = TRUE
                      AND d.paiement_statut = 'paye'
                      AND d.has_delivered_content = FALSE
                      AND (
                          d.last_payment_delivery_reminder IS NULL
                          OR TIMESTAMPDIFF(HOUR, d.last_payment_delivery_reminder, NOW()) >= 24
                      )
                    """
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur extraction demandes payées non livrées pour rappel : %s", exc)
            return []

    def mark_payment_delivery_reminder_sent(self, demande_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE demandes SET last_payment_delivery_reminder = NOW() WHERE id = %s", (int(demande_id),))
        except Exception as exc:
            logger.error("Erreur horodatage rappel livraison post-paiement demande %s : %s", demande_id, exc)

    def get_unpaid_reussie_demandes_for_reminder(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        if days is not None:
            effective_days = days
        elif hasattr(self, "get_payment_reminder_days"):
            effective_days = self.get_payment_reminder_days()
        elif hasattr(self, "get_config_value"):
            effective_days = int(self.get_config_value("delai_paiement_jours", 2) or 2)
        else:
            effective_days = 2

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, request_number, prenom, montant, admin_en_charge, last_payment_reminder
                    FROM demandes
                    WHERE statut = '✅ Réussie'
                      AND prioritaire = TRUE
                      AND paiement_statut = 'en_attente'
                      AND (
                          (last_payment_reminder IS NULL AND TIMESTAMPDIFF(DAY, date_modification, NOW()) >= %s)
                          OR (last_payment_reminder IS NOT NULL AND TIMESTAMPDIFF(DAY, last_payment_reminder, NOW()) >= %s)
                      )
                    """,
                    (effective_days, effective_days)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur extraction demandes impayées pour rappel client : %s", exc)
            return []

    def mark_user_payment_reminder_sent(self, demande_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE demandes SET last_payment_reminder = NOW() WHERE id = %s", (int(demande_id),))
        except Exception as exc:
            logger.error("Erreur horodatage last_payment_reminder demande %s : %s", demande_id, exc)

    def get_expired_remun_demandes_for_abandon(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        if days is not None:
            effective_days = days
        elif hasattr(self, "get_remun_expiration_days"):
            effective_days = self.get_remun_expiration_days()
        elif hasattr(self, "get_config_value"):
            effective_days = int(self.get_config_value("delai_remun_expire_jours", 2) or 2)
        else:
            effective_days = 2

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, request_number, prenom, proposed_by, proposed_price
                    FROM demandes
                    WHERE statut = '📥 Reçue'
                      AND admin_en_charge IS NULL
                      AND remun_asked_at IS NOT NULL
                      AND TIMESTAMPDIFF(DAY, remun_asked_at, NOW()) >= %s
                    """,
                    (effective_days,)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur extraction demandes avec délai de rémunération expiré : %s", exc)
            return []

    def get_undelivered_terminee_demandes_for_reminder(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        if days is not None:
            effective_days = days
        elif hasattr(self, "get_delivery_reminder_days"):
            effective_days = self.get_delivery_reminder_days()
        elif hasattr(self, "get_config_value"):
            effective_days = int(self.get_config_value("delai_livraison_jours", 3) or 3)
        else:
            effective_days = 3

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.request_number, d.prenom, d.nom, ds.admin_id
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE d.statut = '✅ Réussie'
                      AND d.reussie_substatus = 'terminee'
                      AND d.has_delivered_content = FALSE
                      AND (
                          (d.last_delivery_reminder IS NULL AND TIMESTAMPDIFF(DAY, d.date_modification, NOW()) >= %s)
                          OR (d.last_delivery_reminder IS NOT NULL AND TIMESTAMPDIFF(DAY, d.last_delivery_reminder, NOW()) >= %s)
                      )
                    """,
                    (effective_days, effective_days)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur récupération demandes non livrées pour rappel : %s", exc)
            return []

    def mark_delivery_reminder_sent(self, demande_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE demandes SET last_delivery_reminder = NOW() WHERE id = %s", (int(demande_id),))
        except Exception as exc:
            logger.error("Erreur mise à jour last_delivery_reminder demande %s : %s", demande_id, exc)

    def can_send_demande_reminder(self, demande_id: int) -> Tuple[bool, Optional[str]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT last_vip_reminder, admin_en_charge FROM demandes WHERE id = %s", (int(demande_id),))
                row = cursor.fetchone()
                if not row:
                    return False, "Demande introuvable."
                if not row.get("admin_en_charge"):
                    return False, "Aucun référent n'est actuellement assigné à cette demande."

                last_rem = row.get("last_vip_reminder")
                if not last_rem:
                    return True, None

                diff_seconds = (datetime.now() - last_rem).total_seconds()
                sept_jours_sec = 7 * 86400
                if diff_seconds < sept_jours_sec:
                    jours_restants = max(1, int((sept_jours_sec - diff_seconds) // 86400))
                    return False, f"Rappel déjà envoyé cette semaine. Nouveau rappel possible dans {jours_restants} jour(s)."

                return True, None
        except Exception as exc:
            logger.error("Erreur contrôle rappel demande %s : %s", demande_id, exc)
            return False, "Erreur technique."

    def record_demande_reminder_sent(self, demande_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE demandes SET last_vip_reminder = NOW() WHERE id = %s", (int(demande_id),))
        except Exception as exc:
            logger.error("Erreur enregistrement rappel demande %s : %s", demande_id, exc)