from django.contrib import admin

from .models import Need, Project, ProgressUpdate, Team, TeamInvite, TeamMembership


class NeedInline(admin.TabularInline):
    model = Need
    extra = 0


class MembershipInline(admin.TabularInline):
    model = TeamMembership
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "institution", "city", "kind", "verified", "verification_method",
                    "has_minor_members", "created_at")
    list_filter = ("verified", "kind", "city", "has_minor_members")
    search_fields = ("name", "institution", "owner__email")
    raw_id_fields = ("owner",)
    inlines = [MembershipInline]
    actions = ["mark_verified"]

    @admin.action(description="Seçili takımları doğrula (yönetici incelemesi)")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True, verification_method="yonetici")
        self.message_user(request, f"{updated} takım doğrulandı.")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "team", "category", "competition", "stage", "status", "deadline", "created_at")
    list_filter = ("status", "category", "competition", "stage")
    search_fields = ("title", "team__name")
    readonly_fields = ("dossier", "dossier_uploaded_at")
    inlines = [NeedInline]


@admin.register(TeamInvite)
class TeamInviteAdmin(admin.ModelAdmin):
    list_display = ("team", "email", "created_at", "expires_at", "accepted_at")
    search_fields = ("team__name", "email")
    readonly_fields = ("token_hash",)


admin.site.register(ProgressUpdate)
