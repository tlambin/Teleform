"""Dépôt de gestion du staff, alias, permissions opérationnelles et modes de paiement."""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class StaffRepository:
    """Méthodes de gestion de l'équipe Staff."""

    def is_staff(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_admin(uid):
            return True

        cache_key = f"is_staff_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT user_id FROM staff WHERE user_id = %s", (uid,))
                val = bool(cursor.fetchone())
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur contrôle is_staff pour %s : %s", uid, exc)
            return False

    def get_staff_alias(self, user_id: int) -> str:
        cache_key = f"alias_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached:
            return cached

        if self.is_owner(user_id):
            alias = self.get_owner_alias()
            self._set_cached_value(cache_key, alias)
            return alias

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT alias FROM staff WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row and row.get("alias"):
                    alias = row["alias"]
                    self._set_cached_value(cache_key, alias)
                    return alias

                cursor.execute("SELECT alias FROM admins WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row and row.get("alias"):
                    alias = row["alias"]
                    self._set_cached_value(cache_key, alias)
                    return alias

                return "Staff"
        except Exception as exc:
            logger.error("Erreur extraction alias staff %s : %s", user_id, exc)
            return "Staff"

    get_admin_alias = get_staff_alias

    def set_staff_alias(self, user_id: int, new_alias: str) -> bool:
        clean_alias = new_alias.strip()
        if self.is_owner(user_id):
            ok = self.set_owner_alias(clean_alias)
            if ok:
                self.clear_cache(f"alias_{user_id}")
            return ok

        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE staff SET alias = %s WHERE user_id = %s", (clean_alias, user_id))
                cursor.execute("UPDATE admins SET alias = %s WHERE user_id = %s", (clean_alias, user_id))
            self.clear_cache(f"alias_{user_id}")
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour alias %s : %s", user_id, exc)
            return False

    set_admin_alias = set_staff_alias

    def can_staff_edit_alias(self, user_id: int) -> bool:
        if self.is_owner(user_id):
            return True
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT alias_locked FROM staff WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                return not bool(row.get("alias_locked")) if row else False
        except Exception as exc:
            logger.error("Erreur vérification verrou alias pour %s : %s", user_id, exc)
            return False

    can_admin_edit_alias = can_staff_edit_alias

    def lock_staff_alias(self, user_id: int):
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE staff SET alias_locked = TRUE WHERE user_id = %s", (user_id,))
            self.clear_cache(f"alias_{user_id}")
        except Exception as exc:
            logger.error("Erreur verrouillage alias %s : %s", user_id, exc)

    lock_admin_alias = lock_staff_alias

    def can_staff_edit_preferences(self, user_id: int) -> bool:
        if self.is_owner(user_id) or self.is_admin(user_id):
            return True
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT allow_self_prefs FROM staff WHERE user_id = %s", (int(user_id),))
                row = cursor.fetchone()
                return bool(row.get("allow_self_prefs", True)) if row else True
        except Exception as exc:
            logger.error("Erreur vérification allow_self_prefs pour %s : %s", user_id, exc)
            return True

    def toggle_staff_self_prefs(self, user_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE staff SET allow_self_prefs = NOT allow_self_prefs WHERE user_id = %s", (int(user_id),))
            self.clear_cache(f"perm_{user_id}")
            self.clear_cache()
            return True
        except Exception as exc:
            logger.error("Erreur bascule allow_self_prefs pour %s : %s", user_id, exc)
            return False

    def is_staff_paused(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        cache_key = f"staff_paused_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        if self.is_owner(uid):
            val = str(self.get_config_value("owner_is_paused", "false")).lower()
            is_paused = val in ("true", "1", "yes")
            self._set_cached_value(cache_key, is_paused)
            return is_paused

        if self.is_admin(uid):
            try:
                with self.get_cursor() as cursor:
                    cursor.execute("SELECT is_paused FROM admins WHERE user_id = %s", (uid,))
                    row = cursor.fetchone()
                    if row and row.get("is_paused") is not None:
                        is_paused = bool(row["is_paused"])
                        self._set_cached_value(cache_key, is_paused)
                        return is_paused
            except Exception as exc:
                logger.debug("Info contrôle pause admin %s : %s", uid, exc)

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT is_paused FROM staff WHERE user_id = %s", (uid,))
                row = cursor.fetchone()
                val = bool(row.get("is_paused")) if row else False
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur vérification pause staff %s : %s", uid, exc)
            return False

    is_admin_paused = is_staff_paused

    def set_staff_pause_status(self, user_id: int, paused: bool) -> bool:
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False

        if self.is_owner(uid):
            val_str = "true" if paused else "false"
            ok = self.set_config_value("owner_is_paused", val_str)
            self.clear_cache(f"staff_paused_{uid}")
            return ok

        if self.is_admin(uid):
            try:
                with self.transaction() as cursor:
                    cursor.execute("UPDATE admins SET is_paused = %s WHERE user_id = %s", (bool(paused), uid))
                self.clear_cache(f"staff_paused_{uid}")
                return True
            except Exception as exc:
                logger.error("Erreur modification pause admin %s : %s", uid, exc)
                return False

        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE staff SET is_paused = %s WHERE user_id = %s", (bool(paused), uid))
            self.clear_cache(f"staff_paused_{uid}")
            return True
        except Exception as exc:
            logger.error("Erreur modification pause staff %s : %s", uid, exc)
            return False

    set_admin_pause_status = set_staff_pause_status

    def is_staff_trial(self, user_id: int) -> bool:
        cache_key = f"staff_trial_{user_id}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT is_trial FROM staff WHERE user_id = %s", (int(user_id),))
                row = cursor.fetchone()
                val = bool(row.get("is_trial")) if row else False
                self._set_cached_value(cache_key, val)
                return val
        except Exception as exc:
            logger.error("Erreur vérification statut essai staff %s : %s", user_id, exc)
            return False

    def set_staff_trial(self, user_id: int, is_trial: bool) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute("UPDATE staff SET is_trial = %s WHERE user_id = %s", (bool(is_trial), int(user_id)))
            self.clear_cache(f"staff_trial_{user_id}")
            self.clear_cache(f"perm_{user_id}")
            self.clear_cache()
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour statut essai staff %s : %s", user_id, exc)
            return False

    def get_random_demande_for_trial(self, staff_id: int) -> Optional[Dict[str, Any]]:
        perms = self.get_staff_permissions(staff_id)
        p_ori = perms.get("perm_orientation", "all")
        p_res = perms.get("perm_reseaux", "all")
        p_typ = perms.get("perm_type", "all")

        sql_where = [
            "d.statut = '📥 Reçue'",
            "d.admin_en_charge IS NULL",
            "d.user_id != %s"
        ]
        params: List[Any] = [int(staff_id)]

        if p_ori == "hetero":
            sql_where.append("d.orientation IN ('hetero', 'bi')")
        elif p_ori == "gay":
            sql_where.append("d.orientation IN ('gay', 'bi')")

        if p_res == "insta":
            sql_where.append("d.instagram IS NOT NULL AND d.instagram != ''")
        elif p_res == "snap":
            sql_where.append("d.snapchat IS NOT NULL AND d.snapchat != ''")

        if p_typ == "prio_only":
            sql_where.append("d.prioritaire = 1")
        elif p_typ == "standard_only":
            sql_where.append("d.prioritaire = 0")

        query = f"""
            SELECT d.*, u.username, u.first_name AS user_first_name
            FROM demandes d
            LEFT JOIN users u ON d.user_id = u.user_id
            WHERE {' AND '.join(sql_where)}
            ORDER BY RAND()
            LIMIT 1
        """

        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur pioche demande aléatoire pour staff à l'essai %s : %s", staff_id, exc)
            return None

    def get_staff_payment_methods(self, staff_id: int) -> Dict[str, bool]:
        uid = int(staff_id)

        if self.is_owner(uid):
            stars = str(self.get_config_value("owner_accept_stars", "true")).lower() in ("true", "1", "yes")
            direct = str(self.get_config_value("owner_accept_direct", "true")).lower() in ("true", "1", "yes")
            return {"accept_stars": stars, "accept_direct": direct}

        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT accept_stars, accept_direct FROM staff WHERE user_id = %s", (uid,))
                row = cursor.fetchone()
                if row:
                    return {
                        "accept_stars": bool(row.get("accept_stars", True)),
                        "accept_direct": bool(row.get("accept_direct", True)),
                    }
        except Exception as exc:
            logger.error("Erreur lecture modes paiement staff %s : %s", uid, exc)

        return {"accept_stars": True, "accept_direct": True}

    def toggle_staff_payment_method(self, staff_id: int, method: str) -> Tuple[bool, str]:
        if method not in ("accept_stars", "accept_direct"):
            return False, "Méthode de paiement invalide."

        uid = int(staff_id)
        current = self.get_staff_payment_methods(uid)
        stars = current["accept_stars"]
        direct = current["accept_direct"]

        if method == "accept_stars":
            new_val = not stars
            if not new_val and not direct:
                return False, "Vous devez conserver au moins un moyen de paiement actif."
        else:
            new_val = not direct
            if not new_val and not stars:
                return False, "Vous devez conserver au moins un moyen de paiement actif."

        if self.is_owner(uid):
            cfg_key = f"owner_{method}"
            val_str = "true" if new_val else "false"
            ok = self.set_config_value(cfg_key, val_str)
            return (True, "Mode de paiement mis à jour.") if ok else (False, "Erreur technique.")

        try:
            with self.transaction() as cursor:
                cursor.execute(f"UPDATE staff SET `{method}` = %s WHERE user_id = %s", (new_val, uid))
            return True, "Mode de paiement mis à jour."
        except Exception as exc:
            logger.error("Erreur modification mode paiement staff %s : %s", uid, exc)
            return False, "Erreur technique."

    def get_staff_permissions(self, user_id: int) -> Dict[str, Any]:
        uid = int(user_id)
        cache_key = f"perm_{uid}"
        cached = self._get_cached_value(cache_key)
        if cached is not None:
            return cached

        default_perms = {
            "perm_reseaux": "all",
            "perm_type": "all",
            "perm_orientation": "all",
            "allow_self_prefs": True,
            "is_trial": False
        }

        if self.is_owner(uid):
            default_perms["perm_reseaux"] = self.get_config_value("owner_perm_reseaux", "all") or "all"
            default_perms["perm_type"] = self.get_config_value("owner_perm_type", "all") or "all"
            default_perms["perm_orientation"] = self.get_config_value("owner_perm_orientation", "all") or "all"
            default_perms["allow_self_prefs"] = True
            default_perms["is_trial"] = False
            self._set_cached_value(cache_key, default_perms)
            return default_perms

        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    "SELECT perm_reseaux, perm_type, perm_orientation, allow_self_prefs, is_trial FROM staff WHERE user_id = %s",
                    (uid,)
                )
                row = cursor.fetchone()
                if row:
                    default_perms["perm_reseaux"] = row.get("perm_reseaux") or "all"
                    default_perms["perm_type"] = row.get("perm_type") or "all"
                    default_perms["perm_orientation"] = row.get("perm_orientation") or "all"
                    default_perms["allow_self_prefs"] = bool(row.get("allow_self_prefs", True))
                    default_perms["is_trial"] = bool(row.get("is_trial"))
                elif self.is_admin(uid):
                    alias = self.get_staff_alias(uid)
                    cursor.execute(
                        """
                        INSERT INTO staff (user_id, alias, perm_reseaux, perm_type, perm_orientation, allow_self_prefs)
                        VALUES (%s, %s, 'all', 'all', 'all', TRUE)
                        ON DUPLICATE KEY UPDATE user_id = user_id
                        """,
                        (uid, alias)
                    )
            self._set_cached_value(cache_key, default_perms)
            return default_perms
        except Exception as exc:
            logger.error("Erreur lecture permissions staff %s : %s", uid, exc)
            return default_perms

    get_admin_permissions = get_staff_permissions

    def update_staff_permission(self, user_id: int, perm_key: str, perm_value: Any) -> bool:
        allowed = {"perm_reseaux", "perm_type", "perm_orientation", "allow_self_prefs", "is_trial"}
        if perm_key not in allowed:
            return False

        uid = int(user_id)
        if self.is_owner(uid):
            ok = self.set_config_value(f"owner_{perm_key}", str(perm_value))
            self.clear_cache(f"perm_{uid}")
            self.clear_cache(f"cfg_owner_{perm_key}")
            self.clear_cache()
            return ok

        try:
            with self.transaction() as cursor:
                cursor.execute(f"UPDATE staff SET `{perm_key}` = %s WHERE user_id = %s", (perm_value, uid))
                if cursor.rowcount == 0:
                    alias = self.get_staff_alias(uid)
                    cursor.execute(
                        """
                        INSERT INTO staff (user_id, alias, `{perm_key}`)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE `{perm_key}` = VALUES(`{perm_key}`)
                        """,
                        (uid, alias, perm_value)
                    )
            self.clear_cache(f"perm_{uid}")
            self.clear_cache(f"staff_trial_{uid}")
            self.clear_cache()
            return True
        except Exception as exc:
            logger.error("Erreur mise à jour permission %s pour staff %s : %s", perm_key, uid, exc)
            return False

    update_admin_permission = update_staff_permission

    def get_staff_demandes_counts(self, user_id: int) -> Dict[str, int]:
        counts = {"dispo": 0, "suivies": 0, "archives": 0}
        uid = int(user_id)
        is_own = self.is_owner(uid)

        try:
            with self.get_cursor() as cursor:
                perm_res = "all"
                perm_type = "all"
                perm_ori = "all"

                if not is_own:
                    cursor.execute("SELECT perm_reseaux, perm_type, perm_orientation FROM staff WHERE user_id = %s", (uid,))
                    perms = cursor.fetchone() or {}
                    perm_res = perms.get("perm_reseaux") or "all"
                    perm_type = perms.get("perm_type") or "all"
                    perm_ori = perms.get("perm_orientation") or "all"
                else:
                    perm_res = self.get_config_value("owner_perm_reseaux", "all")
                    perm_type = self.get_config_value("owner_perm_type", "all")
                    perm_ori = self.get_config_value("owner_perm_orientation", "all")

                dispo_clauses = ["statut = '📥 Reçue'", "admin_en_charge IS NULL", "user_id != %s"]
                dispo_params: List[Any] = [uid]

                if perm_res == "insta":
                    dispo_clauses.append("instagram IS NOT NULL AND instagram != ''")
                elif perm_res == "snap":
                    dispo_clauses.append("snapchat IS NOT NULL AND snapchat != ''")

                if perm_type == "prio_only":
                    dispo_clauses.append("prioritaire = 1")
                elif perm_type == "standard_only":
                    dispo_clauses.append("prioritaire = 0")

                if perm_ori == "hetero":
                    dispo_clauses.append("orientation IN ('hetero', 'bi')")
                elif perm_ori == "gay":
                    dispo_clauses.append("orientation IN ('gay', 'bi')")
                elif perm_ori == "bi":
                    dispo_clauses.append("orientation = 'bi'")

                sql_dispo = f"SELECT COUNT(*) AS total FROM demandes WHERE {' AND '.join(dispo_clauses)}"
                cursor.execute(sql_dispo, tuple(dispo_params))
                r_dispo = cursor.fetchone()
                counts["dispo"] = int(r_dispo["total"]) if r_dispo and r_dispo.get("total") else 0

                cursor.execute("SELECT COUNT(*) AS total FROM demandes WHERE admin_en_charge = %s", (uid,))
                r_suivi = cursor.fetchone()
                counts["suivies"] = int(r_suivi["total"]) if r_suivi and r_suivi.get("total") else 0

                cursor.execute("SELECT COUNT(*) AS total FROM archives WHERE admin_en_charge = %s", (uid,))
                r_arch = cursor.fetchone()
                counts["archives"] = int(r_arch["total"]) if r_arch and r_arch.get("total") else 0

        except Exception as exc:
            logger.error("Erreur calcul compteurs staff pour user %s : %s", user_id, exc, exc_info=True)

        return counts

    def get_staff_active_demandes(self, staff_id: int) -> List[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.request_number, d.orientation, d.prenom, d.nom, d.statut, d.is_difficile, d.reussie_substatus, d.prioritaire, d.paiement_statut
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours', '✅ Réussie')
                    """,
                    (int(staff_id),)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur récupération demandes actives staff %s : %s", staff_id, exc)
            return []

    get_admin_active_demandes = get_staff_active_demandes

    def abandon_staff_demandes_for_pause(self, staff_id: int) -> List[Dict[str, Any]]:
        alias = self.get_staff_alias(staff_id)
        reason = f"Opérateur ({alias}) actuellement en pause."

        try:
            with self.transaction() as cursor:
                cursor.execute(
                    """
                    SELECT d.id, d.user_id, d.request_number, d.prenom
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours')
                    """,
                    (int(staff_id),)
                )
                rows = cursor.fetchall()

                if rows:
                    ids = [r["id"] for r in rows]
                    placeholders = ", ".join(["%s"] * len(ids))

                    cursor.execute(
                        f"""
                        UPDATE demandes
                        SET statut = '❌ Abandonnée',
                            ancien_admin_alias = %s,
                            admin_en_charge = NULL,
                            is_difficile = FALSE,
                            reussie_substatus = NULL,
                            raison_abandon = %s,
                            date_modification = NOW()
                        WHERE id IN ({placeholders})
                        """,
                        (alias, reason, *ids)
                    )
                    cursor.execute(
                        f"""
                        UPDATE demandes_suivi
                        SET statut_suivi = 'abandonnee', derniere_action = NOW()
                        WHERE demande_id IN ({placeholders}) AND admin_id = %s
                        """,
                        (*ids, int(staff_id))
                    )

            return rows
        except Exception as exc:
            logger.error("Erreur abandon des demandes suite pause staff %s : %s", staff_id, exc)
            return []

    abandon_admin_demandes_for_pause = abandon_staff_demandes_for_pause

    def get_admin_stats(self, admin_id: int) -> Dict[str, Any]:
        try:
            admin_id = int(admin_id)
        except (ValueError, TypeError):
            pass

        is_owner = self.is_owner(admin_id)
        stats = {
            "user_id": admin_id,
            "alias": self.get_staff_alias(admin_id),
            "date_added": None,
            "perm_reseaux": "all",
            "perm_type": "all",
            "perm_orientation": "all",
            "is_trial": False,
            "en_cours": 0,
            "reussies": 0,
            "abandonnees": 0,
            "total_traitees": 0,
            "taux_reussite": 0.0,
            "prioritaires_traitees": 0,
            "montant_total": 0.0,
        }

        try:
            with self.get_cursor() as cursor:
                if is_owner:
                    stats["alias"] = self.get_owner_alias()
                    stats["perm_reseaux"] = self.get_config_value("owner_perm_reseaux", "all") or "all"
                    stats["perm_type"] = self.get_config_value("owner_perm_type", "all") or "all"
                    stats["perm_orientation"] = self.get_config_value("owner_perm_orientation", "all") or "all"
                    stats["is_trial"] = False
                else:
                    cursor.execute(
                        "SELECT alias, date_added, perm_reseaux, perm_type, perm_orientation, is_trial FROM staff WHERE user_id = %s",
                        (admin_id,)
                    )
                    staff_row = cursor.fetchone()
                    if staff_row:
                        stats["alias"] = staff_row.get("alias") or stats["alias"]
                        stats["date_added"] = staff_row.get("date_added")
                        stats["perm_reseaux"] = staff_row.get("perm_reseaux") or "all"
                        stats["perm_type"] = staff_row.get("perm_type") or "all"
                        stats["perm_orientation"] = staff_row.get("perm_orientation") or "all"
                        stats["is_trial"] = bool(staff_row.get("is_trial"))

                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s AND d.statut IN ('⏳ En attente', '🔄 En cours')
                    """,
                    (admin_id,)
                )
                r_encours = cursor.fetchone()
                stats["en_cours"] = int(r_encours["total"]) if r_encours and r_encours.get("total") else 0

                cursor.execute(
                    """
                    SELECT
                        SUM(CASE WHEN d.statut = '✅ Réussie' THEN 1 ELSE 0 END) AS reussies,
                        SUM(CASE WHEN d.statut = '❌ Abandonnée' THEN 1 ELSE 0 END) AS abandonnees,
                        SUM(CASE WHEN d.prioritaire = 1 THEN 1 ELSE 0 END) AS nb_prio,
                        COALESCE(SUM(CASE WHEN d.prioritaire = 1 THEN d.montant ELSE 0 END), 0) AS montant_cumule
                    FROM demandes d
                    JOIN demandes_suivi ds ON d.id = ds.demande_id
                    WHERE ds.admin_id = %s
                    """,
                    (admin_id,)
                )
                r_term = cursor.fetchone()
                if r_term:
                    stats["reussies"] = int(r_term.get("reussies") or 0)
                    stats["abandonnees"] = int(r_term.get("abandonnees") or 0)
                    stats["prioritaires_traitees"] = int(r_term.get("nb_prio") or 0)
                    stats["montant_total"] = float(r_term.get("montant_cumule") or 0.0)

                total_fermees = stats["reussies"] + stats["abandonnees"]
                stats["total_traitees"] = total_fermees
                if total_fermees > 0:
                    stats["taux_reussite"] = round((stats["reussies"] / total_fermees) * 100, 1)

            return stats
        except Exception as exc:
            logger.error("Erreur calcul statistiques staff %s : %s", admin_id, exc, exc_info=True)
            return stats