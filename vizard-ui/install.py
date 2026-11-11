"""Install the PEROVSAT UI overlay into an existing Vizard Unity checkout."""

import argparse
import hashlib
import json
from pathlib import Path


PANEL_PATH = Path('Assets/Scripts/MainScene/MainSceneGUI/GenericStoragePanel/GenericStoragePanelMethods.cs')
MARKER = 'PerovsatTelemetryPanel.Attach(gameObject, scIndex, scName);'
ANCHOR = '\t\tSetPanelSize();\n\t}'


def patch_panel(source):
    if source.count(MARKER) == 1:
        return source
    if MARKER in source or source.count(ANCHOR) != 1:
        raise ValueError('Unrecognized Vizard panel source; refusing to patch it')
    return source.replace(ANCHOR, '\t\tSetPanelSize();\n\t\t' + MARKER + '\n\t}', 1)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def install(project, bundle=None):
    project = Path(project).resolve()
    bundle = Path(bundle).resolve() if bundle else Path(__file__).resolve().parent
    version_file = project / 'ProjectSettings/ProjectVersion.txt'
    if not version_file.exists() or 'm_EditorVersion: 6000.0.68f1' not in version_file.read_text():
        raise ValueError('Expected a Vizard project using Unity 6000.0.68f1')
    target = project / PANEL_PATH
    source = target.read_text(encoding='utf-8')
    patched = patch_panel(source)
    manifest_path = project / 'perovsat-ui-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    planned = {}
    for source_dir, destination_dir in (
        ('Runtime', 'Assets/Scripts/PerovsatTelemetry'),
        ('Editor', 'Assets/Editor/PerovsatTelemetry'),
        ('Fonts', 'Assets/Resources/PerovsatTelemetry'),
    ):
        for source_file in (bundle / source_dir).iterdir():
            if source_file.suffix not in ('.cs', '.ttf', '.txt'):
                continue
            relative = (Path(destination_dir) / source_file.name).as_posix()
            contents = source_file.read_bytes()
            destination = project / relative
            if destination.exists():
                existing_hash = digest(destination.read_bytes())
                if existing_hash not in (digest(contents), manifest.get(relative)):
                    raise ValueError(f'Locally modified file would be overwritten: {relative}')
            planned[relative] = contents
    for required in ('Assets/Scripts/PerovsatTelemetry/PerovsatTelemetryPanel.cs',
                     'Assets/Editor/PerovsatTelemetry/PerovsatBuild.cs',
                     'Assets/Resources/PerovsatTelemetry/Barlow-Regular.ttf',
                     'Assets/Resources/PerovsatTelemetry/Barlow-SemiBold.ttf',
                     'Assets/Resources/PerovsatTelemetry/OFL.txt'):
        if required not in planned:
            raise ValueError(f'Incomplete UI bundle: {required}')
    if patched != source:
        target.write_text(patched, encoding='utf-8')
    for relative, contents in planned.items():
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    manifest_path.write_text(json.dumps({key: digest(value) for key, value in planned.items()}, indent=2) + '\n')
    return sorted(planned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    args = parser.parse_args()
    for path in install(args.project):
        print(path)
    print('Overlay installed. Open the project in Unity to import assets and build.')


if __name__ == '__main__':
    main()
