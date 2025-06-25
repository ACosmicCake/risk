import unittest
from unittest.mock import MagicMock, patch, call
import os

# Ensure API keys are set for LLM interface instantiation, though they won't be used by mock interface
os.environ["OPENAI_API_KEY"] = "test_openai_key_for_player_test"
# Add other keys if your LLM interfaces try to load them immediately even when mocked externally
os.environ["GOOGLE_API_KEY"] = "test_google_key_for_player_test"
os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_key_for_player_test"
os.environ["DEEPSEEK_API_KEY"] = "test_deepseek_key_for_player_test"

from risk.player.llm_player import LLMRiskPlayer, serialize_game_state
from risk.llm.interface import LLMInterface #Needed for type hint
from risk.game_master import GameMaster # For type hinting and structure
from risk.board.territory import Territory # For territory objects

# A mock LLM Interface that we can control for tests
class MockLLMInterface(LLMInterface):
    def __init__(self):
        self.response = None # Default response
        self.get_decision_called_with = []

    def get_decision(self, prompt: str, game_state: dict) -> dict:
        self.get_decision_called_with.append({'prompt': prompt, 'game_state': game_state})
        if self.response:
            return self.response
        # Default fallback response if none is set by the test
        return {"thoughts": "Mock LLM thought something.", "actions": [], "chat": {}}

    def set_response(self, response: dict):
        self.response = response

    def reset_mock(self):
        self.response = None
        self.get_decision_called_with = []

class TestLLMRiskPlayer(unittest.TestCase):

    def setUp(self):
        self.mock_llm_interface = MockLLMInterface()
        self.player = LLMRiskPlayer(name="TestLLMPlayer", llm_interface=self.mock_llm_interface)

        # Mock GameMaster and its dependencies extensively
        self.mock_game_master = MagicMock(spec=GameMaster)
        self.mock_game_master.board = MagicMock()

        # Mock territories
        self.territory_a = Territory("Alaska")
        self.territory_a.armies = 5
        self.territory_a.owner = self.player # Player owns Alaska

        self.territory_b = Territory("Alberta")
        self.territory_b.armies = 3
        self.territory_b.owner = self.player # Player owns Alberta

        self.territory_c = Territory("Kamchatka") # Enemy territory
        self.territory_c.armies = 4
        self.territory_c.owner = "EnemyPlayer"

        # Minimal neighbour setup for any connectivity checks if they become relevant
        # self.territory_a.neighbours = {"Alberta": self.territory_b, "Kamchatka": self.territory_c}
        # self.territory_b.neighbours = {"Alaska": self.territory_a}
        # self.territory_c.neighbours = {"Alaska": self.territory_a}


        # Setup mock_game_master methods
        self.mock_game_master.player_territories.return_value = {
            "Alaska": self.territory_a,
            "Alberta": self.territory_b
        }
        self.mock_game_master.board.territories.return_value = {
            "Alaska": self.territory_a,
            "Alberta": self.territory_b,
            "Kamchatka": self.territory_c
        }
        # GameMaster's player_add_army updates player.reserves
        def mock_player_add_army(player, territory_name, armies):
            player.reserves -= armies
            # Simulate army addition on territory if needed for other logic
            if territory_name == "Alaska": self.territory_a.armies += armies
            elif territory_name == "Alberta": self.territory_b.armies += armies

        self.mock_game_master.player_add_army.side_effect = mock_player_add_army
        self.mock_game_master.player_attack.return_value = True # Assume attack succeeds for move tests

        # Reset player reserves for each test, some methods modify it
        self.player.reserves = 10
        self.mock_game_master.phase = "UNDEFINED" # Default phase


    def tearDown(self):
        # Clean up environment variables if they were specific to this test class
        # For now, they are set globally before class definition
        pass

    def test_player_creation(self):
        self.assertEqual(self.player.name, "TestLLMPlayer")
        self.assertTrue(self.player.is_bot)
        self.assertEqual(self.player.llm_interface, self.mock_llm_interface)

    def test_reinforce_basic(self):
        self.player.reserves = 5
        self.mock_game_master.phase = "REINFORCE"
        self.mock_llm_interface.set_response({
            "actions": [{"command": "add", "armies": 3, "to": "Alaska"},
                        {"command": "add", "armies": 2, "to": "Alberta"}]
        })

        self.player.reinforce(self.mock_game_master)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 3)
        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alberta", 2)
        self.assertEqual(self.player.reserves, 0) # All reserves deployed

    def test_reinforce_partial_llm_deploy_with_fallback(self):
        self.player.reserves = 10
        self.mock_game_master.phase = "REINFORCE"
        # LLM only deploys 5 armies
        self.mock_llm_interface.set_response({
            "actions": [{"command": "add", "armies": 5, "to": "Alaska"}]
        })

        self.player.reinforce(self.mock_game_master)

        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 5)
        # Fallback should deploy remaining 5 to the first territory ("Alaska" in mock setup)
        # The first call is the LLM's, the second is the fallback.
        self.assertEqual(self.mock_game_master.player_add_army.call_count, 2)
        # Check the fallback call specifically (it will be the last one)
        self.mock_game_master.player_add_army.assert_called_with(self.player, "Alaska", 5) # Fallback
        self.assertEqual(self.player.reserves, 0)


    def test_reinforce_no_reserves(self):
        self.player.reserves = 0
        self.mock_game_master.phase = "REINFORCE"
        self.player.reinforce(self.mock_game_master)
        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 0) # Should not call LLM
        self.mock_game_master.player_add_army.assert_not_called()

    def test_attack_basic_and_move(self):
        self.mock_game_master.phase = "ATTACK"
        self.territory_a.armies = 5 # Ensure enough armies to attack and move

        # LLM decides to attack, then specifies move
        self.mock_llm_interface.set_response({
            "actions": [
                {"command": "attack", "from": "Alaska", "to": "Kamchatka"},
                {"command": "move_after_attack", "from": "Alaska", "to": "Kamchatka", "armies": 3}
            ]
        })

        self.player.attack(self.mock_game_master)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_attack.assert_called_once_with(self.player, "Alaska", "Kamchatka")
        # Assuming attack is successful (mocked to return True), player_move_armies should be called
        self.mock_game_master.player_move_armies.assert_called_once_with(self.player, "Alaska", "Kamchatka", 3)

    def test_attack_no_action_from_llm(self):
        self.mock_game_master.phase = "ATTACK"
        self.mock_llm_interface.set_response({"actions": []}) # LLM decides not to attack

        self.player.attack(self.mock_game_master)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_attack.assert_not_called()
        self.mock_game_master.player_move_armies.assert_not_called()

    def test_attack_default_move(self):
        self.mock_game_master.phase = "ATTACK"
        self.territory_a.armies = 5 # Attacking territory
        self.mock_game_master.player_attack.return_value = True # Attack succeeds

        # LLM decides to attack, but does NOT specify move_after_attack
        self.mock_llm_interface.set_response({
            "actions": [{"command": "attack", "from": "Alaska", "to": "Kamchatka"}]
        })

        self.player.attack(self.mock_game_master)

        self.mock_game_master.player_attack.assert_called_once_with(self.player, "Alaska", "Kamchatka")
        # Default move logic: (5-1)//2 = 2 armies. Min 1, Max 4. So 2 is correct.
        self.mock_game_master.player_move_armies.assert_called_once_with(self.player, "Alaska", "Kamchatka", 2)


    def test_fortify_basic(self):
        self.mock_game_master.phase = "FORTIFY"
        self.territory_a.armies = 10 # Source for fortification
        self.mock_llm_interface.set_response({
            "actions": [{"command": "fortify", "from": "Alaska", "to": "Alberta", "with": 3}]
        })

        self.player.fortify(self.mock_game_master)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_move_armies.assert_called_once_with(self.player, "Alaska", "Alberta", 3)

    def test_fortify_no_action_from_llm(self):
        self.mock_game_master.phase = "FORTIFY"
        self.mock_llm_interface.set_response({"actions": []}) # LLM decides not to fortify

        self.player.fortify(self.mock_game_master)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_move_armies.assert_not_called()

    def test_choose_territory_llm_provides_valid(self):
        available = {"Greenland": Territory("Greenland"), "Iceland": Territory("Iceland")}
        # Set required attributes if needed for the test, e.g. owner, armies, though choose_territory might not use them
        available["Greenland"].owner = None
        available["Greenland"].armies = 0
        available["Iceland"].owner = None
        available["Iceland"].armies = 0

        self.mock_llm_interface.set_response({
            "action": {"command": "choose_territory", "territory": "Iceland"}
        })

        choice = self.player.choose_territory(available)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.assertEqual(choice, "Iceland")

    def test_choose_territory_llm_provides_invalid_fallback(self):
        available = {"Greenland": Territory("Greenland"), "Iceland": Territory("Iceland")}
        available["Greenland"].owner = None
        available["Greenland"].armies = 0
        available["Iceland"].owner = None
        available["Iceland"].armies = 0

        self.mock_llm_interface.set_response({
            "action": {"command": "choose_territory", "territory": "Egypt"} # Egypt not available
        })

        choice = self.player.choose_territory(available)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.assertEqual(choice, "Greenland") # Fallback to first available

    def test_deploy_reserve_initial_setup(self):
        self.player.reserves = 7
        max_deploys_this_round = 5
        # Alaska is owned by player from setup
        self.mock_game_master.phase = "INITIAL_DEPLOYMENT"

        self.mock_llm_interface.set_response({
            "actions": [{"command": "deploy_initial", "armies": 3, "to": "Alaska"},
                        {"command": "deploy_initial", "armies": 2, "to": "Alberta"}]
        })

        self.player.deploy_reserve(self.mock_game_master, max_deploys_this_round)

        self.assertEqual(len(self.mock_llm_interface.get_decision_called_with), 1)
        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 3)
        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alberta", 2)
        self.assertEqual(self.mock_game_master.player_add_army.call_count, 2)
        self.assertEqual(self.player.reserves, 2) # 7 - 5 = 2 reserves left overall

    def test_deploy_reserve_llm_fails_fallback(self):
        self.player.reserves = 5
        max_deploys_this_round = 5
        self.mock_game_master.phase = "INITIAL_DEPLOYMENT"

        # LLM only deploys 2, or provides invalid action
        self.mock_llm_interface.set_response({
            "actions": [{"command": "deploy_initial", "armies": 2, "to": "Alaska"}]
        })

        self.player.deploy_reserve(self.mock_game_master, max_deploys_this_round)

        self.mock_game_master.player_add_army.assert_any_call(self.player, "Alaska", 2) # LLM's action
        # Fallback should deploy remaining 3 (5-2) to "Alaska" (first owned territory)
        self.mock_game_master.player_add_army.assert_called_with(self.player, "Alaska", 3) # Fallback call
        self.assertEqual(self.mock_game_master.player_add_army.call_count, 2)
        self.assertEqual(self.player.reserves, 0)

    def test_serialize_game_state_basic(self):
        self.player.reserves = 3
        self.mock_game_master.phase = "TEST_PHASE"
        # player_territories mock is already set up in self.setUp

        state = serialize_game_state(self.mock_game_master, self.player)

        self.assertEqual(state["current_phase"], "TEST_PHASE")
        self.assertEqual(state["my_reserves"], 3)
        self.assertIn("Alaska", state["my_territories"])
        self.assertIn("Alberta", state["my_territories"])


if __name__ == '__main__':
    unittest.main()
