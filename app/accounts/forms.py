"""Email-first login form; Django still expects field name 'username'."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            "autocomplete": "email",
            "placeholder": "you@example.com",
            "autofocus": True,
        }),
    )

    def clean_username(self):
        return self.cleaned_data["username"].strip().casefold()
