from django.db.models.signals import post_save
from django.contrib.auth.models import User
from .models import Profile
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, diamonds=10000)
@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()

from django.contrib.auth.signals import user_logged_out
from django.utils import timezone
from datetime import timedelta

@receiver(user_logged_out)
def update_last_seen_on_logout(sender, request, user, **kwargs):
    if user:
        # Set last_seen to 1 hour ago so they appear offline immediately
        user.profile.last_seen = timezone.now() - timedelta(hours=1)
        user.profile.save()