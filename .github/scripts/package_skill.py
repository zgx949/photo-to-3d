"""Build the installable Skill archive from an explicit file list."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "photo-to-3d"
FILES = (
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.en.md",
    "README.md",
    "SKILL.md",
    "assets/demos/chibi-suit-turntable.gif",
    "assets/demos/figure-turntable.gif",
    "assets/viewer.template.html",
    "docs/architecture.md",
    "docs/faq.md",
    "examples/prompts.md",
    "references/ark-3d-api.md",
    "references/identity-prompt.md",
    "requirements-solidify.txt",
    "requirements.txt",
    "scripts/ark_3d.py",
    "scripts/bake_color.py",
    "scripts/make_preview.py",
    "scripts/pipeline.py",
    "scripts/print_prep.py",
)


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=dist) as tmp:
        archive_path = Path(tmp) / f"{SKILL_NAME}.zip"
        checksum_path = archive_path.with_suffix(".zip.sha256")
        with ZipFile(archive_path, "w") as archive:
            for filename in FILES:
                source = ROOT / filename
                if source.resolve() != source or not source.is_file():
                    raise SystemExit(f"Expected a regular file in the Skill: {filename}")
                # Keep archive metadata independent of local timestamps and permissions.
                info = ZipInfo(f"{SKILL_NAME}/{filename}")
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes(), compress_type=ZIP_DEFLATED)

        checksum = sha256(archive_path.read_bytes()).hexdigest()
        checksum_path.write_bytes(f"{checksum}  {archive_path.name}\n".encode("ascii"))
        for path in (archive_path, checksum_path):
            path.replace(dist / path.name)
            print(f"dist/{path.name}")


if __name__ == "__main__":
    main()
