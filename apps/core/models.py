#from django.db import models

# Create your models here.


from django.conf import settings
from django.db import models
from django.utils import timezone


class SkinProfile(models.Model):
    SKIN_TYPES = [
        ("oily", "Oily"),
        ("dry", "Dry"),
        ("normal", "Normal"),
        ("combination", "Combination"),
        ("sensitive", "Sensitive"),
        ("unknown", "Not Yet Identified"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="skin_profile",
    )
    skin_type = models.CharField(
        max_length=20,
        choices=SKIN_TYPES,
        default="unknown",
    )
    concerns = models.TextField(blank=True)
    sensitivities = models.TextField(blank=True)
    skincare_goals = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} - {self.get_skin_type_display()}"


class SkinAnalysis(models.Model):
    METHODS = [
        ("questionnaire", "Questionnaire"),
        ("camera", "Camera / Photo"),
        ("assistant", "AI Assistant"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="skin_analyses",
    )
    method = models.CharField(max_length=20, choices=METHODS)
    identified_skin_type = models.CharField(
        max_length=20,
        choices=SkinProfile.SKIN_TYPES,
    )
    answers = models.JSONField(default=dict, blank=True)
    image = models.ImageField(
        upload_to="skin_analysis/",
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.method} - {self.identified_skin_type}"


class SkincareProduct(models.Model):
    CATEGORIES = [
        ("cleanser", "Cleanser"),
        ("toner", "Toner"),
        ("serum", "Serum"),
        ("moisturizer", "Moisturizer"),
        ("sunscreen", "Sunscreen"),
        ("treatment", "Treatment"),
    ]

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    description = models.TextField()
    suitable_skin_types = models.JSONField(default=list, blank=True)
    ingredients = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SkincareRoutine(models.Model):
    ROUTINE_TYPES = [
        ("morning", "Morning"),
        ("night", "Night"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="skincare_routines",
    )
    skin_type = models.CharField(
        max_length=20,
        choices=SkinProfile.SKIN_TYPES,
    )
    name = models.CharField(max_length=150)
    routine_type = models.CharField(
        max_length=10,
        choices=ROUTINE_TYPES,
    )
    products = models.ManyToManyField(
        SkincareProduct,
        through="RoutineStep",
        related_name="routines",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.routine_type}"


class RoutineStep(models.Model):
    routine = models.ForeignKey(
        SkincareRoutine,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    product = models.ForeignKey(
        SkincareProduct,
        on_delete=models.CASCADE,
        related_name="routine_steps",
    )
    step_number = models.PositiveIntegerField()
    instructions = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=1)
    tip = models.TextField(blank=True)

    class Meta:
        ordering = ["step_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["routine", "step_number"],
                name="unique_routine_step_number",
            )
        ]

    def __str__(self):
        return f"{self.routine.name} - Step {self.step_number}"


class RoutineProgress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="routine_progress",
    )
    routine = models.ForeignKey(
        SkincareRoutine,
        on_delete=models.CASCADE,
        related_name="progress_entries",
    )
    date = models.DateField(default=timezone.now)
    completed_steps = models.JSONField(default=list, blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["user", "routine", "date"]]

    def __str__(self):
        return f"{self.user} - {self.routine.name} - {self.date}"


# Import timezone for RoutineProgress
from django.utils import timezone


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_profile',
    )
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    location = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} - Profile'



class DailyCheckIn(models.Model):
    """A user's daily skin condition check-in (condition, not skin type)."""

    CONDITION_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('average', 'Average'),
        ('rough', 'Rough'),
        ('irritated', 'Irritated'),
        ('breaking_out', 'Breaking Out'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_check_ins',
    )
    date = models.DateField(default=timezone.localdate)
    skin_condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default='average',
    )
    oiliness = models.PositiveSmallIntegerField(default=1)
    dryness = models.PositiveSmallIntegerField(default=1)
    acne_level = models.PositiveSmallIntegerField(default=1)
    irritation = models.PositiveSmallIntegerField(default=1)
    morning_completed = models.BooleanField(default=False)
    evening_completed = models.BooleanField(default=False)
    products_used = models.TextField(blank=True)
    ingredients_used = models.TextField(blank=True)
    photo = models.ImageField(
        upload_to='skin_progress/photos/',
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'date'],
                name='unique_daily_checkin_per_day',
            )
        ]

    def __str__(self):
        return f'{self.user} - {self.date} - {self.get_skin_condition_display()}'


class IngredientExperience(models.Model):
    """A user's personal observation about an ingredient they used."""

    OUTCOME_CHOICES = [
        ('improvement', 'Improvement noticed'),
        ('no_change', 'No noticeable change'),
        ('irritation', 'Irritation or unwanted reaction'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ingredient_experiences',
    )
    ingredient = models.CharField(max_length=150)
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - {self.ingredient} - {self.get_outcome_display()}'


class UserPreferences(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    theme = models.CharField(max_length=10, default='light', choices=[('light', 'Light'), ('dark', 'Dark')])
    profile_visibility = models.CharField(max_length=20, default='private', choices=[('public', 'Public'), ('private', 'Private')])
    data_sharing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} - Preferences'

