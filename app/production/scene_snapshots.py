"""FS-016c: private, owner-scoped, idempotent PostgreSQL scene snapshots.

Only trusted internal callers. No public HTTP routes, media, TTS, worker or
paid-provider dispatch. Changed facts within the same dossier version cause a
stale-snapshot error; a new dossier version is needed for a new artifact.
"""
from hashlib import sha256
import json
import re

from django.db import transaction

from .models import ProductionJob, ScenePlanSnapshot
from .scene_plan import ScenePlanError, build_scene_plan
from .script_draft import ScriptDraftError, load_job_script_draft
from .script_length import DEFAULT_WORDS_PER_MINUTE

_MAX_BYTES = 512 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class SceneSnapshotError(ValueError):
    """Private-safe code; never includes job metadata or narration."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _request(owner, job_id, dossier_version):
    owner_id = getattr(owner, "pk", None)
    if (
        type(owner_id) is not int or owner_id < 1
        or type(job_id) is not int or job_id < 1
        or type(dossier_version) is not int or dossier_version < 1
    ):
        raise SceneSnapshotError("invalid_request")
    return owner_id


def _encode(payload):
    try:
        raw = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise SceneSnapshotError("invalid_scene_payload") from None
    if len(raw) > _MAX_BYTES:
        raise SceneSnapshotError("scene_payload_too_large")
    return raw


def _check_saved(snapshot):
    plan = snapshot.plan_payload
    if (
        not isinstance(plan, dict)
        or plan.get("schema") != "fs-016c-scene-plan-v1"
        or plan.get("language") != "en"
        or type(plan.get("job_id")) is not int
        or plan["job_id"] != snapshot.job_id
        or type(plan.get("dossier_version")) is not int
        or plan["dossier_version"] != snapshot.dossier_version
        or type(plan.get("words_per_minute")) is not int
        or plan["words_per_minute"] != snapshot.words_per_minute
        or plan.get("source_script_fingerprint_sha256")
        != snapshot.source_script_fingerprint_sha256
        or plan.get("editorial_review_required") is not True
        or plan.get("ready_for_tts") is not False
        or plan.get("ready_for_render") is not False
        or not isinstance(plan.get("scenes"), list)
        or type(plan.get("plan_fingerprint_sha256")) is not str
        or not _SHA256.fullmatch(plan["plan_fingerprint_sha256"])
        or plan["plan_fingerprint_sha256"] != snapshot.plan_fingerprint_sha256
        or type(snapshot.source_script_fingerprint_sha256) is not str
        or not _SHA256.fullmatch(snapshot.source_script_fingerprint_sha256)
    ):
        raise SceneSnapshotError("corrupt_scene_snapshot")
    raw = {key: value for key, value in plan.items()
           if key != "plan_fingerprint_sha256"}
    if sha256(_encode(raw)).hexdigest() != snapshot.plan_fingerprint_sha256:
        raise SceneSnapshotError("corrupt_scene_snapshot")
    return plan


def _current_plan(*, owner, job_id, dossier_version, words_per_minute):
    try:
        draft = load_job_script_draft(
            owner=owner, job_id=job_id, version=dossier_version,
        )
        return build_scene_plan(draft, words_per_minute=words_per_minute)
    except (ScriptDraftError, ScenePlanError) as exc:
        raise SceneSnapshotError(exc.code) from None


def _matching(snapshot, current):
    saved = _check_saved(snapshot)
    if (
        saved["plan_fingerprint_sha256"] != current["plan_fingerprint_sha256"]
        or saved != current
    ):
        raise SceneSnapshotError("stale_scene_snapshot")
    return saved


def save_scene_plan_snapshot(
    *, owner, job_id, dossier_version,
    words_per_minute=DEFAULT_WORDS_PER_MINUTE,
):
    """Create once, or return the identical snapshot without rewriting it.

    Lock the owning job while reading its title and producing the snapshot.
    A changed plan for the same (job, dossier version, speaking rate) fails
    closed, instead of silently overwriting an earlier reviewed artifact.
    """
    owner_id = _request(owner, job_id, dossier_version)
    with transaction.atomic():
        job = ProductionJob.objects.select_for_update().filter(
            pk=job_id, owner_id=owner_id,
        ).first()
        if job is None:
            raise SceneSnapshotError("not_authorized")
        plan = _current_plan(
            owner=owner, job_id=job_id,
            dossier_version=dossier_version,
            words_per_minute=words_per_minute,
        )
        _encode(plan)
        snapshot, created = ScenePlanSnapshot.objects.get_or_create(
            job=job,
            dossier_version=dossier_version,
            words_per_minute=plan["words_per_minute"],
            defaults={
                "source_script_fingerprint_sha256":
                    plan["source_script_fingerprint_sha256"],
                "plan_fingerprint_sha256": plan["plan_fingerprint_sha256"],
                "plan_payload": plan,
            },
        )
        if not created:
            _matching(snapshot, plan)
        return snapshot


def load_scene_plan_snapshot(
    *, owner, job_id, dossier_version,
    words_per_minute=DEFAULT_WORDS_PER_MINUTE,
):
    """Reload a private saved plan, verifying integrity and current inputs.

    A saved plan is never a TTS/render authorization even after validation.
    If its source script has changed, refuse to silently reuse it.
    """
    owner_id = _request(owner, job_id, dossier_version)
    if type(words_per_minute) is not int or not 100 <= words_per_minute <= 200:
        raise SceneSnapshotError("invalid_speaking_rate")
    snapshot = ScenePlanSnapshot.objects.filter(
        job_id=job_id, job__owner_id=owner_id,
        dossier_version=dossier_version, words_per_minute=words_per_minute,
    ).first()
    if snapshot is None:
        raise SceneSnapshotError("scene_snapshot_not_found")
    saved = _check_saved(snapshot)
    current = _current_plan(
        owner=owner, job_id=job_id,
        dossier_version=dossier_version,
        words_per_minute=words_per_minute,
    )
    if saved != current:
        raise SceneSnapshotError("stale_scene_snapshot")
    return saved
