from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def delete_generated_audio_files(
    directory: Path,
    audio_files: Iterable[str],
    *,
    retained: Iterable[str] = (),
) -> dict[str, int]:
    """Delete safe WAV basenames and their Studio metadata sidecars."""
    audio_directory = directory.resolve()
    retained_names = set(retained)
    deleted_audio = 0
    deleted_metadata = 0
    for raw_name in set(audio_files):
        name = Path(str(raw_name)).name
        if (
            name != raw_name
            or Path(name).suffix.lower() != ".wav"
            or name in retained_names
        ):
            continue
        audio_path = (audio_directory / name).resolve()
        if audio_path.parent != audio_directory:
            continue
        metadata_path = audio_path.with_suffix(".json")
        if audio_path.is_file():
            audio_path.unlink()
            deleted_audio += 1
        if metadata_path.is_file():
            metadata_path.unlink()
            deleted_metadata += 1
    return {"audio_deleted": deleted_audio, "metadata_deleted": deleted_metadata}
