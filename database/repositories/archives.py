"""Dépôt de gestion des archives, auto-archivage et désarchivage."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ArchiveRepository:
    """Méthodes de gestion de la table archives."""

    def archiver_demande_reussie(self, demande_id: int) -> bool:
        try:
            with self.transaction() as cursor:
                cursor.execute("SELECT * FROM demandes WHERE id = %s", (int(demande_id),))
                demande = cursor.fetchone()
                if not demande:
                    return False

                cursor.execute(
                    """
                    INSERT INTO archives (
                        original_id, user_id, admin_en_charge, orientation, prenom, nom, age, localisation,
                        photo_id, instagram, snapchat, details, prioritaire,
                        montant, statut, is_difficile, reussie_substatus, paiement_statut,
                        has_delivered_content, date_livraison, date_creation, date_archivage
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    """,
                    (
                        demande["id"],
                        demande["user_id"],
                        demande.get("admin_en_charge"),
                        demande.get("orientation", "hetero"),
                        demande.get("prenom"),
                        demande.get("nom"),
                        demande.get("age"),
                        demande.get("localisation"),
                        demande.get("photo_id"),
                        demande.get("instagram"),
                        demande.get("snapchat"),
                        demande.get("details"),
                        demande.get("prioritaire", False),
                        demande.get("montant", 0.0),
                        demande.get("statut"),
                        demande.get("is_difficile", False),
                        demande.get("reussie_substatus"),
                        demande.get("paiement_statut", "non_requis"),
                        demande.get("has_delivered_content", False),
                        demande.get("date_livraison"),
                        demande.get("date_creation")
                    )
                )

                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (int(demande_id),))
                cursor.execute("DELETE FROM demandes WHERE id = %s", (int(demande_id),))
                return True
        except Exception as exc:
            logger.error("Erreur archivage demande réussie %s : %s", demande_id, exc)
            return False

    def archiver_demande_annulee(self, demande_id: int, raison: str, archive_par_user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        clean_raison = str(raison or "Non précisée").strip()
        try:
            with self.transaction() as cursor:
                cursor.execute("SELECT * FROM demandes WHERE id = %s", (int(demande_id),))
                demande = cursor.fetchone()
                if not demande:
                    return None

                details_existant = demande.get("details") or ""
                details_notes = f"{details_existant}\n[Motif annulation : {clean_raison}]".strip()

                cursor.execute(
                    """
                    INSERT INTO archives (
                        original_id, user_id, admin_en_charge, orientation, prenom, nom, age, localisation,
                        photo_id, instagram, snapchat, details, prioritaire,
                        montant, statut, is_difficile, reussie_substatus, paiement_statut,
                        has_delivered_content, date_livraison, date_creation, date_archivage
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    """,
                    (
                        demande["id"],
                        demande["user_id"],
                        demande.get("admin_en_charge"),
                        demande.get("orientation", "hetero"),
                        demande.get("prenom"),
                        demande.get("nom"),
                        demande.get("age"),
                        demande.get("localisation"),
                        demande.get("photo_id"),
                        demande.get("instagram"),
                        demande.get("snapchat"),
                        details_notes,
                        demande.get("prioritaire", False),
                        demande.get("montant", 0.0),
                        "❌ Annulée",
                        False,
                        None,
                        demande.get("paiement_statut", "non_requis"),
                        False,
                        None,
                        demande.get("date_creation"),
                    )
                )

                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (int(demande_id),))
                cursor.execute("DELETE FROM demandes WHERE id = %s", (int(demande_id),))
                return demande
        except Exception as exc:
            logger.error("Erreur archivage annulation demande %s : %s", demande_id, exc)
            return None

    def archiver_demande_supprimee(self, demande_id: int, raison: str = "Suppression du dossier") -> Optional[Dict[str, Any]]:
        clean_raison = str(raison or "Non précisée").strip()
        try:
            with self.transaction() as cursor:
                cursor.execute("SELECT * FROM demandes WHERE id = %s", (int(demande_id),))
                demande = cursor.fetchone()
                if not demande:
                    return None

                details_existant = demande.get("details") or ""
                details_notes = f"{details_existant}\n[Motif suppression : {clean_raison}]".strip()

                cursor.execute(
                    """
                    INSERT INTO archives (
                        original_id, user_id, admin_en_charge, orientation, prenom, nom, age, localisation,
                        photo_id, instagram, snapchat, details, prioritaire,
                        montant, statut, is_difficile, reussie_substatus, paiement_statut,
                        has_delivered_content, date_livraison, date_creation, date_archivage
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                    """,
                    (
                        demande["id"],
                        demande["user_id"],
                        demande.get("admin_en_charge"),
                        demande.get("orientation", "hetero"),
                        demande.get("prenom"),
                        demande.get("nom"),
                        demande.get("age"),
                        demande.get("localisation"),
                        demande.get("photo_id"),
                        demande.get("instagram"),
                        demande.get("snapchat"),
                        details_notes,
                        demande.get("prioritaire", False),
                        demande.get("montant", 0.0),
                        "🗑️ Supprimée",
                        False,
                        None,
                        demande.get("paiement_statut", "non_requis"),
                        False,
                        None,
                        demande.get("date_creation"),
                    )
                )

                cursor.execute("DELETE FROM demandes_suivi WHERE demande_id = %s", (int(demande_id),))
                cursor.execute("DELETE FROM demandes WHERE id = %s", (int(demande_id),))
                return demande
        except Exception as exc:
            logger.error("Erreur archivage suppression demande %s : %s", demande_id, exc)
            return None

    def desarchiver_demande_abandonnee(self, archive_id: int, operator_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        try:
            with self.transaction() as cursor:
                cursor.execute("SELECT * FROM archives WHERE id = %s FOR UPDATE", (int(archive_id),))
                arch = cursor.fetchone()
                if not arch:
                    return False, "Archive introuvable.", None

                orig_id = arch.get("original_id")
                insta = arch.get("instagram")
                snap = arch.get("snapchat")

                active_statuses = ("📥 Reçue", "🎯 Assignée (VIP)", "⏳ En attente", "🔄 En cours", "✅ Réussie")
                placeholders = ", ".join(["%s"] * len(active_statuses))

                check_clauses = ["statut IN (" + placeholders + ")"]
                check_params = list(active_statuses)
                sub_or = []

                if orig_id:
                    sub_or.append("id = %s")
                    check_params.append(orig_id)
                if insta:
                    clean_insta = insta.strip().lstrip("@")
                    sub_or.append("instagram = %s")
                    check_params.append(clean_insta)
                if snap:
                    clean_snap = snap.strip()
                    sub_or.append("snapchat = %s")
                    check_params.append(clean_snap)

                if sub_or:
                    check_sql = f"SELECT id, request_number, admin_en_charge FROM demandes WHERE {' AND '.join(check_clauses)} AND ({' OR '.join(sub_or)}) LIMIT 1"
                    cursor.execute(check_sql, tuple(check_params))
                    existing = cursor.fetchone()

                    if existing:
                        admin_id = existing.get("admin_en_charge")
                        if admin_id:
                            alias_charge = self.get_staff_alias(admin_id)
                            return False, f"Impossible de désarchiver : ce dossier est déjà actif et pris en charge par {alias_charge} (Dossier #{existing.get('request_number') or existing['id']}).", None
                        else:
                            return False, f"Ce dossier existe déjà dans les demandes disponibles (#{existing.get('request_number') or existing['id']}).", None

                req_num = orig_id or arch["id"]
                prio = bool(arch.get("prioritaire", False))
                montant = float(arch.get("montant") or 0.0)

                cursor.execute(
                    """
                    INSERT INTO demandes (
                        request_number, user_id, orientation, prenom, nom, age, localisation,
                        photo_id, instagram, snapchat, details, prioritaire, montant,
                        statut, is_difficile, reussie_substatus, paiement_statut,
                        has_delivered_content, date_livraison, admin_en_charge,
                        date_creation, date_modification
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        '⏳ En attente', FALSE, NULL, %s,
                        FALSE, NULL, %s,
                        %s, NOW()
                    )
                    """,
                    (
                        req_num,
                        arch["user_id"],
                        arch.get("orientation", "hetero"),
                        arch.get("prenom"),
                        arch.get("nom"),
                        arch.get("age"),
                        arch.get("localisation"),
                        arch.get("photo_id"),
                        arch.get("instagram"),
                        arch.get("snapchat"),
                        arch.get("details"),
                        prio,
                        montant,
                        arch.get("paiement_statut", "non_requis"),
                        int(operator_id),
                        arch.get("date_creation") or datetime.now(),
                    )
                )
                nouvelle_demande_id = cursor.lastrowid

                cursor.execute(
                    """
                    UPDATE demandes_suivi
                    SET admin_id = %s, derniere_action = NOW(), statut_suivi = 'active'
                    WHERE demande_id = %s
                    """,
                    (int(operator_id), int(nouvelle_demande_id))
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO demandes_suivi (demande_id, admin_id, date_suivi, derniere_action, statut_suivi)
                        VALUES (%s, %s, NOW(), NOW(), 'active')
                        """,
                        (int(nouvelle_demande_id), int(operator_id))
                    )

                cursor.execute("DELETE FROM archives WHERE id = %s", (int(archive_id),))

                arch["new_demande_id"] = nouvelle_demande_id
                logger.info("Archive abandonnée #%s désarchivée et assignée à l'opérateur %s (nouvelle demande #%s).", archive_id, operator_id, nouvelle_demande_id)
                return True, "Dossier restauré avec succès !", arch

        except Exception as exc:
            logger.error("Erreur lors du désarchivage de l'archive abandonnée %s : %s", archive_id, exc, exc_info=True)
            return False, "Erreur technique lors du désarchivage.", None

    def get_expired_delivered_demandes(self, hours: Optional[int] = None) -> List[Dict[str, Any]]:
        effective_hours = hours if hours is not None else self.get_auto_archive_hours()
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, request_number, prenom
                    FROM demandes
                    WHERE statut = '✅ Réussie'
                      AND reussie_substatus = 'terminee'
                      AND has_delivered_content = TRUE
                      AND date_livraison IS NOT NULL
                      AND TIMESTAMPDIFF(HOUR, date_livraison, NOW()) >= %s
                    """,
                    (effective_hours,)
                )
                return cursor.fetchall()
        except Exception as exc:
            logger.error("Erreur extraction demandes prêtes pour auto-archivage : %s", exc)
            return []

    def get_archives_count(
        self,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        filter_status: Optional[str] = None,
        orientation: Optional[str] = None
    ) -> int:
        query = "SELECT COUNT(*) AS total FROM archives WHERE 1=1"
        params = []

        if user_id is not None:
            query += " AND user_id = %s"
            params.append(int(user_id))

        if admin_id is not None:
            query += " AND admin_en_charge = %s"
            params.append(int(admin_id))

        if filter_status:
            query += " AND statut LIKE %s"
            params.append(f"%{filter_status}%")

        if orientation:
            query += " AND orientation = %s"
            params.append(orientation)

        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return int(row["total"]) if row and row.get("total") else 0
        except Exception as exc:
            logger.error("Erreur comptage archives (user=%s, admin=%s) : %s", user_id, admin_id, exc)
            return 0

    def get_archives_page(
        self,
        page: int = 0,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        filter_status: Optional[str] = None,
        orientation: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, original_id, user_id, admin_en_charge, orientation, prenom, nom, age, localisation,
                   photo_id, instagram, snapchat, details, prioritaire,
                   montant, statut, is_difficile, reussie_substatus, paiement_statut,
                   has_delivered_content, date_livraison, date_creation, date_archivage
            FROM archives
            WHERE 1=1
        """
        params = []

        if user_id is not None:
            query += " AND user_id = %s"
            params.append(int(user_id))

        if admin_id is not None:
            query += " AND admin_en_charge = %s"
            params.append(int(admin_id))

        if filter_status:
            query += " AND statut LIKE %s"
            params.append(f"%{filter_status}%")

        if orientation:
            query += " AND orientation = %s"
            params.append(orientation)

        query += " ORDER BY date_archivage DESC, id DESC LIMIT 1 OFFSET %s"
        params.append(max(0, int(page)))

        try:
            with self.get_cursor() as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur récupération page archive (page=%s, user=%s, admin=%s) : %s", page, user_id, admin_id, exc)
            return None

    def get_archive_by_id(self, archive_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT * FROM archives WHERE id = %s", (int(archive_id),))
                return cursor.fetchone()
        except Exception as exc:
            logger.error("Erreur récupération archive id %s : %s", archive_id, exc)
            return None