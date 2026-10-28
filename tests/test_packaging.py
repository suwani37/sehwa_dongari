"""Packaging settings must persist outside the one-file extraction directory."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tetris.preferences import PlayerSettings, _settings_path


class PackagingTests(unittest.TestCase):
    def test_frozen_settings_use_user_data(self):
        with TemporaryDirectory() as folder:
            with patch.object(sys, "frozen", True, create=True):
                with patch.dict(os.environ, {"LOCALAPPDATA": folder}):
                    path = _settings_path()
                    self.assertEqual(path, Path(folder) / "SuwanTetris" / "player_settings.json")
                    value = PlayerSettings(das_ms=180, arr_ms=0)
                    value.save(path)
                    self.assertEqual(PlayerSettings.load(path), value)

    def test_source_settings_stay_in_project(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(_settings_path().parent, Path(__file__).resolve().parent.parent)
