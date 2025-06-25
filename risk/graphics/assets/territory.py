import pygame
from pygame.font import Font
import time # Import time for flashing

import risk
import risk.logger
import risk.graphics.assets

from risk.graphics.assets import base
from risk.graphics.assets.base import PicassoAsset, BLACK, WHITE, RED # Added RED for flashing
from risk.graphics.assets.clickable import ClickableAsset
from risk.graphics.assets.text import TextAsset

import math

TERRITORY_ART_ASSET_PATH = './assets/art/territories/'
NO_PLAYER_COLOUR = base.BLACK # Was base.BLACK, but base.WHITE is better for unowned
UNOWNED_COLOUR = base.WHITE # Explicitly define unowned color for clarity

def build_territory_asset(continent, territory, x, y):
    full_path = "%s/%s/%s.png" % \
            (TERRITORY_ART_ASSET_PATH, continent, territory.name)
    return TerritoryAsset(continent, territory, full_path, x, y)

def build_player_colour_mapping(players):
    overflow_colour = base.BLACK
    colours = [
        base.BLUE, base.PURPLE, base.ORANGE, base.YELLOW, base.GREEN, base.RED,
    ] # base.RED was used for flashing, ensure player colors are distinct or flashing uses a different effect
    risk.logger.debug("assigning player colours...")
    TerritoryAsset.mapping = {}
    for player in players:
        try:
            colour = colours.pop(0) # Pop from front for consistency if list changes
            risk.logger.debug("assigning %s with %s" % (player.name, colour))
            TerritoryAsset.mapping[player] = colour
        except IndexError:
            risk.logger.error("no more colours left, assigning %s with %s!" \
                    % (player.name, overflow_colour))
            TerritoryAsset.mapping[player] = overflow_colour

class TerritoryAsset(ClickableAsset):
    mapping = {} # Class variable for player to color mapping

    def __init__(self, continent, territory, image_path, x, y):
        self.territory = territory
        self.last_known_owner = None
        self.last_known_armies = -1 # For dirty check related to army count display (though not directly here)
        self.highlighted = False

        # Flashing attributes
        self.is_flashing = False
        self.flash_end_time = 0
        self.flash_color_tuple = RED # Default flash color
        self.flash_interval = 0.15 # seconds for on/off state of flash
        self._flash_display_on = False # Internal state for alternating flash display
        self._last_flash_toggle_time = 0

        # Load original alpha surface
        self.original_alpha_surface = pygame.image.load(image_path).convert_alpha()
        # Create a working surface that will be colorized
        surface_to_colorize = self.original_alpha_surface.copy()

        ClickableAsset.__init__(self, x, y, 0, 0, "") # width/height from surface
        PicassoAsset.__init__(self, surface_to_colorize, x, y) # Pass the copy to PicassoAsset
     
    def mouse_hovering(self, mouse_pos=None):
        if not mouse_pos:
            mouse_pos = pygame.mouse.get_pos()
        adjusted_position = (mouse_pos[0] - self.x, mouse_pos[1] - self.y)
        try:
            # Check bounds first
            if not self.surface.get_rect().collidepoint(adjusted_position):
                return False
            return ClickableAsset.mouse_hovering(self) and \
                    self.original_alpha_surface.get_at(adjusted_position)[3] > 0 # Check alpha on original
        except IndexError:
            return False

    def _colorize_surface(self, target_surface, color):
        """Helper to colorize the original alpha mask onto the target surface."""
        target_surface.blit(self.original_alpha_surface, (0,0)) # Reset with original shape + alpha
        barray = pygame.surfarray.pixels3d(target_surface)
        alpha_array = pygame.surfarray.pixels_alpha(self.original_alpha_surface)

        # Apply color only where alpha is not transparent
        mask = alpha_array > 0
        barray[mask, 0] = color[0]
        barray[mask, 1] = color[1]
        barray[mask, 2] = color[2]
        del barray # Release lock on surface pixels

    def _get_current_owner_color(self):
        owner = self.territory.owner
        if owner is None:
            return UNOWNED_COLOUR
        try:
            return TerritoryAsset.mapping[owner]
        except KeyError:
            risk.logger.error("no colours assigned to %s" % owner.name)
            return NO_PLAYER_COLOUR # Fallback color

    # Overriding draw from PicassoAsset to handle dynamic updates
    def draw(self):
        if self.dirty():
            self.last_known_owner = self.territory.owner
            self.highlighted = self.mouse_hovering() # Update highlighted state

            current_base_color = self._get_current_owner_color()

            display_color = current_base_color
            is_currently_highlighted = self.highlighted

            if self.is_flashing:
                current_time = time.time()
                if current_time >= self.flash_end_time:
                    self.is_flashing = False
                    is_currently_highlighted = self.mouse_hovering() # Re-check highlight after flash ends
                else:
                    if current_time - self._last_flash_toggle_time > self.flash_interval:
                        self._flash_display_on = not self._flash_display_on
                        self._last_flash_toggle_time = current_time

                    if self._flash_display_on:
                        display_color = self.flash_color_tuple
                    # Flashing overrides normal hover highlighting appearance for the main color
                    is_currently_highlighted = False # Don't apply hover effect if flashing active color

            if is_currently_highlighted:
                # Apply highlight effect (e.g., brighten the display_color)
                # For simplicity, make it slightly lighter. Proper way is to blend.
                r = min(display_color[0] + 60, 255)
                g = min(display_color[1] + 60, 255)
                b = min(display_color[2] + 60, 255)
                display_color = (r, g, b)

            self._colorize_surface(self.surface, display_color)

        return self.surface # Return the up-to-date surface

    def start_flashing(self, duration=0.6, color_tuple=RED, interval=0.15):
        risk.logger.debug(f"Territory {self.territory.name} starting to flash.")
        self.is_flashing = True
        self.flash_color_tuple = color_tuple
        self.flash_interval = interval
        self.flash_end_time = time.time() + duration
        self._flash_display_on = True # Start with flash color on
        self._last_flash_toggle_time = time.time()
        self.dirty() # Mark as dirty to force redraw

    def dirty(self):
        # Always dirty if flashing to ensure animation updates
        if self.is_flashing:
            return True
        return self.last_known_owner != self.territory.owner or \
               self.highlighted != self.mouse_hovering()


class ArmyCountAsset(PicassoAsset):
    def __init__(self, territory_asset, size=32):
        self.territory_asset = territory_asset
        self.current_army_count = -1 # Use a different name to avoid clash if self.count is used elsewhere
        self.last_rendered_army_count = -1
        self.size = size
        self.default_text_colour = base.BLACK
        self.highlight_text_colour = None
        self.highlight_end_time = 0
        self.highlight_duration = 0.75 # seconds

        ta_surface = territory_asset.surface
        # Approximate center for the army count circle based on territory asset's surface
        # This assumes territory asset surface is somewhat consistent or circle is small enough
        center_x_offset = ta_surface.get_width() * 0.6 # Example: 60% from left
        center_y_offset = ta_surface.get_height() * 0.3 # Example: 30% from top

        # We will set self.x, self.y relative to territory_asset later or draw relative to it.
        # For PicassoAsset, x,y are screen coordinates.
        # Let's make ArmyCountAsset calculate its screen x,y based on territory_asset's x,y
        self.abs_x = territory_asset.x + center_x_offset
        self.abs_y = territory_asset.y + center_y_offset

        PicassoAsset.__init__(self, None, self.abs_x, self.abs_y) # Surface created in draw
        self.update_position() # Initial position update based on territory asset

    def update_position(self):
        # Update position if territory asset might move (though unlikely for static territories)
        # Or if using relative positioning within a parent asset that moves.
        # For now, assume territory assets are static once placed.
        # The main purpose here is to set a more reliable x,y for the small circle.
        ta_surface = self.territory_asset.surface
        # A better way for x,y of the circle: place it near a corner or edge of territory sprite
        # Example: Place it towards top-right of the territory sprite
        self.x = self.territory_asset.x + ta_surface.get_width() - 22 # Assuming circle diameter is ~22-30
        self.y = self.territory_asset.y + 5 # A bit from the top
        # Ensure it doesn't go off-screen - Picasso handles clipping, but good to be mindful.


    def draw(self):
        if self.dirty():
            new_count = self.territory_asset.territory.armies
            if self.last_rendered_army_count != -1 and new_count != self.last_rendered_army_count:
                if new_count > self.last_rendered_army_count:
                    self.highlight_text_colour = base.GREEN
                else: # new_count < self.last_rendered_army_count
                    self.highlight_text_colour = base.RED
                self.highlight_end_time = time.time() + self.highlight_duration

            self.current_army_count = new_count
            self.last_rendered_army_count = self.current_army_count # Update after potential highlight set

            font = Font(None, self.size)

            current_text_colour = self.default_text_colour
            if self.highlight_text_colour and time.time() < self.highlight_end_time:
                current_text_colour = self.highlight_text_colour
            elif self.highlight_text_colour and time.time() >= self.highlight_end_time:
                self.highlight_text_colour = None # Reset highlight

            text_render = font.render(str(self.current_army_count), True, current_text_colour)
            text_rect = text_render.get_rect()

            # Dynamic circle radius based on text size
            padding = 4
            circle_radius = max(text_rect.width, text_rect.height) / 2 + padding

            # Surface size based on circle diameter
            surf_size = int(circle_radius * 2)
            self.surface = pygame.Surface([surf_size, surf_size], pygame.SRCALPHA, 32)
            self.surface = self.surface.convert_alpha()

            circle_center = (surf_size // 2, surf_size // 2)

            pygame.draw.circle(self.surface, base.BLACK, circle_center, circle_radius)
            pygame.draw.circle(self.surface, base.LIGHT_BROWN, circle_center, circle_radius - 2)

            # Center text in circle
            text_blit_pos = (circle_center[0] - text_rect.width / 2,
                             circle_center[1] - text_rect.height / 2)
            self.surface.blit(text_render, text_blit_pos)
        return self.surface

    def dirty(self):
        return self.count != self.territory_asset.territory.armies

