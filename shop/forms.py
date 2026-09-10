from django import forms

INPUT_CLASSES = (
    "w-full bg-surface text-ink placeholder-ink-faint text-sm rounded-md "
    "py-2.5 px-3.5 border border-line focus:ring-2 focus:ring-focus "
    "focus:border-transparent outline-none"
)


class CheckoutForm(forms.Form):
    full_name = forms.CharField(
        max_length=200,
        label="Full Name",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "John Doe"}),
    )
    phone = forms.CharField(
        max_length=20,
        label="Phone Number",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "+1 234 567 8900"}),
    )
    address = forms.CharField(
        label="Address",
        widget=forms.Textarea(
            attrs={"class": INPUT_CLASSES, "rows": 3, "placeholder": "Street, house/apartment number"}
        ),
    )
    city = forms.CharField(
        max_length=100,
        label="City",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "City"}),
    )
