from datetime import timedelta, date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json

User = get_user_model()

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=1)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 1 minute.'


DEFAULT_PRODUCTS = [
    {
        'name': 'Gentle Hydrating Cleanser',
        'category': 'cleanser',
        'description': 'A soft gel cleanser that removes daily buildup without stripping the skin barrier.',
        'suitable_skin_types': ['normal', 'dry', 'combination', 'sensitive'],
        'ingredients': 'Glycerin, Ceramides, Allantoin',
    },
    {
        'name': 'Salicylic Acid Cleanser',
        'category': 'cleanser',
        'description': 'A clarifying cleanser with salicylic acid to help clear pores and control excess oil.',
        'suitable_skin_types': ['oily', 'combination'],
        'ingredients': 'Salicylic Acid, Zinc PCA, Glycerin',
    },
    {
        'name': 'Creamy Barrier Cleanser',
        'category': 'cleanser',
        'description': 'A creamy, fragrance-free cleanser that comforts dry and reactive skin.',
        'suitable_skin_types': ['dry', 'sensitive'],
        'ingredients': 'Ceramides, Oat Extract, Glycerin',
    },
    {
        'name': 'Balancing Hydrating Toner',
        'category': 'toner',
        'description': 'A lightweight toner that adds a layer of hydration and preps skin for serums.',
        'suitable_skin_types': ['normal', 'dry', 'combination', 'oily', 'sensitive'],
        'ingredients': 'Hyaluronic Acid, Panthenol, Glycerin',
    },
    {
        'name': 'Soothing Centella Toner',
        'category': 'toner',
        'description': 'A calming toner for skin that gets red or irritated easily.',
        'suitable_skin_types': ['sensitive', 'dry'],
        'ingredients': 'Centella Asiatica, Madecassoside, Panthenol',
    },
    {
        'name': 'Vitamin C Brightening Serum',
        'category': 'serum',
        'description': 'An antioxidant serum that helps brighten dull skin and even tone over time.',
        'suitable_skin_types': ['normal', 'combination', 'oily'],
        'ingredients': 'Vitamin C, Ferulic Acid, Vitamin E',
    },
    {
        'name': 'Niacinamide 10% Serum',
        'category': 'serum',
        'description': 'A balancing serum that supports the barrier and helps refine the look of pores.',
        'suitable_skin_types': ['oily', 'combination'],
        'ingredients': 'Niacinamide, Zinc PCA, Glycerin',
    },
    {
        'name': 'Hyaluronic Acid Serum',
        'category': 'serum',
        'description': 'A hydrating serum that plumps and smooths dehydrated skin.',
        'suitable_skin_types': ['dry', 'normal', 'sensitive'],
        'ingredients': 'Hyaluronic Acid, Panthenol, Glycerin',
    },
    {
        'name': 'Oil-Free Gel Moisturizer',
        'category': 'moisturizer',
        'description': 'A lightweight gel-cream that hydrates without a heavy or greasy finish.',
        'suitable_skin_types': ['oily', 'combination'],
        'ingredients': 'Glycerin, Niacinamide, Squalane',
    },
    {
        'name': 'Barrier Repair Night Cream',
        'category': 'moisturizer',
        'description': 'A rich cream that replenishes lipids and supports overnight repair.',
        'suitable_skin_types': ['dry', 'sensitive', 'normal'],
        'ingredients': 'Ceramides, Shea Butter, Squalane',
    },
    {
        'name': 'Daily Broad Spectrum SPF 50+',
        'category': 'sunscreen',
        'description': 'A lightweight daily sunscreen that protects against UVA and UVB damage.',
        'suitable_skin_types': ['normal', 'dry', 'combination', 'oily', 'sensitive'],
        'ingredients': 'Zinc Oxide, Vitamin E, Glycerin',
    },
    {
        'name': 'BHA Exfoliant Treatment',
        'category': 'treatment',
        'description': 'A gentle exfoliating treatment that helps clear congested pores and smooth texture.',
        'suitable_skin_types': ['oily', 'combination'],
        'ingredients': 'Salicylic Acid, Witch Hazel, Green Tea',
    },
    {
        'name': 'Gentle Retinol Night Serum',
        'category': 'treatment',
        'description': 'A slow-release retinol serum for smoother texture and early signs of aging.',
        'suitable_skin_types': ['normal', 'combination', 'oily'],
        'ingredients': 'Retinol, Squalane, Niacinamide',
    },
    {
        'name': 'Hydrating Peptide Eye Cream',
        'category': 'moisturizer',
        'description': 'A cushiony eye cream that hydrates the delicate eye area.',
        'suitable_skin_types': ['normal', 'dry', 'combination', 'oily', 'sensitive'],
        'ingredients': 'Peptides, Hyaluronic Acid, Shea Butter',
    },
]

ROUTINE_BLUEPRINTS = {
    'oily': {
        'morning': [
            'Salicylic Acid Cleanser',
            'Balancing Hydrating Toner',
            'Niacinamide 10% Serum',
            'Oil-Free Gel Moisturizer',
            'Daily Broad Spectrum SPF 50+',
        ],
        'night': [
            'Salicylic Acid Cleanser',
            'BHA Exfoliant Treatment',
            'Niacinamide 10% Serum',
            'Oil-Free Gel Moisturizer',
        ],
    },
    'dry': {
        'morning': [
            'Creamy Barrier Cleanser',
            'Balancing Hydrating Toner',
            'Hyaluronic Acid Serum',
            'Barrier Repair Night Cream',
            'Daily Broad Spectrum SPF 50+',
        ],
        'night': [
            'Creamy Barrier Cleanser',
            'Hyaluronic Acid Serum',
            'Barrier Repair Night Cream',
            'Hydrating Peptide Eye Cream',
        ],
    },
    'normal': {
        'morning': [
            'Gentle Hydrating Cleanser',
            'Balancing Hydrating Toner',
            'Vitamin C Brightening Serum',
            'Oil-Free Gel Moisturizer',
            'Daily Broad Spectrum SPF 50+',
        ],
        'night': [
            'Gentle Hydrating Cleanser',
            'Gentle Retinol Night Serum',
            'Barrier Repair Night Cream',
            'Hydrating Peptide Eye Cream',
        ],
    },
    'combination': {
        'morning': [
            'Gentle Hydrating Cleanser',
            'Balancing Hydrating Toner',
            'Niacinamide 10% Serum',
            'Oil-Free Gel Moisturizer',
            'Daily Broad Spectrum SPF 50+',
        ],
        'night': [
            'Gentle Hydrating Cleanser',
            'BHA Exfoliant Treatment',
            'Barrier Repair Night Cream',
            'Hydrating Peptide Eye Cream',
        ],
    },
    'sensitive': {
        'morning': [
            'Creamy Barrier Cleanser',
            'Soothing Centella Toner',
            'Hyaluronic Acid Serum',
            'Barrier Repair Night Cream',
            'Daily Broad Spectrum SPF 50+',
        ],
        'night': [
            'Creamy Barrier Cleanser',
            'Soothing Centella Toner',
            'Barrier Repair Night Cream',
            'Hydrating Peptide Eye Cream',
        ],
    },
}

STEP_META = {
    'cleanser': {
        'instructions': 'Massage onto damp skin for about 30 seconds, then rinse with lukewarm water.',
        'tip': 'Avoid hot water, which can strip the skin barrier.',
        'duration': 1,
    },
    'toner': {
        'instructions': 'Press or pat a few drops into damp skin until absorbed.',
        'tip': 'No need to use a cotton pad - hands waste less product.',
        'duration': 1,
    },
    'serum': {
        'instructions': 'Apply 3-4 drops evenly, then follow with moisturizer.',
        'tip': 'Apply to slightly damp skin to improve absorption.',
        'duration': 2,
    },
    'moisturizer': {
        'instructions': 'Smooth a small amount over the face and neck.',
        'tip': 'Apply while skin is still slightly damp to lock in hydration.',
        'duration': 2,
    },
    'sunscreen': {
        'instructions': 'Apply generously as the final morning step. Reapply every two hours outdoors.',
        'tip': 'Do not forget ears, neck, and the backs of your hands.',
        'duration': 2,
    },
    'treatment': {
        'instructions': 'Apply a thin layer to targeted areas. Start 2-3 nights per week.',
        'tip': 'Do not mix strong actives on the same night.',
        'duration': 2,
    },
}

QUESTION_TITLES = {
    'q1': 'Skin feel after cleansing',
    'q2': 'Shininess throughout the day',
    'q3': 'Pore appearance',
    'q4': 'Breakout frequency',
    'q5': 'Reaction to new products',
    'q6': 'Skin in different weather',
    'q7': 'Main skin concern',
    'q8': 'Current skincare routine',
}

CONCERN_FROM_ANSWER = {
    'aging': 'Aging / Wrinkles',
    'dryness': 'Dryness / Dehydration',
    'oil_acne': 'Oil / Acne',
    'dark_spots': 'Dark Spots / Hyperpigmentation',
    'redness': 'Redness / Sensitivity',
    'uneven_texture': 'Uneven Texture',
}



def _reset_lock_state(request):
    request.session['failed_attempts'] = 0
    request.session['lock_time'] = None


def _get_lock_state(request):
    failed_attempts = request.session.get('failed_attempts', 0)
    lock_time = request.session.get('lock_time')

    if not lock_time:
        return failed_attempts, None

    try:
        unlock_time = timezone.datetime.fromisoformat(lock_time)
    except (TypeError, ValueError):
        _reset_lock_state(request)
        return 0, None

    if timezone.now() < unlock_time:
        remaining = int((unlock_time - timezone.now()).total_seconds())
        return failed_attempts, remaining

    _reset_lock_state(request)
    return 0, None


def _set_lock_state(request):
    lock_until = timezone.now() + LOCK_DURATION
    request.session['failed_attempts'] = MAX_FAILED_ATTEMPTS
    request.session['lock_time'] = lock_until.isoformat()
    return int(LOCK_DURATION.total_seconds())


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


def _ensure_catalog():
    """Create the default product catalog if it does not exist yet."""
    from .models import SkincareProduct

    catalog = {}
    for item in DEFAULT_PRODUCTS:
        product, _ = SkincareProduct.objects.get_or_create(
            name=item['name'],
            defaults={
                'category': item['category'],
                'description': item['description'],
                'suitable_skin_types': item['suitable_skin_types'],
                'ingredients': item['ingredients'],
                'is_active': True,
            },
        )
        catalog[product.name] = product
    return catalog


def _ensure_user_routines(user):
    """Make sure the user has a morning and evening routine with steps."""
    from .models import RoutineProgress, SkinProfile, SkincareRoutine, RoutineStep

    catalog = _ensure_catalog()
    profile, _ = SkinProfile.objects.get_or_create(user=user)
    blueprint_key = profile.skin_type if profile.skin_type in ROUTINE_BLUEPRINTS else 'normal'
    blueprint = ROUTINE_BLUEPRINTS[blueprint_key]

    routines = {}
    for routine_type, product_names in blueprint.items():
        routine = SkincareRoutine.objects.filter(
            user=user, routine_type=routine_type
        ).order_by('id').first()

        if routine is None:
            label = 'Morning Glow Routine' if routine_type == 'morning' else 'Evening Repair Routine'
            routine = SkincareRoutine.objects.create(
                user=user,
                skin_type=blueprint_key,
                name=label,
                routine_type=routine_type,
            )
        elif routine.skin_type != blueprint_key:
            routine.skin_type = blueprint_key
            routine.save(update_fields=['skin_type'])
            routine.steps.all().delete()
            RoutineProgress.objects.filter(routine=routine).delete()

        if not routine.steps.exists():
            for index, product_name in enumerate(product_names, start=1):
                product = catalog.get(product_name)
                if product is None:
                    continue
                meta = STEP_META.get(product.category, {})
                RoutineStep.objects.create(
                    routine=routine,
                    product=product,
                    step_number=index,
                    instructions=meta.get('instructions', ''),
                    duration_minutes=meta.get('duration', 1),
                    tip=meta.get('tip', ''),
                )

        routines[routine_type] = routine

    return routines


def _completion_count(routine, progress):
    if not progress or not progress.completed_steps:
        return 0
    valid_ids = {step.id for step in routine.steps.all()}
    return len(set(progress.completed_steps) & valid_ids)


def _user_routine_snapshot(user, on_date):
    """Return routines and progress information for a single date."""
    from .models import RoutineProgress, SkincareRoutine

    _ensure_user_routines(user)

    morning_routines = list(
        SkincareRoutine.objects.filter(user=user, routine_type='morning')
        .prefetch_related('steps__product')
        .order_by('id')
    )
    evening_routines = list(
        SkincareRoutine.objects.filter(user=user, routine_type='night')
        .prefetch_related('steps__product')
        .order_by('id')
    )

    all_routines = morning_routines + evening_routines
    progress_entries = RoutineProgress.objects.filter(
        user=user, routine__in=all_routines, date=on_date
    )
    progress_map = {entry.routine_id: entry for entry in progress_entries}

    for routine in all_routines:
        routine.progress = progress_map.get(routine.id)
        routine.total_steps = len(routine.steps.all())
        routine.completed_count = _completion_count(routine, routine.progress)
        routine.percent = (
            int(routine.completed_count / routine.total_steps * 100)
            if routine.total_steps
            else 0
        )
        routine.is_complete = (
            routine.total_steps > 0
            and routine.completed_count >= routine.total_steps
        )

    def summarize(routines):
        total = sum(len(r.steps.all()) for r in routines)
        completed = sum(
            _completion_count(r, progress_map.get(r.id)) for r in routines
        )
        percent = int(completed / total * 100) if total else 0
        return total, completed, percent

    morning_total, morning_completed, morning_percent = summarize(morning_routines)
    evening_total, evening_completed, evening_percent = summarize(evening_routines)
    overall_total = morning_total + evening_total
    overall_completed = morning_completed + evening_completed
    overall_percent = (
        int(overall_completed / overall_total * 100) if overall_total else 0
    )

    morning_progress = progress_map.get(morning_routines[0].id) if morning_routines else None
    evening_progress = progress_map.get(evening_routines[0].id) if evening_routines else None

    return {
        'morning_routines': morning_routines,
        'evening_routines': evening_routines,
        'morning_progress': morning_progress,
        'evening_progress': evening_progress,
        'morning_total': morning_total,
        'morning_completed': morning_completed,
        'morning_percent': morning_percent,
        'evening_total': evening_total,
        'evening_completed': evening_completed,
        'evening_percent': evening_percent,
        'overall_total': overall_total,
        'overall_completed': overall_completed,
        'overall_percent': overall_percent,
        'progress_map': progress_map,
    }


def _build_week(user, anchor_date):
    """Build a Monday-to-Sunday view of routine completion around a date."""
    from .models import RoutineProgress, SkincareRoutine

    monday = anchor_date - timedelta(days=anchor_date.weekday())
    sunday = monday + timedelta(days=6)

    morning_routines = list(
        SkincareRoutine.objects.filter(user=user, routine_type='morning')
        .prefetch_related('steps')
        .order_by('id')
    )
    evening_routines = list(
        SkincareRoutine.objects.filter(user=user, routine_type='night')
        .prefetch_related('steps')
        .order_by('id')
    )
    routines = morning_routines + evening_routines
    entries = RoutineProgress.objects.filter(
        user=user, routine__in=routines, date__range=(monday, sunday)
    )
    progress_map = {(entry.routine_id, entry.date): entry for entry in entries}

    def day_done(routine_list, day):
        if not routine_list:
            return False
        routine = routine_list[0]
        progress = progress_map.get((routine.id, day))
        if not progress:
            return False
        total = len(routine.steps.all())
        return total > 0 and _completion_count(routine, progress) >= total

    week_days = []
    for offset in range(7):
        day = monday + timedelta(days=offset)
        week_days.append({
            'date': day,
            'iso': day.isoformat(),
            'label': day.strftime('%a'),
            'number': day.day,
            'is_today': day == date.today(),
            'is_selected': day == anchor_date,
            'done_am': day_done(morning_routines, day),
            'done_pm': day_done(evening_routines, day),
        })

    return week_days, monday, sunday


def _routine_streak(user):
    from .models import RoutineProgress

    today = date.today()
    completed_dates = set(
        RoutineProgress.objects.filter(
            user=user, completed=True, date__lte=today
        ).values_list('date', flat=True)
    )
    cursor = today if today in completed_dates else today - timedelta(days=1)
    streak = 0
    while cursor in completed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _routine_days_this_month(user):
    from .models import RoutineProgress

    today = date.today()
    return (
        RoutineProgress.objects.filter(
            user=user, date__year=today.year, date__month=today.month
        )
        .values('date')
        .distinct()
        .count()
    )


def _split_concerns(value):
    if not value:
        return []
    items = []
    for chunk in value.replace('\r', '\n').replace(',', '\n').split('\n'):
        cleaned = chunk.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    failed_attempts, remaining = _get_lock_state(request)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is not None:
        _reset_lock_state(request)
        login(request, user)
        return redirect('dashboard')

    failed_attempts += 1
    request.session['failed_attempts'] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        remaining = _set_lock_state(request)
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def home(request):
    from .models import SkinAnalysis, SkinProfile, SkincareProduct

    profile, _ = SkinProfile.objects.get_or_create(user=request.user)
    latest_analysis = (
        SkinAnalysis.objects.filter(user=request.user)
        .order_by('-created_at')
        .first()
    )
    snapshot = _user_routine_snapshot(request.user, date.today())
    total_assessments = SkinAnalysis.objects.filter(user=request.user).count()
    concerns_value = profile.concerns or (latest_analysis.notes if latest_analysis else '')
    concerns = _split_concerns(concerns_value)

    hour = timezone.localtime().hour
    if hour < 12:
        greeting = 'Good Morning'
    elif hour < 18:
        greeting = 'Good Afternoon'
    else:
        greeting = 'Good Evening'

    context = {
        'profile': profile,
        'skin_type_display': (
            profile.get_skin_type_display()
            if profile.skin_type != 'unknown'
            else 'Not Yet Identified'
        ),
        'latest_analysis': latest_analysis,
        'concerns': concerns,
        'greeting': greeting,
        'total_assessments': total_assessments,
        'routine_days_this_month': _routine_days_this_month(request.user),
        'routine_streak': _routine_streak(request.user),
        'recommended_products': SkincareProduct.objects.filter(is_active=True).count(),
        'today': date.today(),
        **snapshot,
    }
    return render(request, 'home.html', context)


@login_required(login_url='login')
def skin_analysis(request):
    if request.method == 'POST':
        # Handle questionnaire submission
        answers = {}
        for key, value in request.POST.items():
            if key.startswith('q'):
                answers[key] = value
        
        # Simple skin type determination logic
        skin_type = determine_skin_type(answers)
        
        # Save to SkinAnalysis
        from .models import SkinAnalysis, SkinProfile
        analysis = SkinAnalysis.objects.create(
            user=request.user,
            method='questionnaire',
            identified_skin_type=skin_type,
            answers=answers,
        )
        
        # Update or create SkinProfile
        profile, created = SkinProfile.objects.get_or_create(
            user=request.user,
            defaults={'skin_type': skin_type}
        )
        if not created:
            profile.skin_type = skin_type

        main_concern = CONCERN_FROM_ANSWER.get(answers.get('q7', ''))
        if main_concern:
            existing = _split_concerns(profile.concerns)
            if main_concern not in existing:
                existing.insert(0, main_concern)
            profile.concerns = ', '.join(existing[:6])
        profile.save()

        _ensure_user_routines(request.user)
        
        messages.success(request, f'Skin analysis complete! Your skin type is {skin_type.title()}.')
        return redirect('my_recommendations')
    
    return render(request, 'skin_analysis.html')


def determine_skin_type(answers):
    """Score questionnaire answers to identify the most likely skin type."""
    scores = {
        'oily': 0,
        'dry': 0,
        'combination': 0,
        'sensitive': 0,
        'normal': 0,
    }

    oily_values = {
        'very_oily', 'always_oily', 'often_oily', 'enlarged', 'large_visible',
        'clogged', 'frequent', 'hormonal', 'oily_summer', 'oil_acne',
    }
    dry_values = {
        'tight_dry', 'never_dry', 'small_invisible', 'dry_winter', 'flaky',
        'dryness',
    }
    combination_values = {
        'mixed', 'tzone_shiny', 'tzone_large', 'combination_weather', 'slightly_oily',
    }
    sensitive_values = {
        'sensitive', 'sensitive_acne', 'very_sensitive', 'mild_reaction',
        'breaks_out', 'sensitive_weather', 'redness',
    }
    normal_values = {
        'comfortable_normal', 'normal', 'rare_never', 'stable', 'tolerates_well',
        'rarely', 'occasional',
    }

    for key, raw_value in answers.items():
        value = str(raw_value).lower()
        if value in oily_values:
            scores['oily'] += 2
        if value in dry_values:
            scores['dry'] += 2
        if value in combination_values:
            scores['combination'] += 2
        if value in sensitive_values:
            scores['sensitive'] += 2
        if value in normal_values:
            scores['normal'] += 1
        if 'oily' in value:
            scores['oily'] += 1
        if 'dry' in value:
            scores['dry'] += 1
        if 'sensitive' in value or 'irritat' in value:
            scores['sensitive'] += 1

    scores['normal'] += 1
    return max(scores, key=scores.get)


@login_required(login_url='login')
def my_recommendations(request):
    from .models import SkinProfile, SkinAnalysis, SkincareProduct, SkincareRoutine

    profile, _ = SkinProfile.objects.get_or_create(user=request.user)
    latest_analysis = (
        SkinAnalysis.objects.filter(user=request.user)
        .order_by('-created_at')
        .first()
    )

    _ensure_user_routines(request.user)

    # Get routines for the user by type
    morning_routines = SkincareRoutine.objects.filter(
        user=request.user, routine_type='morning'
    ).prefetch_related('steps__product')
    evening_routines = SkincareRoutine.objects.filter(
        user=request.user, routine_type='night'
    ).prefetch_related('steps__product')

    # Collect recommended ingredients from products in routines
    recommended_ingredients_set = set()
    for routine in list(morning_routines) + list(evening_routines):
        for step in routine.steps.all():
            prod = step.product
            if prod.ingredients:
                # Split by comma/newline for a cleaner list
                for ing in prod.ingredients.replace('\n', ',').split(','):
                    ing_clean = ing.strip()
                    if ing_clean:
                        recommended_ingredients_set.add(ing_clean)

    recommended_ingredients = sorted(list(recommended_ingredients_set))[:12]

    # Build AI explanations and tips
    skin_type_display = profile.get_skin_type_display() if profile.skin_type != 'unknown' else 'Not Yet Identified'
    concerns = profile.concerns or (latest_analysis.notes if latest_analysis and latest_analysis.notes else '')

    ai_explanations = [
        f"Your skin type is identified as {skin_type_display}. Our system tailors product selection to balance your skin's unique needs.",
        "We prioritize gentle actives and barrier-supporting ingredients to minimize irritation while addressing your concerns.",
        "Consistency is key - following AM/PM routines helps maintain hydration and protection throughout the day.",
    ]

    personalized_tips = [
        "Always apply sunscreen as the last step of your morning routine.",
        "Patch test new products on a small area before full application.",
        "Stay hydrated and maintain a balanced diet to support skin health.",
        "Adjust your routine with seasons - your skin may need more moisture in winter.",
    ]

    important_notes = [
        "If you experience persistent irritation, discontinue use and consult a dermatologist.",
        "Introduce new actives (like exfoliants/retinoids) gradually, 1-2 times per week.",
        "Store products away from direct sunlight to maintain efficacy.",
    ]

    context = {
        'profile': profile,
        'latest_analysis': latest_analysis,
        'skin_type_display': skin_type_display,
        'concerns': concerns,
        'morning_routines': morning_routines,
        'evening_routines': evening_routines,
        'recommended_ingredients': recommended_ingredients,
        'ai_explanations': ai_explanations,
        'personalized_tips': personalized_tips,
        'important_notes': important_notes,
    }
    return render(request, 'my_recommendations.html', context)


@login_required(login_url='login')
def routine_planner(request):
    from .models import (
        SkinAnalysis,
        SkinProfile,
        SkincareProduct,
        SkincareRoutine,
        RoutineProgress,
    )

    selected_date = parse_date(request.GET.get('date', '')) or date.today()
    profile, _ = SkinProfile.objects.get_or_create(user=request.user)
    latest_analysis = (
        SkinAnalysis.objects.filter(user=request.user)
        .order_by('-created_at')
        .first()
    )

    snapshot = _user_routine_snapshot(request.user, selected_date)
    week_days, week_start, week_end = _build_week(request.user, selected_date)
    streak = _routine_streak(request.user)

    # Ensure progress rows exist for today so toggling has something to update.
    if selected_date == date.today():
        for routine in snapshot['morning_routines'] + snapshot['evening_routines']:
            RoutineProgress.objects.get_or_create(
                user=request.user, routine=routine, date=selected_date
            )

    routine_notes = []
    for routine in snapshot['morning_routines'] + snapshot['evening_routines']:
        for step in routine.steps.all():
            if step.tip:
                routine_notes.append({
                    'product': step.product.name,
                    'tip': step.tip,
                })
    routine_notes = routine_notes[:4]

    skin_type_display = (
        profile.get_skin_type_display()
        if profile.skin_type != 'unknown'
        else 'Not Yet Identified'
    )
    concerns = profile.concerns or (
        latest_analysis.notes if latest_analysis and latest_analysis.notes else ''
    )

    context = {
        'profile': profile,
        'skin_type_display': skin_type_display,
        'concerns': concerns,
        'selected_date': selected_date,
        'week_days': week_days,
        'week_start': week_start,
        'week_end': week_end,
        'routine_streak': streak,
        'streak_percent': min(int(streak / 7 * 100), 100),
        'routine_notes': routine_notes,
        'all_products': SkincareProduct.objects.filter(is_active=True).order_by(
            'category', 'name'
        ),
        'today': date.today(),
        **snapshot,
    }
    return render(request, 'routine_planner.html', context)


@login_required(login_url='login')
def assessment_history(request):
    from .models import SkinAnalysis

    user = request.user
    analyses = (
        SkinAnalysis.objects.filter(user=user)
        .order_by('-created_at')
    )

    total_assessments = analyses.count()
    latest_analysis = analyses.first()

    # Calculate most common skin type
    skin_type_counts = {}
    for analysis in analyses:
        st = analysis.identified_skin_type
        if st:
            skin_type_counts[st] = skin_type_counts.get(st, 0) + 1

    most_common_skin_type = None
    most_common_count = 0
    for st, count in skin_type_counts.items():
        if count > most_common_count:
            most_common_count = count
            most_common_skin_type = st

    # Get display names
    skin_type_display_map = dict(SkinAnalysis._meta.get_field('identified_skin_type').choices)
    latest_skin_type_display = (
        skin_type_display_map.get(latest_analysis.identified_skin_type)
        if latest_analysis
        else None
    )
    most_common_skin_type_display = (
        skin_type_display_map.get(most_common_skin_type)
        if most_common_skin_type
        else None
    )

    # Prepare chart data
    chart_data = []
    for analysis in analyses.order_by('created_at'):
        chart_data.append({
            'date': analysis.created_at.strftime('%Y-%m-%d'),
            'skin_type': analysis.identified_skin_type,
            'skin_type_display': skin_type_display_map.get(analysis.identified_skin_type, analysis.identified_skin_type),
        })

    # Generate journey explanation
    journey_explanation = None
    if total_assessments == 0:
        journey_explanation = "No assessments yet. Start your first skin analysis to begin tracking your skin journey."
    elif total_assessments == 1:
        journey_explanation = "This is your first assessment. Take more assessments over time to see how your skin type evolves with changes in your routine and environment."
    else:
        # Check if skin type changed
        skin_types_sequence = [a.identified_skin_type for a in analyses.order_by('created_at')]
        if len(set(skin_types_sequence)) == 1:
            journey_explanation = f"Your skin type has remained consistent as {skin_type_display_map.get(skin_types_sequence[0])} across your assessments. Consistency suggests your current routine is working well for you."
        else:
            journey_explanation = f"Your skin type has changed across assessments, showing how your skin responds to different factors over time. It's normal for skin conditions to evolve due to skincare habits, environment, stress, and other influences."

    context = {
        'assessments': analyses,
        'total_assessments': total_assessments,
        'latest_analysis': latest_analysis,
        'latest_skin_type_display': latest_skin_type_display,
        'most_common_skin_type_display': most_common_skin_type_display,
        'most_common_count': most_common_count,
        'chart_data': chart_data,
        'journey_explanation': journey_explanation,
        'skin_type_categories': ['Oily', 'Combination', 'Normal', 'Dry', 'Sensitive'],
    }
    return render(request, 'assessment_history.html', context)


@login_required(login_url='login')
def assessment_detail(request, pk):
    from .models import SkinAnalysis

    analysis = SkinAnalysis.objects.filter(user=request.user, pk=pk).first()
    if not analysis:
        messages.error(request, 'Assessment not found.')
        return redirect('assessment_history')

    skin_type_display_map = dict(SkinAnalysis._meta.get_field('identified_skin_type').choices)
    answer_rows = []
    if analysis.answers:
        for key in sorted(analysis.answers.keys()):
            raw_value = analysis.answers.get(key, '')
            display_value = str(raw_value).replace('_', ' ').title()
            answer_rows.append({
                'key': key,
                'question': QUESTION_TITLES.get(key, key.upper()),
                'answer': display_value,
            })

    context = {
        'analysis': analysis,
        'skin_type_display': skin_type_display_map.get(analysis.identified_skin_type),
        'answer_rows': answer_rows,
    }
    return render(request, 'assessment_detail.html', context)


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def assessment_compare(request):
    from .models import SkinAnalysis

    analyses = SkinAnalysis.objects.filter(user=request.user).order_by('-created_at')

    if request.method == 'POST':
        pk1 = request.POST.get('analysis1')
        pk2 = request.POST.get('analysis2')
        a1 = analyses.filter(pk=pk1).first()
        a2 = analyses.filter(pk=pk2).first()
        if not a1 or not a2 or a1.pk == a2.pk:
            messages.error(request, 'Please select two different assessments to compare.')
            return render(request, 'assessment_compare.html', {'assessments': analyses})
        skin_type_display_map = dict(SkinAnalysis._meta.get_field('identified_skin_type').choices)
        return render(request, 'assessment_compare.html', {
            'assessments': analyses,
            'a1': a1,
            'a2': a2,
            'skin_type_display_map': skin_type_display_map,
        })

    return render(request, 'assessment_compare.html', {'assessments': analyses})


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def my_profile(request):
    from .models import SkinProfile, UserProfile, UserPreferences

    profile, _ = SkinProfile.objects.get_or_create(user=request.user)
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    preferences, _ = UserPreferences.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'update_account':
            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            errors = []

            if not username:
                errors.append('Username is required.')
            elif (
                User.objects.exclude(pk=request.user.pk)
                .filter(username=username)
                .exists()
            ):
                errors.append('That username is already taken.')

            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    errors.append('Enter a valid email address.')
                else:
                    if (
                        User.objects.exclude(pk=request.user.pk)
                        .filter(email=email)
                        .exists()
                    ):
                        errors.append('That email is already registered.')

            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                request.user.username = username
                request.user.first_name = first_name
                request.user.last_name = last_name
                request.user.email = email
                request.user.save()
                messages.success(request, 'Your account information has been updated.')
            return redirect('my_profile')

        if action == 'change_password':
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            errors = []

            if not current_password or not request.user.check_password(current_password):
                errors.append('Your current password is incorrect.')
            if not new_password:
                errors.append('A new password is required.')
            else:
                try:
                    validate_password(new_password, request.user)
                except ValidationError as exc:
                    errors.extend(exc.messages)
            if new_password != confirm_password:
                errors.append('The new passwords do not match.')

            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Your password has been changed.')
            return redirect('my_profile')

        if action == 'update_skin':
            skin_type = request.POST.get('skin_type', '')
            valid_types = {choice[0] for choice in SkinProfile.SKIN_TYPES}
            if skin_type in valid_types:
                profile.skin_type = skin_type
            profile.concerns = request.POST.get('concerns', '').strip()
            profile.sensitivities = request.POST.get('sensitivities', '').strip()
            profile.skincare_goals = request.POST.get('skincare_goals', '').strip()
            profile.save()
            messages.success(request, 'Your skin profile has been updated.')
            return redirect('my_profile')

        if action == 'update_avatar':
            avatar = request.FILES.get('avatar')
            if avatar:
                user_profile.avatar = avatar
                user_profile.save()
                messages.success(request, 'Your profile photo has been updated.')
            else:
                messages.error(request, 'Please choose an image to upload.')
            return redirect('my_profile')

    context = {
        'profile': profile,
        'user_profile': user_profile,
        'preferences': preferences,
        'skin_type_choices': SkinProfile.SKIN_TYPES,
    }
    return render(request, 'my_profile.html', context)


@login_required(login_url='login')
@require_http_methods(['POST'])
def toggle_step_completion(request):
    from .models import SkincareRoutine, RoutineProgress

    try:
        data = json.loads(request.body)
        routine_id = data.get('routine_id')
        step_id = data.get('step_id')
        completed = bool(data.get('completed', False))
        on_date = parse_date(data.get('date') or '') or date.today()

        routine = SkincareRoutine.objects.filter(
            id=routine_id, user=request.user
        ).first()
        if routine is None:
            return JsonResponse(
                {'success': False, 'error': 'Routine not found.'}, status=404
            )

        try:
            step_id = int(step_id)
        except (TypeError, ValueError):
            return JsonResponse(
                {'success': False, 'error': 'Invalid step.'}, status=400
            )

        if not routine.steps.filter(id=step_id).exists():
            return JsonResponse(
                {'success': False, 'error': 'Step does not belong to this routine.'},
                status=400,
            )

        progress, _ = RoutineProgress.objects.get_or_create(
            user=request.user,
            routine=routine,
            date=on_date,
            defaults={'completed_steps': []},
        )

        completed_steps = [
            int(step) for step in (progress.completed_steps or [])
            if str(step).isdigit()
        ]
        if completed and step_id not in completed_steps:
            completed_steps.append(step_id)
        elif not completed and step_id in completed_steps:
            completed_steps = [step for step in completed_steps if step != step_id]

        total_steps = routine.steps.count()
        progress.completed_steps = completed_steps
        progress.completed = total_steps > 0 and len(completed_steps) >= total_steps
        progress.save()

        percent = int(len(completed_steps) / total_steps * 100) if total_steps else 0
        return JsonResponse({
            'success': True,
            'completed': len(completed_steps),
            'total': total_steps,
            'percent': percent,
            'all_done': progress.completed,
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@login_required(login_url='login')
@require_http_methods(['POST'])
def update_preferences(request):
    from .models import UserPreferences

    try:
        data = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'}, status=400)

    field = data.get('field')
    value = data.get('value')
    allowed_fields = {'email_notifications', 'push_notifications', 'data_sharing', 'profile_visibility', 'theme'}
    if field not in allowed_fields:
        return JsonResponse({'success': False, 'error': 'Unknown preference.'}, status=400)

    if field in {'email_notifications', 'push_notifications', 'data_sharing'}:
        value = bool(value)
    elif field == 'profile_visibility' and value not in {'public', 'private'}:
        return JsonResponse({'success': False, 'error': 'Invalid profile visibility.'}, status=400)
    elif field == 'theme' and value not in {'light', 'dark'}:
        return JsonResponse({'success': False, 'error': 'Invalid theme.'}, status=400)

    preferences, _ = UserPreferences.objects.get_or_create(user=request.user)
    setattr(preferences, field, value)
    preferences.save()

    return JsonResponse({'success': True, 'field': field, 'value': value})


@login_required(login_url='login')
@require_http_methods(['POST'])
def add_routine_step(request):
    from .models import SkincareProduct, SkincareRoutine, RoutineStep

    try:
        data = json.loads(request.body)
        routine = SkincareRoutine.objects.filter(
            id=data.get('routine_id'), user=request.user
        ).first()
        product = SkincareProduct.objects.filter(
            id=data.get('product_id'), is_active=True
        ).first()

        if routine is None:
            return JsonResponse(
                {'success': False, 'error': 'Routine not found.'}, status=404
            )
        if product is None:
            return JsonResponse(
                {'success': False, 'error': 'Please choose a product.'}, status=400
            )

        last_number = (
            routine.steps.order_by('-step_number')
            .values_list('step_number', flat=True)
            .first()
            or 0
        )
        try:
            duration = max(1, min(int(data.get('duration_minutes', 1)), 120))
        except (TypeError, ValueError):
            duration = 1

        step = RoutineStep.objects.create(
            routine=routine,
            product=product,
            step_number=last_number + 1,
            instructions=(data.get('instructions') or '').strip(),
            duration_minutes=duration,
            tip=(data.get('tip') or '').strip(),
        )

        return JsonResponse({
            'success': True,
            'step_id': step.id,
            'step_number': step.step_number,
            'product': product.name,
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )
    login(request, user)
    return redirect('dashboard')
