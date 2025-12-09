from django.contrib import admin
from .models import Resource , Tag , Comment, UserResourceInteraction


# Register your models here.
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name','slug')
    prepopulated_fields = {'slug':('name',)}

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'difficulty', 'is_approved', 'upvote_count', 'created_at')
    list_filter = ('difficulty', 'category', 'is_approved', 'created_at')
    search_fields = ('title', 'description', 'author__email')
    prepopulated_fields = {'slug':('title',)}
    #Use filter horizontal for M2M fields
    filter_horizontal = ('tags',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('resource', 'author', 'created_at','parent')
    list_filter = ('created_at',)
    search_fields = ('resource__title', 'author__email', 'content')

@admin.register(UserResourceInteraction)
class UserResourceInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'upvoted','saved','completed','created_at')
    list_filter = ('upvoted','saved','completed','created_at')
    search_fields = ('user__email', 'resource__title')



