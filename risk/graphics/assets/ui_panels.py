import pygame
from risk.graphics.assets.base import PicassoAsset, GREY, BLACK, WHITE # Assuming these colors are defined
from risk.graphics.assets.text import TextAsset # May not be directly used if rendering manually

# Dimensions and positions will likely be passed in or configured elsewhere
DEFAULT_PANEL_COLOR = GREY
DEFAULT_TEXT_COLOR = BLACK
DEFAULT_FONT_SIZE = 20
LINE_HEIGHT_MULTIPLIER = 1.2 # Adjust for line spacing

class ScrollableTextPanel(PicassoAsset):
    def __init__(self, x, y, width, height, background_color=DEFAULT_PANEL_COLOR, text_color=DEFAULT_TEXT_COLOR, font_size=DEFAULT_FONT_SIZE, initial_text=""):
        super().__init__(None, x, y) # PicassoAsset takes surface, x, y
        self.width = width
        self.height = height
        self.background_color = background_color
        self.text_color = text_color
        self.font_size = font_size
        try:
            self.font = pygame.font.Font(None, self.font_size)
        except pygame.error: # Fallback if default font not found (e.g. pygame not fully init)
            self.font = pygame.font.SysFont("arial", self.font_size)


        self.full_text_content = initial_text # The entire text
        self.rendered_lines = [] # List of (surface, rect) for visible lines
        self.scroll_offset_y = 0 # How many pixels we've scrolled down
        self.padding = 5 # Padding within the panel

        self.surface = pygame.Surface((self.width, self.height))
        self._render_text_to_lines() # Initial rendering of text

    def set_text(self, new_text):
        self.full_text_content = new_text
        self.scroll_offset_y = 0 # Reset scroll on new text
        self._render_text_to_lines()
        self._update_surface()

    def add_text(self, text_to_add):
        if self.full_text_content and not self.full_text_content.endswith("\n"):
            self.full_text_content += "\n"
        self.full_text_content += text_to_add
        self._render_text_to_lines()
        # TODO: Smart scroll: if already at bottom, stay at bottom. Otherwise, keep current view.
        # For now, just re-renders. Scrolling to bottom might be good default.
        self._update_surface()


    def _render_text_to_lines(self):
        self.rendered_lines = []
        words = self.full_text_content.split(' ')
        current_line = ""
        line_height = int(self.font_size * LINE_HEIGHT_MULTIPLIER)

        lines_split_by_newline = self.full_text_content.split('\n')

        temp_rendered_text_surfaces = []

        for paragraph_line in lines_split_by_newline:
            words = paragraph_line.split(' ')
            current_line_text = ""
            for word in words:
                if not current_line_text:
                    test_line = word
                else:
                    test_line = current_line_text + " " + word

                text_surface_test = self.font.render(test_line, True, self.text_color)
                if text_surface_test.get_width() <= self.width - 2 * self.padding:
                    current_line_text = test_line
                else:
                    # Word doesn't fit, render previous line and start new one with current word
                    if current_line_text: # If there was something on the line before this long word
                        line_surf = self.font.render(current_line_text, True, self.text_color)
                        temp_rendered_text_surfaces.append(line_surf)

                    # Handle very long words that might exceed panel width even alone
                    current_word_part = word
                    while self.font.render(current_word_part, True, self.text_color).get_width() > self.width - 2 * self.padding:
                        # Chop characters off the word until it fits
                        # This is a basic way, better would be char-by-char fitting or hyphenation
                        chopped = False
                        for k in range(len(current_word_part) -1, 0, -1):
                            if self.font.render(current_word_part[:k], True, self.text_color).get_width() <= self.width - 2 * self.padding:
                                temp_rendered_text_surfaces.append(self.font.render(current_word_part[:k], True, self.text_color))
                                current_word_part = current_word_part[k:]
                                chopped = True
                                break
                        if not chopped: # Should not happen if k > 0
                            break
                    if current_word_part: # Remainder of a long word
                         current_line_text = current_word_part
                    else: # Word was fully processed by chopping
                        current_line_text = ""

            # Add the last line of the paragraph
            if current_line_text:
                line_surf = self.font.render(current_line_text, True, self.text_color)
                temp_rendered_text_surfaces.append(line_surf)

        self.rendered_lines = temp_rendered_text_surfaces


    def _update_surface(self):
        self.surface.fill(self.background_color)
        current_y = self.padding - self.scroll_offset_y
        line_height = int(self.font_size * LINE_HEIGHT_MULTIPLIER)

        for line_surface in self.rendered_lines:
            if current_y + line_surface.get_height() > self.padding and current_y < self.height - self.padding:
                # Only draw if line is at least partially visible
                self.surface.blit(line_surface, (self.padding, current_y))
            current_y += line_height
            if current_y > self.height - self.padding: # Optimization: stop if below visible area
                break

    def scroll(self, dy):
        """Scrolls the text by dy pixels. Positive dy scrolls down, negative up."""
        line_height = int(self.font_size * LINE_HEIGHT_MULTIPLIER)
        total_text_height = len(self.rendered_lines) * line_height

        max_scroll = total_text_height - (self.height - 2 * self.padding)
        if max_scroll < 0: max_scroll = 0 # Cannot scroll if text is smaller than panel

        self.scroll_offset_y += dy

        if self.scroll_offset_y < 0:
            self.scroll_offset_y = 0
        if self.scroll_offset_y > max_scroll:
            self.scroll_offset_y = max_scroll

        self._update_surface()

    def handle_event(self, event, mouse_pos):
        # Check if mouse is over this panel for scroll wheel events
        panel_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        if panel_rect.collidepoint(mouse_pos):
            if event.type == pygame.MOUSEWHEEL:
                # pygame.MOUSEWHEEL event.y is usually 1 for scroll up, -1 for scroll down
                # We want to scroll content up (offset decreases) when wheel scrolls up (event.y > 0)
                # We want to scroll content down (offset increases) when wheel scrolls down (event.y < 0)
                line_height = int(self.font_size * LINE_HEIGHT_MULTIPLIER)
                self.scroll(-event.y * line_height * 3) # Scroll by 3 lines
                return True # Event handled
        return False # Event not handled by this panel

    def draw(self): # Required by PicassoAsset
        # The surface is already updated by set_text or scroll
        return self.surface


class ThoughtsPanel(ScrollableTextPanel):
    def __init__(self, x, y, width, height, initial_thought="AI thoughts will appear here..."):
        super().__init__(x, y, width, height, initial_text=initial_thought, font_size=18)
        # Specific styling for thoughts panel if needed

class CommunicationPanel(PicassoAsset): # More complex, might have tabs
    def __init__(self, x, y, width, height):
        super().__init__(None, x, y)
        self.width = width
        self.height = height
        self.surface = pygame.Surface((self.width, self.height))
        self.surface.fill(GREY) # Placeholder

        # For now, a very simple implementation, will be expanded for tabs
        self.global_chat_display = ScrollableTextPanel(x + 5, y + 5, width - 10, height - 10, font_size=16)
        self.global_chat_display.set_text("Global Chat:\n")

    def add_global_message(self, sender_name, message):
        self.global_chat_display.add_text(f"[{sender_name}]: {message}")

    def add_private_message(self, sender_name, receiver_name, message, current_player_name):
        # For now, just add to global chat with prefix, until tabs are done
        self.global_chat_display.add_text(f"[Private {sender_name} to {receiver_name}]: {message}")

    def handle_event(self, event, mouse_pos):
        # Pass event to child scrollable panels
        # This needs to be adjusted if there are multiple active areas (tabs, private chat selection)
        # For now, only global_chat_display needs mouse wheel if mouse is over it.
        # Need to translate mouse_pos relative to the child panel if its x,y are relative to this CommunicationPanel

        # Assuming global_chat_display x,y are screen coordinates for now
        # If they were relative, you'd do:
        # relative_mouse_pos = (mouse_pos[0] - self.x - self.global_chat_display.x,
        #                        mouse_pos[1] - self.y - self.global_chat_display.y)
        # panel_rect = pygame.Rect(self.global_chat_display.x + self.x, self.global_chat_display.y + self.y, ...)
        # if panel_rect.collidepoint(mouse_pos):
        #     if self.global_chat_display.handle_event(event, mouse_pos): return True

        # For now, assuming global_chat_display x,y are screen coordinates for simplicity
        if self.global_chat_display.handle_event(event, mouse_pos):
            return True
        return False


    def draw(self):
        # Draw child panels onto this panel's surface, then return this surface
        self.surface.fill(GREY) # Clear/background for the main comms panel

        # This draw logic is a bit off if global_chat_display is already a PicassoAsset using screen coords.
        # If ScrollableTextPanel is a self-contained drawable surface, then blit it.
        # For now, assuming ScrollableTextPanel.draw() returns its own surface correctly.
        # This part needs careful thought on how PicassoAsset children are composed.
        # A simpler way: CommunicationPanel doesn't draw its children directly on its surface,
        # but rather, Picasso draws them as separate assets.
        # Let's assume CommunicationPanel is just a conceptual container for now,
        # and its children are added to Picasso separately.
        # So, this draw method might just draw a border or background for the comms area.

        # Placeholder: just return a grey box. The actual text panels will be drawn by Picasso.
        pygame.draw.rect(self.surface, WHITE, (0,0,self.width, self.height), 2) # Border
        return self.surface

# Example usage (not part of the class definitions)
if __name__ == '__main__':
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Panel Test")

    thoughts_panel = ThoughtsPanel(50, 50, 300, 200)
    thoughts_panel.set_text("This is a very long line of text that should wrap multiple times to test the wrapping capabilities of the panel. Let's add even more words to ensure it properly handles overflow and creates new lines as needed. This also tests the scrollability if the text exceeds the panel height.\nNew paragraph here.\nAnd another one.")

    comms_panel_container = pygame.Rect(50, 300, 300, 250) # Conceptual container
    comms_panel_display = CommunicationPanel(comms_panel_container.x, comms_panel_container.y, comms_panel_container.width, comms_panel_container.height)
    comms_panel_display.add_global_message("Jules", "Hello World!")
    comms_panel_display.add_private_message("PlayerA", "PlayerB", "Secret plans?", "PlayerB")


    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            thoughts_panel.handle_event(event, mouse_pos) # Pass event to panel
            comms_panel_display.global_chat_display.handle_event(event, mouse_pos) # Pass to child

        screen.fill(BLACK)
        screen.blit(thoughts_panel.draw(), (thoughts_panel.x, thoughts_panel.y))

        # For comms_panel, if it's just a container, draw its children separately
        screen.blit(comms_panel_display.draw(), (comms_panel_display.x, comms_panel_display.y)) # Draws the border
        screen.blit(comms_panel_display.global_chat_display.draw(), (comms_panel_display.global_chat_display.x, comms_panel_display.global_chat_display.y))


        pygame.display.flip()
        pygame.time.Clock().tick(30)

    pygame.quit()
