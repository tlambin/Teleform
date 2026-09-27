"""Module d'initialisation des schémas, tables et index MySQL."""

import logging
from mysql.connector import Error

logger = logging.getLogger(__name__)


class SchemaManager:
    """Gère la création des tables et des index d'origine."""

    def create_tables(self):
        """Crée ou met à jour les tables nécessaires."""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS config (
                key_name VARCHAR(64) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(64),
                first_name VARCHAR(64),
                is_vip BOOLEAN DEFAULT FALSE,
                vip_until DATETIME DEFAULT NULL,
                vip_auto_assign VARCHAR(32) DEFAULT 'prompt',
                derniere_activite DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                date_inscription DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_by BIGINT DEFAULT NULL,
                reason TEXT DEFAULT NULL,
                date_ban DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_banned_date (date_ban)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS staff (
                user_id BIGINT PRIMARY KEY,
                alias VARCHAR(64) NOT NULL,
                added_by BIGINT,
                perm_reseaux VARCHAR(16) DEFAULT 'all',
                perm_type VARCHAR(16) DEFAULT 'all',
                perm_orientation VARCHAR(16) DEFAULT 'all',
                alias_locked BOOLEAN DEFAULT FALSE,
                allow_self_prefs BOOLEAN DEFAULT TRUE,
                is_paused BOOLEAN DEFAULT FALSE,
                is_trial BOOLEAN DEFAULT FALSE,
                accept_stars BOOLEAN DEFAULT TRUE,
                accept_direct BOOLEAN DEFAULT TRUE,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                alias VARCHAR(64) NOT NULL,
                is_owner BOOLEAN DEFAULT FALSE,
                is_vip BOOLEAN DEFAULT FALSE,
                is_paused BOOLEAN DEFAULT FALSE,
                can_manage_staff BOOLEAN DEFAULT TRUE,
                can_manage_vips BOOLEAN DEFAULT TRUE,
                can_view_stats BOOLEAN DEFAULT TRUE,
                can_manage_delais BOOLEAN DEFAULT FALSE,
                can_view_archives BOOLEAN DEFAULT FALSE,
                can_monitor_staff BOOLEAN DEFAULT FALSE,
                can_ban_users BOOLEAN DEFAULT FALSE,
                can_edit_others_demandes BOOLEAN DEFAULT FALSE,
                added_by BIGINT DEFAULT NULL,
                date_added DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS demandes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                orientation VARCHAR(16) DEFAULT 'hetero',
                prenom VARCHAR(64) NOT NULL,
                nom VARCHAR(64),
                age INT,
                localisation VARCHAR(128),
                photo_id VARCHAR(256),
                instagram VARCHAR(64),
                snapchat VARCHAR(64),
                details TEXT,
                prioritaire BOOLEAN DEFAULT FALSE,
                montant DECIMAL(10, 2) DEFAULT 0.00,
                statut VARCHAR(32) DEFAULT '📥 Reçue',
                is_difficile BOOLEAN NOT NULL DEFAULT FALSE,
                reussie_substatus VARCHAR(20) DEFAULT NULL,
                paiement_statut VARCHAR(20) DEFAULT 'non_requis',
                has_delivered_content BOOLEAN NOT NULL DEFAULT FALSE,
                date_livraison DATETIME DEFAULT NULL,
                last_delivery_reminder DATETIME DEFAULT NULL,
                last_payment_delivery_reminder DATETIME DEFAULT NULL,
                last_payment_reminder DATETIME DEFAULT NULL,
                admin_en_charge BIGINT DEFAULT NULL,
                ancien_admin_alias VARCHAR(64) DEFAULT NULL,
                raison_abandon TEXT DEFAULT NULL,
                last_vip_reminder DATETIME DEFAULT NULL,
                proposed_price DECIMAL(10, 2) DEFAULT NULL,
                proposed_by BIGINT DEFAULT NULL,
                remun_asked_at DATETIME DEFAULT NULL,
                date_creation DATETIME DEFAULT CURRENT_TIMESTAMP,
                date_modification DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                request_number INT DEFAULT NULL,
                INDEX idx_user (user_id),
                INDEX idx_statut (statut),
                INDEX idx_orientation (orientation),
                INDEX idx_insta (instagram),
                INDEX idx_snap (snapchat)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS demandes_suivi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                demande_id INT NOT NULL,
                admin_id BIGINT NOT NULL,
                date_suivi DATETIME DEFAULT CURRENT_TIMESTAMP,
                derniere_action DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                statut_suivi VARCHAR(32) DEFAULT 'active',
                UNIQUE KEY unique_demande_admin (demande_id, admin_id),
                INDEX idx_admin (admin_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS archives (
                id INT AUTO_INCREMENT PRIMARY KEY,
                original_id INT NOT NULL,
                user_id BIGINT NOT NULL,
                admin_en_charge BIGINT DEFAULT NULL,
                orientation VARCHAR(16) DEFAULT 'hetero',
                prenom VARCHAR(64),
                nom VARCHAR(64),
                age INT,
                localisation VARCHAR(128),
                photo_id VARCHAR(256),
                instagram VARCHAR(64),
                snapchat VARCHAR(64),
                details TEXT,
                prioritaire BOOLEAN DEFAULT FALSE,
                montant DECIMAL(10, 2) DEFAULT 0.00,
                statut VARCHAR(32),
                is_difficile BOOLEAN NOT NULL DEFAULT FALSE,
                reussie_substatus VARCHAR(20) DEFAULT NULL,
                paiement_statut VARCHAR(20) DEFAULT 'non_requis',
                has_delivered_content BOOLEAN NOT NULL DEFAULT FALSE,
                date_livraison DATETIME DEFAULT NULL,
                date_creation DATETIME,
                date_archivage DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_archive_user (user_id),
                INDEX idx_archive_admin (admin_en_charge),
                INDEX idx_archive_orientation (orientation),
                INDEX idx_archive_date (date_archivage)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_preferences (
                user_id BIGINT PRIMARY KEY,
                notif_new_mode VARCHAR(16) DEFAULT 'sound',
                rappel_mode VARCHAR(16) DEFAULT 'sound',
                rappel_freq VARCHAR(16) DEFAULT 'daily',
                rappel_heure INT DEFAULT 18,
                rappel_jour_semaine INT DEFAULT 6,
                rappel_jour_mois INT DEFAULT 1,
                last_rappel_date DATE DEFAULT NULL,
                monitor_prise_en_charge BOOLEAN DEFAULT TRUE,
                monitor_changement_statut BOOLEAN DEFAULT TRUE,
                monitor_abandon BOOLEAN DEFAULT TRUE,
                monitor_reussite BOOLEAN DEFAULT TRUE,
                monitor_staff_msg BOOLEAN DEFAULT TRUE,
                monitor_user_msg BOOLEAN DEFAULT TRUE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """,
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id BIGINT PRIMARY KEY,
                notif_status_mode VARCHAR(16) DEFAULT 'sound',
                notif_prise_en_charge VARCHAR(16) DEFAULT 'sound',
                notif_messages VARCHAR(16) DEFAULT 'sound'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
        ]

        expected_columns = [
            ("staff", "perm_reseaux", "VARCHAR(16) DEFAULT 'all'"),
            ("staff", "perm_type", "VARCHAR(16) DEFAULT 'all'"),
            ("staff", "perm_orientation", "VARCHAR(16) DEFAULT 'all'"),
            ("staff", "alias_locked", "BOOLEAN DEFAULT FALSE"),
            ("staff", "allow_self_prefs", "BOOLEAN DEFAULT TRUE"),
            ("staff", "is_paused", "BOOLEAN DEFAULT FALSE"),
            ("staff", "is_trial", "BOOLEAN DEFAULT FALSE"),
            ("staff", "accept_stars", "BOOLEAN DEFAULT TRUE"),
            ("staff", "accept_direct", "BOOLEAN DEFAULT TRUE"),
            ("admins", "is_owner", "BOOLEAN DEFAULT FALSE"),
            ("admins", "is_vip", "BOOLEAN DEFAULT FALSE"),
            ("admins", "is_paused", "BOOLEAN DEFAULT FALSE"),
            ("admins", "can_manage_staff", "BOOLEAN DEFAULT TRUE"),
            ("admins", "can_manage_vips", "BOOLEAN DEFAULT TRUE"),
            ("admins", "can_view_stats", "BOOLEAN DEFAULT TRUE"),
            ("admins", "can_manage_delais", "BOOLEAN DEFAULT FALSE"),
            ("admins", "can_view_archives", "BOOLEAN DEFAULT FALSE"),
            ("admins", "can_monitor_staff", "BOOLEAN DEFAULT FALSE"),
            ("admins", "can_ban_users", "BOOLEAN DEFAULT FALSE"),
            ("admins", "can_edit_others_demandes", "BOOLEAN DEFAULT FALSE"),
            ("demandes", "orientation", "VARCHAR(16) DEFAULT 'hetero'"),
            ("demandes", "is_difficile", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("demandes", "reussie_substatus", "VARCHAR(20) DEFAULT NULL"),
            ("demandes", "paiement_statut", "VARCHAR(20) DEFAULT 'non_requis'"),
            ("demandes", "has_delivered_content", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("demandes", "date_livraison", "DATETIME DEFAULT NULL"),
            ("demandes", "last_delivery_reminder", "DATETIME DEFAULT NULL"),
            ("demandes", "last_payment_delivery_reminder", "DATETIME DEFAULT NULL"),
            ("demandes", "last_payment_reminder", "DATETIME DEFAULT NULL"),
            ("demandes", "admin_en_charge", "BIGINT DEFAULT NULL"),
            ("demandes", "ancien_admin_alias", "VARCHAR(64) DEFAULT NULL"),
            ("demandes", "raison_abandon", "TEXT DEFAULT NULL"),
            ("demandes", "request_number", "INT DEFAULT NULL"),
            ("demandes", "date_modification", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            ("demandes", "last_vip_reminder", "DATETIME DEFAULT NULL"),
            ("demandes", "proposed_price", "DECIMAL(10, 2) DEFAULT NULL"),
            ("demandes", "proposed_by", "BIGINT DEFAULT NULL"),
            ("demandes", "remun_asked_at", "DATETIME DEFAULT NULL"),
            ("archives", "admin_en_charge", "BIGINT DEFAULT NULL"),
            ("archives", "orientation", "VARCHAR(16) DEFAULT 'hetero'"),
            ("archives", "is_difficile", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("archives", "reussie_substatus", "VARCHAR(20) DEFAULT NULL"),
            ("archives", "paiement_statut", "VARCHAR(20) DEFAULT 'non_requis'"),
            ("archives", "has_delivered_content", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ("archives", "date_livraison", "DATETIME DEFAULT NULL"),
            ("admin_preferences", "notif_new_mode", "VARCHAR(16) DEFAULT 'sound'"),
            ("admin_preferences", "rappel_mode", "VARCHAR(16) DEFAULT 'sound'"),
            ("admin_preferences", "rappel_freq", "VARCHAR(16) DEFAULT 'daily'"),
            ("admin_preferences", "rappel_heure", "INT DEFAULT 18"),
            ("admin_preferences", "rappel_jour_semaine", "INT DEFAULT 6"),
            ("admin_preferences", "rappel_jour_mois", "INT DEFAULT 1"),
            ("admin_preferences", "last_rappel_date", "DATE DEFAULT NULL"),
            ("admin_preferences", "monitor_prise_en_charge", "BOOLEAN DEFAULT TRUE"),
            ("admin_preferences", "monitor_changement_statut", "BOOLEAN DEFAULT TRUE"),
            ("admin_preferences", "monitor_abandon", "BOOLEAN DEFAULT TRUE"),
            ("admin_preferences", "monitor_reussite", "BOOLEAN DEFAULT TRUE"),
            ("admin_preferences", "monitor_staff_msg", "BOOLEAN DEFAULT TRUE"),
            ("admin_preferences", "monitor_user_msg", "BOOLEAN DEFAULT TRUE"),
            ("users", "is_vip", "BOOLEAN DEFAULT FALSE"),
            ("users", "vip_until", "DATETIME DEFAULT NULL"),
            ("users", "vip_auto_assign", "VARCHAR(32) DEFAULT 'prompt'"),
            ("user_preferences", "notif_status_mode", "VARCHAR(16) DEFAULT 'sound'"),
            ("user_preferences", "notif_prise_en_charge", "VARCHAR(16) DEFAULT 'sound'"),
            ("user_preferences", "notif_messages", "VARCHAR(16) DEFAULT 'sound'"),
        ]

        expected_indexes = [
            ("demandes", "idx_demandes_dispo_routing", "CREATE INDEX idx_demandes_dispo_routing ON demandes (statut, admin_en_charge, orientation, prioritaire, date_creation)"),
            ("demandes", "idx_demandes_staff_suivi", "CREATE INDEX idx_demandes_staff_suivi ON demandes (admin_en_charge, prioritaire, date_modification)"),
            ("demandes", "idx_demandes_user_statut", "CREATE INDEX idx_demandes_user_statut ON demandes (user_id, statut, id)"),
            ("demandes", "idx_demandes_dedup_insta", "CREATE INDEX idx_demandes_dedup_insta ON demandes (instagram, statut)"),
            ("demandes", "idx_demandes_dedup_snap", "CREATE INDEX idx_demandes_dedup_snap ON demandes (snapchat, statut)"),
            ("demandes", "idx_demandes_auto_archive", "CREATE INDEX idx_demandes_auto_archive ON demandes (statut, reussie_substatus, has_delivered_content, date_livraison)"),
            ("demandes_suivi", "idx_suivi_admin_action", "CREATE INDEX idx_suivi_admin_action ON demandes_suivi (admin_id, statut_suivi, date_suivi)"),
            ("archives", "idx_archives_user_date", "CREATE INDEX idx_archives_user_date ON archives (user_id, date_archivage)"),
            ("archives", "idx_archives_staff_date", "CREATE INDEX idx_archives_staff_date ON archives (admin_en_charge, date_archivage)"),
            ("users", "idx_users_cleanup_activite", "CREATE INDEX idx_users_cleanup_activite ON users (derniere_activite, date_inscription)"),
        ]

        try:
            with self.get_cursor() as cursor:
                for query in tables:
                    cursor.execute(query)

                for table, col, col_def in expected_columns:
                    try:
                        cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
                        if not cursor.fetchone():
                            cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {col_def}")
                            logger.info("Auto-migration : colonne ajoutée -> %s.%s", table, col)
                    except Error as e:
                        if getattr(e, "errno", None) != 1060:
                            logger.debug("Info colonne %s.%s : %s", table, col, e)

                for table, idx_name, create_sql in expected_indexes:
                    try:
                        cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", (idx_name,))
                        if not cursor.fetchone():
                            cursor.execute(create_sql)
                            logger.info("Index créé : %s sur `%s`", idx_name, table)
                    except Exception as idx_err:
                        logger.debug("Vérification index %s sur `%s` : %s", idx_name, table, idx_err)

                k_col, v_col = self._get_config_columns()
                default_configs = [
                    ('bot_active', 'true'),
                    ('maintenance_mode', 'false'),
                    ('demandes_enabled', 'true'),
                    ('max_total_demandes', '0'),
                    ('max_demandes_per_user', '3'),
                    ('auto_archive_hours', '72'),
                    ('delivery_reminder_days', '7'),
                    ('payment_reminder_days', '7'),
                    ('remun_expiration_days', '7'),
                    ('allow_hetero_insta', 'true'),
                    ('allow_hetero_snap', 'true'),
                    ('allow_gay_insta', 'true'),
                    ('allow_gay_snap', 'true'),
                    ('max_hetero_insta', '0'),
                    ('max_hetero_snap', '0'),
                    ('max_gay_insta', '0'),
                    ('max_gay_snap', '0'),
                    ('required_group_enabled', 'false'),
                    ('required_group_id', '0'),
                    ('group_subscription_link', '@parascriptionbot'),
                    ('support_contact', '@ContactParaBot'),
                    ('owner_is_paused', 'false'),
                    ('owner_perm_reseaux', 'all'),
                    ('owner_perm_type', 'all'),
                    ('owner_perm_orientation', 'all'),
                ]
                for k, v in default_configs:
                    cursor.execute(
                        f"""
                        INSERT INTO config ({k_col}, {v_col})
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE {k_col} = {k_col}
                        """,
                        (k, v)
                    )

                owner_id = getattr(self.config, "OWNER_ID", 0) or int(self.get_config_value("owner_id", "0"))
                if owner_id:
                    owner_alias = self.get_config_value("owner_alias", "Propriétaire")
                    cursor.execute(
                        """
                        INSERT INTO admins (
                            user_id, alias, is_owner, is_vip, can_manage_staff, can_manage_vips, 
                            can_view_stats, can_manage_delais, can_view_archives, can_monitor_staff, 
                            can_ban_users, can_edit_others_demandes
                        ) VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE)
                        ON DUPLICATE KEY UPDATE 
                            is_owner = TRUE, is_vip = TRUE, can_manage_staff = TRUE, can_manage_vips = TRUE, 
                            can_view_stats = TRUE, can_manage_delais = TRUE, can_view_archives = TRUE, 
                            can_monitor_staff = TRUE, can_ban_users = TRUE, can_edit_others_demandes = TRUE
                        """,
                        (owner_id, owner_alias)
                    )

            logger.info("Vérification et création des tables terminées avec succès.")
        except Exception as exc:
            logger.error("Erreur lors de la création des tables : %s", exc)
            raise

    # Alias pour compatibilité
    init_db = create_tables