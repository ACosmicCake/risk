import unittest
from unittest.mock import MagicMock, patch, call
import os

# Ensure API keys are set for LLM interface instantiation
os.environ["OPENAI_API_KEY"] = "test_openai_key_for_player_test"
os.environ["GOOGLE_API_KEY"] = "test_google_key_for_player_test"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key_for_player_test"
os.environ["DEEPSEEK_API_KEY"] = "test_deepseek_key_for_player_test"

from risk.player.llm_player import LLMRiskPlayer, serialize_game_state
from risk.llm.interface import LLMInterface
from risk.game_master import GameMaster
from risk.board.territory import Territory
from risk.player.player import AbstractRiskPlayer


class MockLLMInterface(LLMInterface):
    def __init__(self):
        self.response_to_provide = None
        self.get_decision_call_args_list = []

    def get_decision(self, prompt: str, game_state: dict) -> dict:
        self.get_decision_call_args_list.append({'prompt': prompt, 'game_state': game_state})
        if self.response_to_provide:
            return self.response_to_provide
        return {"thoughts": "Default mock thought.", "actions": [], "chat": {"global": "", "private": []}}

    def set_response(self, response: dict):
        self.response_to_provide = response

    def reset_mock(self):
        self.response_to_provide = None
        self.get_decision_call_args_list = []

class TestLLMRiskPlayer(unittest.TestCase):

    def setUp(self):
        self.mock_llm_interface = MockLLMInterface()

        # Mock serialize_game_state to capture the phase it was called with
        self.captured_phase_in_serialize = None
        def side_effect_serialize_game_state(gm, player_persp):
            self.captured_phase_in_serialize = gm.phase # Capture phase
            return {"mocked_game_state": "data", "phase_during_serialization": gm.phase} # Return a value

        self.patcher = patch('risk.player.llm_player.serialize_game_state', side_effect=side_effect_serialize_game_state)
        self.mock_serialize_game_state_patched_obj = self.patcher.start() # This is the MagicMock object

        self.player = LLMRiskPlayer(name="TestLLMPlayer", llm_interface=self.mock_llm_interface)

        self.mock_game_master = MagicMock(spec=GameMaster)
        self.mock_game_master.board = MagicMock()

        self.alaska = Territory("Alaska"); self.alaska.owner = self.player; self.alaska.armies = 5
        self.alberta = Territory("Alberta"); self.alberta.owner = self.player; self.alberta.armies = 3
        self.kamchatka = Territory("Kamchatka"); self.kamchatka.owner = "Enemy"; self.kamchatka.armies = 8
        self.greenland = Territory("Greenland"); self.greenland.owner = None; self.greenland.armies = 0

        self.alaska.neighbours = {"Alberta": self.alberta, "Kamchatka": self.kamchatka}
        self.alberta.neighbours = {"Alaska": self.alaska}

        self.mock_game_master.player_territories.return_value = {"Alaska": self.alaska, "Alberta": self.alberta}
        self.mock_game_master.board.territories.return_value = {
            "Alaska": self.alaska, "Alberta": self.alberta,
            "Kamchatka": self.kamchatka, "Greenland": self.greenland
        }
        self.mock_game_master.board.continents = { # For serialize_game_state when not mocked
            "North America": {"Alaska": self.alaska, "Alberta": self.alberta, "Greenland": self.greenland},
            "Asia": {"Kamchatka": self.kamchatka}
        }
        self.mock_game_master.players = [self.player, MagicMock(spec=AbstractRiskPlayer, name="Opponent1")]
        self.mock_game_master.current_player.return_value = self.player

        def mock_player_add_army_side_effect(player, territory_name, armies):
            player.reserves -= armies
            # Minimal simulation of army change
            if territory_name == "Alaska": self.alaska.armies += armies
            elif territory_name == "Alberta": self.alberta.armies += armies
        self.mock_game_master.player_add_army.side_effect = mock_player_add_army_side_effect

        self.mock_game_master.player_attack.return_value = True
        self.player.reserves = 10
        self.mock_game_master.phase = "UNDEFINED" # Default phase for most tests

    def tearDown(self):
        self.patcher.stop()

    @patch('builtins.print')
    def test_reinforce_with_thoughts_and_chat(self, mock_print):
        self.player.reserves = 5
        self.mock_game_master.phase = "REINFORCE" # Original phase
        self.mock_llm_interface.set_response({
            "thoughts": "Reinforcing Alaska strategically.",
            "actions": [{"command": "add", "armies": 5, "to": "Alaska"}],
            "chat": {"global": "Taking my turn!", "private": [{"to": "Opponent1", "message": "Watch out!"}]}
        })

        self.player.reinforce(self.mock_game_master)

        self.mock_serialize_game_state_patched_obj.assert_called_once_with(self.mock_game_master, self.player)
        self.assertEqual(self.captured_phase_in_serialize, "REINFORCE") # Phase during serialization
        self.assertEqual(len(self.mock_llm_interface.get_decision_call_args_list), 1)
        self.mock_game_master.player_add_army.assert_called_once_with(self.player, "Alaska", 5)
        self.assertEqual(self.player.reserves, 0)

        mock_print.assert_any_call("LLM (TestLLMPlayer) thoughts: Reinforcing Alaska strategically.")
        mock_print.assert_any_call("LLM (TestLLMPlayer) global chat: Taking my turn!")
        mock_print.assert_any_call("LLM (TestLLMPlayer) private chat to Opponent1: Watch out!")


    @patch('builtins.print')
    def test_attack_with_thoughts_and_default_move(self, mock_print):
        self.mock_game_master.phase = "ATTACK"
        self.alaska.armies = 5
        self.mock_llm_interface.set_response({
            "thoughts": "Attacking Kamchatka seems viable.",
            "actions": [{"command": "attack", "from": "Alaska", "to": "Kamchatka"}],
            "chat": {}
        })

        self.player.attack(self.mock_game_master)

        self.mock_serialize_game_state_patched_obj.assert_called_once_with(self.mock_game_master, self.player)
        self.assertEqual(self.captured_phase_in_serialize, "ATTACK")
        self.mock_game_master.player_attack.assert_called_once_with(self.player, "Alaska", "Kamchatka")
        self.mock_game_master.player_move_armies.assert_called_once_with(self.player, "Alaska", "Kamchatka", 2)
        mock_print.assert_any_call("LLM (TestLLMPlayer) thoughts: Attacking Kamchatka seems viable.")

    @patch('builtins.print')
    def test_fortify_no_action(self, mock_print):
        self.mock_game_master.phase = "FORTIFY"
        self.mock_llm_interface.set_response({
            "thoughts": "No good fortification move this turn.",
            "actions": [],
            "chat": {"global": "Passing fortify."}
        })

        self.player.fortify(self.mock_game_master)

        self.mock_serialize_game_state_patched_obj.assert_called_once_with(self.mock_game_master, self.player)
        self.assertEqual(self.captured_phase_in_serialize, "FORTIFY")
        self.mock_game_master.player_move_armies.assert_not_called()
        mock_print.assert_any_call("LLM (TestLLMPlayer) thoughts: No good fortification move this turn.")
        mock_print.assert_any_call("LLM (TestLLMPlayer) global chat: Passing fortify.")

    def test_choose_territory_refined(self):
        self.patcher.stop() # Stop general patch for this specific test

        available = {"Greenland": Territory("Greenland"), "Iceland": Territory("Iceland")}
        available["Greenland"].owner = None; available["Iceland"].owner = None

        self.mock_llm_interface.set_response({"chosen_territory": "Iceland"})

        choice = self.player.choose_territory(available)

        self.assertEqual(len(self.mock_llm_interface.get_decision_call_args_list), 1)
        prompt_arg = self.mock_llm_interface.get_decision_call_args_list[0]['prompt']
        game_state_arg = self.mock_llm_interface.get_decision_call_args_list[0]['game_state']

        self.assertIn("INITIAL_TERRITORY_SELECTION", game_state_arg["current_phase"])
        self.assertIn("chosen_territory", prompt_arg)
        self.assertEqual(choice, "Iceland")

        self.patcher.start() # Restart patch


    @patch('builtins.print')
    def test_deploy_reserve_refined(self, mock_print):
        self.player.reserves = 7
        max_deploys_this_round = 5
        self.mock_game_master.phase = "DEPLOY_TROOPS_PHASE_UNRELATED_TO_SERIALIZATION" # Actual GM phase

        self.mock_game_master.player_territories.return_value = {"Alaska": self.alaska} # For deploy_reserve logic

        self.mock_llm_interface.set_response({
            "thoughts": "Deploying initial armies.",
            "actions": [{"command": "deploy_initial", "armies": 3, "to": "Alaska"},
                        {"command": "deploy_initial", "armies": 2, "to": "Alaska"}],
            "chat": {}
        })

        self.player.deploy_reserve(self.mock_game_master, max_deploys_this_round)

        self.mock_serialize_game_state_patched_obj.assert_called_once_with(self.mock_game_master, self.player)
        # Check that serialize_game_state was called with the phase overridden
        self.assertEqual(self.captured_phase_in_serialize, "INITIAL_DEPLOYMENT")
        # Check that game_master.phase is restored after the call to _get_llm_decision
        self.assertEqual(self.mock_game_master.phase, "DEPLOY_TROOPS_PHASE_UNRELATED_TO_SERIALIZATION")

        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 3)
        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 2)
        self.assertEqual(self.mock_game_master.player_add_army.call_count, 2)
        self.assertEqual(self.player.reserves, 2)
        mock_print.assert_any_call("LLM (TestLLMPlayer) thoughts: Deploying initial armies.")

    def test_serialize_game_state_comprehensive(self):
        self.patcher.stop() # Stop the general patch to test the real serialize_game_state

        mock_player_self_obj = MagicMock(spec=AbstractRiskPlayer)
        mock_player_self_obj.name = "TestLLMPlayerSerialize"
        mock_player_self_obj.reserves = 7

        mock_player_other_obj = MagicMock(spec=AbstractRiskPlayer)
        mock_player_other_obj.name = "OpponentSerialize"
        mock_player_other_obj.reserves = 10

        alaska = Territory("Alaska"); alberta = Territory("Alberta")
        kamchatka = Territory("Kamchatka"); greenland = Territory("Greenland")

        alaska.owner = mock_player_self_obj; alaska.armies = 5
        alberta.owner = mock_player_self_obj; alberta.armies = 3
        kamchatka.owner = mock_player_other_obj; kamchatka.armies = 8
        greenland.owner = None; greenland.armies = 0

        alaska.neighbours = {"Alberta": alberta, "Kamchatka": kamchatka}
        alberta.neighbours = {"Alaska": alaska}; kamchatka.neighbours = {"Alaska": alaska}
        greenland.neighbours = {}

        mock_gm = MagicMock(spec=GameMaster)
        mock_gm.current_player.return_value = mock_player_self_obj
        mock_gm.phase = "ATTACK_SERIALIZE"
        # Mock players list on game_master
        mock_gm.players = [mock_player_self_obj, mock_player_other_obj]


        mock_board = MagicMock()
        mock_board.continents = {
            "North America": {"Alaska": alaska, "Alberta": alberta, "Greenland": greenland},
            "Asia": {"Kamchatka": kamchatka}
        }
        mock_board.territories.return_value = {
            "Alaska": alaska, "Alberta": alberta, "Kamchatka": kamchatka, "Greenland": greenland
        }
        mock_gm.board = mock_board

        def s_player_territories(player):
            if player == mock_player_self_obj: return {"Alaska": alaska, "Alberta": alberta}
            if player == mock_player_other_obj: return {"Kamchatka": kamchatka}
            return {}
        mock_gm.player_territories.side_effect = s_player_territories

        def s_player_total_armies(player):
            count = 0; terrs = s_player_territories(player)
            if isinstance(terrs, dict):
                for terr_obj in terrs.values(): count += terr_obj.armies
            return count
        mock_gm.player_total_armies.side_effect = s_player_total_armies

        state = serialize_game_state(mock_gm, mock_player_self_obj)

        self.assertEqual(state["current_turn"]["player_name"], "TestLLMPlayerSerialize")
        self.assertEqual(state["current_turn"]["phase"], "ATTACK_SERIALIZE")
        self.assertEqual(state["your_status"]["name"], "TestLLMPlayerSerialize")
        self.assertEqual(len(state["your_status"]["territories_owned"]), 2)
        alaska_status = next(t for t in state["your_status"]["territories_owned"] if t["name"] == "Alaska")
        self.assertEqual(alaska_status["continent"], "North America")
        self.assertEqual(len(state["board_state"]), 4)
        self.assertEqual(len(state["players"]), 2)
        player_other_in_list = next(p for p in state["players"] if p["name"] == "OpponentSerialize")
        self.assertEqual(player_other_in_list["territory_count"], 1)
        self.assertEqual(player_other_in_list["total_armies"], 8)

        self.patcher.start()

if __name__ == '__main__':
    unittest.main()
