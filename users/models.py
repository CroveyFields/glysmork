from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from PIL import Image
# Create your models here.


class Profile(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'), 
        ('F', 'Female'), 
        ('O', 'Other')
    ]
    user = models.OneToOneField(User, on_delete = models.CASCADE)
    image = models.ImageField(default = 'default.jpg', upload_to = 'profile_pics')
    bio = models.TextField(max_length = 500, blank = True)
    gender = models.CharField(max_length = 1, choices = GENDER_CHOICES, default = 'O')
    location = models.CharField(max_length = 100, blank = True) # Deprecated, keeping for fallback
    
    from django_countries.fields import CountryField
    country = CountryField(blank=True)
    state = models.CharField(max_length=100, blank=True)
    
    diamonds = models.IntegerField(default = 20)
    age = models.PositiveIntegerField(default = 18)
    call_price = models.IntegerField(default = 0)
    last_seen = models.DateTimeField(default = timezone.now)

    # Verification
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    
    # Moderation
    reports_received = models.IntegerField(default=0)
    is_banned = models.BooleanField(default=False)
    
    # Verification (Voting)
    male_votes = models.IntegerField(default=0)
    female_votes = models.IntegerField(default=0)

    @property
    def is_gender_locked(self):
        return (self.male_votes + self.female_votes) > 0

    def __str__(self):
        return f'{self.user.username}'
    
    def is_online(self):
        return timezone.now() - self.last_seen < timezone.timedelta(minutes = 5)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        try:
            img = Image.open(self.image.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.image.path)
        except:
             # Handle cases where image path is not accessible or other errors
             pass

class Report(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_sent')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received_incidents')
    reason = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.reporter} reported {self.reported_user}"
        
