from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Info  # Ensure this matches your notification/info model name

def home(request):
    return render(request, 'index.html')


@login_required
def notifications_view(request):
    # Fetch notifications for the logged-in user
    user_notifications = Info.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'notifications': user_notifications,
    }
    return render(request, 'notifications.html', context)


@login_required
def mark_notification_as_read(request, pk):
    notification = get_object_or_404(Info, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('notifications')