from app.content_department.ai_artists.base_artist import BaseArtist


class SpectraVeritas(BaseArtist):
    """
    Spectra Veritas - An AI artist personality.
    Inherits shared functionality from BaseArtist and BaseCreator.
    """

    # Fixed identity traits
    FIRST_NAME = "Spectra"
    LAST_NAME = "Veritas"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "neutral"  # Artists stay apolitical
    STYLE = "versatile"  # Randomized per image
