from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import  CustomUser , UserProfile, Skill, Category , SiteStats
# Register your models here.


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    """
    Custom Admin interface for our Custom User Model
    """
    list_display =  ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
    """
    In the user list, show these 5 columns:
    
    Email, First Name, Last Name
    
    Is Staff? (Yes/No for admin access)
    
    Is Active? (Yes/No for active accounts)
    """
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)


    #define the fields to show in the form
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions',{'fields' : ('is_active','is_staff','is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields' : ( 'last_login', 'date_joined')}),
    )
    """
    This organizes the edit form into sections:
        
        Login Info: Email & Password
        
        Personal Info: First & Last Name
        
        Permissions: Active status, admin rights, groups
        
        Dates: Last login & join date
    """

    #remove the default username field from the list and form
    filter_horizontal = ('groups', 'user_permissions')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for our User Model
    """
    list_display = ('user', 'bio', 'avatar')
    search_fields = ('user__email', 'bio')


#Register Skill and Category
@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)} #autofill slug when typing name

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon_class')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

@admin.register(SiteStats)
class SiteStatsAdmin(admin.ModelAdmin):
    list_display = ('total_resources', 'total_users', 'total_goals_completed','last_updated')
    #Ensures no one can manually create more than one
    def has_add_permission(self, request):
        return not SiteStats.objects.exists()




