"""Gestion compte utilisateur selon réinitialisation_du_système [source 4]"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class CompteManager:
    """Gestionnaire compte - Premier module migration selon [source 4]"""

    def __init__(self, db_manager, config):
        """Initialisation propre selon nouveau départ [source 4]"""
        self.db_manager = db_manager
        self.config = config
        logger.info("CompteManager initialisé - Migration ÉTAPE 2.1")

    async def ensure_user_registered(self, update: Update):
        """
        Enregistrement automatique utilisateur selon [source 4]
        Compatible callbacks et messages - Nouvelle implémentation propre
        """
        user = update.effective_user

        if not user:
            logger.warning("Impossible de récupérer les données utilisateur")
            return False

        try:
            with self.db_manager.get_cursor() as cursor:
                # ✅ UPSERT intelligent selon approche propre [source 4]
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, date_inscription, derniere_activite)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        username = VALUES(username),
                        first_name = VALUES(first_name),
                        last_name = VALUES(last_name),
                        derniere_activite = NOW()
                """, (
                    user.id,
                    user.username or None,
                    user.first_name or '',
                    user.last_name or ''
                ))

                # Logging selon dépannage méthodique [source 5]
                if cursor.rowcount == 1:
                    logger.info(f"✅ Nouvel utilisateur enregistré: {user.id} - {user.first_name}")
                elif cursor.rowcount == 2:  # ON DUPLICATE KEY UPDATE
                    logger.debug(f"✅ Utilisateur existant mis à jour: {user.id}")

                return True

        except Exception as e:
            logger.error(f"❌ Erreur enregistrement utilisateur {user.id}: {e}")
            return False

    async def update_user_activity(self, user_id):
        """Mise à jour activité selon optimisation [source 3]"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE users SET derniere_activite = NOW() WHERE user_id = %s
                """, (user_id,))

                if cursor.rowcount == 0:
                    logger.warning(f"⚠️ Utilisateur {user_id} non trouvé pour mise à jour activité")
                    return False

                return True

        except Exception as e:
            logger.error(f"❌ Erreur mise à jour activité {user_id}: {e}")
            return False

    async def get_user_display_name(self, user_id):
        """Récupère nom d'affichage selon gestion_des_fichiers [source 3]"""
        try:
            with self.db_manager.get_cursor() as cursor:
                cursor.execute("""
                    SELECT first_name, last_name, username
                    FROM users WHERE user_id = %s
                """, (user_id,))
                result = cursor.fetchone()

                if result:
                    if result['first_name']:
                        name = result['first_name']
                        if result['last_name']:
                            name += f" {result['last_name']}"
                        return name
                    elif result['username']:
                        return f"@{result['username']}"
                    else:
                        return f"User {user_id}"
                else:
                    return f"User {user_id}"

        except Exception as e:
            logger.error(f"❌ Erreur récupération nom utilisateur {user_id}: {e}")
            return f"User {user_id}"

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Gestion messages texte généraux + édition"""
        # Mettre à jour activité utilisateur
        await self.update_user_activity(update.effective_user.id)

        # Vérifier si en mode édition
        if 'editing' in context.user_data:
            # Déléguer à EditionManager pour traitement
            # Note: Il faut passer l'instance EditionManager ici
            # Cela sera géré via UserHandlers
            return

        # Message par défaut pour texte non reconnu
        await update.message.reply_text(
            "🤖 Je n'ai pas compris votre message.\n"
            "Utilisez /start pour voir les options disponibles.",
            parse_mode='HTML'
        )
