# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 情绪零碎の佳 (Jia060117)
"""Per-user calibration location; never bundle a developer's device profile."""
import os
from pathlib import Path

RENDER_PROFILE=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Automix/render-profile.json'
