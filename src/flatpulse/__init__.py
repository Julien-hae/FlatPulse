"""FlatPulse: real-time alerts on the listings Swiss agencies publish on their own sites.

Scrapers read the agencies (`scrapers`), on the shared models and Swiss-format
parsing of `common`; `db` stores what they find. Architecture: docs/architecture.md.
"""

from flatpulse.common import logging_configuration

logging_configuration.configure_logger()
