"""Confirmed profiles must remain readable after form schema changes."""

import copy
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.profile import router as profile_router
from backend.app.api.profile_drafts import router as drafts_router
from backend.app.schemas.profile import MasterProfile, StoredProfile


def legacy_record():
    return {
        "schema_version": 2,
        "profile": {
            "contact": {"full_name": "Test Candidate"},
            "experience": [{
                "job_title": "Developer", "role": "Backend",
                "achievements": ["Delivered the API"],
                "technologies_used": ["Python"],
            }],
            "project": [{
                "project_name": "Career Workspace", "role": "Developer",
                "technologies": ["React", "Python"],
                "contributions": ["Built CV import"],
                "outcomes": ["Released the application"],
            }],
            "education": [], "involvement": [], "skills": [],
        },
    }


class ProfileCompatibilityTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(profile_router)
        app.include_router(drafts_router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_postgres_list_and_read_preserve_existing_fields(self):
        record = legacy_record()
        original = copy.deepcopy(record)
        with (
            patch("backend.app.db.database.enabled", return_value=True),
            patch("backend.app.db.database.list_records", return_value=[
                {"id": "saved_profile", "data": record},
                {"id": "cvlocal_saved", "data": record},
            ]),
            patch("backend.app.db.database.get_record", return_value=record),
        ):
            listing = self.client.get("/api/profile-drafts/profiles")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual([item["profile_id"] for item in listing.json()], ["saved_profile"])
            response = self.client.get("/api/profiles/saved_profile")
            self.assertEqual(response.status_code, 200)
            profile = response.json()["profile"]
            for section in ("experience", "project"):
                for field, value in record["profile"][section][0].items():
                    self.assertEqual(profile[section][0][field], value)
        self.assertEqual(record, original)

    def test_new_minimal_profiles_still_work(self):
        profile = MasterProfile(contact={}, experience=[], project=[{}],
                                education=[], involvement=[], skills=[])
        self.assertEqual(profile.project[0].technologies, [])
        self.assertEqual(profile.project[0].outcomes, [])

    def test_unknown_fields_are_still_rejected(self):
        record = legacy_record()
        record["profile"]["project"][0]["unknown_field"] = "unsupported"
        with self.assertRaises(ValidationError):
            StoredProfile.model_validate(record)
