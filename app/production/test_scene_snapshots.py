"""FS-016c scene plan PostgreSQL snapshots: owner isolation and restart safety."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.clubs.models import Club, Country, League

from .models import FactDossier, ProductionJob, ScenePlanSnapshot
from .script_draft import build_script_draft
from .scene_snapshots import (
    SceneSnapshotError, load_scene_plan_snapshot, save_scene_plan_snapshot,
)
from .test_script_draft import reviewed_snapshot


class ScenePlanSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="scene-snapshot-owner@example.org",
            password="Test-only-not-a-real-secret-1234",
        )
        self.other = User.objects.create_user(
            email="scene-snapshot-other@example.org",
            password="Test-only-not-a-real-secret-1234",
        )
        country = Country.objects.create(code="GB", name="United Kingdom")
        league = League.objects.create(country=country, name="Example League")
        club = Club.objects.create(league=league, name="Example FC")
        self.job = ProductionJob.objects.create(
            owner=self.owner, club=club,
            country_code="GB", league_name="Example League",
            club_name="Example FC", title="A Sourced Example FC Story",
        )
        FactDossier.objects.create(job=self.job, version=2)

    def generated_draft(self, version=2):
        source = reviewed_snapshot()
        source["job_id"] = self.job.pk
        source["version"] = version
        return build_script_draft(
            source, club_name=self.job.club_name,
            selected_title=self.job.title,
        )

    def save(self, **kwargs):
        args = dict(
            owner=self.owner, job_id=self.job.pk, dossier_version=2,
        )
        args.update(kwargs)
        return save_scene_plan_snapshot(**args)

    def load(self, **kwargs):
        args = dict(
            owner=self.owner, job_id=self.job.pk, dossier_version=2,
        )
        args.update(kwargs)
        return load_scene_plan_snapshot(**args)

    def test_snapshot_is_persistent_immutable_and_idempotent(self):
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ) as loader:
            first = self.save()
            second = self.save()
            stored = self.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)
        self.assertEqual(first.created_at, second.created_at)
        self.assertEqual(first.plan_payload, stored)
        self.assertEqual(stored["job_id"], self.job.pk)
        self.assertEqual(stored["dossier_version"], 2)
        self.assertEqual(len(stored["scenes"]), 3)
        self.assertEqual(stored["scenes"][1]["evidence_refs"][0]["source_id"], 11)
        self.assertFalse(stored["ready_for_tts"])
        self.assertFalse(stored["ready_for_render"])
        self.assertEqual(loader.call_count, 3)

    def test_separate_version_and_rate_are_separate_artifacts(self):
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ):
            original = self.save()
            faster = self.save(words_per_minute=180)
            version3 = self.save(dossier_version=3)
            self.assertNotEqual(original.pk, faster.pk)
            self.assertNotEqual(original.pk, version3.pk)
            self.assertEqual(ScenePlanSnapshot.objects.count(), 3)
            self.assertEqual(
                self.load(dossier_version=3)["dossier_version"], 3
            )
            self.assertEqual(
                self.load(words_per_minute=180)["words_per_minute"], 180
            )

    def test_unowned_job_cannot_be_written_or_read(self):
        with patch("app.production.scene_snapshots.load_job_script_draft") as loader:
            with self.assertRaisesMessage(SceneSnapshotError, "not_authorized"):
                self.save(owner=self.other)
            with self.assertRaisesMessage(
                SceneSnapshotError, "scene_snapshot_not_found"
            ):
                self.load(owner=self.other)
            loader.assert_not_called()
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_invalid_ids_and_speaking_rate_fail_without_db_writes(self):
        for kw in (
            {"job_id": True}, {"job_id": 0}, {"dossier_version": False},
            {"dossier_version": -1}, {"owner": None},
        ):
            with self.subTest(kw=kw), self.assertRaisesMessage(
                SceneSnapshotError, "invalid_request"
            ):
                self.save(**kw)
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ):
            for rate in (99, 201, True, 145.0, None):
                with self.subTest(rate=rate), self.assertRaises(SceneSnapshotError):
                    self.save(words_per_minute=rate)
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    def test_plan_change_same_version_never_overwrites_existing(self):
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ):
            first = self.save()
            old_payload = deepcopy(first.plan_payload)
            self.job.title = "An Updated Example FC Story"
            self.job.save(update_fields=["title", "updated_at"])
            with self.assertRaisesMessage(SceneSnapshotError, "stale_scene_snapshot"):
                self.save()
            with self.assertRaisesMessage(SceneSnapshotError, "stale_scene_snapshot"):
                self.load()
        self.assertEqual(ScenePlanSnapshot.objects.count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.plan_payload, old_payload)

    def test_corrupt_payload_and_changed_hash_cannot_be_reused(self):
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ):
            created = self.save()
            ScenePlanSnapshot.objects.filter(pk=created.pk).update(
                plan_fingerprint_sha256="0" * 64,
            )
            with self.assertRaisesMessage(SceneSnapshotError, "corrupt_scene_snapshot"):
                self.load()
            with self.assertRaisesMessage(SceneSnapshotError, "corrupt_scene_snapshot"):
                self.save()
            ScenePlanSnapshot.objects.filter(pk=created.pk).update(
                plan_fingerprint_sha256=created.plan_fingerprint_sha256,
                plan_payload={"schema": "fs-016c-scene-plan-v1"},
            )
            with self.assertRaisesMessage(SceneSnapshotError, "corrupt_scene_snapshot"):
                self.load()

    def test_missing_snapshot_and_empty_real_dossier_do_not_write(self):
        with self.assertRaisesMessage(
            SceneSnapshotError, "scene_snapshot_not_found"
        ):
            self.load()
        with self.assertRaisesMessage(SceneSnapshotError, "no_reviewed_facts"):
            self.save()
        self.assertEqual(ScenePlanSnapshot.objects.count(), 0)

    @patch("urllib.request.urlopen")
    @patch("socket.getaddrinfo")
    def test_round_trip_has_no_network_or_paid_provider_calls(self, dns, http):
        with patch(
            "app.production.scene_snapshots.load_job_script_draft",
            side_effect=lambda **kwargs: self.generated_draft(kwargs["version"]),
        ):
            self.save()
            self.load()
        dns.assert_not_called()
        http.assert_not_called()
