from abc import ABC, abstractmethod

class LLMInterface(ABC):
    """
    Abstract base class for Large Language Model interfaces.
    Ensures a standardized way to interact with different LLMs.
    """

    @abstractmethod
    def get_decision(self, prompt: str, game_state: dict) -> dict:
        """
        Gets a decision from the LLM based on the provided prompt and game state.

        Args:
            prompt: The instruction or question for the LLM.
            game_state: A dictionary representing the current state of the game,
                        structured for the LLM to understand.

        Returns:
            A dictionary containing the LLM's decision, typically including
            strategic thoughts and actions in a standardized format.
        """
        pass
