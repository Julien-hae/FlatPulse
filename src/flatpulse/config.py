"""Configuration management for the FlatPulse application."""

import os

REQUIRED_VARS = ["DATABASE_URL", "TELEGRAM_BOT_TOKEN"]


class Config:
    """Represents the application configuration."""

    def __init__(self) -> None:
        """Initialize the configuration by reading environment variables."""
        missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
        if missing:
            raise SystemExit(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example → .env and fill in the values."
            )
        self.database_url = os.environ["DATABASE_URL"]
        self.telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.log_format = os.environ.get("LOG_FORMAT", "text")
        self.poll_interval = int(os.environ.get("POLL_INTERVAL_DEFAULT", "120"))


CANTON_TO_ABR = {
    # Zürich (ZH)
    "Zürich": "ZH",
    "Zurich": "ZH",
    "Zurigo": "ZH",
    # Bern (BE)
    "Bern": "BE",
    "Berne": "BE",
    "Berna": "BE",
    # Luzern (LU)
    "Luzern": "LU",
    "Lucerne": "LU",
    "Lucerna": "LU",
    # Uri (UR)
    "Uri": "UR",
    # Schwyz (SZ)
    "Schwyz": "SZ",
    "Schwytz": "SZ",
    "Svitto": "SZ",
    # Obwalden (OW)
    "Obwalden": "OW",
    "Obwald": "OW",
    "Obvaldo": "OW",
    # Nidwalden (NW)
    "Nidwalden": "NW",
    "Nidwald": "NW",
    "Nidvaldo": "NW",
    # Glarus (GL)
    "Glarus": "GL",
    "Glaris": "GL",
    "Glarona": "GL",
    # Zug (ZG)
    "Zug": "ZG",
    "Zoug": "ZG",
    "Zugo": "ZG",
    # Fribourg (FR)
    "Fribourg": "FR",
    "Freiburg": "FR",
    "Friburgo": "FR",
    # Solothurn (SO)
    "Solothurn": "SO",
    "Soleure": "SO",
    "Soletta": "SO",
    # Basel-Stadt (BS)
    "Basel": "BS",  # générique (comme dans votre exemple)
    "Bâle": "BS",  # générique FR
    "Basel-Stadt": "BS",
    "Basel-City": "BS",
    "Bâle-Ville": "BS",
    "Basilea Città": "BS",
    # Basel-Landschaft (BL)
    "Basel-Landschaft": "BL",
    "Basel-Country": "BL",
    "Bâle-Campagne": "BL",
    "Basilea Campagna": "BL",
    # Schaffhausen (SH)
    "Schaffhausen": "SH",
    "Schaffhouse": "SH",
    "Sciaffusa": "SH",
    # Appenzell Ausserrhoden (AR)
    "Appenzell Ausserrhoden": "AR",
    "Appenzell Rhodes-Extérieures": "AR",
    "Appenzello Esterno": "AR",
    # Appenzell Innerrhoden (AI)
    "Appenzell Innerrhoden": "AI",
    "Appenzell Rhodes-Intérieures": "AI",
    "Appenzello Interno": "AI",
    # St. Gallen (SG)
    "St. Gallen": "SG",
    "St Gall": "SG",
    "Sankt Gallen": "SG",
    "Saint-Gall": "SG",
    "San Gallo": "SG",
    # Graubünden (GR)
    "Graubünden": "GR",
    "Grisons": "GR",
    "Grigioni": "GR",
    # Aargau (AG)
    "Aargau": "AG",
    "Argovie": "AG",
    "Argovia": "AG",
    # Thurgau (TG)
    "Thurgau": "TG",
    "Thurgovie": "TG",
    "Turgovia": "TG",
    # Ticino (TI)
    "Ticino": "TI",
    "Tessin": "TI",
    # Vaud (VD)
    "Vaud": "VD",
    "Waadt": "VD",
    # Valais (VS)
    "Valais": "VS",
    "Wallis": "VS",
    "Vallese": "VS",
    # Neuchâtel (NE)
    "Neuchâtel": "NE",
    "Neuenburg": "NE",
    # Genève (GE)
    "Genève": "GE",
    "Geneva": "GE",
    "Genf": "GE",
    "Ginevra": "GE",
    # Jura (JU)
    "Jura": "JU",
    "Giura": "JU",
}
