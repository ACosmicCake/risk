from .base import *
from .clickable import *
from .dialog import *
from .gameplay import *
from .image import *
from .message import * # Assuming message.py exists or is planned
from .player import *  # Assuming player.py exists (likely for player specific GUI assets not Player logic)
from .territory import *
from .text import *
from .ui_panels import * # This should now work as ui_panels.py exists

# It's good practice to define __all__ to specify what gets exported with "from .assets import *"
# Collect __all__ from submodules if they define it, or list names explicitly.
# For simplicity now, assuming direct imports are used or modules handle their own exports.
# However, if we want to control `from risk.graphics.assets import *`:
_base_all = ['PicassoAsset', 'ColourBlockAsset', 'BLACK', 'WHITE', 'GREY', 'RED', 'GREEN', 'BLUE', 'YELLOW', 'PURPLE', 'ORANGE', 'PINK', 'BROWN', 'CYAN'] # from base.py
_clickable_all = ['ClickableAsset', 'ImageButtonAsset'] # from clickable.py
_dialog_all = ['ConfirmDialog'] # from dialog.py
_gameplay_all = ['PlayersAsset'] # from gameplay.py
_image_all = ['ImageAsset', 'ToggleImageAsset'] # from image.py
_message_all = [] # from message.py (if it has exported names)
_player_all = [] # from player.py (if it has exported names)
_territory_all = ['TerritoryAsset', 'ArmyCountAsset', 'build_territory_asset', 'build_player_colour_mapping'] # from territory.py
_text_all = ['TextAsset', 'CentredTextAsset', 'CurrentPlayerAsset'] # from text.py
_ui_panels_all = ['ScrollableTextPanel', 'ThoughtsPanel', 'CommunicationPanel'] # from ui_panels.py


__all__ = _base_all + _clickable_all + _dialog_all + _gameplay_all + \
            _image_all + _message_all + _player_all + _territory_all + \
            _text_all + _ui_panels_all
