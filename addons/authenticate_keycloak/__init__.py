from . import models
from . import controllers
from dotenv import load_dotenv

# load_dotenv()  # take environment variables
import os
import logging

_logger = logging.getLogger(__name__)

env_path = "/etc/odoo/.env"
if os.path.exists(env_path):
    load_dotenv(env_path)
    _logger.info("Loaded environment variables from %s", env_path)
else:
    load_dotenv(override=False)
