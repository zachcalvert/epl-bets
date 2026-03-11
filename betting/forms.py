from decimal import Decimal

from django import forms

from betting.models import BetSlip


class PlaceBetForm(forms.Form):
    selection = forms.ChoiceField(
        choices=BetSlip.Selection.choices,
        widget=forms.RadioSelect(
            attrs={"class": "hidden peer"},
        ),
    )
    stake = forms.DecimalField(
        min_value=Decimal("0.50"),
        max_value=Decimal("500.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "w-full bg-dark border border-gray-600 rounded-md px-3 py-2 text-white font-mono text-base text-right focus:outline-none focus:border-accent",
                "placeholder": "0.00",
                "step": "0.50",
                "min": "0.50",
                "max": "500.00",
            }
        ),
    )
