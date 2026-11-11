"""Validate safe, repeatable installation without requiring a Unity editor."""

from pathlib import Path
import runpy
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1] / 'vizard-ui'
INSTALLER = runpy.run_path(str(BUNDLE / 'install.py'))


class VizardUiInstallTests(unittest.TestCase):
    def project(self, directory):
        project = Path(directory)
        version = project / 'ProjectSettings/ProjectVersion.txt'
        version.parent.mkdir(parents=True)
        version.write_text('m_EditorVersion: 6000.0.68f1\n')
        target = project / INSTALLER['PANEL_PATH']
        target.parent.mkdir(parents=True)
        target.write_text('class Example {\n\tvoid InitializePanel(int scIndex, string scName) {\n'
                          '\t\tSetPanelSize();\n\t}\n}\n')
        return project, target

    def test_install_is_idempotent_and_preserves_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            project, target = self.project(directory)
            paths = INSTALLER['install'](project, BUNDLE)
            self.assertEqual(len(paths), 5)
            first = target.read_bytes()
            INSTALLER['install'](project, BUNDLE)
            self.assertEqual(target.read_bytes(), first)
            self.assertEqual(target.read_text().count(INSTALLER['MARKER']), 1)
            self.assertIn('SetPanelSize();', target.read_text())
            self.assertTrue((project / 'perovsat-ui-manifest.json').exists())

    def test_unknown_source_is_rejected_without_partial_install(self):
        with tempfile.TemporaryDirectory() as directory:
            project, target = self.project(directory)
            target.write_text('different upstream version')
            with self.assertRaisesRegex(ValueError, 'Unrecognized'):
                INSTALLER['install'](project, BUNDLE)
            self.assertFalse((project / 'Assets/Scripts/PerovsatTelemetry').exists())
            self.assertEqual(target.read_text(), 'different upstream version')

    def test_local_customizations_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            project, target = self.project(directory)
            INSTALLER['install'](project, BUNDLE)
            custom = project / 'Assets/Scripts/PerovsatTelemetry/PerovsatTelemetryPanel.cs'
            custom.write_text('user customization')
            with self.assertRaisesRegex(ValueError, 'Locally modified'):
                INSTALLER['install'](project, BUNDLE)
            self.assertEqual(custom.read_text(), 'user customization')

    def test_wrong_unity_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project, target = self.project(directory)
            (project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.0f1')
            with self.assertRaisesRegex(ValueError, '6000.0.68f1'):
                INSTALLER['install'](project, BUNDLE)
            self.assertNotIn(INSTALLER['MARKER'], target.read_text())
