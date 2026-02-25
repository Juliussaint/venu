from django import forms
from .models import Question

class RegistrationForm(forms.Form):
    # --- CSS Class Definitions for Tailwind v4 ---
    # Standard input/select styling
    INPUT_CLASS = "block w-full rounded-xl border-0 py-3 px-4 text-zinc-900 shadow-sm ring-1 ring-zinc-300 placeholder:text-zinc-400 focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2 transition-all"
    
    # Radio/Checkbox input styling (smaller, usually inline or list items)
    CHOICE_INPUT_CLASS = "h-4 w-4 text-indigo-600 border-zinc-300 focus:ring-indigo-500"

    # Basic Participant Fields
    participant_name = forms.CharField(
        label="Full Name", 
        max_length=200,
        widget=forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'John Doe'})
    )
    participant_email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={'class': INPUT_CLASS, 'placeholder': 'john@example.com'})
    )
    participant_phone = forms.CharField(
        label="Phone Number", 
        required=False,
        widget=forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': '+1 234 567 890'})
    )

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)

        # Dynamically add custom questions
        questions = self.event.questions.all()
        for question in questions:
            field_name = f'question_{question.id}'
            
            # Common attributes for the widget
            attrs = {'class': self.INPUT_CLASS}

            if question.field_type == 'text':
                field = forms.CharField(
                    label=question.label, 
                    required=question.required,
                    widget=forms.TextInput(attrs=attrs)
                )
            
            elif question.field_type in ['select', 'radio']:
                choices = [(c.text, c.text) for c in question.choices.all()]
                
                if question.field_type == 'select':
                    # Dropdown Select
                    field = forms.ChoiceField(
                        label=question.label, 
                        choices=choices, 
                        required=question.required,
                        widget=forms.Select(attrs=attrs)
                    )
                else:
                    # Radio Buttons
                    # We use a custom class for the individual inputs
                    radio_attrs = {'class': self.CHOICE_INPUT_CLASS}
                    field = forms.ChoiceField(
                        label=question.label, 
                        choices=choices, 
                        required=question.required, 
                        widget=forms.RadioSelect(attrs=radio_attrs)
                    )

            elif question.field_type == 'checkbox':
                choices = [(c.text, c.text) for c in question.choices.all()]
                checkbox_attrs = {'class': self.CHOICE_INPUT_CLASS}
                field = forms.MultipleChoiceField(
                    label=question.label, 
                    choices=choices, 
                    required=question.required, 
                    widget=forms.CheckboxSelectMultiple(attrs=checkbox_attrs)
                )
            
            else:
                continue

            self.fields[field_name] = field