from app.content_department.ai_artists.base_artist import BaseArtist


class FRA1(BaseArtist):
    """
    FRA1 - Fall River Artist 1.
    Inherits shared functionality from BaseArtist and BaseCreator.
    """

    # Fixed identity traits
    FIRST_NAME = "FR"
    LAST_NAME = "A1"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "neutral"  # Artists stay apolitical
    STYLE = "versatile"  # Randomized per image
