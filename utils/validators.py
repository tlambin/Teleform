import re
from typing import Optional, Tuple
import pytz

class ValidationError(Exception):
    """Exception personnalisée pour les erreurs de validation"""
    pass

def convert_utc_to_paris(utc_datetime):
    """Convertit datetime UTC vers timezone Paris"""
    if utc_datetime.tzinfo is None:
        # Si le datetime est naive (sans timezone), on assume qu'il est en UTC
        utc_datetime = pytz.utc.localize(utc_datetime)

    paris_tz = pytz.timezone('Europe/Paris')
    return utc_datetime.astimezone(paris_tz)

class Validators:
    # ===== VALIDATIONS EXISTANTES AMÉLIORÉES =====

    @staticmethod
    def validate_age(age_str: str) -> int:
        """Valide l'âge avec contraintes renforcées"""
        try:
            age = int(age_str.strip())
            if not 18 <= age <= 40:
                raise ValidationError("L'âge doit être entre 18 et 40 ans")
            return age
        except ValueError:
            raise ValidationError("Veuillez entrer un âge valide (nombre entier)")

    @staticmethod
    def validate_amount(amount_str: str) -> float:
        """Valide le montant pour les demandes prioritaires"""
        try:
            # Remplacer la virgule par un point
            amount_str = amount_str.replace(',', '.').strip()
            amount = float(amount_str)

            if amount < 5:
                raise ValidationError("Le montant minimum est de 5€")
            if amount > 10000:
                raise ValidationError("Le montant maximum est de 10 000€")

            # Vérifier qu'il n'y a pas plus de 2 décimales
            if round(amount, 2) != amount:
                amount = round(amount, 2)

            return amount
        except ValueError:
            raise ValidationError("Veuillez entrer un montant valide (ex: 5.50)")

    @staticmethod
    def validate_instagram(username: str) -> Optional[str]:
        """Valide le nom d'utilisateur Instagram"""
        if username.lower() in ['/skip', '/', 'skip', 'passer']:
            return None

        # Nettoyer l'URL Instagram si fournie
        if 'instagram.com/' in username:
            username = username.split('instagram.com/')[-1].split('/')[0]

        if username.startswith('@'):
            username = username[1:]

        # CONVERSION AUTOMATIQUE EN MINUSCULES
        username = username.lower()

        # Validation regex Instagram améliorée
        if not re.match(r'^[a-zA-Z0-9._]{1,30}$', username):
            raise ValidationError("Format Instagram invalide. Utilisez uniquement lettres, chiffres, points et underscores")

        # Vérifier qu'il n'y a pas que des points ou underscores
        if username.replace('.', '').replace('_', '') == '':
            raise ValidationError("Le nom d'utilisateur Instagram ne peut pas contenir uniquement des points et underscores")

        if '..' in username:
            raise ValidationError("Le nom d'utilisateur Instagram ne peut pas contenir deux points consécutifs")

        if username.startswith('.') or username.endswith('.'):
            raise ValidationError("Le nom d'utilisateur Instagram ne peut pas commencer ou finir par un point")

        return username

    @staticmethod
    def validate_snapchat(username: str) -> Optional[str]:
        """Valide le nom d'utilisateur Snapchat"""
        if username.lower() in ['/skip', '/', 'skip', 'passer']:
            return None

        # CONVERSION AUTOMATIQUE EN MINUSCULES
        username = username.lower()

        # Validation Snapchat (3-15 caractères, lettres, chiffres, tirets, underscores)
        if not re.match(r'^[a-zA-Z0-9_-]{3,15}$', username):
            raise ValidationError("Format Snapchat invalide. 3-15 caractères: lettres, chiffres, tirets, underscores")

        if username.startswith('-') or username.endswith('-'):
            raise ValidationError("Le nom d'utilisateur Snapchat ne peut pas commencer ou finir par un tiret")

        return username

    @staticmethod
    def validate_text_field(text: str, field_name: str, max_length: int = 100, min_length: int = 0, required: bool = True) -> str:
        """Valide un champ texte générique avec options étendues"""
        if not text or not text.strip():
            if required:
                raise ValidationError(f"Le champ {field_name} ne peut pas être vide")
            return text

        text = text.strip()

        if len(text) < min_length:
            raise ValidationError(f"Le champ {field_name} doit contenir au moins {min_length} caractères")

        if len(text) > max_length:
            raise ValidationError(f"Le champ {field_name} ne peut pas dépasser {max_length} caractères")

        return text

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Nettoie un nom de fichier pour la sécurité"""
        # Supprimer les caractères dangereux
        filename = re.sub(r'[^\w\s-.]', '', filename)
        # Limiter la longueur
        if len(filename) > 100:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:95] + ('.' + ext if ext else '')
        return filename

    @staticmethod
    def validate_alias(alias: str) -> Tuple[bool, str]:
        """Valide le format d'un alias administrateur"""
        # Vérifier que l'alias n'est pas vide
        if not alias or not alias.strip():
            return False, "L'alias ne peut pas être vide"

        alias = alias.strip()

        # Longueur entre 3 et 20 caractères
        if len(alias) < 3:
            return False, "L'alias doit contenir au moins 3 caractères"

        if len(alias) > 20:
            return False, "L'alias ne peut pas dépasser 20 caractères"

        # Seulement lettres, chiffres et underscore
        if not re.match(r'^[a-zA-Z0-9_]+$', alias):
            return False, "L'alias ne peut contenir que des lettres, chiffres et underscores"

        # Ne doit pas commencer par un chiffre
        if alias[0].isdigit():
            return False, "L'alias ne peut pas commencer par un chiffre"

        return True, ""

    @staticmethod
    def validate_alias_uniqueness(db_manager, alias: str, exclude_user_id: int = None) -> tuple[bool, str]:
        """Vérifie l'unicité d'un alias dans toutes les tables"""
        try:
            with db_manager.get_cursor() as cursor:
                # Vérifier dans la table admins
                if exclude_user_id:
                    cursor.execute("SELECT user_id FROM admins WHERE alias = %s AND user_id != %s",
                                  (alias, exclude_user_id))
                else:
                    cursor.execute("SELECT user_id FROM admins WHERE alias = %s", (alias,))

                if cursor.fetchone():
                    return False, "Cet alias est déjà utilisé par un administrateur"

                # Vérifier dans la table owner_config
                if exclude_user_id:
                    cursor.execute("SELECT owner_id FROM owner_config WHERE alias = %s AND owner_id != %s",
                                  (alias, exclude_user_id))
                else:
                    cursor.execute("SELECT owner_id FROM owner_config WHERE alias = %s", (alias,))

                if cursor.fetchone():
                    return False, "Cet alias est déjà utilisé par le propriétaire"

                return True, ""

        except Exception as e:
            return False, f"Erreur lors de la vérification : {str(e)}"

    @staticmethod
    def validate_alias_complete(db_manager, alias: str, exclude_user_id: int = None) -> tuple[bool, str]:
        """Validation complète d'un alias (format + unicité)"""
        # 1. Validation du format
        is_format_valid, format_error = Validators.validate_alias(alias)
        if not is_format_valid:
            return False, format_error

        # 2. Validation de l'unicité
        is_unique, uniqueness_error = Validators.validate_alias_uniqueness(db_manager, alias, exclude_user_id)
        if not is_unique:
            return False, uniqueness_error

        return True, ""

    # ===== NOUVELLES VALIDATIONS AJOUTÉES =====

    @staticmethod
    def validate_prenom(prenom: str) -> str:
        """Valide un prénom"""
        if not prenom or not prenom.strip():
            raise ValidationError("Le prénom est obligatoire")

        prenom = prenom.strip()

        if len(prenom) < 2:
            raise ValidationError("Le prénom doit contenir au moins 2 caractères")

        if len(prenom) > 50:
            raise ValidationError("Le prénom ne peut pas dépasser 50 caractères")

        # Autoriser lettres, espaces, apostrophes, tirets et caractères accentués
        if not re.match(r"^[a-zA-ZÀ-ÿ\s'\-]+$", prenom):
            raise ValidationError("Le prénom ne peut contenir que des lettres, espaces, apostrophes et tirets")

        return prenom

    @staticmethod
    def validate_nom(nom: str) -> Optional[str]:
        """Valide un nom de famille (optionnel)"""
        if not nom or not nom.strip():
            return None  # Nom optionnel

        nom = nom.strip()

        if len(nom) > 50:
            raise ValidationError("Le nom ne peut pas dépasser 50 caractères")

        if not re.match(r"^[a-zA-ZÀ-ÿ\s'\-]+$", nom):
            raise ValidationError("Le nom ne peut contenir que des lettres, espaces, apostrophes et tirets")

        return nom

    @staticmethod
    def validate_localisation(localisation: str) -> str:
        """Valide une localisation/ville"""
        if not localisation or not localisation.strip():
            raise ValidationError("La localisation est obligatoire")

        localisation = localisation.strip()

        if len(localisation) < 2:
            raise ValidationError("La localisation doit contenir au moins 2 caractères")

        if len(localisation) > 100:
            raise ValidationError("La localisation ne peut pas dépasser 100 caractères")

        # Autoriser lettres, chiffres, espaces, tirets, apostrophes, points, parenthèses
        if not re.match(r"^[a-zA-ZÀ-ÿ0-9\s'\-.,()]+$", localisation):
            raise ValidationError("Localisation invalide - caractères non autorisés")

        return localisation

    @staticmethod
    def validate_details(details: str) -> Optional[str]:
        """Valide les détails d'une demande"""
        if not details or not details.strip():
            return None  # Détails optionnels

        details = details.strip()

        if len(details) > 1000:
            raise ValidationError("Les détails ne peuvent pas dépasser 1000 caractères")

        # Vérifier qu'il n'y a pas que des caractères spéciaux
        if not any(c.isalnum() for c in details):
            raise ValidationError("Les détails doivent contenir au moins un caractère alphanumérique")

        return details

    @staticmethod
    def validate_user_id(user_id: str) -> int:
        """Valide un ID utilisateur Telegram"""
        try:
            uid = int(user_id)
            # Les IDs Telegram sont des entiers positifs entre 1 et 2^63-1
            if uid <= 0:
                raise ValidationError("L'ID utilisateur doit être positif")
            if uid > 9223372036854775807:  # 2^63-1
                raise ValidationError("ID utilisateur invalide (trop grand)")
            return uid
        except ValueError:
            raise ValidationError("L'ID utilisateur doit être un nombre")

    @staticmethod
    def validate_file_id(file_id: str) -> str:
        """Valide un file_id Telegram"""
        if not file_id or not file_id.strip():
            raise ValidationError("Le file_id ne peut pas être vide")

        file_id = file_id.strip()

        # Les file_id Telegram ont généralement entre 20 et 200 caractères
        if len(file_id) < 10:
            raise ValidationError("File_id trop court (probablement invalide)")

        if len(file_id) > 255:
            raise ValidationError("File_id trop long")

        # Les file_id peuvent contenir des caractères alphanumériques et quelques symboles
        if not re.match(r'^[a-zA-Z0-9_-]+$', file_id):
            raise ValidationError("File_id contient des caractères invalides")

        return file_id

    @staticmethod
    def validate_statut_demande(statut: str) -> str:
        """Valide un statut de demande"""
        statuts_valides = [
            '📨 Reçue',
            'En attente',
            'En cours',
            'Réussie',
            'Difficile',
            'Abandonnée'
        ]

        if statut not in statuts_valides:
            raise ValidationError(f"Statut invalide. Statuts autorisés : {', '.join(statuts_valides)}")

        return statut

    @staticmethod
    def validate_priority_choice(choice: str) -> bool:
        """Valide un choix de priorité"""
        choix_valides = ['priorite_oui', 'priorite_non']

        if choice not in choix_valides:
            raise ValidationError("Choix de priorité invalide")

        return choice == 'priorite_oui'

    @staticmethod
    def validate_command_permissions(config, user_id: int, required_level: str) -> bool:
        """Valide les permissions d'un utilisateur pour une commande"""
        if required_level == "owner":
            if not config.is_owner(user_id):
                raise ValidationError("Seul le propriétaire peut effectuer cette action")
        elif required_level == "admin":
            if not config.is_admin(user_id):
                raise ValidationError("Accès non autorisé - Permission administrateur requise")
        elif required_level == "user":
            # Validation basique utilisateur
            pass
        else:
            raise ValidationError("Niveau de permission invalide")

        return True

    # ===== MÉTHODES D'AIDE ET DE RÈGLES =====

    @staticmethod
    def get_alias_rules() -> str:
        """Retourne les règles de validation d'alias pour l'affichage"""
        return (
            "**Règles d'alias :**\n"
            "• 3 à 20 caractères\n"
            "• Lettres, chiffres et underscore uniquement\n"
            "• Ne peut pas commencer par un chiffre\n"
            "• Pas d'espaces"
        )

    @staticmethod
    def get_validation_rules() -> dict:
        """Retourne toutes les règles de validation pour l'aide utilisateur"""
        return {
            'alias': (
                "**Règles d'alias :**\n"
                "• 3 à 20 caractères\n"
                "• Lettres, chiffres et underscore uniquement\n"
                "• Ne peut pas commencer par un chiffre\n"
                "• Pas d'espaces"
            ),
            'prenom': (
                "**Règles prénom :**\n"
                "• Obligatoire\n"
                "• 2 à 50 caractères\n"
                "• Lettres, espaces, apostrophes et tirets uniquement"
            ),
            'age': (
                "**Règles âge :**\n"
                "• Entre 18 et 40 ans\n"
                "• Nombre entier uniquement"
            ),
            'montant': (
                "**Règles montant :**\n"
                "• Entre 5€ et 10 000€\n"
                "• Maximum 2 décimales\n"
                "• Format : 123.45 ou 123,45"
            ),
            'instagram': (
                "**Règles Instagram :**\n"
                "• Optionnel (tapez /skip pour passer)\n"
                "• 1 à 30 caractères\n"
                "• Lettres, chiffres, points et underscores"
            ),
            'snapchat': (
                "**Règles Snapchat :**\n"
                "• Optionnel (tapez /skip pour passer)\n"
                "• 3 à 15 caractères\n"
                "• Lettres, chiffres, tirets et underscores"
            ),
            'localisation': (
                "**Règles localisation :**\n"
                "• Obligatoire\n"
                "• 2 à 100 caractères\n"
                "• Lettres, chiffres, espaces et ponctuation de base"
            )
        }

    @staticmethod
    def get_validation_help(field: str = None) -> str:
        """Retourne l'aide de validation pour un champ spécifique ou tous"""
        rules = Validators.get_validation_rules()

        if field and field in rules:
            return rules[field]

        # Retourner l'aide complète
        help_text = "📋 **Guide de Validation Complet**\n\n"
        for field_name, rule in rules.items():
            help_text += f"{rule}\n\n"

        return help_text

    @staticmethod
    def is_skip_command(text: str) -> bool:
        """Vérifie si l'input est une commande de skip"""
        if not text:
            return False
        return text.lower().strip() in ['/skip', '/', 'skip', 'passer', 'next']

    @staticmethod
    def clean_input(text: str) -> str:
        """Nettoie un input utilisateur de base"""
        if not text:
            return ""

        # Supprimer les espaces en début/fin
        text = text.strip()

        # Supprimer les caractères de contrôle
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

        return text

    @staticmethod
    def validate_batch(*validations) -> bool:
        """Exécute plusieurs validations en batch et lève la première erreur rencontrée"""
        for validation_func, value, *args in validations:
            try:
                validation_func(value, *args)
            except ValidationError:
                raise  # Re-lever la première erreur rencontrée

        return True
