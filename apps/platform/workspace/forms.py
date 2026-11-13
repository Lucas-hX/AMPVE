from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import ReaderBook, User


class SignInForm(AuthenticationForm):
    username = forms.EmailField(label='Email address', widget=forms.EmailInput(attrs={'autocomplete': 'username', 'placeholder': 'you@example.com'}))
    password = forms.CharField(label='Password', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        labels = {'first_name': 'First name', 'last_name': 'Last name'}


class AccountCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']


class AccountChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'


class ConnectionForm(forms.Form):
    provider = forms.ChoiceField(choices=[('gemini', 'Gemini Live'), ('openai', 'OpenAI Realtime')])
    label = forms.CharField(max_length=80, label='Connection name')
    api_key = forms.CharField(min_length=16, max_length=512, strip=True,
        label='API key', widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'off', 'spellcheck': 'false'}))

    def clean_api_key(self):
        value = self.cleaned_data['api_key']
        if any(c.isspace() for c in value) or not value.isascii():
            raise forms.ValidationError('Enter an API key without spaces.')
        return value


class ReplaceKeyForm(forms.Form):
    api_key = ConnectionForm.base_fields['api_key']

    def clean_api_key(self):
        return ConnectionForm.clean_api_key(self)


class ClaimDeviceForm(forms.Form):
    code = forms.CharField(max_length=20, label='Pairing code',
        widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'off'}))
    name = forms.CharField(max_length=80, label='Device name')
    confirm = forms.BooleanField(label='I can see this code on the device I want to add.')

    def clean_code(self):
        import re
        code = self.cleaned_data['code'].replace('-', '').replace(' ', '').upper()
        if not re.fullmatch('[A-HJ-NP-Z2-9]{12}', code):
            raise forms.ValidationError('Enter the 12-character code shown by AMPVE firmware.')
        return code


class DeviceSettingsForm(forms.Form):
    name = forms.CharField(max_length=80, label='Device name')


class ReaderUploadForm(forms.Form):
    MAX_BYTES = 100 * 1024 * 1024

    existing_book = forms.ModelChoiceField(
        queryset=ReaderBook.objects.none(), required=False, empty_label='Create a new book',
        label='Add to an existing book')
    book_title = forms.CharField(max_length=160, required=False, label='New book title')
    part_title = forms.CharField(max_length=160, required=False, label='Part name')
    collection_name = forms.CharField(max_length=80, required=False, label='Collection')
    page_start = forms.IntegerField(min_value=1, required=False, label='First page (optional)')
    page_end = forms.IntegerField(min_value=1, required=False, label='Last page (optional)')
    document = forms.FileField(label='PDF file')

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['existing_book'].queryset = ReaderBook.objects.filter(owner=owner)

    def clean_document(self):
        document = self.cleaned_data['document']
        if document.size <= 0 or document.size > self.MAX_BYTES:
            raise forms.ValidationError('Choose a PDF no larger than 100 MB.')
        if not document.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Choose a PDF file.')
        header = document.read(1024)
        document.seek(0)
        if b'%PDF-' not in header:
            raise forms.ValidationError('This file does not have a valid PDF header.')
        return document

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('existing_book') and not cleaned.get('book_title'):
            self.add_error('book_title', 'Enter a title for the new book.')
        start, end = cleaned.get('page_start'), cleaned.get('page_end')
        if (start is None) != (end is None):
            self.add_error('page_end' if end is None else 'page_start', 'Enter both ends of the page range.')
        elif start is not None and end < start:
            self.add_error('page_end', 'The last page must not be before the first page.')
        return cleaned
