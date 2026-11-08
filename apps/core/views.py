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

# What each common skincare ingredient does, for the plain-language
# explanations shown on the My Routine page.
INGREDIENT_PURPOSES = {
    'Glycerin': 'Draws water into the skin and keeps it hydrated.',
    'Ceramides': 'Repair and strengthen the skin barrier.',
    'Allantoin': 'Soothes rough or irritated skin and supports healing.',
    'Salicylic Acid': 'Gently exfoliates inside pores to clear oil and blackheads.',
    'Zinc PCA': 'Controls excess oil and calms redness.',
    'Oat Extract': 'Comforts dry, itchy, or easily irritated skin.',
    'Hyaluronic Acid': 'Plumps and deeply hydrates without feeling heavy.',
    'Panthenol': 'Pro-vitamin B5 that soothes and supports skin repair.',
    'Centella Asiatica': 'Calms redness and helps stressed skin recover.',
    'Madecassoside': 'Soothes irritation from centella and supports healing.',
    'Vitamin C': 'Brightens dull skin and evens out tone.',
    'Ferulic Acid': 'Antioxidant that keeps vitamin C stable and effective.',
    'Vitamin E': 'Antioxidant that protects and conditions the skin.',
    'Niacinamide': 'Balances oil, refines pores, and supports the skin barrier.',
    'Squalane': 'Lightweight lipid that softens and seals in moisture.',
    'Shea Butter': 'Rich moisturizer for dry, tight skin.',
    'Zinc Oxide': 'Mineral filter that protects against UVA/UVB damage.',
    'Witch Hazel': 'Mild plant extract that helps control oil and tighten pores.',
    'Green Tea': 'Antioxidant that helps calm oiliness and redness.',
    'Retinol': 'Smooths texture and softens fine lines over time.',
    'Peptides': 'Support firmness and hydrate the delicate eye area.',
}


def _ingredient_details(user):
    """Ingredients from the user's routines with a short purpose each."""
    from .models import SkincareRoutine

    details = {}
    for routine in SkincareRoutine.objects.filter(
        user=user
    ).prefetch_related('steps__product'):
        for step in routine.steps.all():
            if not step.product.ingredients:
                continue
            for name in step.product.ingredients.replace('\n', ',').split(','):
                name = name.strip()
                if not name:
                    continue
                if name not in details:
                    details[name] = {
                        'name': name,
                        'purpose': INGREDIENT_PURPOSES.get(
                            name, 'Keeps your routine gentle and effective.'
                        ),
                    }
    return list(details.values())[:12]


QUESTION_TITLES = {
    'q1': 'Skin feel after cleansing',
    'q2': 'Shininess throughout the day',
    'q3': 'Pore appearance',
    'q4': 'Breakout frequency',
    'q5': 'Reaction to new products',
    'q6': 'Skin in different weather',
    'q7': 'Main skin concern',
    'q8': 'Current skincare routine',
    'ai_primary_skin_type': 'AI estimate: primary skin type',
    'ai_sensitivity_level': 'AI estimate: sensitivity level',
    'ai_summary': 'AI summary',
    'ai_observations': 'Observations from the conversation',
    'ai_morning_routine': 'Suggested morning routine',
    'ai_evening_routine': 'Suggested evening routine',
    'ai_ingredients': 'Ingredients to look for',
    'ai_precautions': 'Precautions',
    'ai_follow_up': 'Follow-up questions',
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
    from .models import SkinAnalysis, SkinProfile

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
        return redirect('routine_planner')

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
def my_recommendations_redirect(request):
    """The old My Recommendations page was combined into My Routine."""
    return redirect('routine_planner')


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
        'ingredient_details': _ingredient_details(request.user),
        'routine_tips': [
            'Always apply sunscreen as the last step of your morning routine.',
            'Patch test new products on a small area before full application.',
            'Stay hydrated and maintain a balanced diet to support skin health.',
            'Adjust your routine with seasons. Your skin may need more moisture in winter.',
        ],
        'important_notes': [
            'If you experience persistent irritation, discontinue use and consult a dermatologist.',
            'Introduce new actives (like exfoliants or retinoids) gradually, 1-2 times per week.',
        ],
        'today': date.today(),
        **snapshot,
    }
    return render(request, 'routine_planner.html', context)


# ---------------------------------------------------------------------------
# Skin Progress History
# ---------------------------------------------------------------------------

CHECKIN_RATING_FIELDS = ['oiliness', 'dryness', 'acne_level', 'irritation']

RATING_DESCRIPTIONS = {
    1: '1 - None / Very low',
    2: '2 - Mild',
    3: '3 - Moderate',
    4: '4 - Noticeable',
    5: '5 - Severe / Very high',
}

CONDITION_SCORES = {
    'excellent': 5,
    'good': 4,
    'average': 3,
    'rough': 2,
    'irritated': 2,
    'breaking_out': 2,
}

ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_PHOTO_SIZE_MB = 5


def _parse_range(request):
    """Return (range_key, range_start) from ?range= 7 | 30 | 90 | all."""
    key = request.GET.get('range', '30')
    days = {'7': 7, '30': 30, '90': 90}.get(key)
    if days:
        return days, date.today() - timedelta(days=days - 1)
    return 'all', None


def _checkin_streak(user):
    """Count consecutive days (ending today or yesterday) with a check-in."""
    from .models import DailyCheckIn

    checkin_dates = set(
        DailyCheckIn.objects.filter(user=user).values_list('date', flat=True)
    )
    today = date.today()
    cursor = today if today in checkin_dates else today - timedelta(days=1)
    streak = 0
    while cursor in checkin_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _routine_consistency(user, start_date=None):
    """Average percentage of routine steps completed by the user."""
    from .models import RoutineProgress, SkincareRoutine

    entries = RoutineProgress.objects.filter(user=user)
    if start_date:
        entries = entries.filter(date__gte=start_date)
    if not entries.exists():
        return None

    step_counts = {
        routine.id: routine.steps.count()
        for routine in SkincareRoutine.objects.filter(user=user)
    }
    total_done = 0
    total_steps = 0
    for entry in entries:
        count = step_counts.get(entry.routine_id, 0)
        if not count:
            continue
        completed = min(len(entry.completed_steps or []), count)
        total_done += completed
        total_steps += count
    if not total_steps:
        return None
    return int(total_done / total_steps * 100)


def _build_progress_calendar(user, anchor):
    """Build a Monday-first month grid marked with check-in/completion flags."""
    from .models import DailyCheckIn, RoutineProgress, SkincareRoutine

    import calendar

    month_range = calendar.monthrange(anchor.year, anchor.month)
    first_day = date(anchor.year, anchor.month, 1)
    last_day = date(anchor.year, anchor.month, month_range[1])

    checkin_days = set(
        DailyCheckIn.objects.filter(user=user, date__range=(first_day, last_day))
        .values_list('date', flat=True)
    )
    photo_days = set(
        DailyCheckIn.objects.filter(
            user=user, date__range=(first_day, last_day)
        )
        .exclude(photo='')
        .exclude(photo__isnull=True)
        .values_list('date', flat=True)
    )

    routine_ids = list(
        SkincareRoutine.objects.filter(user=user).values_list('id', flat=True)
    )
    routine_days = set()
    if routine_ids:
        entries = RoutineProgress.objects.filter(
            user=user, routine_id__in=routine_ids,
            date__range=(first_day, last_day), completed=True,
        )
        step_counts = {
            routine.id: routine.steps.count()
            for routine in SkincareRoutine.objects.filter(user=user)
        }
        for entry in entries:
            if step_counts.get(entry.routine_id, 0) and len(
                entry.completed_steps or []
            ) >= step_counts[entry.routine_id]:
                routine_days.add(entry.date)

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(
        anchor.year, anchor.month
    )
    today = date.today()
    calendar_weeks = []
    for week in weeks:
        row = []
        for day_number in week:
            if day_number == 0:
                row.append(None)
                continue
            day = date(anchor.year, anchor.month, day_number)
            row.append({
                'date': day,
                'iso': day.isoformat(),
                'number': day_number,
                'is_today': day == today,
                'is_future': day > today,
                'has_checkin': day in checkin_days,
                'has_photo': day in photo_days,
                'routine_done': day in routine_days,
            })
        calendar_weeks.append(row)

    prev_month = (first_day - timedelta(days=1))
    next_month = last_day + timedelta(days=1)
    return {
        'anchor': anchor,
        'month_label': anchor.strftime('%B %Y'),
        'weeks': calendar_weeks,
        'prev_month': prev_month.strftime('%Y-%m'),
        'next_month': next_month.strftime('%Y-%m'),
    }


def _recommended_ingredients(user):
    """Ingredients from products used in the user's routines."""
    from .models import SkincareRoutine

    ingredients_set = set()
    routines = SkincareRoutine.objects.filter(
        user=user
    ).prefetch_related('steps__product')
    for routine in routines:
        for step in routine.steps.all():
            if step.product.ingredients:
                for ing in step.product.ingredients.replace('\n', ',').split(','):
                    cleaned = ing.strip()
                    if cleaned:
                        ingredients_set.add(cleaned)
    return sorted(ingredients_set)[:24]


def _validate_progress_photo(upload):
    """Validate an optional skin progress photo. Returns an error or None."""
    if upload is None:
        return None
    import os

    from PIL import Image

    max_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
    if upload.size > max_bytes:
        return f'Photo is too large. Maximum size is {MAX_PHOTO_SIZE_MB}MB.'
    extension = os.path.splitext(upload.name or '')[1].lower()
    if extension not in ALLOWED_PHOTO_EXTENSIONS:
        return 'Photo must be a JPG, PNG, or WEBP image.'
    try:
        Image.open(upload).verify()
    except Exception:
        return 'That file does not look like a valid image.'
    finally:
        try:
            upload.seek(0)
        except Exception:
            pass
    return None


def _timeline_events(user, range_start):
    """Merge assessments and check-ins into one chronological timeline."""
    from .models import DailyCheckIn, SkinAnalysis

    events = []
    analyses = SkinAnalysis.objects.filter(user=user).order_by('created_at')
    for analysis in analyses:
        local_time = timezone.localtime(analysis.created_at)
        events.append({
            'kind': 'assessment',
            'date': local_time.date(),
            'datetime': local_time,
            'analysis': analysis,
        })

    checkins = DailyCheckIn.objects.filter(user=user)
    if range_start:
        checkins = checkins.filter(date__gte=range_start)
    for checkin in checkins:
        events.append({
            'kind': 'checkin',
            'date': checkin.date,
            'datetime': checkin.created_at,
            'checkin': checkin,
        })

    events.sort(key=lambda e: e['datetime'], reverse=True)
    return events


@login_required(login_url='login')
def skin_progress_history(request):
    """Skin Progress History dashboard (was Assessment History)."""
    from .models import DailyCheckIn, IngredientExperience, SkinAnalysis, SkinProfile

    user = request.user
    profile, _ = SkinProfile.objects.get_or_create(user=user)
    range_key, range_start = _parse_range(request)
    today = date.today()

    all_checkins = DailyCheckIn.objects.filter(user=user)
    latest_checkin = all_checkins.first()
    analyses = SkinAnalysis.objects.filter(user=user).order_by('-created_at')
    latest_analysis = analyses.first()

    # Most common identified skin type across all assessments (milestones).
    skin_type_counts = {}
    for analysis in analyses:
        skin_type_counts[analysis.identified_skin_type] = (
            skin_type_counts.get(analysis.identified_skin_type, 0) + 1
        )
    most_common_skin_type = max(
        skin_type_counts,
        key=skin_type_counts.get,
        default=None,
    )
    skin_type_display_map = dict(
        SkinAnalysis._meta.get_field('identified_skin_type').choices
    )
    most_common_skin_type_display = skin_type_display_map.get(most_common_skin_type)
    latest_skin_type_display = (
        skin_type_display_map.get(latest_analysis.identified_skin_type)
        if latest_analysis
        else None
    )

    # Skin type trend chart data (kept from the old assessment history page).
    chart_data = []
    for analysis in analyses.order_by('created_at'):
        chart_data.append({
            'date': analysis.created_at.strftime('%Y-%m-%d'),
            'skin_type': analysis.identified_skin_type,
            'skin_type_display': skin_type_display_map.get(
                analysis.identified_skin_type, analysis.identified_skin_type
            ),
        })

    # Skin condition chart series built from real check-in records.
    range_checkins = all_checkins.order_by('date')
    if range_start:
        range_checkins = range_checkins.filter(date__gte=range_start)
    chart_labels = [c.date.strftime('%b %d') for c in range_checkins]
    chart_series = {
        'oiliness': [c.oiliness for c in range_checkins],
        'dryness': [c.dryness for c in range_checkins],
        'acne_level': [c.acne_level for c in range_checkins],
        'irritation': [c.irritation for c in range_checkins],
    }
    condition_scores = [CONDITION_SCORES.get(c.skin_condition, 3) for c in range_checkins]

    # Verdict: does the routine appear to be helping? Compares the average
    # skin-condition score from the first half of the range with the second
    # half. Scores go from 1 (worst) to 5 (best per CONDITION_SCORES).
    routine_helping = None
    if len(condition_scores) >= 3:
        half = len(condition_scores) // 2
        earlier = sum(condition_scores[:half]) / half
        later = sum(condition_scores[half:]) / (len(condition_scores) - half)
        delta = later - earlier
        if delta >= 0.3:
            trend = 'improving'
        elif delta <= -0.3:
            trend = 'declining'
        else:
            trend = 'stable'
        routine_helping = {
            'trend': trend,
            'earlier': round(earlier, 1) if half else None,
            'later': round(later, 1),
            'consistency': _routine_consistency(user, range_start),
        }

    # Journey explanation (adapted from the old assessment history view).
    journey_explanation = None
    if analyses.count() == 0:
        journey_explanation = (
            'No assessments yet. Start your first skin analysis to begin '
            'tracking your skin journey.'
        )
    elif analyses.count() == 1:
        journey_explanation = (
            'This is your first assessment. Take more assessments over time '
            'to see how your skin type evolves with changes in your routine '
            'and environment.'
        )
    else:
        skin_types_sequence = [a.identified_skin_type for a in analyses.order_by('created_at')]
        if len(set(skin_types_sequence)) == 1:
            journey_explanation = (
                f'Your skin type has remained consistent as '
                f'{skin_type_display_map.get(skin_types_sequence[0])} across your '
                f'assessments. Consistency suggests your current routine is '
                f'working well for you.'
            )
        else:
            journey_explanation = (
                'Your skin type has changed across assessments, showing how '
                'your skin responds to different factors over time. It is '
                'normal for skin conditions to evolve due to skincare habits, '
                'environment, stress, hormones, and other influences.'
            )

    # Month parameter for the progress calendar.
    month_value = request.GET.get('month', '')
    try:
        calendar_month = date.fromisoformat(f'{month_value}-01')
        if not month_value:
            raise ValueError
    except ValueError:
        calendar_month = today.replace(day=1)
    calendar_data = _build_progress_calendar(user, calendar_month)

    context = {
        # Header / controls
        'today': today,
        'range_key': range_key,
        # Summary cards
        'total_checkins': all_checkins.count(),
        'routine_consistency': _routine_consistency(user, range_start),
        'routine_streak': _routine_streak(user),
        'checkin_streak': _checkin_streak(user),
        'latest_assessment': latest_analysis,
        'latest_skin_type_display': latest_skin_type_display,
        'latest_checkin': latest_checkin,
        'latest_condition_display': (
            latest_checkin.get_skin_condition_display() if latest_checkin else None
        ),
        'total_assessments': analyses.count(),
        'most_common_skin_type_display': most_common_skin_type_display,
        # Charts
        'chart_labels': chart_labels,
        'chart_series': chart_series,
        'condition_scores': condition_scores,
        'chart_data': chart_data,
        'journey_explanation': journey_explanation,
        'routine_helping': routine_helping,
        # Daily check-ins
        'checkin_list': all_checkins[:20],
        'condition_choices': DailyCheckIn.CONDITION_CHOICES,
        'rating_descriptions': RATING_DESCRIPTIONS,
        'rating_labels': {
            '1': 'None / Very low',
            '2': 'Mild',
            '3': 'Moderate',
            '4': 'Noticeable',
            '5': 'Severe / Very high',
        },
        'form_defaults': {
            'date': today.isoformat(),
            'skin_condition': latest_checkin.skin_condition if latest_checkin else 'average',
            'oiliness': latest_checkin.oiliness if latest_checkin else 1,
            'dryness': latest_checkin.dryness if latest_checkin else 1,
            'acne_level': latest_checkin.acne_level if latest_checkin else 1,
            'irritation': latest_checkin.irritation if latest_checkin else 1,
        },
        # Calendar / timeline
        'calendar': calendar_data,
        'timeline': _timeline_events(user, range_start),
        # Photos
        'photo_checkins': (
            all_checkins.exclude(photo='').exclude(photo__isnull=True)[:12]
        ),
        # Ingredient experience tracker
        'ingredient_experiences': IngredientExperience.objects.filter(user=user)[:15],
        'recommended_ingredients': _recommended_ingredients(user),
        # Previous assessments
        'assessments': analyses,
        'profile': profile,
    }
    return render(request, 'assessment_history.html', context)


@login_required(login_url='login')
@require_http_methods(['POST'])
def checkin_save(request):
    """Create or update the signed-in user's check-in for one date."""
    from .models import DailyCheckIn

    user = request.user
    raw_date = parse_date(request.POST.get('date', '')) or timezone.localdate()
    today = timezone.localdate()
    if raw_date > today:
        messages.error(request, 'You cannot record a check-in for a future date.')
        return redirect('assessment_history')

    valid_conditions = {choice[0] for choice in DailyCheckIn.CONDITION_CHOICES}
    skin_condition = request.POST.get('skin_condition', '')
    if skin_condition not in valid_conditions:
        messages.error(request, 'Please choose a valid skin condition.')
        return redirect('assessment_history')

    ratings = {}
    for field in CHECKIN_RATING_FIELDS:
        raw_value = request.POST.get(field, '')
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            messages.error(request, 'All rating levels must be whole numbers from 1 to 5.')
            return redirect('assessment_history')
        if not 1 <= value <= 5:
            messages.error(request, 'All rating levels must be between 1 and 5.')
            return redirect('assessment_history')
        ratings[field] = value

    photo = request.FILES.get('photo')
    photo_error = _validate_progress_photo(photo)
    if photo_error:
        messages.error(request, photo_error)
        return redirect('assessment_history')

    checkin, _created = DailyCheckIn.objects.get_or_create(
        user=user,
        date=raw_date,
        defaults={
            'skin_condition': skin_condition,
            **ratings,
            'morning_completed': request.POST.get('morning_completed') in {'on', 'true', '1'},
            'evening_completed': request.POST.get('evening_completed') in {'on', 'true', '1'},
            'products_used': request.POST.get('products_used', '').strip()[:2000],
            'ingredients_used': request.POST.get('ingredients_used', '').strip()[:2000],
            'notes': request.POST.get('notes', '').strip()[:2000],
            'photo': photo,
        },
    )
    if not _created:
        # Updating the existing record for the same user + date.
        checkin.skin_condition = skin_condition
        for field in CHECKIN_RATING_FIELDS:
            setattr(checkin, field, ratings[field])
        checkin.morning_completed = request.POST.get('morning_completed') in {'on', 'true', '1'}
        checkin.evening_completed = request.POST.get('evening_completed') in {'on', 'true', '1'}
        checkin.products_used = request.POST.get('products_used', '').strip()[:2000]
        checkin.ingredients_used = request.POST.get('ingredients_used', '').strip()[:2000]
        checkin.notes = request.POST.get('notes', '').strip()[:2000]
        if photo:
            if checkin.photo:
                try:
                    checkin.photo.delete(save=False)
                except Exception:
                    pass
            checkin.photo = photo
    checkin.save()

    if _created:
        messages.success(request, f'Daily check-in saved for {raw_date.strftime("%B %d, %Y")}.')
    else:
        messages.success(request, f'Check-in for {raw_date.strftime("%B %d, %Y")} was updated.')
    return redirect('assessment_history')


@login_required(login_url='login')
@require_http_methods(['POST'])
def checkin_delete(request):
    """Delete the signed-in user's check-in for one date."""
    from .models import DailyCheckIn

    try:
        checkin_id = int(request.POST.get('id', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid check-in.')
        return redirect('assessment_history')

    checkin = DailyCheckIn.objects.filter(user=request.user, pk=checkin_id).first()
    if checkin is None:
        messages.error(request, 'Check-in not found.')
        return redirect('assessment_history')

    if checkin.photo:
        try:
            checkin.photo.delete(save=False)
        except Exception:
            pass
    checkin.delete()
    messages.success(request, 'Daily check-in deleted.')
    return redirect('assessment_history')


@login_required(login_url='login')
@require_http_methods(['POST'])
def checkin_photo_delete(request):
    """Remove an uploaded progress photo, keeping the check-in record."""
    from .models import DailyCheckIn

    try:
        checkin_id = int(request.POST.get('id', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid check-in.')
        return redirect('assessment_history')

    checkin = DailyCheckIn.objects.filter(user=request.user, pk=checkin_id).first()
    if checkin is None or not checkin.photo:
        messages.error(request, 'Photo not found.')
        return redirect('assessment_history')
    try:
        checkin.photo.delete(save=False)
    except Exception:
        pass
    checkin.photo = None
    checkin.save(update_fields=['photo', 'updated_at'])
    messages.success(request, 'Progress photo removed.')
    return redirect('assessment_history')


@login_required(login_url='login')
@require_http_methods(['GET'])
def checkin_day_details(request):
    """JSON details for everything saved on one date (calendar day click)."""
    from .models import DailyCheckIn, IngredientExperience, SkinAnalysis

    day = parse_date(request.GET.get('date', ''))
    if not day:
        return JsonResponse({'success': False, 'error': 'Invalid date.'}, status=400)

    checkin = DailyCheckIn.objects.filter(user=request.user, date=day).first()
    analysis = (
        SkinAnalysis.objects.filter(user=request.user, created_at__date=day)
        .order_by('-created_at')
        .first()
    )
    experiences = IngredientExperience.objects.filter(
        user=request.user, created_at__date=day
    )

    data = {
        'success': True,
        'date': day.isoformat(),
        'display_date': day.strftime('%B %d, %Y'),
        'checkin': None,
        'assessment': None,
        'experiences': [
            {
                'ingredient': item.ingredient,
                'outcome': item.get_outcome_display(),
                'comment': item.comment,
            }
            for item in experiences
        ],
    }
    if checkin:
        data['checkin'] = {
            'date': checkin.date.isoformat(),
            'skin_condition': checkin.get_skin_condition_display(),
            'skin_condition_value': checkin.skin_condition,
            'oiliness': checkin.oiliness,
            'dryness': checkin.dryness,
            'acne_level': checkin.acne_level,
            'irritation': checkin.irritation,
            'morning_completed': checkin.morning_completed,
            'evening_completed': checkin.evening_completed,
            'products_used': checkin.products_used,
            'ingredients_used': checkin.ingredients_used,
            'notes': checkin.notes,
            'photo': checkin.photo.url if checkin.photo else None,
        }
    if analysis:
        data['assessment'] = {
            'id': analysis.pk,
            'method': analysis.get_method_display(),
            'skin_type': analysis.get_identified_skin_type_display(),
            'created_at': timezone.localtime(analysis.created_at).strftime('%I:%M %p'),
        }
    return JsonResponse(data)


@login_required(login_url='login')
@require_http_methods(['POST'])
def ingredient_experience_save(request):
    """Save the user's personal observation about an ingredient they used."""
    from .models import IngredientExperience

    outcome_choices = {choice[0] for choice in IngredientExperience.OUTCOME_CHOICES}
    ingredient = (
        request.POST.get('ingredient')
        or request.POST.get('ingredient_other')
        or ''
    ).strip()
    if len(ingredient) > 150:
        ingredient = ingredient[:150]
    outcome = request.POST.get('outcome', '')
    comment = request.POST.get('comment', '').strip()[:1000]

    if not ingredient:
        messages.error(request, 'Please choose or type the ingredient you used.')
        return redirect('assessment_history')
    if outcome not in outcome_choices:
        messages.error(request, 'Please choose a valid outcome.')
        return redirect('assessment_history')

    IngredientExperience.objects.create(
        user=request.user,
        ingredient=ingredient,
        outcome=outcome,
        comment=comment,
    )
    messages.success(request, 'Ingredient experience saved. Personal observations only - results vary from person to person.')
    return redirect('assessment_history')


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
            if key.startswith('ai_'):
                # AI answers are already readable prose; do not title-case them.
                display_value = str(raw_value).strip()
                default_title = key[3:].replace('_', ' ').title()
            else:
                display_value = str(raw_value).replace('_', ' ').title()
                default_title = key.upper()
            answer_rows.append({
                'key': key,
                'question': QUESTION_TITLES.get(key, default_title),
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
