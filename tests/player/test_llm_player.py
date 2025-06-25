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
# from risk.board.board import RiskBoard
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

        self.captured_phase_in_serialize = None
        def side_effect_serialize_game_state(gm, player_persp):
            self.captured_phase_in_serialize = gm.phase
            return {"mocked_game_state": "data",
                    "current_turn": {"phase": gm.phase},
                    "your_status": {}, "board_state": {}, "players": [], "chat_history": {}}

        self.patcher = patch('risk.player.llm_player.serialize_game_state', side_effect=side_effect_serialize_game_state)
        self.mock_serialize_game_state_patched_obj = self.patcher.start()

        self.player = LLMRiskPlayer(name="TestLLMPlayer", llm_interface=self.mock_llm_interface)

        self.mock_game_master = MagicMock(spec=GameMaster)
        self.mock_game_master.callbacks = {
            'ai_thoughts_updated': [], 'new_chat_message': [], 'attack_declared': []
        }

        board_mock_for_setup = MagicMock()
        board_mock_for_setup.get_continent_bonus_values.return_value = {
            'north_america': 5, 'asia': 7, 'europe': 5, 'africa': 3,
            'south_america': 2, 'australia': 2
        }
        self.alaska = Territory("Alaska"); self.alaska.owner = self.player; self.alaska.armies = 5
        self.alberta = Territory("Alberta"); self.alberta.owner = self.player; self.alberta.armies = 3
        self.kamchatka = Territory("Kamchatka"); self.kamchatka.owner = "Enemy"; self.kamchatka.armies = 8
        self.greenland = Territory("Greenland"); self.greenland.owner = None; self.greenland.armies = 0

        self.alaska.neighbours = {"Alberta": self.alberta, "Kamchatka": self.kamchatka}
        self.alberta.neighbours = {"Alaska": self.alaska}
        self.kamchatka.neighbours = {"Alaska": self.alaska}

        board_mock_for_setup.territories.return_value = {
            "Alaska": self.alaska, "Alberta": self.alberta,
            "Kamchatka": self.kamchatka, "Greenland": self.greenland
        }
        board_mock_for_setup.continents = {
            "north_america": {"Alaska": self.alaska, "Alberta": self.alberta, "Greenland": self.greenland},
            "asia": {"Kamchatka": self.kamchatka}
        }
        self.mock_game_master.board = board_mock_for_setup

        self.mock_game_master.player_territories.return_value = {"Alaska": self.alaska, "Alberta": self.alberta}
        self.mock_game_master.players = [self.player, MagicMock(spec=AbstractRiskPlayer, name="Opponent1")]
        self.mock_game_master.current_player.return_value = self.player
        self.mock_game_master.chat_log = []
        self.mock_game_master.turn_count = 1

        def mock_player_add_army_side_effect(player, territory_name, armies):
            player.reserves -= armies
        self.mock_game_master.player_add_army.side_effect = mock_player_add_army_side_effect

        self.mock_game_master.player_attack.return_value = True
        self.player.reserves = 10
        self.mock_game_master.phase = "UNDEFINED"

    def tearDown(self):
        self.patcher.stop()

    @patch('builtins.print')
    def test_reinforce_with_thoughts_and_chat(self, mock_print):
        self.player.reserves = 5
        self.mock_game_master.phase = "REINFORCE"
        self.mock_llm_interface.set_response({
            "thoughts": "Reinforcing Alaska strategically.",
            "actions": [{"command": "add", "armies": 5, "to": "Alaska"}],
            "chat": {"global": "Taking my turn!", "private": [{"to": "Opponent1", "message": "Watch out!"}]}
        })
        self.player.reinforce(self.mock_game_master)
        self.assertEqual(self.captured_phase_in_serialize, "REINFORCE")
        self.mock_game_master.player_add_army.assert_called_once_with(self.player, "Alaska", 5)
        mock_print.assert_any_call("LLM (TestLLMPlayer) thoughts: Reinforcing Alaska strategically.")
        self.assertIn(call("LLM (TestLLMPlayer) global chat: Taking my turn!"), mock_print.call_args_list)
        self.assertIn(call("LLM (TestLLMPlayer) private chat to Opponent1: Watch out!"), mock_print.call_args_list)

    @patch('builtins.print')
    def test_attack_with_thoughts_and_default_move(self, mock_print):
        self.mock_game_master.phase = "ATTACK"
        self.alaska.armies = 5
        self.mock_llm_interface.set_response({
            "thoughts": "Attacking Kamchatka seems viable.",
            "actions": [{"command": "attack", "from": "Alaska", "to": "Kamchatka"}], "chat": {}
        })
        self.player.attack(self.mock_game_master)
        self.assertEqual(self.captured_phase_in_serialize, "ATTACK")
        self.mock_game_master.player_attack.assert_called_once_with(self.player, "Alaska", "Kamchatka")
        self.mock_game_master.player_move_armies.assert_called_once_with(self.player, "Alaska", "Kamchatka", 2)

    @patch('builtins.print')
    def test_fortify_no_action(self, mock_print):
        self.mock_game_master.phase = "FORTIFY"
        self.mock_llm_interface.set_response({
            "thoughts": "No good fortification move.", "actions": [], "chat": {"global": "Passing."}
        })
        self.player.fortify(self.mock_game_master)
        self.assertEqual(self.captured_phase_in_serialize, "FORTIFY")
        self.mock_game_master.player_move_armies.assert_not_called()

    def test_choose_territory_refined(self):
        self.patcher.stop()
        available = {"Greenland": Territory("Greenland"), "Iceland": Territory("Iceland")}
        available["Greenland"].owner = None; available["Iceland"].owner = None
        self.mock_llm_interface.set_response({"chosen_territory": "Iceland"})
        choice = self.player.choose_territory(available)
        self.assertEqual(choice, "Iceland")
        self.patcher.start()

    @patch('builtins.print')
    def test_deploy_reserve_phase_override_check(self, mock_print):
        self.player.reserves = 5
        self.mock_game_master.phase = "SOME_OTHER_PHASE"
        self.mock_game_master.player_territories.return_value = {"Alaska": self.alaska}
        self.mock_llm_interface.set_response({
            "actions": [{"command": "deploy_initial", "armies": 5, "to": "Alaska"}]
        })
        self.player.deploy_reserve(self.mock_game_master, 5)
        self.assertEqual(self.captured_phase_in_serialize, "INITIAL_DEPLOYMENT")
        self.assertEqual(self.mock_game_master.phase, "SOME_OTHER_PHASE")
        self.mock_game_master.player_add_army.assert_called_once_with(self.player, "Alaska", 5)

    def test_serialize_game_state_comprehensive_and_chat(self):
        self.patcher.stop()

        p1 = MagicMock(spec=AbstractRiskPlayer); p1.name = "P1"; p1.reserves = 5
        p2 = MagicMock(spec=AbstractRiskPlayer); p2.name = "P2"; p2.reserves = 5

        t_ak = Territory("Alaska"); t_ak.owner = p1; t_ak.armies = 5
        t_kam = Territory("Kamchatka"); t_kam.owner = p2; t_kam.armies = 8

        t_ak.neighbours = {"Kamchatka": t_kam}
        t_kam.neighbours = {"Alaska": t_ak}

        mock_gm = MagicMock() # No spec for this test's GameMaster mock
        mock_gm.current_player.return_value = p1
        mock_gm.phase = "ATTACK_TEST"
        mock_gm.players = [p1, p2]
        mock_gm.turn_count = 1

        # Configure mock_gm.board and its attributes/methods directly
        mock_gm.board = MagicMock() # board is a MagicMock

        # Assign a real dictionary to the .continents attribute of mock_gm.board
        mock_gm.board.continents = {
            "north_america": {"Alaska": t_ak},
            "asia": {"Kamchatka": t_kam}
        }
        mock_gm.board.get_continent_bonus_values.return_value = {
            'north_america': 5, 'asia': 7
        }
        mock_gm.board.territories.return_value = {
            "Alaska": t_ak, "Kamchatka": t_kam
        }

        def s_player_territories(player):
            if player == p1: return {"Alaska": t_ak}
            if player == p2: return {"Kamchatka": t_kam}
            return {}
        mock_gm.player_territories.side_effect = s_player_territories

        def s_player_total_armies(player):
            count = 0; terrs = s_player_territories(player)
            if isinstance(terrs, dict):
                for terr_obj in terrs.values(): count += terr_obj.armies
            return count
        mock_gm.player_total_armies.side_effect = s_player_total_armies

        # Pre-assertions about the mock setup
        self.assertIsNotNone(mock_gm.board.continents)
        self.assertIsInstance(mock_gm.board.continents, dict)
        self.assertEqual(len(mock_gm.board.continents), 2)
        self.assertIn("north_america", mock_gm.board.continents)

        mock_gm.chat_log = [{"turn": 1, "type": "global", "sender_name": "P2", "message": "Hi P1!"}]

        state = serialize_game_state(mock_gm, p1)

        self.assertEqual(state["current_turn"]["player_name"], "P1")
        self.assertEqual(state["continent_bonuses"]["north_america"], 5)

        # Main assertion that was failing
        self.assertEqual(len(state["continent_control_status"]), 2,
                         f"Expected 2 continents, got: {state['continent_control_status']}")

        continent_names_in_status = [cs["name"] for cs in state["continent_control_status"]]
        self.assertIn("north_america", continent_names_in_status)
        self.assertIn("asia", continent_names_in_status)

        na_status = next(c for c in state["continent_control_status"] if c["name"] == "north_america")
        self.assertEqual(na_status["current_owner"], "P1")

        potential_attacks = state["your_status"]["potential_attacks"]
        self.assertEqual(len(potential_attacks), 1)
        self.assertEqual(potential_attacks[0]["to_territory"], "Kamchatka")

        self.assertEqual(len(state["chat_history"]["global"]), 1)
        self.assertEqual(state["chat_history"]["global"][0]["message"], "Hi P1!")

        self.patcher.start()

if __name__ == '__main__':
    unittest.main()
