import pygame
import risk.graphics.assets.text as text_assets
import risk.graphics.assets.clickable as clickable_assets
from risk.graphics.assets.base import GREY, WHITE, BLACK, RED, GREEN # Example colors
from risk.llm import __all__ as llm_interface_names_list # Gets ['LLMInterface', 'ChatGPTInterface', ...]
from risk.ai.bots import BasicRiskBot # Assuming BasicRiskBot is what's used

# Filter out LLMInterface itself, just keep concrete ones
AVAILABLE_LLM_INTERFACES = [name for name in llm_interface_names_list if name != "LLMInterface" and name.endswith("Interface")]
# Manually add other player types
PLAYER_TYPES = ["Human", "BasicBot"] + AVAILABLE_LLM_INTERFACES


class SetupScreen:
    def __init__(self, screen, picasso_instance):
        self.screen = screen
        self.picasso = picasso_instance # May not be used if setup is pre-picasso init
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 28)
        self.running = True
        self.next_screen = None # To indicate what to do after setup

        self.num_players = 2
        # Player configurations: list of dicts e.g. [{"name": "Player 1", "type": "Human"}, ...]
        self.player_configs = [{"name": f"Player {i+1}", "type": PLAYER_TYPES[0]} for i in range(self.num_players)]
        self.active_dropdown = None # To manage which player's type selection is active

        self.ui_elements = {} # Store clickable elements here
        self._create_ui_elements()

    def _create_ui_elements(self):
        self.ui_elements = {} # Clear previous elements

        # Title
        self.ui_elements['title'] = text_assets.TextAsset(50, 50, "Game Setup", colour=WHITE, size=48)

        # Number of players selection
        self.ui_elements['num_players_label'] = text_assets.TextAsset(50, 120, f"Number of Players: {self.num_players}", colour=WHITE)
        self.ui_elements['num_players_decrease'] = clickable_assets.ClickableAsset(300, 118, 30, 30, "-", text_colour=BLACK, size=30, bg_colour=GREY, highlight_bg=WHITE)
        self.ui_elements['num_players_increase'] = clickable_assets.ClickableAsset(340, 118, 30, 30, "+", text_colour=BLACK, size=30, bg_colour=GREY, highlight_bg=WHITE)

        # Player type selectors
        y_offset = 180
        for i in range(self.num_players):
            player_label = f"player_{i}_label"
            player_type_button = f"player_{i}_type_button"
            self.ui_elements[player_label] = text_assets.TextAsset(50, y_offset, f"Player {i+1} Type:", colour=WHITE)
            current_type = self.player_configs[i]["type"]
            self.ui_elements[player_type_button] = clickable_assets.ClickableAsset(250, y_offset -2, 250, 30, current_type, text_colour=BLACK, bg_colour=GREY, highlight_bg=WHITE)

            # Dropdown options (simplified: shown when active_dropdown == i)
            if self.active_dropdown == i:
                dropdown_y = y_offset + 35
                for pt_idx, p_type in enumerate(PLAYER_TYPES):
                    option_key = f"player_{i}_option_{p_type}"
                    self.ui_elements[option_key] = clickable_assets.ClickableAsset(250, dropdown_y + (pt_idx * 30), 250, 25, p_type, text_colour=BLACK, size=24, bg_colour=WHITE, highlight_bg=GREEN)
            y_offset += 80 if self.active_dropdown == i else 40 # More space if dropdown is open
            if self.active_dropdown == i: y_offset += len(PLAYER_TYPES) * 30


        # Start Game Button
        self.ui_elements['start_button'] = clickable_assets.ClickableAsset(50, y_offset + 50, 200, 50, "Start Game", text_colour=BLACK, bg_colour=GREEN, highlight_bg=WHITE)
        self.ui_elements['quit_button'] = clickable_assets.ClickableAsset(300, y_offset + 50, 200, 50, "Quit", text_colour=BLACK, bg_colour=RED, highlight_bg=WHITE)


    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()
            # Number of players
            if self.ui_elements['num_players_decrease'].mouse_hovering(mouse_pos):
                if self.num_players > 2:
                    self.num_players -= 1
                    self._update_player_configs()
                    self.active_dropdown = None # Close dropdown on change
                    self._create_ui_elements()
            elif self.ui_elements['num_players_increase'].mouse_hovering(mouse_pos):
                if self.num_players < 6: # Max 6 players
                    self.num_players += 1
                    self._update_player_configs()
                    self.active_dropdown = None
                    self._create_ui_elements()

            # Player type selection buttons
            for i in range(self.num_players):
                type_button_key = f"player_{i}_type_button"
                if self.ui_elements[type_button_key].mouse_hovering(mouse_pos):
                    self.active_dropdown = i if self.active_dropdown != i else None
                    self._create_ui_elements() # Rebuild to show/hide dropdown
                    break
                # Check dropdown options if active
                if self.active_dropdown == i:
                    for p_type in PLAYER_TYPES:
                        option_key = f"player_{i}_option_{p_type}"
                        if self.ui_elements[option_key].mouse_hovering(mouse_pos):
                            self.player_configs[i]["type"] = p_type
                            self.active_dropdown = None # Close dropdown
                            self._create_ui_elements() # Rebuild to update button text
                            break
                    if self.active_dropdown is None: break # Exit outer loop if selection made

            # Start Game Button
            if self.ui_elements['start_button'].mouse_hovering(mouse_pos):
                print("Start Game clicked. Configuration:")
                print(f"Number of players: {self.num_players}")
                for i, config in enumerate(self.player_configs):
                    print(f"Player {i+1}: Name - {config['name']}, Type - {config['type']}")
                self.running = False
                self.next_screen = "game" # Signal to start the game

            if self.ui_elements['quit_button'].mouse_hovering(mouse_pos):
                self.running = False
                self.next_screen = "quit"


    def _update_player_configs(self):
        # Adjust player_configs list size based on num_players
        current_len = len(self.player_configs)
        if self.num_players > current_len:
            for i in range(current_len, self.num_players):
                self.player_configs.append({"name": f"Player {i+1}", "type": PLAYER_TYPES[0]})
        elif self.num_players < current_len:
            self.player_configs = self.player_configs[:self.num_players]


    def draw(self):
        self.screen.fill(BLACK) # Background
        for element in self.ui_elements.values():
            # All our assets are PicassoAssets and have a draw() method that returns a surface,
            # and a get_coordinate() method for their position.
            self.screen.blit(element.draw(), element.get_coordinate())

        pygame.display.flip()

    def run_loop(self):
        """Main loop for the setup screen."""
        # This loop would typically be called from risk.py before graphics.init()
        # It needs its own Pygame event loop.
        pygame.init() # Ensure Pygame is initialized for this screen
        # screen = pygame.display.set_mode((800, 600)) # Example size, should match game
        pygame.display.set_caption("Risk Game Setup")

        self.running = True
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    self.next_screen = "quit"
                self.handle_event(event)

            # The hover state is checked dynamically within each asset's draw() method,
            # so we don't need to manage it externally here.
            
            self.draw()
            pygame.time.Clock().tick(30) # Limit FPS

        return self.num_players, self.player_configs, self.next_screen

if __name__ == '__main__':
    # This is for testing the setup screen independently
    pygame.init()
    screen_width, screen_height = 800, 700 # Example, adjust as needed
    screen = pygame.display.set_mode((screen_width, screen_height))

    # The setup screen doesn't need full picasso for its own drawing,
    # as it's pre-game. Passing None or a dummy if necessary.
    setup_screen_instance = SetupScreen(screen, None)
    num_players, player_configs, next_action = setup_screen_instance.run_loop()

    if next_action == "game":
        print("\nSetup Complete. Proceeding to game with settings:")
        print(f"Number of Players: {num_players}")
        for i, p_config in enumerate(player_configs):
            print(f"  Player {i+1}: Name - {p_config['name']}, Type - {p_config['type']}")
    else:
        print("\nSetup exited or quit.")
    pygame.quit()
