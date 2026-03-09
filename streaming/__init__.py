from .base import StreamingModule
from .filmix.core import Filmix
from .kinopub.core import KinoPub

STREAMING_MODULES: list[type[StreamingModule]] = [
    Filmix,
    KinoPub
]
