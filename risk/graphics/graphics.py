import _thread
import time

import pygame

import risk
import risk.player
from risk.graphics import picasso
from risk.graphics.assets import base
from risk.graphics.assets import clickable
from risk.graphics.assets import territory
from risk.graphics.assets import dialog
from risk.graphics.assets import image
from risk.graphics.assets import gameplay
from risk.graphics.assets import text
from risk.graphics.assets import ui_panels

from risk.logger import *
from risk.game_master import UNDEFINED, REINFORCE, ATTACK, FORTIFY
from risk.graphics.event import wait_for_event, get_events
from risk.graphics.datastore import Datastore
from risk.graphics.picasso import get_picasso
from risk.graphics.assets.territory import build_territory_asset
from risk.graphics.assets.territory import build_player_colour_mapping
from risk.graphics.assets.territory import TerritoryAsset

DEFAULT_WIDTH  = 1152
DEFAULT_HEIGHT = 720
DEFAULT_BACKGROUND = 'resources/risk_board.png'
DEFAULT_OVERLAY = 'assets/art/gui/main_borders.png'

INFO_PANEL_X = 370
INFO_PANEL_Y = 585
INFO_PANEL_WIDTH = 410
INFO_PANEL_HEIGHT = 110

# Delay for AI actions to make them observable
AI_ACTION_DELAY_SECONDS = 0.5 # Configurable: 0.5 seconds delay between AI actions

UI_OVERLAY_LEVEL0 = '2_ui'
UI_OVERLAY_LEVEL1 = '3_ui'

territory_coordinates = {
    'north_america': {
        'alaska': (29, 117),
        'northwest_territory': (98, 97),
        'greenland': (335, 42),
        'alberta': (113, 157),
        'ontario': (227, 158),
        'eastern_canada': (310, 153),
        'western_united_states': (164, 213),
        'eastern_united_states': (245, 210),
        'central_america': (182, 267)
    },
    'south_america': {
        'venezuela': (293, 328),
        'peru': (291, 372),
        'brazil': (344, 350),
        'argentina': (317, 445),
    },
    'europe': {
        'iceland': (517, 122),
        'scandinavia': (577, 113),
        'russia': (630, 119),
        'great_britain': (511, 166),
        'northern_europe': (576, 177),
        'western_europe': (528, 200),
        'southern_europe': (589, 211)
    },
    'africa': {
        'north_africa': (504, 251),
        'egypt': (603, 253),
        'central_africa': (581, 333),
        'east_africa': (651, 302),
        'south_africa': (601, 395),
        'madagascar': (698, 380)
    },
    'asia': {
        'ural': (764, 92),
        'siberia': (793, 57),
        'yakutsk': (930, 90),
        'kamchatka': (983, 115),
        'irkutsk': (875, 142),
        'afghanistan': (705, 192),
        'china': (811, 196),
        'mongolia': (871, 182),
        'japan': (977, 201),
        'middle_east': (644, 230),
        'india': (770, 257),
        'southern_asia': (847, 274)
    },
    'australia': {
        'indonesia': (861, 355),
        'new_guinea': (994, 357),
        'western_australia': (941, 412),
        'eastern_australia': (1004, 402)
    }
}

def init(game_master, screen=None): # Add screen parameter with a default
    debug("initializing graphics library...")
    add_graphic_hooks(game_master)
    debug("attempting to get singleton picasso")
    # If a screen is passed, Picasso should use it instead of creating a new one.
    # This requires picasso.get_picasso to be able to accept a 'screen' argument.
    # For now, this change assumes picasso.get_picasso is adapted or ignores extra kwargs.
    # If screen is None, it operates as before.
    picasso = get_picasso(width=DEFAULT_WIDTH, 
            height=DEFAULT_HEIGHT, background=DEFAULT_BACKGROUND, screen=screen)
    debug("obtained picasso instance")
    debug("building risk board")
    initialize_territories(picasso, game_master)
    initialize_other_graphic_assets(picasso, game_master)
    debug("starting picasso graphics subsystem")
    picasso.start()
    debug("picasso subsystem successfully launched!")
    debug("adding basic assets")
    add_overlay(picasso)
    add_buttons(picasso)
    debug("returning control to main loop")

def shutdown(*args):
    debug("end game event received! attempting to shutdown picasso...")
    picasso = get_picasso()
    picasso.end()
    debug("sent picasso shutdown event, fingers crossed...")

def add_graphic_hooks(game_master):
    game_master.add_start_turn_callback(check_picasso_liveness)
    game_master.add_start_turn_callback(show_bot_player_hint)
    #game_master.add_start_turn_callback(show_human_player)
    game_master.add_start_turn_callback(delay)
    game_master.add_start_turn_callback(check_gui_quit_event)
    game_master.add_end_turn_callback(check_gui_quit_event)
    game_master.add_end_action_callback(release_control)
    game_master.add_start_turn_callback(update_game_info_panel)
    game_master.add_end_action_callback(update_game_info_panel)
    game_master.add_end_phase_callback(update_current_phase)
    game_master.add_start_turn_callback(show_current_human_player)
    #game_master.add_end_action_callback(delay)

    # Add hooks for AI Mind-Reader panels
    game_master.add_ai_thoughts_updated_callback(update_ai_thoughts_panel)
    game_master.add_new_chat_message_callback(add_chat_message_to_panel)
    # Add hook for attack declaration visualization
    game_master.add_attack_declared_callback(visualize_attack_declaration)


# Handler for AI thoughts update
def update_ai_thoughts_panel(player_name, thoughts_text):
    datastore = Datastore()
    try:
        thoughts_panel = datastore.get_entry('thoughts_panel')
        if game_master_instance and player_name == game_master_instance.current_player().name: # Ensure it's the current player's thoughts
            thoughts_panel.set_text(f"[{player_name}'s Thoughts]:\n{thoughts_text}")
        elif not game_master_instance : # Should not happen if game is running
             thoughts_panel.set_text(f"[{player_name}'s Thoughts (GM not ref)]:\n{thoughts_text}")
    except KeyError:
        error("Thoughts panel not found in datastore for AI thoughts update.")
    except Exception as e:
        error(f"Error updating thoughts panel: {e}")

# Handler for new chat messages
def add_chat_message_to_panel(chat_data):
    datastore = Datastore()
    try:
        comm_panel = datastore.get_entry('communication_panel')
        sender = chat_data.get("sender_name", "Unknown")
        message = chat_data.get("message", "")

        if chat_data.get("type") == "global":
            comm_panel.add_global_message(sender, message)
        elif chat_data.get("type") == "private":
            receiver = chat_data.get("receiver_name", "Unknown")
            # Pass current player name if needed by add_private_message for context
            # For now, assuming CommunicationPanel handles the display logic sufficiently
            comm_panel.add_private_message(sender, receiver, message,
                                           current_player_name=game_master_instance.current_player().name if game_master_instance else "N/A")
    except KeyError:
        error("Communication panel not found in datastore for chat message.")
    except Exception as e:
        error(f"Error adding chat message to panel: {e}")

# Handler for attack declaration visualization
def visualize_attack_declaration(origin_name, target_name):
    datastore = Datastore()
    try:
        origin_asset = datastore.get_entry(origin_name, 'territories')
        target_asset = datastore.get_entry(target_name, 'territories')

        if origin_asset and hasattr(origin_asset, 'start_flashing'):
            origin_asset.start_flashing(duration=1.0, color=base.ORANGE) # Flash orange for attacker
        else:
            warn(f"Could not find TerritoryAsset for origin: {origin_name} or it doesn't support flashing.")

        if target_asset and hasattr(target_asset, 'start_flashing'):
            target_asset.start_flashing(duration=1.0, color=base.RED) # Flash red for defender
        else:
            warn(f"Could not find TerritoryAsset for target: {target_name} or it doesn't support flashing.")

    except KeyError as e:
        error(f"Territory asset not found in datastore for attack visualization: {e}")
    except Exception as e:
        error(f"Error during attack visualization: {e}")


# Need a reference to game_master for context in callbacks, e.g. current player
game_master_instance = None

def initialize_territories(picasso, game_master):
    global game_master_instance
    game_master_instance = game_master # Store game_master reference

    datastore = Datastore()
    for continent, territories in game_master.board.continents.items():
        for territory_name, territory_obj in territories.items():
            coordinate = territory_coordinates[continent][territory_name]
            graphic_asset = build_territory_asset(continent, territory_obj, coordinate[0], coordinate[1])
            army_count_asset = territory.ArmyCountAsset(graphic_asset)
            picasso.add_asset('3_territories', graphic_asset)
            picasso.add_asset('4_army_count', army_count_asset)
            
            datastore.add_entry(territory_name, graphic_asset, 'territories')
    risk.logger.debug("assigning player colours")
    build_player_colour_mapping(game_master.players)

def initialize_other_graphic_assets(picasso, game_master):
    picasso = get_picasso()
    datastore = Datastore()
    #current_player_asset = assets.text.CurrentPlayerAsset(
    #        100, 100, game_master)
    #picasso.add_asset('4_current_player', current_player_asset)
    #datastore.add_entry('current_player', current_player_asset)
    feedback_asset = text.TextAsset(100, 650, 
            'choose territory to attack')
    datastore.add_entry('attack_feedback', feedback_asset)
    game_info_asset = gameplay.PlayersAsset(30, 550, game_master)
    picasso.add_asset(UI_OVERLAY_LEVEL0, game_info_asset)
    datastore.add_entry('game_info', game_info_asset)
    add_state_indicators(picasso, game_master)
    player_background_asset = base.ColourBlockAsset(
        1000, 548, 123, 80, base.BLACK)
    human_player_asset = base.ColourBlockAsset(
        1002, 550, 119, 76, base.GREY)
    datastore.add_entry('player_colour', human_player_asset)
    picasso.add_asset(UI_OVERLAY_LEVEL0, player_background_asset)
    picasso.add_asset(UI_OVERLAY_LEVEL1, human_player_asset)

    # Initialize AI Mind-Reader Panels
    # Define panel dimensions and positions (these are examples, adjust as needed)
    thoughts_panel_x = 750  # Right side of the screen
    thoughts_panel_y = 350
    thoughts_panel_width = 370
    thoughts_panel_height = 150

    comms_panel_x = thoughts_panel_x
    comms_panel_y = thoughts_panel_y + thoughts_panel_height + 10 # Below thoughts panel
    comms_panel_width = thoughts_panel_width
    comms_panel_height = 150

    thoughts_panel = ui_panels.ThoughtsPanel(
        thoughts_panel_x, thoughts_panel_y, thoughts_panel_width, thoughts_panel_height
    )
    datastore.add_entry('thoughts_panel', thoughts_panel)
    picasso.add_asset(UI_OVERLAY_LEVEL0, thoughts_panel) # Add to a suitable layer

    # CommunicationPanel currently draws its own children in its test code.
    # For Picasso integration, we'd typically add children as separate assets
    # or CommunicationPanel's draw() returns a fully composed surface.
    # Let's assume CommunicationPanel's children (like its internal global_chat_display)
    # will be managed by its own draw method for now, or added separately if they become PicassoAssets.

    # communication_panel_container = assets.ui_panels.CommunicationPanel(
    #     comms_panel_x, comms_panel_y, comms_panel_width, comms_panel_height
    # )
    # datastore.add_entry('communication_panel_container', communication_panel_container)
    # picasso.add_asset(UI_OVERLAY_LEVEL0, communication_panel_container) # Draws the border/bg

    # The actual text display part of CommunicationPanel
    # This assumes CommunicationPanel is updated to expose its child display panel
    # Or, we create and manage it here. For simplicity, let's assume comms_panel_display is the main asset.
    communication_panel_display = ui_panels.CommunicationPanel( # Renaming for clarity
         comms_panel_x, comms_panel_y, comms_panel_width, comms_panel_height
    )
    datastore.add_entry('communication_panel', communication_panel_display)
    # Add its main surface (border/bg)
    picasso.add_asset(UI_OVERLAY_LEVEL0, communication_panel_display)
    # Add its child text display panel (global_chat_display)
    # This requires CommunicationPanel to expose global_chat_display as a PicassoAsset
    # or for global_chat_display to be created and managed here.
    # For now, let's assume CommunicationPanel.global_chat_display is a PicassoAsset
    # and its x,y are screen coordinates.
    # This part is a bit tricky with current CommunicationPanel design.
    # A simpler approach for now: CommPanel's draw() renders everything on its surface.
    # Or, we only instantiate and add its ScrollableTextPanel child directly to Picasso for now.

    # Let's refine CommunicationPanel: its draw() should return its fully rendered surface.
    # The ScrollableTextPanel child will be drawn onto CommunicationPanel's surface.
    # So, only communication_panel_display (the CommunicationPanel instance) is added to Picasso.

    # If CommunicationPanel's children (like global_chat_display) need separate event handling
    # or Picasso layer management, they would need to be separate PicassoAssets.
    # For now, CommunicationPanel's handle_event will manage its children's events.


def add_state_indicators(picasso, game_master):
    datastore = Datastore()
    pos_x = 867
    state_indicators = {
        'reinforce': (pos_x, 548),
        'attack': (pos_x, 600),
        'fortify': (pos_x, 652),
    }
    for state, coordinate in state_indicators.items():
        asset = image.ToggleImageAsset(coordinate[0], coordinate[1],
            "assets/art/gui/button_%s_highlight.png" % state)
        datastore.add_entry(state, asset, 'states')
        picasso.add_asset(UI_OVERLAY_LEVEL0, asset)
   
def add_buttons(picasso):
    datastore = Datastore()
    #next_button = assets.clickable.ClickableAsset(
    #    1000, 635, 120, 65, 'NEXT')
    next_button = clickable.ImageButtonAsset(
        1000, 635,
        'assets/art/gui/button_next_up.png',
        'assets/art/gui/button_next_down.png'
    )
    datastore.add_entry('next', next_button, 'buttons')

    for button in list(datastore.get_storage('buttons').values()):
        picasso.add_asset('1_buttons', button)

def add_overlay(picasso):
    datastore = Datastore()
    overlay = image.ImageAsset(0, 0, DEFAULT_OVERLAY)
    datastore.add_entry('overlay', overlay)
    picasso.add_asset('0_overlay', overlay)

def show_human_player(game_master):
    layer = 3
    if not hasattr(show_human_player, 'asset'):
        asset = text.TextAsset(
            50, 50, 'Player is taking turn...')
        setattr(show_human_player, 'asset', asset)
    asset = getattr(show_human_player, 'asset')
    if isinstance(game_master.current_player(), risk.player.HumonRiskPlayer):
        get_picasso().add_asset('1_text', asset)
    else:
        get_picasso().remove_asset('1_text', asset)

def show_current_human_player(game_master):
    datastore = Datastore()
    asset = datastore.get_entry('player_colour')
    player = game_master.current_player()
    if isinstance(player, risk.player.HumonRiskPlayer):
        try:
            asset.set_colour(TerritoryAsset.mapping[player])
        except KeyError:
            error("couldn't find key entry for player: %s" % player.name)
            asset.set_colour(base.BLACK)
    else:
        asset.set_colour(base.GREY)

def is_human_player(game_master):
    return isinstance(game_master.current_player(), 
            risk.player.HumonRiskPlayer)

def delay(game_master, *args):
    if not is_human_player(game_master):
        time.sleep(1)

def check_picasso_liveness(game_master):
    if not get_picasso().is_alive():
        game_master.end_game()

def check_gui_quit_event(game_master):
    """
    During a non-human player's turn, this allows the event queue to be
    pumped, specifically to check for a QUIT event.
    """
    if not is_human_player(game_master):
        # get_events() will raise UserQuitInput if a QUIT event is found, which
        # is caught by the main run_game loop to gracefully end the game.
        get_events()

def update_game_info_panel(*args):
    Datastore().get_entry('game_info').update()

def update_current_phase(game_master, previous, current):
    for state, asset in Datastore().get_storage('states').items():
        asset.set_state(state == current)

def show_bot_player_hint(game_master):
    datastore = Datastore()
    picasso = get_picasso()
    if not datastore.has_entry('bot_player_hint'):
        hint_asset = text.CentredTextAsset(INFO_PANEL_X, INFO_PANEL_Y, 
                    INFO_PANEL_WIDTH, INFO_PANEL_HEIGHT, 
                    "AI TAKING TURNS...",
                    bold=True)
        datastore.add_entry('bot_player_hint', hint_asset)
    hint_asset = datastore.get_entry('bot_player_hint')
    if not is_human_player(game_master):
        picasso.add_asset(UI_OVERLAY_LEVEL0, hint_asset)
    else:
        picasso.remove_asset(UI_OVERLAY_LEVEL0, hint_asset)

def release_control(game_master, *args):
    # release CPU for faster screen update
    time.sleep(0)

def pressed_clickables(mouse_pos, storage='buttons'):
    datastore = Datastore()
    storage = datastore.get_storage(storage)
    clicked = []
    for name, button in storage.items():
        if button.mouse_hovering(mouse_pos):
            if button.confirmed_click():
                clicked.append((name, button))
    return clicked
