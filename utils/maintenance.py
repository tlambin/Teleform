import os
import logging
import subprocess

logger = logging.getLogger(__name__)

def cleanup_temp_files():
    """Nettoie les fichiers temporaires"""
    try:
        # Nettoyer les logs anciens (garder seulement les 1000 dernières lignes)
        log_files = ['/tmp/bot.log', '/tmp/bot_console.log', '/tmp/maintenance_task.log']
        for log_file in log_files:
            if os.path.exists(log_file):
                # Garder seulement les 1000 dernières lignes
                os.system(f"tail -n 1000 {log_file} > {log_file}.tmp && mv {log_file}.tmp {log_file}")

        # Nettoyer les fichiers Python compilés
        cleanup_commands = [
            "find /home/paraworld -name '*.pyc' -delete 2>/dev/null || true",
            "find /home/paraworld -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true",
            "find /tmp -name 'core.*' -delete 2>/dev/null || true"
        ]

        for cmd in cleanup_commands:
            subprocess.run(cmd, shell=True, capture_output=True)

        logger.info("🧹 Nettoyage des fichiers temporaires terminé")

    except Exception as e:
        logger.error(f"Erreur nettoyage fichiers temporaires: {e}")

def archive_old_requests(db_manager):
    """Archive les demandes anciennes"""
    try:
        with db_manager.get_cursor() as cursor:
            # Archiver les demandes terminées de plus de 7 jours
            archive_query = """
                INSERT INTO archives (
                    original_id, user_id, prenom, nom, age, localisation,
                    photo_id, instagram, snapchat, details, prioritaire,
                    montant, statut, date_creation
                )
                SELECT id, user_id, prenom, nom, age, localisation,
                       photo_id, instagram, snapchat, details, prioritaire,
                       montant, statut, date_creation
                FROM demandes
                WHERE date_creation < DATE_SUB(NOW(), INTERVAL 7 DAY)
                AND statut IN ('✅ Réussie', '❌ Abandonnée')
            """
            cursor.execute(archive_query)
            archived_count = cursor.rowcount

            # Supprimer les demandes archivées
            if archived_count > 0:
                delete_query = """
                    DELETE FROM demandes
                    WHERE date_creation < DATE_SUB(NOW(), INTERVAL 7 DAY)
                    AND statut IN ('✅ Réussie', '❌ Abandonnée')
                """
                cursor.execute(delete_query)
                logger.info(f"📦 {archived_count} demandes archivées et supprimées")
            else:
                logger.info("📦 Aucune demande à archiver")

    except Exception as e:
        logger.error(f"Erreur archivage automatique: {e}")

def check_storage_usage():
    """Vérifie l'usage du stockage et retourne l'usage en MB"""
    try:
        # Vérifier l'espace disque utilisé dans le répertoire home
        result = subprocess.run(['du', '-sb', os.path.expanduser('~')],
                              capture_output=True, text=True)

        if result.returncode == 0:
            bytes_used = int(result.stdout.split()[0])
            mb_used = bytes_used / (1024 * 1024)

            # Alerte si plus de 400MB utilisés (sur 512MB disponibles)
            if mb_used > 400:
                logger.warning(f"⚠️ Usage stockage élevé: {mb_used:.1f}MB / 512MB")
                cleanup_temp_files()

            logger.info(f"💾 Usage stockage: {mb_used:.1f}MB / 512MB ({(mb_used/512)*100:.1f}%)")
            return mb_used
        else:
            logger.error(f"Erreur vérification stockage: {result.stderr}")
            return 0

    except Exception as e:
        logger.error(f"Erreur vérification stockage: {e}")
        return 0

def optimize_database(db_manager):
    """Optimise les tables de la base de données"""
    try:
        with db_manager.get_cursor() as cursor:
            # Optimiser les tables
            tables = ['demandes', 'archives', 'users', 'demandes_status']
            for table in tables:
                try:
                    cursor.execute(f"OPTIMIZE TABLE {table}")
                    logger.info(f"✅ Table {table} optimisée")
                except Exception as e:
                    logger.warning(f"⚠️ Impossible d'optimiser {table}: {e}")

            # Nettoyer le cache de l'application
            db_manager.clear_cache()

            logger.info("🔧 Optimisation DB terminée")

    except Exception as e:
        logger.error(f"Erreur optimisation DB: {e}")

def cleanup_database(db_manager):
    """Nettoie les données anciennes de la base de données"""
    try:
        with db_manager.get_cursor() as cursor:
            # Nettoyer les archives très anciennes (plus de 3 mois)
            cursor.execute("""
                DELETE FROM archives
                WHERE date_archivage < DATE_SUB(NOW(), INTERVAL 3 MONTH)
            """)
            old_archives_deleted = cursor.rowcount

            if old_archives_deleted > 0:
                logger.info(f"🗑️ {old_archives_deleted} archives anciennes supprimées")

            # Nettoyer les utilisateurs inactifs (plus de 6 mois sans activité)
            cursor.execute("""
                DELETE u FROM users u
                LEFT JOIN demandes d ON u.user_id = d.user_id
                WHERE u.derniere_activite < DATE_SUB(NOW(), INTERVAL 6 MONTH)
                AND d.user_id IS NULL
            """)
            inactive_users_deleted = cursor.rowcount

            if inactive_users_deleted > 0:
                logger.info(f"👥 {inactive_users_deleted} utilisateurs inactifs supprimés")

    except Exception as e:
        logger.error(f"Erreur nettoyage base de données: {e}")

def get_system_stats(db_manager):
    """Récupère les statistiques système"""
    try:
        stats = {}

        # Usage disque
        storage_mb = check_storage_usage()
        stats['storage_mb'] = storage_mb
        stats['storage_percent'] = (storage_mb / 512) * 100

        # Nombre de fichiers dans /tmp
        tmp_files = len([f for f in os.listdir('/tmp') if os.path.isfile(os.path.join('/tmp', f))])
        stats['tmp_files'] = tmp_files

        # Taille des logs
        log_files = ['/tmp/bot.log', '/tmp/bot_console.log', '/tmp/maintenance_task.log']
        total_log_size = 0
        for log_file in log_files:
            if os.path.exists(log_file):
                total_log_size += os.path.getsize(log_file)
        stats['logs_mb'] = total_log_size / (1024 * 1024)

        # Statistiques DB
        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM demandes")
            stats['demandes_count'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM archives")
            stats['archives_count'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM users")
            stats['users_count'] = cursor.fetchone()['count']

        return stats

    except Exception as e:
        logger.error(f"Erreur récupération statistiques: {e}")
        return {}

def emergency_cleanup():
    """Nettoyage d'urgence si l'espace disque est critique"""
    try:
        logger.warning("🚨 Nettoyage d'urgence activé")

        # Supprimer tous les fichiers temporaires
        subprocess.run("rm -rf /tmp/*.log.* 2>/dev/null || true", shell=True)
        subprocess.run("find /tmp -name '*.tmp' -delete 2>/dev/null || true", shell=True)

        # Tronquer les logs à 100 lignes
        log_files = ['/tmp/bot.log', '/tmp/bot_console.log', '/tmp/maintenance_task.log']
        for log_file in log_files:
            if os.path.exists(log_file):
                os.system(f"tail -n 100 {log_file} > {log_file}.tmp && mv {log_file}.tmp {log_file}")

        # Nettoyage agressif de la DB
        cleanup_database()

        logger.info("🚨 Nettoyage d'urgence terminé")

    except Exception as e:
        logger.error(f"Erreur nettoyage d'urgence: {e}")

def daily_maintenance(db_manager):
    """Maintenance quotidienne complète"""
    logger.info("🔧 === Début maintenance quotidienne ===")

    try:
        # Vérifier l'usage du stockage
        storage_mb = check_storage_usage()

        # Si l'usage est critique (>90%), nettoyage d'urgence
        if storage_mb > 460:  # 90% de 512MB
            emergency_cleanup()
        else:
            # Maintenance normale
            cleanup_temp_files()
            archive_old_requests(db_manager)
            cleanup_database(db_manager)
            optimize_database(db_manager)

        # Statistiques finales
        final_stats = get_system_stats(db_manager)

        logger.info("📊 === Statistiques finales ===")
        logger.info(f"💾 Stockage: {final_stats.get('storage_mb', 0):.1f}MB ({final_stats.get('storage_percent', 0):.1f}%)")
        logger.info(f"📝 Demandes: {final_stats.get('demandes_count', 0)}")
        logger.info(f"📦 Archives: {final_stats.get('archives_count', 0)}")
        logger.info(f"👥 Utilisateurs: {final_stats.get('users_count', 0)}")
        logger.info(f"📄 Logs: {final_stats.get('logs_mb', 0):.1f}MB")
        logger.info(f"🗂️ Fichiers tmp: {final_stats.get('tmp_files', 0)}")

        logger.info("✅ === Maintenance quotidienne terminée ===")

    except Exception as e:
        logger.error(f"❌ Erreur lors de la maintenance: {e}")

if __name__ == "__main__":
    daily_maintenance()