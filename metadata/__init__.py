from .base import MetadataModule
from .tmdb.core import TheMovieDB

METADATA_MODULES: list[type[MetadataModule]] = [TheMovieDB]
