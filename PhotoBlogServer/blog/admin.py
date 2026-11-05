from django.contrib import admin
from .models import Post
from .ownership import is_blog_owner, can_manage_post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_date", "published_date")
    readonly_fields = ("created_date", "published_date")
    search_fields = ("title", "text", "author__username")

    def has_add_permission(self, request):
        return is_blog_owner(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return is_blog_owner(request.user) and (obj is None or can_manage_post(request.user, obj)) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return is_blog_owner(request.user) and (obj is None or can_manage_post(request.user, obj)) and super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return (*self.readonly_fields, "author")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)


