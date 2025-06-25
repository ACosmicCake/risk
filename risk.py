#!/usr/bin/env python3
# std
import argparse
import sys
import os
# user
import risk
import risk.logger
import risk.game_master
from risk import board
from risk.game_master import GameMaster

# fixes the pathing so that the game doesn't need to be run from root
if '__file__' in globals():
    root = os.path.dirname(__file__) or './'
    os.path.join(root)
    os.chdir(root)

# exit codes
_EXIT_BAD_ARGS = -1

###############################################################################
## CLI option parsing
#
def app_setup():
    parser = argparse.ArgumentParser(description='Risk game with Python')
    # dev build defaults to debug for now
    parser.add_argument('--verbose', '-v', action='count',
                        help='extra output', default=risk.logger.LEVEL_DEBUG)
    parser.add_argument('--cli', '-c', action='store_true',
                        help='commandline version of game', default=False)
    settings = parser.parse_args()
    risk.logger.LOG_LEVEL = settings.verbose
    return settings

###############################################################################
## CLI functionsr
#
def print_banner():
    print("""
    --==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==--
    ||                              PyRisk                             ||
    ||-----------------------------------------------------------------||
    || Risk is a turn-based game for two to six players. The standard  ||
    || version is played on a board depicting a political map of the   ||
    || Earth, divided into forty-two territories, which are grouped    ||
    || into six continents. The primary object of the game is "world   ||
    || domination," or "to occupy every territory on the board and in  ||
    || so doing, eliminate all other players." Players control         ||
    || armies with which they attempt to capture territories from      ||
    || other players, with results determined by dice rolls.           ||
    ||-----------------------------------------------------------------||
    ||                     By: CMPT106 Group Beta                      ||
    --==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==-==--
""")


###############################################################################
## Debug functions
#
def end_turn_debug_print(game_master):
    risk.logger.debug('Ending turn...')

###############################################################################
## Main game functions
#
def game_setup(settings):
    _DEV_HUMAN_PLAYERS = 1
    game_board = board.generate_empty_board()
    #game_board = board.generate_mini_board()
    game_master = risk.game_master.GameMaster(game_board, settings)
    game_master.generate_players(_DEV_HUMAN_PLAYERS, settings.cli)
    game_master.add_end_turn_callback(end_turn_debug_print)
    # dev
    board.dev_random_assign_owners(game_master)
    return game_master

def run_game(game_master):
    print_banner()
    risk.logger.debug('Starting risk game...')
    try:
        #game_master.choose_territories()
        #game_master.deploy_troops()
        while not game_master.ended:
            run_turn(game_master)
    except (risk.errors.input.UserQuitInput, KeyboardInterrupt, EOFError):
        game_master.end_game()
    except BaseException as e:
        risk.logger.critical(repr(e))
        risk.logger.critical('unknown error occured, attempting perform'\
            ' graceful shutdown...')
        game_master.end_game()
    risk.logger.debug('User quit the game!')

def run_turn(game_master):
    risk.logger.debug('Current player is: %s' % 
                      game_master.current_player().name)
    game_master.player_take_turn()
    game_master.call_end_turn_callbacks()
    game_master.end_turn()

if __name__ == '__main__':
    settings = app_setup()
    risk.logger.debug(settings)

    if not settings.cli:
        import pygame # Import pygame for setup screen
        from risk.graphics.screens import SetupScreen # Import the new setup screen

        pygame.init()
        # Determine screen size - use defaults from graphics.py or define here
        # For now, using a common size, can be refactored to use graphics.DEFAULT_WIDTH/HEIGHT
        screen_width = 1152
        screen_height = 720
        screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Risk Game Setup")

        setup_screen_instance = SetupScreen(screen, None) # Picasso not needed for setup screen itself
        num_players_from_setup, player_configs_from_setup, next_action = setup_screen_instance.run_loop()

        if next_action == "quit":
            risk.logger.info("User quit from setup screen.")
            pygame.quit()
            sys.exit()

        # Proceed to game_setup with new configurations
        # We need to modify game_setup to accept these new parameters
        # For now, game_setup is not modified, but master will be configured based on setup.
        # This part needs careful integration with how GameMaster is initialized.

        game_board = board.generate_empty_board()
        # GameMaster needs to be initialized *after* setup gives us player configs
        master = risk.game_master.GameMaster(game_board, settings)
        # generate_players will need to be updated to use player_configs_from_setup
        # master.generate_players(num_players_from_setup, player_configs_from_setup, cli=False)
        # For now, I'll call a modified generate_players later in the plan step.

        # Initialize main game graphics AFTER setup is done
        import risk.graphics
        risk.graphics.init(master) # This will use the already created screen if picasso is adapted
                                   # or picasso might re-create its own screen.
                                   # Ideally, picasso should take the existing screen.
                                   # For now, assuming picasso handles this.
        master.add_end_game_callback(risk.graphics.shutdown)

        # Initialize GameMaster with the correct number of players from setup
        master = risk.game_master.GameMaster(game_board, settings, num_players=num_players_from_setup)

        # Call the updated generate_players method
        master.generate_players(player_configs_from_setup, cli=False)

        # Assign territories and reserves AFTER players are generated
        # These were previously in game_setup() or called by it.
        board.dev_random_assign_owners(master) # Or a more structured territory selection process
                                               # For now, dev_random_assign_owners includes _assign_player_reserves

        # Initialize main game graphics AFTER setup and GameMaster player generation is done
        import risk.graphics
        # Picasso might need to be initialized with the existing screen from setup
        # For now, assuming risk.graphics.init() can handle this or adapt.
        # It might be better if picasso = get_picasso(screen=screen) is possible
        risk.graphics.init(master, screen=screen) # Pass screen to graphics.init
        master.add_end_game_callback(risk.graphics.shutdown)

    else: # CLI mode
        # CLI mode still uses the old game_setup for now.
        # Could be refactored to also use a simpler config mechanism if desired.
        master = game_setup(settings)

    # Common game run logic
    if master: # Ensure master was initialized
        # Add other common callbacks if they were in game_setup previously
        master.add_end_turn_callback(end_turn_debug_print)
        run_game(master)
    else:
        risk.logger.critical("GameMaster not initialized. Exiting.")
        if not settings.cli and pygame.get_init():
            pygame.quit()
        sys.exit(_EXIT_BAD_ARGS)
