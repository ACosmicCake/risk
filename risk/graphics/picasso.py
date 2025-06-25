import time
import threading
import sys

from datetime import timedelta
from datetime import datetime

import pygame
from pygame.locals import *

import risk
import risk.logger
import risk.errors.input

from risk.graphics.event import get_events
from risk.graphics.assets.base import PicassoAsset

MOUSE_CURSOR_LOCATION = 'assets/art/cursor/mickey_mouse.png'

def get_picasso(*args, **kwargs):
    if not hasattr(get_picasso, 'picasso_instance'):
        get_picasso.picasso_instance = Picasso(*args, **kwargs)
        get_picasso.picasso_instance.daemon = True
    return get_picasso.picasso_instance
  

class Picasso(threading.Thread):
    def __init__(self, background='', width=1920, 
                height=1080, fps=100, caption='RiskPy', screen=None): # Added screen parameter
        # Pygame should already be initialized by the time Picasso is called if a screen is passed
        # If not, or if screen is None, initialize it.
        if not pygame.get_init():
            pygame.init()

        flags = 0x0
        flags |= pygame.RESIZABLE # Keep resizable if that's desired

        if screen:
            self.window = screen
            # If using an existing screen, width/height should ideally match
            # For now, we'll use the passed screen's dimensions if they differ from defaults
            width = screen.get_width()
            height = screen.get_height()
        else:
            self.window = pygame.display.set_mode((width, height), flags)
            pygame.display.set_caption(caption)
            
        # convert background for faster draw
        if background: # Only load background if a path is provided
            self.background = pygame.image.load(background).convert()
            self.background = \
                pygame.transform.scale(self.background, (width, height))
        else: # Provide a default black background if none specified
            self.background = pygame.Surface((width, height))
            self.background.fill((0,0,0)) # Black

        self.fps = fps
        self.canvas = {}
        self.ended = False
        self.game_master = None
        
        from risk.graphics import assets
        self.clock = pygame.time.Clock()
        self.cursor = assets.image.ImageAsset(0, 0, MOUSE_CURSOR_LOCATION)

        threading.Thread.__init__(self)

    def run(self):
        try:
            pygame.mouse.set_visible(False)
            while not self.ended:
                # Event handling
                mouse_pos = pygame.mouse.get_pos() # Get mouse position once per frame
                try:
                    events = get_events()
                except risk.errors.input.UserQuitInput:
                    self.ended = True
                    # Potentially call game_master.end_game() or a shutdown callback here
                    # For now, just ending Picasso loop. GameMaster should handle full exit.
                    break

                for event in events:
                    # Pass event to interactive assets/panels
                    # This needs a way to access these specific assets.
                    # Using Datastore is one option if panels are registered there.
                    # Or Picasso could maintain a list of event-handling assets.
                    # For now, let's assume we can get them from Datastore for simplicity.
                    try:
                        from risk.graphics.datastore import Datastore # Local import for now
                        datastore = Datastore()
                        thoughts_panel = datastore.get_entry('thoughts_panel')
                        if thoughts_panel and hasattr(thoughts_panel, 'handle_event'):
                            if thoughts_panel.handle_event(event, mouse_pos):
                                continue # Event handled by this panel

                        comm_panel = datastore.get_entry('communication_panel')
                        if comm_panel and hasattr(comm_panel, 'handle_event'):
                            if comm_panel.handle_event(event, mouse_pos):
                                continue # Event handled

                        # Add other event handling for existing clickables if not covered by pump()
                        # The existing `pump()` in event.py might handle some global events or specific clicks.
                        # This new loop is more explicit for panel interactions.

                    except Exception as e_event_handling:
                        risk.logger.error(f"Error during Picasso event handling: {e_event_handling}")

                if self.ended: break

                self.draw_canvas_contents() # Renamed drawing part
                self.clock.tick(self.fps)
        except Exception as e:
            risk.logger.critical(
                "Exception in Picasso subsystem run loop! %s" % e)
        finally: # Ensure pygame quits if Picasso thread exits unexpectedly
            if pygame.get_init(): # Check if pygame is still initialized
                 risk.logger.debug("Picasso thread ending, calling pygame.quit()")
                 pygame.quit()


    def draw_canvas_contents(self): # Renamed from draw_canvas
        # pump() # Original pump() call - review its purpose. It might be for custom event queue.
               # For now, using pygame.event.get() above is more standard.
               # If pump() from event.py is critical for other things, it needs to be integrated.
               # From event.py, pump() seems to just call pygame.event.pump().
               # pygame.event.get() also calls pump internally, so direct pump() might be redundant.

        self.window.blit(self.background, (0, 0))

        # make a deep copy of layers first to avoid race condition where dict
        # size can change during iteration. try to do it lockless, if we're
        # still having issues, fix with mutex
        try:
            for _, level in sorted(self.canvas.items()):
                for asset in level:
                    if isinstance(asset, PicassoAsset):
                        self.window.blit(asset.draw(), asset.get_coordinate())
                    else:
                        risk.logger.warn("None asset detected in canvas, ",
                            "skipping...[%s]" % asset)
        except RuntimeError:
            risk.logger.error("ignoring dictionary size change...")
        fps_asset = self.get_fps_asset()
        self.window.blit(fps_asset.draw(), fps_asset.get_coordinate())
        self.cursor.x, self.cursor.y = pygame.mouse.get_pos()
        self.window.blit(self.cursor.draw(), self.cursor.get_coordinate())
        pygame.display.flip()

    def add_asset(self, layer, asset):
        try:
            self.canvas[layer].add(asset)
        except KeyError:
            self.canvas[layer] = set()
        finally:
            self.canvas[layer].add(asset)

    def remove_asset(self, layer, asset):
        try:
            self.canvas[layer].remove(asset)
        except KeyError:
            pass


    def end(self):
        risk.logger.debug("received request to terminate graphics subsystem!")
        self.ended = True

    def get_fps_asset(self):
        from risk.graphics.assets.text import TextAsset
        asset = TextAsset(1000, 16, "%s FPS" % int(self.clock.get_fps()),
                (255, 255, 0), 32)
        return asset

    def get_width(self):
        return self.window.get_width()

    def get_height(self):
        return self.window.get_height()
