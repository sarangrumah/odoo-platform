# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    custom_ai_enabled = fields.Boolean(
        string="Enable AI Intelligence",
        config_parameter="custom_ai.enabled",
        default=True,
    )
    custom_ai_default_quality = fields.Selection(
        [("fast", "Fast (default)"), ("high", "High quality (more expensive)")],
        string="Default Quality Tier",
        config_parameter="custom_ai.quality",
        default="fast",
    )
    custom_ai_provider_override = fields.Selection(
        [
            ("", "Use gateway default"),
            ("anthropic", "Anthropic Claude"),
            ("openai", "OpenAI"),
            ("ollama", "Local Ollama"),
        ],
        string="Provider Override",
        config_parameter="custom_ai.provider_override",
    )
