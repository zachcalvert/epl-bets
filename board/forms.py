from django import forms

from board.models import PostType


class BoardPostForm(forms.Form):
    post_type = forms.ChoiceField(
        choices=PostType.choices,
        initial=PostType.PREDICTION,
        widget=forms.RadioSelect(
            attrs={"class": "hidden peer"},
        ),
    )
    body = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "class": "themed-input w-full text-sm",
                "rows": 3,
                "placeholder": "Share your take...",
                "maxlength": "2000",
            }
        ),
    )
