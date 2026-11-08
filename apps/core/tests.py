import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import DailyCheckIn, IngredientExperience, SkinAnalysis

User = get_user_model()

MEDIA_ROOT_TEMP = tempfile.mkdtemp()

CHECKIN_SAVE_URL = reverse('checkin_save')
CHECKIN_DELETE_URL = reverse('checkin_delete')
DAY_DETAILS_URL = reverse('checkin_day_details')
PHOTO_DELETE_URL = reverse('checkin_photo_delete')
EXPERIENCE_URL = reverse('ingredient_experience_save')
HISTORY_URL = reverse('assessment_history')

VALID_CHECKIN_DATA = {
    'date': '2026-11-05',
    'skin_condition': 'good',
    'oiliness': '2',
    'dryness': '3',
    'acne_level': '1',
    'irritation': '1',
    'morning_completed': 'on',
    'products_used': 'Gentle Hydrating Cleanser',
    'ingredients_used': 'Glycerin, Ceramides',
    'notes': 'Feeling balanced today.',
}


class SkinProgressHistoryPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret1234')

    def test_page_requires_login(self):
        response = self.client.get(HISTORY_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=/assessment-history/', response.url)

    def test_page_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(HISTORY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'assessment_history.html')
        self.assertContains(response, 'Skin Progress History')
        self.assertNotContains(response, '<h1 class="ah-title">Assessment History')

    def test_empty_state_shown_without_records(self):
        self.client.force_login(self.user)
        response = self.client.get(HISTORY_URL)
        self.assertContains(response, 'No check-ins yet')
        self.assertContains(response, 'No assessments yet')

    def test_existing_assessments_still_shown(self):
        analysis = SkinAnalysis.objects.create(
            user=self.user,
            method='questionnaire',
            identified_skin_type='combination',
            notes='My main concern is redness.',
        )
        self.client.force_login(self.user)
        response = self.client.get(HISTORY_URL)
        self.assertContains(response, 'Combination Skin')
        self.assertContains(response, 'My main concern is redness.')
        self.assertContains(response, reverse('assessment_detail', args=[analysis.pk]))

    def test_range_filter_options(self):
        self.client.force_login(self.user)
        for key in ('7', '30', '90', 'all'):
            response = self.client.get(HISTORY_URL + f'?range={key}')
            self.assertEqual(response.status_code, 200)


class DailyCheckInTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret1234')
        self.other_user = User.objects.create_user(username='other', password='secret1234')
        self.client.force_login(self.user)

    def test_create_checkin(self):
        response = self.client.post(CHECKIN_SAVE_URL, VALID_CHECKIN_DATA)
        self.assertRedirects(response, HISTORY_URL)
        checkin = DailyCheckIn.objects.get(user=self.user, date='2026-11-05')
        self.assertEqual(checkin.skin_condition, 'good')
        self.assertEqual(checkin.oiliness, 2)
        self.assertEqual(checkin.dryness, 3)
        self.assertEqual(checkin.acne_level, 1)
        self.assertEqual(checkin.morning_completed, True)
        self.assertEqual(checkin.notes, 'Feeling balanced today.')

    def test_same_date_updates_instead_of_duplicating(self):
        self.client.post(CHECKIN_SAVE_URL, VALID_CHECKIN_DATA)
        updated = dict(VALID_CHECKIN_DATA, skin_condition='excellent', oiliness='4')
        self.client.post(CHECKIN_SAVE_URL, updated)
        checkins = DailyCheckIn.objects.filter(user=self.user, date='2026-11-05')
        self.assertEqual(checkins.count(), 1)
        self.assertEqual(checkins.first().skin_condition, 'excellent')
        self.assertEqual(checkins.first().oiliness, 4)

    def test_rejects_out_of_range_rating(self):
        data = dict(VALID_CHECKIN_DATA, oiliness='7')
        self.client.post(CHECKIN_SAVE_URL, data)
        self.assertFalse(DailyCheckIn.objects.filter(user=self.user).exists())

    def test_rejects_future_date(self):
        data = dict(VALID_CHECKIN_DATA, date='2099-01-01')
        self.client.post(CHECKIN_SAVE_URL, data)
        self.assertFalse(DailyCheckIn.objects.filter(user=self.user).exists())

    def test_rejects_invalid_condition(self):
        data = dict(VALID_CHECKIN_DATA, skin_condition='glowing')
        self.client.post(CHECKIN_SAVE_URL, data)
        self.assertFalse(DailyCheckIn.objects.filter(user=self.user).exists())

    def test_user_isolation_on_create(self):
        """A check-in is always attached to the logged-in user, never others."""
        self.client.post(CHECKIN_SAVE_URL, VALID_CHECKIN_DATA)
        self.assertFalse(DailyCheckIn.objects.filter(user=self.other_user).exists())

    def test_delete_own_checkin(self):
        checkin = DailyCheckIn.objects.create(
            user=self.user,
            date='2026-11-05',
            skin_condition='good',
        )
        DailyCheckIn.objects.create(
            user=self.other_user,
            date='2026-11-05',
            skin_condition='good',
        )
        response = self.client.post(CHECKIN_DELETE_URL, {'id': checkin.pk})
        self.assertRedirects(response, HISTORY_URL)
        self.assertFalse(
            DailyCheckIn.objects.filter(user=self.user, pk=checkin.pk).exists()
        )
        # The other user's record must survive.
        self.assertTrue(DailyCheckIn.objects.filter(user=self.other_user).exists())

    def test_day_details_json_and_privacy(self):
        DailyCheckIn.objects.create(
            user=self.user,
            date='2026-11-05',
            skin_condition='rough',
            oiliness=3,
            dryness=5,
            acne_level=2,
            irritation=1,
            morning_completed=True,
            notes='Tight skin after cleansing.',
        )
        response = self.client.get(DAY_DETAILS_URL + '?date=2026-11-05')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['checkin']['skin_condition'], 'Rough')
        self.assertEqual(data['checkin']['oiliness'], 3)

    def test_day_details_hidden_from_other_user(self):
        DailyCheckIn.objects.create(
            user=self.other_user,
            date='2026-11-05',
            skin_condition='rough',
        )
        response = self.client.get(DAY_DETAILS_URL + '?date=2026-11-05')
        self.assertIsNone(response.json()['checkin'])

    def test_day_details_requires_valid_date(self):
        response = self.client.get(DAY_DETAILS_URL + '?date=not-a-date')
        self.assertEqual(response.status_code, 400)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMP)
class ProgressPhotoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='photo_user', password='secret1234')
        self.client.force_login(self.user)

    def _checkin(self):
        return DailyCheckIn.objects.create(
            user=self.user,
            date='2026-11-05',
            skin_condition='good',
        )

    def test_rejects_non_image_file(self):
        data = dict(VALID_CHECKIN_DATA)
        data['photo'] = SimpleUploadedFile('notes.txt', b'not an image', content_type='text/plain')
        self.client.post(CHECKIN_SAVE_URL, data)
        self.assertFalse(DailyCheckIn.objects.filter(user=self.user).exists())

    @staticmethod
    def _png_bytes():
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), color=(180, 200, 170)).save(buffer, format='PNG')
        return buffer.getvalue()

    def test_rejects_oversized_photo(self):
        from unittest.mock import patch

        data = dict(VALID_CHECKIN_DATA)
        data['photo'] = SimpleUploadedFile(
            'selfie.png',
            self._png_bytes(),
            content_type='image/png',
        )
        with patch('apps.core.views.MAX_PHOTO_SIZE_MB', 0):
            response = self.client.post(CHECKIN_SAVE_URL, data)
        # MAX_PHOTO_SIZE_MB is read at call time, so 0MB limit rejects the file.
        self.assertFalse(DailyCheckIn.objects.filter(user=self.user).exists())
        self.assertEqual(response.status_code, 302)

    def test_valid_photo_saves(self):
        data = dict(VALID_CHECKIN_DATA)
        data['photo'] = SimpleUploadedFile(
            'selfie.png',
            self._png_bytes(),
            content_type='image/png',
        )
        self.client.post(CHECKIN_SAVE_URL, data)
        checkin = DailyCheckIn.objects.get(user=self.user, date='2026-11-05')
        self.assertTrue(checkin.photo, 'A valid photo should be stored.')
        checkin.photo.delete(save=False)

    def test_photo_delete_keeps_checkin(self):
        from apps.core.views import _validate_progress_photo

        upload = SimpleUploadedFile(
            'selfie.png',
            self._png_bytes(),
            content_type='image/png',
        )
        self.assertIsNone(_validate_progress_photo(upload))
        data = dict(VALID_CHECKIN_DATA)
        data['photo'] = upload
        self.client.post(CHECKIN_SAVE_URL, data)
        checkin = DailyCheckIn.objects.get(user=self.user, date='2026-11-05')
        response = self.client.post(PHOTO_DELETE_URL, {'id': checkin.pk})
        self.assertRedirects(response, HISTORY_URL)
        checkin.refresh_from_db()
        self.assertFalse(checkin.photo)
        self.assertTrue(DailyCheckIn.objects.filter(pk=checkin.pk).exists())


class IngredientExperienceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester2', password='secret1234')
        self.client.force_login(self.user)

    def test_create_experience(self):
        response = self.client.post(EXPERIENCE_URL, {
            'ingredient': 'Niacinamide',
            'outcome': 'improvement',
            'comment': 'Less oil after two weeks.',
        })
        self.assertRedirects(response, HISTORY_URL)
        exp = IngredientExperience.objects.get(user=self.user)
        self.assertEqual(exp.ingredient, 'Niacinamide')
        self.assertEqual(exp.outcome, 'improvement')

    def test_rejects_unknown_outcome(self):
        self.client.post(EXPERIENCE_URL, {'ingredient': 'Niacinamide', 'outcome': 'magic'})
        self.assertFalse(IngredientExperience.objects.filter(user=self.user).exists())

    def test_rejects_empty_ingredient(self):
        self.client.post(EXPERIENCE_URL, {'ingredient': '', 'outcome': 'improvement'})
        self.assertFalse(IngredientExperience.objects.filter(user=self.user).exists())

    def test_privacy_between_users(self):
        other = User.objects.create_user(username='other2', password='secret1234')
        self.client.post(EXPERIENCE_URL, {'ingredient': 'Niacinamide', 'outcome': 'no_change'})
        self.assertFalse(IngredientExperience.objects.filter(user=other).exists())
