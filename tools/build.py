import argparse
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect_licenses(notices):
    notices.mkdir(parents=True, exist_ok=True)
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or []:
            if file.name.lower().startswith(("license", "copying", "notice")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = notices / distribution.metadata["Name"] / str(file).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser(description="Сборка настольного MDOW")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--onefile", action="store_true", help="Single EXE with local tools included"
    )
    args = parser.parse_args()
    destination = args.dist_dir.resolve()
    notices = ROOT / "build" / "third-party-licenses"
    collect_licenses(notices)
    extra_args = [
        "--icon",
        str(ROOT / "src/app/assets/md.ico"),
        "--add-data",
        f"{ROOT / 'src/app/assets'};app/assets",
    ]
    if args.onefile:
        for name in ("FFmpeg.txt", "Deno.txt"):
            license_file = ROOT / "tools/bin/licenses" / name
            if not license_file.is_file():
                parser.error(f"Missing bundled tool license: {license_file}")
            shutil.copy2(license_file, notices / name)
        for name in ("ffmpeg.exe", "ffprobe.exe", "deno.exe"):
            tool = ROOT / "tools/bin" / name
            if not tool.is_file():
                parser.error(f"Missing bundled tool: {tool}")
            extra_args.extend(["--add-binary", f"{tool};tools/bin"])
        extra_args.extend(["--add-data", f"{ROOT / 'THIRD_PARTY_NOTICES.md'};."])
        extra_args.extend(["--add-data", f"{notices};third-party-licenses"])
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile" if args.onefile else "--onedir",
            "--windowed",
            "--name",
            "MDOW",
            "--specpath",
            str(ROOT / "build"),
            "--distpath",
            str(destination),
            "--paths",
            str(ROOT / "src"),
            "--collect-all",
            "yt_dlp",
            "--collect-all",
            "yt_dlp_ejs",
            "--copy-metadata",
            "yt-dlp",
            "--copy-metadata",
            "yt-dlp-ejs",
            "--hidden-import",
            "app.adapters.youtube_worker",
            *extra_args,
            str(ROOT / "src" / "app" / "__main__.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    output = destination if args.onefile else destination / "MDOW"
    shutil.copytree(notices, output / "third-party-licenses", dirs_exist_ok=True)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", output)
    print(output / "MDOW.exe")


if __name__ == "__main__":
    main()
