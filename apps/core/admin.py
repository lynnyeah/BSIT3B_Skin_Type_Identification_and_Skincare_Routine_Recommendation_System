# Register your models here

from django.contrib import admin

from .models import (
    SkinProfile,
    SkinAnalysis,
    SkincareProduct,
    SkincareRoutine,
    RoutineStep,
    RoutineProgress,
)


admin.site.register(SkinProfile)
admin.site.register(SkinAnalysis)
admin.site.register(SkincareProduct)
admin.site.register(SkincareRoutine)
admin.site.register(RoutineStep)
admin.site.register(RoutineProgress)
