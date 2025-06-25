from risk.player.player import AbstractRiskPlayer
from risk.llm.interface import LLMInterface
# Import game_master related errors if needed for type hinting or specific exceptions
# from risk.errors.game_master import *

# Placeholder for serialize_game_state, will be moved or properly defined later
def serialize_game_state(game_master, player_perspective) -> dict:
    """
    Serializes the game state for the LLM.
    This is a basic placeholder and will be significantly expanded in Phase 2.
    """
    if not game_master or not player_perspective:
        # This basic check might be useful for early testing before game_master is fully mocked
        return {"error": "Game master or player perspective not available"}

    current_phase = "unknown"
    # hasattr check is a safe way if game_master might not always have 'phase' (e.g. in minimal mocks)
    if hasattr(game_master, 'phase'):
        current_phase = game_master.phase

    player_territories_data = {}
    if hasattr(game_master, 'player_territories'):
        try:
            territories = game_master.player_territories(player_perspective)
            # Ensure territories is a dict as expected by .keys()
            if isinstance(territories, dict):
                 player_territories_data = list(territories.keys())
            else: # Basic fallback if the structure isn't a dict (e.g. list of territory objects)
                player_territories_data = [str(t) for t in territories] # Or t.name if they are objects
        except Exception as e:
            # Log or handle error if player_territories call fails
            print(f"Error accessing player territories: {e}")
            player_territories_data = {"error": str(e)}


    return {
        "current_phase": current_phase,
        "my_territories": player_territories_data,
        "my_reserves": player_perspective.reserves if hasattr(player_perspective, 'reserves') else 0,
        # Add more basic states as needed for initial LLM calls
    }


class LLMRiskPlayer(AbstractRiskPlayer):
    """
    A Risk player AI controlled by a Large Language Model.
    """
    def __init__(self, name: str, llm_interface: LLMInterface):
        super().__init__(name)
        self.llm_interface = llm_interface
        self.is_bot = True # LLM players are bots

    def reinforce(self, game_master):
        """
        Handles the reinforcement phase for the LLM player.
        The LLM decides where to place armies.
        """
        print(f"{self.name}: Entering reinforcement phase with {self.reserves} reserves.")
        if self.reserves <= 0:
            print(f"{self.name}: No reserves to deploy.")
            return

        game_state_dict = serialize_game_state(game_master, self)
        prompt = (
            f"You are {self.name}, a Risk player. It is the REINFORCE phase. "
            f"You have {self.reserves} reserve armies to deploy. "
            "Analyze your territories and the board state to decide where to place your armies. "
            "Provide your decisions in the specified JSON format under the 'actions' key, like: "
            """{"actions": [{"command": "add", "armies": <number>, "to": "<territory_name>"}]}"""
            "You can specify multiple 'add' commands if you want to distribute armies across territories."
        )

        llm_response = self.llm_interface.get_decision(prompt, game_state_dict)

        actions_taken_count = 0
        if llm_response and "actions" in llm_response:
            for action in llm_response["actions"]:
                if self.reserves <= 0:
                    print(f"{self.name}: All reserves deployed or no more valid actions.")
                    break
                if action.get("command") == "add":
                    try:
                        territory_name = action["to"]
                        armies_to_add = int(action["armies"])

                        if armies_to_add <= 0:
                            print(f"{self.name}: Invalid army count ({armies_to_add}) for {territory_name}. Skipping.")
                            continue

                        # Ensure we don't deploy more than available reserves overall
                        # or more than the player wants for this specific action if it's less than total reserves
                        actual_armies_to_deploy = min(armies_to_add, self.reserves)

                        print(f"{self.name}: Attempting to deploy {actual_armies_to_deploy} armies to {territory_name}.")
                        # TODO: Add proper error handling from game_master.player_add_army
                        game_master.player_add_army(self, territory_name, actual_armies_to_deploy)
                        # self.reserves is updated by game_master.player_add_army
                        print(f"{self.name}: Successfully deployed to {territory_name}. Reserves left: {self.reserves}")
                        actions_taken_count +=1
                    except KeyError:
                        print(f"{self.name}: Malformed 'add' action from LLM: {action}. Missing 'to' or 'armies'.")
                    except ValueError:
                        print(f"{self.name}: Invalid army count in action from LLM: {action}.")
                    except Exception as e: # Catching general exceptions from player_add_army (e.g. TerritoryNotOwned)
                        print(f"{self.name}: Error deploying armies to {action.get('to', 'unknown territory')} as per LLM: {e}")

        if actions_taken_count == 0 :
            print(f"{self.name}: LLM provided no valid 'add' actions, or ran out of reserves. Reinforcement might be incomplete if reserves > 0.")

        # Fallback: If LLM fails to deploy all reserves, distribute remaining ones (e.g., first owned territory or randomly)
        # This is a safety net. Ideally, the LLM and prompt engineering should handle full deployment.
        if self.reserves > 0:
            print(f"{self.name}: {self.reserves} reserves remaining after LLM actions. Attempting fallback deployment.")
            player_territories = game_master.player_territories(self)
            if player_territories:
                # Simple fallback: add all remaining to the first territory.
                # A more sophisticated fallback could distribute them.
                fallback_territory = list(player_territories.keys())[0]
                try:
                    print(f"{self.name}: Fallback: Deploying remaining {self.reserves} armies to {fallback_territory}.")
                    game_master.player_add_army(self, fallback_territory, self.reserves)
                except Exception as e:
                    print(f"{self.name}: Error during fallback deployment to {fallback_territory}: {e}")
            else:
                print(f"{self.name}: No territories to deploy remaining reserves. This shouldn't happen if player is still in game.")
        print(f"{self.name}: Reinforcement phase complete. Reserves left: {self.reserves}")


    def attack(self, game_master):
        """
        Handles the attack phase for the LLM player.
        The LLM decides which territories to attack, if any.
        """
        print(f"{self.name}: Entering attack phase.")
        game_state_dict = serialize_game_state(game_master, self)
        prompt = (
            f"You are {self.name}, a Risk player. It is the ATTACK phase. "
            "Analyze the board state to decide if and where to attack. "
            "Your goal is to conquer territories. Consider army counts and strategic positions. "
            "Provide your decisions in the specified JSON format under the 'actions' key, like: "
            """{"actions": [{"command": "attack", "from": "<your_territory>", "to": "<enemy_territory>"}]}"""
            "You can specify multiple 'attack' commands. If you don't want to attack, provide an empty list for 'actions'."
            "After a successful attack, you must decide how many armies to move into the conquered territory (at least 1, up to all but 1 from the attacking territory)."
            "For this, use the 'move_after_attack' command: "
            """{"command": "move_after_attack", "from": "<origin_territory>", "to": "<conquered_territory>", "armies": <number>}"""
            "The 'move_after_attack' action should immediately follow the 'attack' action that prompted it in the sequence if the LLM is to decide this."
            "Alternatively, the system can handle a default move if this action is not provided after a successful attack."
        )

        llm_response = self.llm_interface.get_decision(prompt, game_state_dict)

        if llm_response and "actions" in llm_response:
            for action_index, action in enumerate(llm_response["actions"]): # Use enumerate to get index
                if action.get("command") == "attack":
                    try:
                        origin_name = action["from"]
                        target_name = action["to"]

                        origin_territory = game_master.board.territories().get(origin_name)
                        if not origin_territory or origin_territory.owner != self or origin_territory.armies < 2:
                            print(f"{self.name}: Cannot attack from {origin_name} (not owned, or < 2 armies). Skipping attack on {target_name}.")
                            continue

                        print(f"{self.name}: Attempting to attack from {origin_name} to {target_name}.")
                        success = game_master.player_attack(self, origin_name, target_name)

                        if success:
                            print(f"{self.name}: Successfully conquered {target_name} from {origin_name}!")
                            self._handle_move_after_attack(game_master, origin_name, target_name, llm_response, action_index) # Pass action_index
                        else:
                            print(f"{self.name}: Attack from {origin_name} to {target_name} failed.")
                    except KeyError:
                        print(f"{self.name}: Malformed 'attack' action from LLM: {action}.")
                    except Exception as e:
                        print(f"{self.name}: Error during attack from {action.get('from', 'unknown')} to {action.get('to', 'unknown')}: {e}")
        else:
            print(f"{self.name}: LLM provided no attack actions or response was malformed.")

        print(f"{self.name}: Attack phase complete.")

    def _handle_move_after_attack(self, game_master, origin_name, target_name, llm_response, attack_action_index): # Added attack_action_index
        """
        Handles moving armies after a successful attack.
        The LLM can specify this, or a default logic is applied.
        """
        armies_to_move = None
        # Check if LLM provided a 'move_after_attack' action immediately following this attack
        if attack_action_index + 1 < len(llm_response["actions"]):
            next_action = llm_response["actions"][attack_action_index + 1]
            if next_action.get("command") == "move_after_attack" and \
               next_action.get("from") == origin_name and \
               next_action.get("to") == target_name:
                try:
                    armies_to_move = int(next_action["armies"])
                    print(f"{self.name}: LLM specified moving {armies_to_move} armies to {target_name}.")
                except (ValueError, KeyError):
                    print(f"{self.name}: LLM provided invalid 'move_after_attack' action: {next_action}. Using default.")
                    armies_to_move = None

        origin_territory = game_master.board.territories().get(origin_name) # Get latest state

        if not origin_territory or origin_territory.owner != self : # Check if still owned (e.g. if it was part of a chain reaction not handled here)
            print(f"{self.name}: Origin territory {origin_name} no longer owned or accessible. Cannot move armies.")
            return

        if origin_territory.armies <= 1:
            print(f"{self.name}: Only 1 army left in {origin_name}, cannot move armies to {target_name}.")
            return

        min_move = 1
        max_move = origin_territory.armies - 1

        if armies_to_move is None:
            armies_to_move = max(min_move, min(max_move, (origin_territory.armies -1) // 2))
            if armies_to_move == 0 and max_move > 0 : armies_to_move = min_move
            print(f"{self.name}: Using default logic: moving {armies_to_move} armies to {target_name}.")

        armies_to_move = max(min_move, min(armies_to_move, max_move)) # Clamp to valid range

        if armies_to_move > 0 :
            try:
                game_master.player_move_armies(self, origin_name, target_name, armies_to_move)
                print(f"{self.name}: Successfully moved {armies_to_move} armies from {origin_name} to {target_name}.")
            except Exception as e:
                print(f"{self.name}: Error moving armies after attack from {origin_name} to {target_name}: {e}")
        else:
            print(f"{self.name}: No armies to move from {origin_name} to {target_name} after adjustments (available: {origin_territory.armies}).")


    def fortify(self, game_master):
        """
        Handles the fortification phase for the LLM player.
        The LLM decides which territories to move armies between, if any.
        One fortification move is allowed per turn.
        """
        print(f"{self.name}: Entering fortification phase.")
        game_state_dict = serialize_game_state(game_master, self)
        prompt = (
            f"You are {self.name}, a Risk player. It is the FORTIFY phase. "
            "You can make one move to fortify a position by moving armies between two of your connected territories. "
            "Analyze the board state to decide if and what fortification move to make. "
            "Provide your decision in the specified JSON format under the 'actions' key, like: "
            """{"actions": [{"command": "fortify", "from": "<your_territory_A>", "to": "<your_territory_B>", "with": <number_of_armies>}]}"""
            "If you don't want to fortify, provide an empty list for 'actions' or an action with 'with': 0."
        )

        llm_response = self.llm_interface.get_decision(prompt, game_state_dict)

        if llm_response and "actions" in llm_response:
            for action in llm_response["actions"]:
                if action.get("command") == "fortify":
                    try:
                        origin_name = action["from"]
                        target_name = action["to"]
                        armies_to_move = int(action["with"])

                        if armies_to_move <= 0:
                            print(f"{self.name}: LLM chose not to fortify (armies: {armies_to_move}).")
                            break

                        origin_territory = game_master.player_territories(self).get(origin_name)
                        if not origin_territory or origin_territory.armies <= armies_to_move :
                            print(f"{self.name}: Cannot fortify from {origin_name} (not enough armies or not owned). Skipping.")
                            break

                        print(f"{self.name}: Attempting to fortify from {origin_name} to {target_name} with {armies_to_move} armies.")
                        game_master.player_move_armies(self, origin_name, target_name, armies_to_move)
                        print(f"{self.name}: Successfully fortified from {origin_name} to {target_name}.")
                        break
                    except KeyError:
                        print(f"{self.name}: Malformed 'fortify' action from LLM: {action}.")
                    except ValueError:
                        print(f"{self.name}: Invalid army count in 'fortify' action from LLM: {action}.")
                    except Exception as e:
                        print(f"{self.name}: Error during fortification: {e}")
                    break
        else:
            print(f"{self.name}: LLM provided no fortify actions or response was malformed.")

        print(f"{self.name}: Fortification phase complete.")

    def choose_territory(self, available_territories_map: dict) -> str:
        """
        Handles initial territory selection for the LLM player.
        """
        print(f"{self.name}: Choosing initial territory.")
        game_state_for_selection = {
            "current_phase": "INITIAL_TERRITORY_SELECTION",
            "available_territories": list(available_territories_map.keys()),
            "board_state": {name: {"owner": None, "armies": 0} for name in available_territories_map.keys()}
        }

        prompt = (
            f"You are {self.name}, a Risk player. It is the initial territory selection phase. "
            f"The following territories are available: {list(available_territories_map.keys())}. "
            "Choose one territory to claim. Consider strategic value. "
            """Provide your decision in JSON format: {"action": {"command": "choose_territory", "territory": "<territory_name>"}}"""
        )

        llm_response = self.llm_interface.get_decision(prompt, game_state_for_selection)

        chosen_territory = None
        if llm_response and "action" in llm_response:
            action = llm_response["action"]
            if action.get("command") == "choose_territory" and action.get("territory") in available_territories_map:
                chosen_territory = action["territory"]
                print(f"{self.name}: LLM chose territory: {chosen_territory}")
            else:
                print(f"{self.name}: LLM provided invalid choice: {action.get('territory')}. Fallback.")
        else:
            print(f"{self.name}: LLM failed to provide valid choice. Fallback.")

        if not chosen_territory:
            chosen_territory = list(available_territories_map.keys())[0]
            print(f"{self.name}: Fallback: Chose territory {chosen_territory}")

        return chosen_territory

    def deploy_reserve(self, game_master, max_deploys: int = 0):
        """
        Handles deployment of reserves during the initial setup phase.
        """
        armies_to_deploy_this_round = min(self.reserves, max_deploys)
        if armies_to_deploy_this_round <= 0:
            return

        print(f"{self.name}: Initial deployment. Has {self.reserves}, deploying up to {armies_to_deploy_this_round} this round.")

        player_owned_territories_names = list(game_master.player_territories(self).keys())
        if not player_owned_territories_names:
            print(f"{self.name}: No territories owned to deploy initial reserves. Skipping deployment.")
            return

        game_state_dict = serialize_game_state(game_master, self)
        prompt = (
            f"You are {self.name}, a Risk player. Initial army deployment phase. "
            f"You own: {player_owned_territories_names}. "
            f"You have {self.reserves} total reserves. This round, deploy exactly {armies_to_deploy_this_round} armies. "
            """Provide decisions as {"actions": [{"command": "deploy_initial", "armies": <N>, "to": "<your_territory>"}]}"""
            f"Sum of 'armies' must be {armies_to_deploy_this_round}."
        )

        llm_response = self.llm_interface.get_decision(prompt, game_state_dict)

        deployed_this_round_count = 0
        if llm_response and "actions" in llm_response:
            for action in llm_response["actions"]:
                if deployed_this_round_count >= armies_to_deploy_this_round:
                    break
                if action.get("command") == "deploy_initial":
                    try:
                        territory_name = action["to"]
                        armies_to_add = int(action["armies"])

                        if armies_to_add <= 0: continue
                        if territory_name not in player_owned_territories_names:
                            print(f"{self.name}: Cannot deploy to {territory_name} (not owned). Skipping.")
                            continue

                        actual_add = min(armies_to_add, armies_to_deploy_this_round - deployed_this_round_count)

                        game_master.player_add_army(self, territory_name, actual_add)
                        deployed_this_round_count += actual_add
                        print(f"{self.name}: Deployed {actual_add} to {territory_name}. Round total: {deployed_this_round_count}/{armies_to_deploy_this_round}. Reserves left: {self.reserves}")

                    except (KeyError, ValueError) as e:
                        print(f"{self.name}: Invalid 'deploy_initial' action ({action}): {e}.")
                    except Exception as e:
                        print(f"{self.name}: Error deploying to {action.get('to', 'unknown')}: {e}")

        if deployed_this_round_count < armies_to_deploy_this_round:
            remaining_for_round = armies_to_deploy_this_round - deployed_this_round_count
            print(f"{self.name}: LLM did not deploy all {armies_to_deploy_this_round}. {remaining_for_round} left. Fallback.")
            if player_owned_territories_names: # Should always be true if we entered this method with armies to deploy
                fallback_territory = player_owned_territories_names[0]
                try:
                    game_master.player_add_army(self, fallback_territory, remaining_for_round)
                    print(f"{self.name}: Fallback: Deployed {remaining_for_round} to {fallback_territory}. Reserves: {self.reserves}")
                except Exception as e:
                    print(f"{self.name}: Error during fallback deployment to {fallback_territory}: {e}")

    def move_after_attack(self, game_master, origin_name: str, target_name: str):
        """
        Called by GameMaster for human players. LLMRiskPlayer handles this internally.
        """
        pass

"""
# Example of how LLMRiskPlayer might be instantiated and used (conceptual)
# from risk.llm.chatgpt import ChatGPTInterface
# from risk.game_master import GameMaster # Assuming GameMaster can be imported
# from risk.board.board import StandardBoard # Assuming a board can be created

# This is for illustrative purposes and would not run directly without a game setup

# def main_example():
    # 1. Create an LLM Interface instance
    # try:
    #     chatgpt_interface = ChatGPTInterface()
    # except ValueError as e:
    #     print(f"Failed to init LLM Interface: {e}")
    #     return

    # 2. Create an LLMRiskPlayer instance
    # llm_player = LLMRiskPlayer(name="Botzilla-GPT", llm_interface=chatgpt_interface)

    # 3. In a game loop (managed by GameMaster), when it's llm_player's turn:
    # Assume game_master object exists and is set up
    # game_board = StandardBoard() # Example board
    # settings = {} # Example settings
    # num_players = 2 # Example
    # game = GameMaster(board=game_board, settings=settings, num_players=num_players)
    # game.players = [llm_player, OtherPlayer()] # Simplified player setup
    # game._current_player = 0 # Set current player to LLM player for testing a phase

    # Manually set some reserves for testing reinforce
    # llm_player.reserves = 10
    # Mock player territories for testing reinforce
    # class MockTerritory:
    #     def __init__(self, name, owner, armies):
    #         self.name = name
    #         self.owner = owner
    #         self.armies = armies
    #     def __str__(self): return self.name

    # territory_alaska = MockTerritory("alaska", llm_player, 5)
    # territory_kamchatka = MockTerritory("kamchatka", "enemy", 3) #
    # territory_alberta = MockTerritory("alberta", llm_player, 2)

    # mock_player_territories = {"alaska": territory_alaska, "alberta": territory_alberta }
    # all_territories = {**mock_player_territories, "kamchatka": territory_kamchatka}


    # Mock game_master methods needed by reinforce and serialize_game_state
    # def mock_gm_player_territories(player):
    #     if player == llm_player:
    #         return mock_player_territories
    #     return {}

    # def mock_gm_player_add_army(player, territory_name, armies):
    #     if player == llm_player and territory_name in mock_player_territories:
    #         mock_player_territories[territory_name].armies += armies
    #         player.reserves -= armies # Crucial: GameMaster is responsible for this
    #         print(f"[Mock GM]: Added {armies} to {territory_name}, new total: {mock_player_territories[territory_name].armies}. Player reserves: {player.reserves}")
    #     else:
    #         raise Exception(f"Mock GM: Cannot add army to {territory_name} for {player.name}")

    # game.player_territories = mock_gm_player_territories
    # game.player_add_army = mock_gm_player_add_army
    # game.phase = "REINFORCE" # Current phase for serialize_game_state
    # game.board = lambda: None # Placeholder
    # game.board.territories = lambda: all_territories # Make all_territories accessible


    # print(f"\n--- Testing Reinforce for {llm_player.name} ---")
    # llm_player.reinforce(game) # game_master instance is passed

    # print(f"\n--- Testing Attack for {llm_player.name} ---")
    # Add mock attack and move methods to game for attack phase test
    # def mock_gm_player_attack(player, origin, target):
    #     print(f"[Mock GM]: {player.name} attacks from {origin} to {target}")
    #     # Simulate success for testing move_after_attack
    #     # In real game, this involves dice rolls etc.
    #     # Assume target territory is conquered:
    #     target_obj = all_territories.get(target)
    #     if target_obj: target_obj.owner = player # change ownership
    #     return True # Simulate attack success

    # def mock_gm_player_move_armies(player, origin, dest, armies):
    #      print(f"[Mock GM]: {player.name} moves {armies} from {origin} to {dest}")
    #      # Actual army updates
    #      if origin in mock_player_territories: mock_player_territories[origin].armies -= armies
    #      if dest in mock_player_territories: mock_player_territories[dest].armies += armies
    #      # if dest was newly conquered, it needs to be added to player's territories if not already
    #      # This logic is simplified for mock.

    # game.player_attack = mock_gm_player_attack
    # game.player_move_armies = mock_gm_player_move_armies
    # game.phase = "ATTACK"
    # llm_player.attack(game)


    # print(f"\n--- Testing Fortify for {llm_player.name} ---")
    # game.phase = "FORTIFY"
    # llm_player.fortify(game)

    # print(f"\n--- Testing Choose Territory for {llm_player.name} ---")
    # available_for_choice = {"greenland": MockTerritory("greenland", None, 0), "iceland": MockTerritory("iceland", None, 0)}
    # choice = llm_player.choose_territory(available_for_choice)
    # print(f"{llm_player.name} chose: {choice}")

    # print(f"\n--- Testing Deploy Reserve for {llm_player.name} ---")
    # llm_player.reserves = 7 # Set reserves for initial deployment test
    # # Assume "alaska" was chosen and is now owned, for deploy_reserve to work on it
    # if "alaska" not in mock_player_territories and "alaska" in all_territories:
    #      all_territories["alaska"].owner = llm_player
    #      mock_player_territories["alaska"] = all_territories["alaska"]

    # game.phase = "INITIAL_DEPLOYMENT"
    # llm_player.deploy_reserve(game, max_deploys=5) # Deploy 5 armies
    # llm_player.deploy_reserve(game, max_deploys=5) # Deploy remaining 2 armies

# if __name__ == "__main__":
#      # This example won't run correctly without a proper environment
#      # and more complete mocking or actual game setup.
#      # main_example()
#      pass
"""
