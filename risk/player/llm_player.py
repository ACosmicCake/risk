import time
from risk.player.player import AbstractRiskPlayer
from risk.llm.interface import LLMInterface
try:
    from risk.graphics.graphics import AI_ACTION_DELAY_SECONDS
except ImportError: # Fallback if graphics not available (e.g. CLI mode tests)
    AI_ACTION_DELAY_SECONDS = 0


# Import game_master related errors if needed for type hinting or specific exceptions
# from risk.errors.game_master import *

# Placeholder for serialize_game_state, will be moved or properly defined later
def get_territory_continent(board_continents: dict, territory_name: str) -> str:
    """Helper function to find the continent of a territory."""
    for continent_name, territories_in_continent in board_continents.items():
        if territory_name in territories_in_continent:
            return continent_name
    return "Unknown" # Should not happen in a consistent board state

def serialize_game_state(game_master, player_perspective) -> dict:
    """
    Serializes the game state for the LLM, providing a comprehensive view.
    """
    if not game_master or not player_perspective:
        return {"error": "Game master or player perspective not available for serialization."}

    current_player_obj = game_master.current_player()
    current_player_name = current_player_obj.name if current_player_obj else "Unknown"
    current_phase = game_master.phase if hasattr(game_master, 'phase') else "UNDEFINED"

    # Your Status
    owned_territories_details = []
    player_owned_territories_map = game_master.player_territories(player_perspective)
    if isinstance(player_owned_territories_map, dict):
        for terr_name, terr_obj in player_owned_territories_map.items():
            owned_territories_details.append({
                "name": terr_obj.name,
                "armies": terr_obj.armies,
                "continent": get_territory_continent(game_master.board.continents, terr_obj.name),
                "neighbors": list(terr_obj.neighbours.keys())
            })
    else:
        print(f"Warning: player_territories for {player_perspective.name} was not a dict, attempting to adapt.")

    your_status = {
        "name": player_perspective.name,
        "reserves": player_perspective.reserves,
        "territories_owned": owned_territories_details,
        "cards": []
    }

    # Board State
    all_territories_details = []
    all_board_territories_for_state = game_master.board.territories() # Method call
    for terr_name, terr_obj in all_board_territories_for_state.items():
        owner_name = terr_obj.owner.name if terr_obj.owner else None
        all_territories_details.append({
            "name": terr_obj.name,
            "owner": owner_name,
            "armies": terr_obj.armies,
            "continent": get_territory_continent(game_master.board.continents, terr_obj.name),
            "neighbors": list(terr_obj.neighbours.keys())
        })

    # Players
    players_details = []
    for p in game_master.players:
        p_territories_count = len(game_master.player_territories(p))
        players_details.append({
            "name": p.name,
            "territory_count": p_territories_count,
            "total_armies": game_master.player_total_armies(p),
            "cards_count": 0
        })

    chat_history = { "global": [], "private": [] }
    if hasattr(game_master, 'chat_log'):
        for msg_entry in reversed(game_master.chat_log):
            if len(chat_history["global"]) >= 10 and msg_entry["type"] == "global": continue
            if len(chat_history["private"]) >= 10 and msg_entry["type"] == "private": continue

            if msg_entry["type"] == "global":
                chat_history["global"].insert(0, msg_entry)
            elif msg_entry["type"] == "private" and \
               (msg_entry["sender_name"] == player_perspective.name or msg_entry["receiver_name"] == player_perspective.name):
                chat_history["private"].insert(0, msg_entry)
            if len(chat_history["global"]) >=10 and len(chat_history["private"]) >=10: break # Combined limit check

    result = {
        "current_turn": { "player_name": current_player_name, "phase": current_phase },
        "your_status": your_status,
        "board_state": all_territories_details,
        "players": players_details,
        "chat_history": chat_history,
        "continent_bonuses": {},
        "continent_control_status": [] # Initialize as empty list
    }

    if hasattr(game_master, 'board') and hasattr(game_master.board, 'get_continent_bonus_values'):
        result["continent_bonuses"] = game_master.board.get_continent_bonus_values()

    # Populate continent_control_status (Restored original complex logic)
    if hasattr(game_master, 'board') and hasattr(game_master.board, 'continents') and isinstance(game_master.board.continents, dict):
        all_board_territories_for_continents = game_master.board.territories() # Potentially re-fetch or use all_board_territories_for_state
        for continent_name, territories_in_continent_map in game_master.board.continents.items():
            total_territories_in_continent = len(territories_in_continent_map)
            territories_held_by_player = {}
            continent_owner = None

            for terr_name_in_continent in territories_in_continent_map.keys():
                terr_obj = all_board_territories_for_continents.get(terr_name_in_continent)
                if terr_obj and terr_obj.owner:
                    owner_name = terr_obj.owner.name
                    territories_held_by_player[owner_name] = territories_held_by_player.get(owner_name, 0) + 1

            for p_name, count in territories_held_by_player.items():
                if count == total_territories_in_continent:
                    continent_owner = p_name
                    break

            control_details = [{"player_name": p_name, "territories_held": count}
                               for p_name, count in territories_held_by_player.items()]

            result["continent_control_status"].append({
                "name": continent_name,
                "bonus_value": result["continent_bonuses"].get(continent_name, 0),
                "total_territories": total_territories_in_continent,
                "current_owner": continent_owner,
                "control_details": control_details
            })

    # Populate potential_attacks for the current player (player_perspective)
    potential_attacks_list = []
    if isinstance(player_owned_territories_map, dict):
        for terr_name, terr_obj in player_owned_territories_map.items():
            if terr_obj.armies > 1:
                for neighbor_name, neighbor_obj in terr_obj.neighbours.items():
                    # Ensure neighbor_obj is not None before accessing owner
                    if neighbor_obj and neighbor_obj.owner != player_perspective:
                        potential_attacks_list.append({
                            "from_territory": terr_name,
                            "to_territory": neighbor_name,
                            "target_owner": neighbor_obj.owner.name if neighbor_obj.owner else "Unowned",
                            "target_armies": neighbor_obj.armies
                        })
    result["your_status"]["potential_attacks"] = potential_attacks_list

    return result


class LLMRiskPlayer(AbstractRiskPlayer):
    def __init__(self, name: str, llm_interface: LLMInterface):
        super().__init__(name)
        self.llm_interface = llm_interface
        self.is_bot = True

        self.system_prompt_part = (
            "You are a grand strategist and a master of diplomacy, playing the board game Risk. "
            "Your objective is to control all 42 territories on the map. "
            "All responses from you MUST be in a valid JSON format. "
            "The top-level JSON object must contain three keys: `thoughts`, `actions`, and `chat`. "
            "`thoughts`: Your detailed strategic analysis and justification for your moves. "
            "`actions`: A list of action objects specific to the current game phase. "
            "`chat`: An object for communication (`{\"global\": \"msg\", \"private\": [{\"to\": \"player\", \"message\": \"msg\"}]}`). "
            "Review `chat_history` for context and to reply to messages.\n"
            "STRATEGIC CONSIDERATIONS:\n"
            "- Alliances: You can form alliances with other players. Use private chat for negotiations, but be wary of betrayal.\n"
            "- Continent Bonuses: Controlling entire continents provides bonus armies each turn. Prioritize securing and holding them. (Refer to 'continent_bonuses' and 'continent_control_status' in game state).\n"
            "- Threat Assessment: Evaluate other players based on their army count, territory holdings, income, and strategic positions. Identify major threats and opportunities.\n"
            "- Diplomacy: Use global and private chat to build relationships, spread misinformation, intimidate rivals, or coordinate with allies."
        )

    def _get_llm_decision(self, game_master, task_prompt_part: str, current_phase_override: str = None) -> dict:
        original_phase = None
        if current_phase_override and hasattr(game_master, 'phase'):
            original_phase = game_master.phase
            game_master.phase = current_phase_override

        game_state_dict = serialize_game_state(game_master, self)

        if original_phase is not None and hasattr(game_master, 'phase'):
            game_master.phase = original_phase

        full_prompt = f"{self.system_prompt_part}\n\nCURRENT_SITUATION_AND_TASK:\n{task_prompt_part}\n\nGAME_STATE:\n{game_state_dict}"
        llm_response = self.llm_interface.get_decision(full_prompt, game_state_dict)

        player_thoughts = llm_response.get('thoughts', None)
        if player_thoughts:
            print(f"LLM ({self.name}) thoughts: {player_thoughts}")
            for callback in game_master.callbacks.get('ai_thoughts_updated', []):
                callback(self.name, player_thoughts)

        if llm_response.get("chat"):
            current_turn_number = getattr(game_master, 'turn_count', -1)

            global_message = llm_response["chat"].get("global")
            if global_message:
                chat_entry = {"turn": current_turn_number, "type": "global",
                              "sender_name": self.name, "message": global_message}
                if hasattr(game_master, 'chat_log'): game_master.chat_log.append(chat_entry)
                print(f"LLM ({self.name}) global chat: {global_message}")
                for callback in game_master.callbacks.get('new_chat_message', []):
                    callback(chat_entry)

            private_messages = llm_response["chat"].get("private")
            if isinstance(private_messages, list):
                for private_msg in private_messages:
                    if isinstance(private_msg, dict) and "to" in private_msg and "message" in private_msg:
                        chat_entry = {"turn": current_turn_number, "type": "private",
                                      "sender_name": self.name, "receiver_name": private_msg["to"],
                                      "message": private_msg["message"]}
                        if hasattr(game_master, 'chat_log'): game_master.chat_log.append(chat_entry)
                        print(f"LLM ({self.name}) private chat to {private_msg.get('to')}: {private_msg.get('message')}")
                        for callback in game_master.callbacks.get('new_chat_message', []):
                            callback(chat_entry)
                    else:
                        print(f"LLM ({self.name}) malformed private chat entry: {private_msg}")
        return llm_response

    def reinforce(self, game_master):
        print(f"{self.name}: Entering reinforcement phase with {self.reserves} reserves.")
        if self.reserves <= 0:
            print(f"{self.name}: No reserves to deploy.")
            return

        task_prompt = (
            f"It is your turn, {self.name}. Game phase: REINFORCE. "
            f"You have {self.reserves} reserve armies. Deploy them strategically to your territories. "
            "Consider continent control status, potential threats, and opportunities for expansion. "
            "Specify reinforcements using 'add' commands in 'actions'. "
            "Example: `\"actions\": [{\"command\": \"add\", \"armies\": 3, \"to\": \"alaska\"}]`"
        )
        llm_response = self._get_llm_decision(game_master, task_prompt)

        actions_taken_count = 0
        if llm_response and "actions" in llm_response and isinstance(llm_response["actions"], list):
            for action in llm_response["actions"]:
                if self.reserves <= 0: break
                if isinstance(action, dict) and action.get("command") == "add":
                    try:
                        territory_name = action["to"]
                        armies_to_add = int(action["armies"])
                        if armies_to_add <= 0: continue

                        actual_armies_to_deploy = min(armies_to_add, self.reserves)
                        print(f"{self.name}: Attempting to deploy {actual_armies_to_deploy} to {territory_name}.")
                        game_master.player_add_army(self, territory_name, actual_armies_to_deploy)
                        print(f"{self.name}: Deployed to {territory_name}. Reserves left: {self.reserves}")
                        actions_taken_count +=1
                        if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
                    except (KeyError, ValueError) as e:
                        print(f"{self.name}: Malformed 'add' action: {action}. Error: {e}")
                    except Exception as e:
                        print(f"{self.name}: Error deploying to {action.get('to', 'unknown')}: {e}")

        if actions_taken_count == 0 and self.reserves > 0:
            print(f"{self.name}: LLM provided no valid 'add' actions. {self.reserves} reserves remain.")

        if self.reserves > 0: # Fallback
            print(f"{self.name}: {self.reserves} reserves remaining. Attempting fallback deployment.")
            player_territories = game_master.player_territories(self)
            if player_territories and isinstance(player_territories, dict) and len(player_territories) > 0 :
                fallback_territory = list(player_territories.keys())[0]
                try:
                    print(f"{self.name}: Fallback: Deploying {self.reserves} to {fallback_territory}.")
                    game_master.player_add_army(self, fallback_territory, self.reserves)
                except Exception as e:
                    print(f"{self.name}: Error during fallback deployment: {e}")
            else:
                print(f"{self.name}: No territories for fallback deployment or territories not in expected dict format.")
        print(f"{self.name}: Reinforcement complete. Reserves left: {self.reserves}")


    def attack(self, game_master):
        print(f"{self.name}: Entering attack phase.")
        task_prompt = (
            f"It is your turn, {self.name}. Game phase: ATTACK. "
            "Decide if and where to attack. Review `your_status.potential_attacks` for immediate options. "
            "Consider current army distributions, continent bonuses, and player threats. "
            "Actions: `{\"command\": \"attack\", \"from\": \"A\", \"to\": \"B\"}`. "
            "If attack succeeds, follow with: `{\"command\": \"move_after_attack\", \"from\": \"A\", \"to\": \"B\", \"armies\": N}`. "
            "Move N armies (min 1, leave 1 in origin). Empty 'actions' list to skip attacking."
        )
        llm_response = self._get_llm_decision(game_master, task_prompt)

        if llm_response and "actions" in llm_response and isinstance(llm_response["actions"], list):
            for action_index, action in enumerate(llm_response["actions"]):
                if not isinstance(action, dict):
                    print(f"{self.name}: Invalid action format: {action}. Skipping.")
                    continue

                if action.get("command") == "attack":
                    try:
                        origin_name = action["from"]
                        target_name = action["to"]

                        origin_territory = game_master.board.territories().get(origin_name)
                        if not origin_territory or origin_territory.owner != self or origin_territory.armies < 2:
                            print(f"{self.name}: Invalid attack: {origin_name} ({origin_territory.armies if origin_territory else 'N/A'}) to {target_name}. Skipping.")
                            continue

                        print(f"{self.name}: Declaring attack: {origin_name} to {target_name}.")
                        for callback in game_master.callbacks.get('attack_declared', []):
                            callback(origin_name, target_name)

                        success = game_master.player_attack(self, origin_name, target_name)

                        if success:
                            print(f"{self.name}: Conquered {target_name} from {origin_name}!")
                            if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
                            self._handle_move_after_attack(game_master, origin_name, target_name, llm_response, action_index)
                        else:
                            print(f"{self.name}: Attack {origin_name} to {target_name} failed.")
                            if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
                    except KeyError as e:
                        print(f"{self.name}: Malformed 'attack' action: {action}. Missing key: {e}")
                    except Exception as e:
                        print(f"{self.name}: Error during attack {action.get('from', '?')}->{action.get('to', '?')}: {e}")
        else:
            print(f"{self.name}: No attack actions or malformed response.")
        print(f"{self.name}: Attack phase complete.")

    def _handle_move_after_attack(self, game_master, origin_name, target_name, llm_response, attack_action_index):
        armies_to_move = None
        if attack_action_index + 1 < len(llm_response["actions"]):
            next_action = llm_response["actions"][attack_action_index + 1]
            if isinstance(next_action, dict) and \
               next_action.get("command") == "move_after_attack" and \
               next_action.get("from") == origin_name and \
               next_action.get("to") == target_name:
                try:
                    armies_to_move = int(next_action["armies"])
                    print(f"{self.name}: LLM move {armies_to_move} to {target_name}.")
                except (ValueError, KeyError) as e:
                    print(f"{self.name}: Invalid 'move_after_attack' action ({next_action}): {e}. Defaulting.")
                    armies_to_move = None

        origin_territory = game_master.board.territories().get(origin_name)
        if not origin_territory or origin_territory.owner != self :
            print(f"{self.name}: Origin {origin_name} not owned/accessible for move. Skipping.")
            return
        if origin_territory.armies <= 1:
            print(f"{self.name}: Only 1 army in {origin_name}. Cannot move. Skipping.")
            return

        min_move = 1
        max_move = origin_territory.armies - 1

        if armies_to_move is None:
            armies_to_move = max(min_move, min(max_move, (origin_territory.armies -1) // 2))
            if armies_to_move == 0 and max_move > 0 : armies_to_move = min_move
            print(f"{self.name}: Default logic: move {armies_to_move} to {target_name}.")

        armies_to_move = max(min_move, min(armies_to_move, max_move))

        if armies_to_move > 0 :
            try:
                game_master.player_move_armies(self, origin_name, target_name, armies_to_move)
                print(f"{self.name}: Moved {armies_to_move} from {origin_name} to {target_name}.")
                if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
            except Exception as e:
                print(f"{self.name}: Error moving armies {origin_name}->{target_name}: {e}")
        else:
            print(f"{self.name}: No armies to move from {origin_name} (available: {origin_territory.armies}).")


    def fortify(self, game_master):
        print(f"{self.name}: Entering fortification phase.")
        task_prompt = (
            f"It is your turn, {self.name}. Game phase: FORTIFY. "
            "Make one move between your connected territories to consolidate forces or strengthen a border. "
            "Consider strategic positioning for future turns and defending continents. "
            "Action: `{\"command\": \"fortify\", \"from\": \"A\", \"to\": \"B\", \"with\": N}`. "
            "Empty 'actions' or 'with: 0' to skip. Only first valid fortify action is used."
        )
        llm_response = self._get_llm_decision(game_master, task_prompt)

        if llm_response and "actions" in llm_response and isinstance(llm_response["actions"], list):
            for action in llm_response["actions"]:
                if not isinstance(action, dict):
                    print(f"{self.name}: Invalid action format: {action}. Skipping.")
                    continue
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
                            print(f"{self.name}: Cannot fortify from {origin_name} (armies: {origin_territory.armies if origin_territory else 'N/A'}, needed: {armies_to_move}). Skipping.")
                            break

                        print(f"{self.name}: Attempting fortify: {origin_name} to {target_name} with {armies_to_move}.")
                        game_master.player_move_armies(self, origin_name, target_name, armies_to_move)
                        print(f"{self.name}: Fortified {origin_name} to {target_name}.")
                        if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
                    except KeyError as e:
                        print(f"{self.name}: Malformed 'fortify' action: {action}. Missing key: {e}")
                    except ValueError as e:
                        print(f"{self.name}: Invalid army count in 'fortify' ({action}): {e}.")
                    except Exception as e:
                        print(f"{self.name}: Error during fortification: {e}")
                    break
        else:
            print(f"{self.name}: No fortify actions or malformed response.")
        print(f"{self.name}: Fortification phase complete.")

    def choose_territory(self, available_territories_map: dict) -> str:
        print(f"{self.name}: Choosing initial territory.")
        current_available_names = list(available_territories_map.keys())
        game_state_for_selection = {
            "current_phase": "INITIAL_TERRITORY_SELECTION",
            "your_name": self.name,
            "available_territories": current_available_names,
            "board_overview": {name: "unclaimed" for name in current_available_names}
        }

        task_prompt = (
            f"It is an initial territory selection phase. You are {self.name}. "
            f"The following territories are available: {current_available_names}. "
            "Select one territory to claim. Your choice should be strategic. "
            "Your response MUST be a JSON object containing a single key 'chosen_territory', "
            "and its value should be the name of the territory you choose. "
            "Example: `{\"chosen_territory\": \"alaska\"}`"
        )

        full_prompt = f"{self.system_prompt_part}\n\nCURRENT_SITUATION_AND_TASK:\n{task_prompt}"
        llm_response = self.llm_interface.get_decision(full_prompt, game_state_for_selection)

        chosen_territory = None
        if isinstance(llm_response, dict) and "chosen_territory" in llm_response:
            candidate_territory = llm_response["chosen_territory"]
            if candidate_territory in available_territories_map:
                chosen_territory = candidate_territory
                print(f"{self.name}: LLM chose territory: {chosen_territory}")
            else:
                print(f"{self.name}: LLM chose unavailable territory '{candidate_territory}'. Fallback.")
        else:
            print(f"{self.name}: LLM failed to provide valid 'chosen_territory' in response ({llm_response}). Fallback.")

        if not chosen_territory:
            chosen_territory = current_available_names[0]
            print(f"{self.name}: Fallback: Chose territory {chosen_territory}")
        return chosen_territory

    def deploy_reserve(self, game_master, max_deploys: int = 0):
        armies_to_deploy_this_round = min(self.reserves, max_deploys)
        if armies_to_deploy_this_round <= 0: return

        print(f"{self.name}: Initial deployment. Has {self.reserves}, deploying {armies_to_deploy_this_round} this round.")

        player_owned_territories_map = game_master.player_territories(self)
        player_owned_territories_names = list(player_owned_territories_map.keys())

        if not player_owned_territories_names:
            print(f"{self.name}: No territories owned for initial deployment. Skipping.")
            return

        task_prompt = (
            f"It is an initial army deployment phase. You are {self.name}. "
            f"You currently own these territories: {player_owned_territories_names}. "
            f"You have {self.reserves} total reserve armies remaining for the entire initial setup. "
            f"In this specific round, you MUST deploy exactly {armies_to_deploy_this_round} armies onto your territories. "
            "Distribute these armies. Provide your decisions in the 'actions' list of your JSON response, using the format: "
            "`{\"command\": \"deploy_initial\", \"armies\": <number>, \"to\": \"<your_territory_name>\"}`. "
            f"The sum of 'armies' in all your 'deploy_initial' actions for this round MUST equal {armies_to_deploy_this_round}."
        )
        llm_response = self._get_llm_decision(game_master, task_prompt, current_phase_override="INITIAL_DEPLOYMENT")

        deployed_this_round_count = 0
        if llm_response and "actions" in llm_response and isinstance(llm_response["actions"], list):
            for action in llm_response["actions"]:
                if deployed_this_round_count >= armies_to_deploy_this_round: break
                if isinstance(action, dict) and action.get("command") == "deploy_initial":
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
                        print(f"{self.name}: Deployed {actual_add} to {territory_name}. Round total: {deployed_this_round_count}/{armies_to_deploy_this_round}. Reserves: {self.reserves}")
                        if AI_ACTION_DELAY_SECONDS > 0: time.sleep(AI_ACTION_DELAY_SECONDS)
                    except (KeyError, ValueError) as e:
                        print(f"{self.name}: Invalid 'deploy_initial' action ({action}): {e}.")
                    except Exception as e:
                        print(f"{self.name}: Error deploying to {action.get('to', 'unknown')}: {e}")

        if deployed_this_round_count < armies_to_deploy_this_round: # Fallback
            remaining_for_round = armies_to_deploy_this_round - deployed_this_round_count
            print(f"{self.name}: LLM under-deployed ({deployed_this_round_count}/{armies_to_deploy_this_round}). {remaining_for_round} left. Fallback.")
            if player_owned_territories_names:
                fallback_territory = player_owned_territories_names[0]
                try:
                    game_master.player_add_army(self, fallback_territory, remaining_for_round)
                    print(f"{self.name}: Fallback: Deployed {remaining_for_round} to {fallback_territory}. Reserves: {self.reserves}")
                except Exception as e:
                    print(f"{self.name}: Error in fallback deployment to {fallback_territory}: {e}")

    def move_after_attack(self, game_master, origin_name: str, target_name: str):
        pass

"""
# Example of how LLMRiskPlayer might be instantiated and used (conceptual)
# ... (rest of the example comments remain the same)
"""
