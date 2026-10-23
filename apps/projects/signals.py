"""Arama dizinini ilgili kayıtlar değiştikçe günceller."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Need, Project, Team


@receiver(post_save, sender=Need)
@receiver(post_delete, sender=Need)
def need_changed(sender, instance, **kwargs):
    project = Project.objects.filter(pk=instance.project_id).first()
    if project is not None:
        project.refresh_search_index()


@receiver(post_save, sender=Team)
def team_changed(sender, instance, created, **kwargs):
    if created:
        return
    for project in instance.projects.all():
        project.refresh_search_index()
