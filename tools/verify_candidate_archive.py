#!/usr/bin/env python3
"""Verify a weather candidate ZIP against its JSON manifest without extracting."""

import argparse
import hashlib
import json
import sys
import zipfile


def sha256_stream(stream):
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="path to c8_hardware_candidates_v1.zip")
    parser.add_argument("manifest", help="path to matching .manifest.json")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    failures = []
    with open(args.archive, "rb") as archive_file:
        archive_digest = sha256_stream(archive_file)
    expected_archive_digest = manifest.get("archive_sha256")
    if expected_archive_digest and archive_digest != expected_archive_digest:
        failures.append(f"archive SHA-256 mismatch: expected {expected_archive_digest}, got {archive_digest}")

    expected = {entry["path"]: entry for entry in manifest.get("files", [])}
    if len(expected) != len(manifest.get("files", [])):
        failures.append("manifest contains duplicate file paths")

    checked = 0
    with zipfile.ZipFile(args.archive, "r") as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        actual_names = [info.filename for info in members]
        if len(set(actual_names)) != len(actual_names):
            failures.append("archive contains duplicate file paths")

        actual = set(actual_names)
        embedded_manifest_seen = False
        for info in members:
            if info.filename != "manifest.json":
                continue
            embedded_manifest_seen = True
            with archive.open(info, "r") as member_stream:
                embedded = json.load(member_stream)
            if embedded.get("status") != manifest.get("status"):
                failures.append("embedded manifest status does not match external manifest")
            if embedded.get("files") != manifest.get("files"):
                failures.append("embedded manifest file list does not match external manifest")

        for path in sorted(set(expected) - actual):
            failures.append(f"missing archive member: {path}")
        for path in sorted(actual - set(expected) - {"manifest.json"}):
            failures.append(f"unlisted archive member: {path}")

        for info in members:
            entry = expected.get(info.filename)
            if entry is None:
                continue
            checked += 1
            if info.file_size != entry["bytes"]:
                failures.append(
                    f"{info.filename}: size mismatch, expected {entry['bytes']}, got {info.file_size}"
                )
            with archive.open(info, "r") as member_stream:
                digest = sha256_stream(member_stream)
            if digest != entry["sha256"]:
                failures.append(f"{info.filename}: SHA-256 mismatch")

    print(f"archive_sha256={archive_digest}")
    print(f"embedded_manifest={'present' if embedded_manifest_seen else 'absent'}")
    print(f"manifest_files={len(expected)}")
    print(f"verified_members={checked}")
    print(f"status={'FAIL' if failures else 'PASS'}")
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
