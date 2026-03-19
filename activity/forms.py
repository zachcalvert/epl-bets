from django import forms

from users.models import User


class ActivityPreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["show_activity_toasts"]
