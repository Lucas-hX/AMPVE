from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import User


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
    volume = forms.IntegerField(min_value=0, max_value=80, label='Speaker volume (0–80)')
    microphone_muted = forms.BooleanField(required=False, label='Mute microphone')
