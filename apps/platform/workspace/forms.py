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
