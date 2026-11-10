"""Email-first user model; must exist before production users are created."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class EmailUserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def canonical_email(email):
        return (email or "").strip().casefold()

    def create_user(self, email, password=None, **extra_fields):
        normalized = self.canonical_email(email)
        if not normalized:
            raise ValueError("Email address required.")
        user = self.model(email=normalized, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser requires is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser requires is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """User identity is a unique, canonicalized email, with no username."""
    username = None
    email = models.EmailField("email address", unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = EmailUserManager()

    def clean(self):
        super().clean()
        self.email = EmailUserManager.canonical_email(self.email)

    def __str__(self):
        return self.email
