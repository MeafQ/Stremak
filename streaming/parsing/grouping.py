from utils import slugify

from .models import Media


def build_binge_group(source: str, stream: Media) -> str:
    parts: list[str] = [source]

    if stream.tracks:
        parts.extend(stream.tracks[0].identity_tokens())

    for field in Media.FIELDS:
        if value := getattr(stream, field):
            parts.append(value.id)

    return slugify("-".join(parts))