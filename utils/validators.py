"""Module centralisé de validation des entrées et de gestion des formats temporels."""

from datetime import date, datetime, timezone
import html
import logging
import re
from typing import Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    PARIS_TZ = ZoneInfo("Europe/Paris")
except ImportError:
    import pytz
    PARIS_TZ = pytz.timezone("Europe/Paris")

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Exception personnalisée levée lors d'un échec de validation métier."""
    pass


def convert_utc_to_paris(utc_datetime) -> datetime:
    """Convertit un datetime (ou chaîne ISO/SQL) UTC vers le fuseau horaire Europe/Paris."""
    if utc_datetime is None:
        return datetime.now(PARIS_TZ)

    if isinstance(utc_datetime, str):
        cleaned = utc_datetime.replace("T", " ").replace("Z", "")
        try:
            utc_datetime = datetime.fromisoformat(cleaned)
        except ValueError:
            try:
                utc_datetime = datetime.strptime(cleaned[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.now(PARIS_TZ)

    elif isinstance(utc_datetime, date) and not isinstance(utc_datetime, datetime):
        utc_datetime = datetime.combine(utc_datetime, datetime.min.time())

    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=timezone.utc)

    return utc_datetime.astimezone(PARIS_TZ)


class Validators:
    """Bibliothèque statique de validation et d'assainissement des données."""

    @staticmethod
    def validate_age(age_str: str) -> int:
        """Valide l'âge (doit être un entier entre 18 et 40 ans inclus)."""
        try:
            age = int(str(age_str).strip())
            if not (18 <= age <= 40):
                raise ValidationError("L'âge doit être compris entre 18 et 40 ans.")
            return age
        except ValueError:
            raise ValidationError("Veuillez entrer un âge valide sous forme de nombre entier.")

    @staticmethod
    def validate_amount(amount_str: str) -> float:
        """Valide le montant des demandes prioritaires (entre 5 € et 10 000 €)."""
        try:
            amount_clean = str(amount_str).replace(",", ".").strip()
            amount = float(amount_clean)

            if amount < 5.0:
                raise ValidationError("Le montant minimum pour une demande prioritaire est de 5 €.")
            if amount > 10000.0:
                raise ValidationError("Le montant maximum autorisé est de 10 000 €.")

            return round(amount, 2)
        except ValueError:
            raise ValidationError("Format de montant invalide (ex : 15 ou 25.50).")

    @staticmethod
    def validate_instagram(username: str) -> Optional[str]:
        """Valide et normalise un nom d'utilisateur Instagram."""
        if Validators.is_skip_command(username):
            return None

        clean_user = str(username).strip()
        if "instagram.com/" in clean_user:
            clean_user = clean_user.split("instagram.com/")[-1].split("/")[0].split("?")[0]

        if clean_user.startswith("@"):
            clean_user = clean_user[1:]

        clean_user = clean_user.lower()

        if not re.match(r"^[a-zA-Z0-9._]{1,30}$", clean_user):
            raise ValidationError("Format Instagram invalide (1 à 30 lettres, chiffres, points ou underscores).")

        if clean_user.replace(".", "").replace("_", "") == "":
            raise ValidationError("Le nom Instagram ne peut pas comporter uniquement des caractères de séparation.")

        if ".." in clean_user or clean_user.startswith(".") or clean_user.endswith("."):
            raise ValidationError("Le nom Instagram ne peut pas contenir de points consécutifs ou en bordure.")

        return clean_user

    @staticmethod
    def validate_snapchat(username: str) -> Optional[str]:
        """Valide et normalise un nom d'utilisateur Snapchat."""
        if Validators.is_skip_command(username):
            return None

        clean_user = str(username).strip().lower()
        if clean_user.startswith("@"):
            clean_user = clean_user[1:]

        if not re.match(r"^[a-zA-Z0-9_.-]{3,15}$", clean_user):
            raise ValidationError("Format Snapchat invalide (3 à 15 caractères : lettres, chiffres, tirets, points).")

        if clean_user.startswith("-") or clean_user.endswith("-"):
            raise ValidationError("Le nom Snapchat ne peut pas commencer ou finir par un tiret.")

        return clean_user

    @staticmethod
    def validate_prenom(prenom: str) -> str:
        """Valide le prénom obligatoire."""
        if not prenom or not str(prenom).strip():
            raise ValidationError("Le prénom est obligatoire.")

        p = str(prenom).strip()
        if len(p) < 2:
            raise ValidationError("Le prénom doit contenir au moins 2 caractères.")
        if len(p) > 50:
            raise ValidationError("Le prénom ne peut pas excéder 50 caractères.")

        if not re.match(r"^[a-zA-Z\u00C0-\u017F\s'\-]+$", p):
            raise ValidationError("Le prénom ne peut contenir que des lettres, tirets ou apostrophes.")

        return p

    @staticmethod
    def validate_nom(nom: str) -> Optional[str]:
        """Valide le nom de famille facultatif."""
        if not nom or not str(nom).strip() or Validators.is_skip_command(nom):
            return None

        n = str(nom).strip()
        if len(n) > 50:
            raise ValidationError("Le nom ne peut pas dépasser 50 caractères.")

        if not re.match(r"^[a-zA-Z\u00C0-\u017F\s'\-]+$", n):
            raise ValidationError("Le nom ne peut contenir que des lettres, tirets ou apostrophes.")

        return n

    @staticmethod
    def validate_localisation(localisation: str) -> str:
        """Valide la ville ou région."""
        if not localisation or not str(localisation).strip():
            raise ValidationError("La localisation est obligatoire.")

        loc = str(localisation).strip()
        if len(loc) < 2:
            raise ValidationError("La localisation doit contenir au moins 2 caractères.")
        if len(loc) > 100:
            raise ValidationError("La localisation ne peut pas dépasser 100 caractères.")

        if not re.match(r"^[a-zA-Z\u00C0-\u017F0-9\s'\-.,()]+$", loc):
            raise ValidationError("Caractères spéciaux non autorisés dans la localisation.")

        return loc

    @staticmethod
    def validate_details(details: str) -> Optional[str]:
        """Valide les détails ou remarques complémentaires."""
        if not details or not str(details).strip() or Validators.is_skip_command(details):
            return None

        d = str(details).strip()
        if len(d) > 1000:
            raise ValidationError("Le texte de remarques ne peut pas dépasser 1 000 caractères.")

        if not any(c.isalnum() for c in d):
            raise ValidationError("Les remarques doivent comporter au moins un mot compréhensible.")

        return d

    @staticmethod
    def validate_alias(alias: str) -> Tuple[bool, str]:
        """Valide la structure syntaxique d'un pseudonyme admin."""
        if not alias or not str(alias).strip():
            return False, "L'alias ne peut pas être vide."

        a = str(alias).strip()
        if len(a) < 2:
            return False, "L'alias doit comporter au moins 2 caractères."
        if len(a) > 30:
            return False, "L'alias ne peut pas excéder 30 caractères."

        test_str = a.replace(" ", "").replace("-", "").replace("_", "")
        if not test_str.isalnum():
            return False, "Caractères autorisés : lettres, chiffres, espaces, tirets et underscores."

        return True, ""

    @staticmethod
    def validate_alias_uniqueness(db_manager, alias: str, exclude_user_id: int = None) -> Tuple[bool, str]:
        """Contrôle l'unicité de l'alias contre la table admins et la table config (owner)."""
        try:
            clean_alias = str(alias).strip()
            owner_alias = db_manager.get_config_value("owner_alias", "Propriétaire") or "Propriétaire"
            if owner_alias.lower() == clean_alias.lower():
                raw_owner_id = db_manager.get_owner_id()
                owner_id = int(raw_owner_id) if raw_owner_id else 0
                if not (exclude_user_id and int(exclude_user_id) == owner_id):
                    return False, "Cet alias est réservé au compte propriétaire."

            with db_manager.get_cursor() as cursor:
                if exclude_user_id:
                    cursor.execute(
                        "SELECT user_id FROM admins WHERE LOWER(alias) = LOWER(%s) AND user_id != %s",
                        (clean_alias, int(exclude_user_id)),
                    )
                else:
                    cursor.execute(
                        "SELECT user_id FROM admins WHERE LOWER(alias) = LOWER(%s)",
                        (clean_alias,),
                    )

                if cursor.fetchone():
                    return False, "Cet alias est déjà utilisé par un autre administrateur."

            return True, ""
        except Exception as exc:
            logger.error("Erreur contrôle unicité alias : %s", exc)
            return False, "Erreur technique lors de la vérification de l'alias."

    @staticmethod
    def is_skip_command(text: str) -> bool:
        """Détecte si la saisie correspond à une intention de passer l'étape."""
        if not text:
            return False
        cleaned = str(text).lower().strip()
        return cleaned in ["/skip", "/", "skip", "passer", "next", "-"]

    @staticmethod
    def clean_input(text: str) -> str:
        """Supprime les espaces superflus, les espaces insécables et les caractères de contrôle."""
        if not text:
            return ""
        # Remplacement des espaces insécables et assimilés
        t = str(text).replace("\xa0", " ").replace("\u202f", " ").replace("\u200b", "").strip()
        return "".join(c for c in t if ord(c) >= 32 or c in "\n\t")

    @staticmethod
    def get_validation_help(field: str = None) -> str:
        """Renvoie le guide de saisie formaté en HTML pour les messages Telegram."""
        rules = {
            "prenom": (
                "<b>Règles pour le prénom :</b>\n"
                "• Obligatoire (2 à 50 caractères)\n"
                "• Lettres, espaces, tirets et apostrophes"
            ),
            "nom": (
                "<b>Règles pour le nom :</b>\n"
                "• Optionnel (max 50 caractères)\n"
                "• Lettres, espaces, tirets et apostrophes"
            ),
            "age": (
                "<b>Règles pour l'âge :</b>\n"
                "• Doit être un nombre entier entre 18 et 40 ans"
            ),
            "localisation": (
                "<b>Règles pour la localisation :</b>\n"
                "• Ville, département ou région (2 à 100 caractères)"
            ),
            "montant": (
                "<b>Règles pour le montant :</b>\n"
                "• Minimum 5 €, maximum 10 000 €\n"
                "• Format numérique (ex : 20 ou 15.50)"
            ),
            "instagram": (
                "<b>Règles Instagram :</b>\n"
                "• 1 à 30 caractères sans espaces (ex : @pseudo)"
            ),
            "snapchat": (
                "<b>Règles Snapchat :</b>\n"
                "• 3 à 15 caractères sans espaces"
            ),
            "details": (
                "<b>Règles pour les remarques :</b>\n"
                "• Maximum 1 000 caractères"
            ),
            "alias": (
                "<b>Règles d'alias :</b>\n"
                "• 2 à 30 caractères\n"
                "• Lettres, chiffres, espaces et tirets"
            ),
        }
        return rules.get(field, "Veuillez respecter le format attendu.")