from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Application
from .forms import AccountCreationForm, AccountChangeForm


@admin.register(User)
class AccountAdmin(UserAdmin):
    add_form = AccountCreationForm
    form = AccountChangeForm
    ordering = ['email']
    list_display = ['email', 'first_name', 'is_staff', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    fieldsets = ((None, {'fields': ('email', 'password')}), ('Profile', {'fields': ('first_name', 'last_name')}),
                 ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
                 ('Dates', {'fields': ('last_login', 'date_joined')}))
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('email', 'first_name', 'password1', 'password2')}),)


admin.site.register(Application)
admin.site.site_header = 'AMPVE administration'
admin.site.site_title = 'AMPVE'
