import kivy
kivy.require('2.0.0')

import os
import time
import json
import hashlib
from pathlib import Path

import kivy.app
import kivy.uix.widget
import kivy.uix.label
import kivy.uix.button
import kivy.uix.boxlayout
import kivy.uix.popup
import kivy.uix.gridlayout
import kivy.uix.spinner
import kivy.graphics
import kivy.core.window
import kivy.core.audio
import kivy.clock
import kivy.utils
import kivy.uix.floatlayout
import kivy.uix.textinput

kivy.core.window.Window.size = (900, 700)


class SimpleRandom:
    def __init__(self, seed=42):
        self.seed = seed

    def random(self):
        self.seed = (self.seed * 1103515245 + 12345) & 0xFFFFFFFF
        return self.seed / 0xFFFFFFFF

    def choice(self, items):
        index = int(self.random() * len(items))
        return items[index]

    def randint(self, a, b):
        return a + int(self.random() * (b - a + 1))


rnd = SimpleRandom(42)

MAZE_MAP = [
    "############################",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#..........................#",
    "#.####.##.########.##.####.#",
    "#......##....##....##......#",
    "######.#####.##.#####.######",
    "#....#................#....#",
    "#.##.#.####.####.####.#.##.#",
    "#....#................#....#",
    "####.#.##.########.##.#.####",
    "####.#.##....##....##.#.####",
    "#........##.####.##........#",
    "####.#.##.########.##.#.####",
    "####.#.##....##....##.#.####",
    "#....#................#....#",
    "#.##.#.####.####.####.#.##.#",
    "#....#................#....#",
    "######.#####.##.#####.######",
    "#......##....##....##......#",
    "#.####.##.########.##.####.#",
    "#..........................#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#............##............#",
    "############################",
]


class AudioManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.sounds = {
            "opening": self._load("Opening.mp3", 0.7),
            "not_eating": self._load("NotEating.mp3", 0.6),
            "eating": self._load("Eating.mp3", 0.7),
            "frenzy": self._load("Frenzy Eating.mp3", 0.7),
            "game_over": self._load("GameOver.mp3", 0.8),
        }
        self.current_loop = None
        self.opening_active = False
        self.game_over_played = False
        self.suppress_until = 0.0

    def _load(self, filename, volume):
        path = os.path.join(self.base_dir, filename)
        if not os.path.exists(path):
            return None
        sound = kivy.core.audio.SoundLoader.load(path)
        if sound:
            sound.volume = volume
        return sound

    def stop_all(self):
        for sound in self.sounds.values():
            if sound:
                sound.stop()
        self.current_loop = None

    def play_opening(self):
        self.stop_all()
        opening = self.sounds.get("opening")
        if opening:
            opening.loop = False
            opening.play()
            self.opening_active = True
        else:
            self.opening_active = False
        self.game_over_played = False
        self.suppress_until = 0.0

    def play_loop(self, key):
        sound = self.sounds.get(key)
        if not sound:
            return
        if self.current_loop is sound and sound.state == "play":
            return
        if self.current_loop and self.current_loop is not sound:
            self.current_loop.stop()
        sound.loop = True
        sound.play()
        self.current_loop = sound

    def play_one_shot(self, key):
        sound = self.sounds.get(key)
        if not sound:
            return
        sound.stop()
        sound.loop = False
        sound.play()
        length = sound.length if sound.length else 0.4
        self.suppress_until = time.time() + max(0.2, length)

    def update(self, game):
        now = time.time()

        if game.game_over:
            if not self.game_over_played:
                self.stop_all()
                self.play_one_shot("game_over")
                self.game_over_played = True
            return

        if game.won:
            if self.current_loop:
                self.current_loop.stop()
                self.current_loop = None
            return

        if game.paused:
            if self.current_loop:
                self.current_loop.stop()
                self.current_loop = None
            return

        if self.opening_active:
            opening = self.sounds.get("opening")
            if not opening or opening.state != "play":
                self.opening_active = False
                self.play_loop("not_eating")
            return

        if now < self.suppress_until:
            if self.current_loop:
                self.current_loop.stop()
                self.current_loop = None
            return

        self.play_loop("not_eating")


def simple_distance(x1, y1, x2, y2):
    dx = x1 - x2
    dy = y1 - y2
    return (dx * dx + dy * dy) ** 0.5


class Pellet:
    def __init__(self, x, y, size=5):
        self.x = x
        self.y = y
        self.size = size
        self.eaten = False
        self.color = (1, 1, 1, 1)


class Ghost:
    def __init__(self, x, y, color, speed=1.5, aggression=0.7, size=24, bounds=None):
        self.x = x
        self.y = y
        self.original_x = x
        self.original_y = y
        self.original_color = color
        self.color = color
        self.speed = speed
        self.base_speed = speed
        self.aggression = aggression
        self.size = size
        self.bounds = bounds
        self.direction = rnd.choice(['left', 'right', 'up', 'down'])
        self.direction_timer = 0
        self.direction_change_interval = 0.5
        self.frightened = False
        self.frightened_until = 0
        self.move_target = None

    def set_frightened(self, until_time):
        self.frightened = True
        self.frightened_until = until_time
        # blue-ish frightened color
        try:
            self.color = kivy.utils.get_color_from_hex('#4D79FF')
        except Exception:
            self.color = (0.3, 0.5, 1, 1)
        self.speed = max(0.6, self.base_speed * 0.8)

    def clear_frightened(self):
        self.frightened = False
        self.frightened_until = 0
        self.color = self.original_color
        self.speed = self.base_speed

    def update(self, game, dt):
        # support legacy signature if called differently
        try:
            pacman_x = game.pacman_x
            pacman_y = game.pacman_y
            walls = game.walls
        except Exception:
            return

        now = time.time()
        if self.frightened and now > self.frightened_until:
            self.clear_frightened()

        self.direction_timer += dt

        # refresh roam target if reached or missing
        if self.move_target is None or simple_distance(self.x, self.y, *self.move_target) < max(8, self.speed * 2):
            cols = game.maze_cols
            rows = game.maze_rows
            for _ in range(24):
                c = rnd.randint(0, cols - 1)
                r = rnd.randint(0, rows - 1)
                tc, tr = game.find_open_tile(c, r)
                tx, ty = game.grid_to_pos(tc, tr)
                if game.is_walkable_cell(tc, tr):
                    self.move_target = (tx, ty)
                    break

        if self.direction_timer >= self.direction_change_interval:
            self.direction_timer = 0

            # decide on a position to head towards
            if self.frightened:
                # flee: pick a point away from pacman
                target_x = self.x + (self.x - pacman_x) * 2
                target_y = self.y + (self.y - pacman_y) * 2
            else:
                if rnd.random() < self.aggression:
                    target_x, target_y = pacman_x, pacman_y
                else:
                    if self.move_target:
                        target_x, target_y = self.move_target
                    else:
                        target_x, target_y = self.x, self.y

            # choose best adjacent walkable tile that reduces distance to target
            # convert current position to grid cell
            try:
                cur_col = int((self.x - game.maze_offset_x) / game.tile_size)
                cur_row = int((self.y - game.maze_offset_y) / game.tile_size)
            except Exception:
                cur_col, cur_row = None, None

            best = None
            candidates = []
            for d, dc, dr in (('left', -1, 0), ('right', 1, 0), ('up', 0, 1), ('down', 0, -1)):
                if cur_col is None:
                    candidates.append((1e6, d))
                    continue
                nc = cur_col + dc
                nr = cur_row + dr
                if game.is_walkable_cell(nc, nr):
                    cx, cy = game.grid_to_pos(nc, nr)
                    dist = simple_distance(cx, cy, target_x, target_y)
                    candidates.append((dist, d))

            if candidates:
                candidates.sort(key=lambda x: x[0])
                self.direction = candidates[0][1]
            else:
                # fallback: random nearby walkable direction
                dirs = []
                if cur_col is not None:
                    for d, dc, dr in (('left', -1, 0), ('right', 1, 0), ('up', 0, 1), ('down', 0, -1)):
                        nc = cur_col + dc
                        nr = cur_row + dr
                        if game.is_walkable_cell(nc, nr):
                            dirs.append(d)
                if dirs:
                    self.direction = rnd.choice(dirs)
                else:
                    self.direction = rnd.choice(['left', 'right', 'up', 'down'])

        self.move_in_direction(self.direction, walls)

    def move_in_direction(self, direction, walls):
        new_x, new_y = self.x, self.y

        if direction == 'left':
            new_x -= self.speed
        elif direction == 'right':
            new_x += self.speed
        elif direction == 'up':
            new_y += self.speed
        elif direction == 'down':
            new_y -= self.speed

        if not self.check_wall_collision(new_x, new_y, walls):
            self.x, self.y = new_x, new_y
        else:
            # try perpendicular alternatives to avoid getting stuck
            alt_dirs = ['left', 'right'] if direction in ['up', 'down'] else ['up', 'down']
            for d in alt_dirs:
                ax, ay = self.x, self.y
                if d == 'left':
                    ax -= self.speed
                elif d == 'right':
                    ax += self.speed
                elif d == 'up':
                    ay += self.speed
                elif d == 'down':
                    ay -= self.speed
                if not self.check_wall_collision(ax, ay, walls):
                    self.x, self.y = ax, ay
                    self.direction = d
                    break
            else:
                self.direction = rnd.choice(['left', 'right', 'up', 'down'])

        if self.bounds:
            bx, by, bw, bh = self.bounds
            padding = self.size / 2
            self.x = max(bx + padding, min(self.x, bx + bw - padding))
            self.y = max(by + padding, min(self.y, by + bh - padding))
        else:
            self.x = max(30, min(self.x, kivy.core.window.Window.width - 30))
            self.y = max(30, min(self.y, kivy.core.window.Window.height - 30))

    def check_wall_collision(self, new_x, new_y, walls):
        half = self.size / 2
        ghost_rect = (new_x - half, new_y - half, self.size, self.size)
        for wall in walls:
            if self.rect_collide(ghost_rect, wall):
                return True
        return False

    def rect_collide(self, rect1, rect2):
        return not (rect1[0] + rect1[2] < rect2[0] or
                    rect1[0] > rect2[0] + rect2[2] or
                    rect1[1] + rect1[3] < rect2[1] or
                    rect1[1] > rect2[1] + rect2[3])

    def reset(self):
        self.x = self.original_x
        self.y = self.original_y
        self.direction = rnd.choice(['left', 'right', 'up', 'down'])
        self.clear_frightened()


class PacmanGame(kivy.uix.widget.Widget):
    def __init__(self, difficulty='medium', **kwargs):
        super().__init__(**kwargs)

        self.difficulty = difficulty

        self.score = 0
        self.game_over = False
        self.won = False
        self.paused = False

        self.pacman_x = 300
        self.pacman_y = 300
        self.pacman_direction = 'right'
        self.pacman_target_direction = 'right'
        self.pacman_mouth_angle = 45
        self.mouth_opening = True

        self.configure_maze_metrics()
        self.set_difficulty_parameters()

        self.moving_left = False
        self.moving_right = False
        self.moving_up = False
        self.moving_down = False

        self.walls = []
        self.create_maze()
        self.set_spawn_positions()

        self.pellets = []
        self.create_pellets()

        self.create_ghosts()

        music_dir = os.path.join(os.path.dirname(__file__), "Music")
        self.audio = AudioManager(music_dir)
        self.audio.play_opening()
        self.intro_locked = self.audio.opening_active
        self.start_banner_until = 0.0

        self.last_eat_time = 0.0
        self.frenzy_until = 0.0
        self.frenzy_duration = 8.0

        self._keyboard = None
        self.bind_keyboard()

        self._update_event = kivy.clock.Clock.schedule_interval(self.update, 1 / 60.0)

        self._last_layout_state = None
        self.bind(pos=self.on_layout_change, size=self.on_layout_change)
        kivy.clock.Clock.schedule_once(self.on_layout_change, 0)

        self.initialized = True

    def destroy(self):
        if hasattr(self, '_update_event') and self._update_event:
            self._update_event.cancel()
            self._update_event = None
        self.on_keyboard_closed()
        if hasattr(self, 'audio'):
            self.audio.stop_all()

    def bind_keyboard(self):
        if self._keyboard is None:
            self._keyboard = kivy.core.window.Window.request_keyboard(self.on_keyboard_closed, self)
            if self._keyboard:
                self._keyboard.bind(on_key_down=self.on_key_down)
                self._keyboard.bind(on_key_up=self.on_key_up)

    def set_difficulty_parameters(self):
        if self.difficulty == 'easy':
            self.pacman_speed = self.tile_size * 0.28
            self.pacman_radius = self.tile_size * 0.45
            self.ghost_count = 2
            self.pellet_density = 1.0
            self.power_pellet_chance = 0.08
        elif self.difficulty == 'medium':
            self.pacman_speed = self.tile_size * 0.24
            self.pacman_radius = self.tile_size * 0.42
            self.ghost_count = 3
            self.pellet_density = 0.9
            self.power_pellet_chance = 0.05
        else:
            self.pacman_speed = self.tile_size * 0.21
            self.pacman_radius = self.tile_size * 0.4
            self.ghost_count = 4
            self.pellet_density = 0.8
            self.power_pellet_chance = 0.03
        self.pacman_collision_radius = self.pacman_radius * 0.72

    def configure_maze_metrics(self, available_width=None, available_height=None, origin_x=0.0, origin_y=0.0):
        self.maze_rows = len(MAZE_MAP)
        self.maze_cols = len(MAZE_MAP[0])

        if available_width is None or available_height is None:
            available_width = kivy.core.window.Window.width
            available_height = kivy.core.window.Window.height
            origin_x = 0.0
            origin_y = 0.0

        max_tile_width = (available_width - 80) / self.maze_cols
        max_tile_height = (available_height - 80) / self.maze_rows
        self.tile_size = max(16, int(min(max_tile_width, max_tile_height)))

        self.maze_width = self.tile_size * self.maze_cols
        self.maze_height = self.tile_size * self.maze_rows
        self.maze_offset_x = origin_x + (available_width - self.maze_width) / 2
        self.maze_offset_y = origin_y + (available_height - self.maze_height) / 2
        self.maze_bounds = (self.maze_offset_x, self.maze_offset_y, self.maze_width, self.maze_height)

    def on_layout_change(self, *args):
        if self.width <= 0 or self.height <= 0:
            return
        layout_state = (int(self.x), int(self.y), int(self.width), int(self.height))
        if self._last_layout_state == layout_state:
            return
        self.recalculate_layout()
        self.redraw_canvas()

    def recalculate_layout(self):
        old_tile_size = getattr(self, 'tile_size', None)
        old_offset_x = getattr(self, 'maze_offset_x', 0.0)
        old_offset_y = getattr(self, 'maze_offset_y', 0.0)

        pac_tile = None
        ghost_data = []
        pellet_data = []

        if old_tile_size:
            pac_tile = (
                (self.pacman_x - old_offset_x) / old_tile_size,
                (self.pacman_y - old_offset_y) / old_tile_size,
            )

            if hasattr(self, 'ghosts'):
                for ghost in self.ghosts:
                    target_tile = None
                    if ghost.move_target:
                        tx, ty = ghost.move_target
                        target_tile = (
                            (tx - old_offset_x) / old_tile_size,
                            (ty - old_offset_y) / old_tile_size,
                        )
                    ghost_data.append((
                        ghost,
                        (ghost.x - old_offset_x) / old_tile_size,
                        (ghost.y - old_offset_y) / old_tile_size,
                        target_tile,
                    ))

            for pellet in self.pellets:
                pellet_data.append((
                    pellet,
                    (pellet.x - old_offset_x) / old_tile_size,
                    (pellet.y - old_offset_y) / old_tile_size,
                    pellet.size > 5,
                ))

        self.configure_maze_metrics(self.width, self.height, self.x, self.y)
        self.set_difficulty_parameters()
        self.create_maze()

        if old_tile_size and pac_tile:
            self.pacman_x = self.maze_offset_x + pac_tile[0] * self.tile_size
            self.pacman_y = self.maze_offset_y + pac_tile[1] * self.tile_size

        if old_tile_size:
            scale = self.tile_size / old_tile_size
            ghost_size = self.tile_size * 0.9

            for ghost, gx, gy, target_tile in ghost_data:
                ghost.x = self.maze_offset_x + gx * self.tile_size
                ghost.y = self.maze_offset_y + gy * self.tile_size
                ghost.size = ghost_size
                ghost.speed = max(0.1, ghost.speed * scale)
                ghost.base_speed = max(0.1, ghost.base_speed * scale)
                ghost.bounds = self.maze_bounds
                if target_tile:
                    ghost.move_target = (
                        self.maze_offset_x + target_tile[0] * self.tile_size,
                        self.maze_offset_y + target_tile[1] * self.tile_size,
                    )

            small_size = max(3, self.tile_size * 0.2)
            big_size = max(7, self.tile_size * 0.5)
            for pellet, px, py, is_big in pellet_data:
                pellet.x = self.maze_offset_x + px * self.tile_size
                pellet.y = self.maze_offset_y + py * self.tile_size
                pellet.size = big_size if is_big else small_size

        bx, by, bw, bh = self.maze_bounds
        self.pacman_x = max(bx + self.pacman_radius, min(self.pacman_x, bx + bw - self.pacman_radius))
        self.pacman_y = max(by + self.pacman_radius, min(self.pacman_y, by + bh - self.pacman_radius))

        self._last_layout_state = (int(self.x), int(self.y), int(self.width), int(self.height))

    def create_maze(self):
        self.walls = []
        for row_index, row in enumerate(MAZE_MAP):
            maze_row = self.maze_rows - 1 - row_index
            for col, cell in enumerate(row):
                if cell == '#':
                    x = self.maze_offset_x + col * self.tile_size
                    y = self.maze_offset_y + maze_row * self.tile_size
                    self.walls.append((x, y, self.tile_size, self.tile_size))

    def create_pellets(self):
        self.pellets = []
        small_size = max(3, self.tile_size * 0.2)
        big_size = max(7, self.tile_size * 0.5)
        for row_index, row in enumerate(MAZE_MAP):
            maze_row = self.maze_rows - 1 - row_index
            for col, cell in enumerate(row):
                if cell not in ['.', 'o']:
                    continue
                x = self.maze_offset_x + (col + 0.5) * self.tile_size
                y = self.maze_offset_y + (maze_row + 0.5) * self.tile_size
                size = big_size if cell == 'o' else small_size
                self.pellets.append(Pellet(x, y, size))

    def create_ghosts(self):
        self.ghosts = []

        base_speed = self.tile_size * 0.16
        ghost_size = self.tile_size * 0.9

        ghost_configs = [
            ('#FF4D4D', 1.1, 0.8),
            ('#4DD6FF', 1.0, 0.6),
            ('#FF8FDB', 1.05, 0.7),
            ('#FFB04D', 0.95, 0.5),
        ]

        spawn_cols = [self.maze_cols // 2 - 1, self.maze_cols // 2 + 1,
                      self.maze_cols // 2 - 3, self.maze_cols // 2 + 3]
        spawn_rows = [self.maze_rows // 2 + 1, self.maze_rows // 2 + 1,
                      self.maze_rows // 2 - 1, self.maze_rows // 2 - 1]

        for i in range(self.ghost_count):
            color, speed_mult, aggression = ghost_configs[i]

            col = spawn_cols[i]
            row = spawn_rows[i]
            # ensure spawn tile is open; find nearby open tile if needed
            sc, sr = self.find_open_tile(col, row)
            x, y = self.grid_to_pos(sc, sr)
            speed = base_speed * speed_mult

            if self.difficulty == 'easy':
                speed = speed * 0.8
                aggression = aggression * 0.7
            elif self.difficulty == 'hard':
                speed = speed * 1.2
                aggression = min(aggression * 1.3, 0.95)

            g = Ghost(x, y,
                      kivy.utils.get_color_from_hex(color),
                      speed, aggression, ghost_size, self.maze_bounds)
            # stagger targets so ghosts roam independently
            self.ghosts.append(g)
            try:
                cols = self.maze_cols
                rows = self.maze_rows
                for _ in range(16):
                    c = rnd.randint(0, cols - 1)
                    r = rnd.randint(0, rows - 1)
                    tc, tr = self.find_open_tile(c, r)
                    tx, ty = self.grid_to_pos(tc, tr)
                    if not self.check_wall_collision(tx, ty):
                        g.move_target = (tx, ty)
                        break
            except Exception:
                pass
            g.direction_change_interval = 0.25 + i * 0.08
            try:
                g.clear_frightened()
            except Exception:
                g.frightened = False
                g.frightened_until = 0


    def on_keyboard_closed(self):
        if self._keyboard:
            self._keyboard.unbind(on_key_down=self.on_key_down)
            self._keyboard.unbind(on_key_up=self.on_key_up)
            self._keyboard = None

    def on_key_down(self, keyboard, keycode, text, modifiers):
        # Support numeric keycodes (keycode[0]) and name (keycode[1])
        code = None
        name = None
        try:
            code = int(keycode[0])
        except Exception:
            code = None
        try:
            name = keycode[1]
        except Exception:
            name = None

        # handle control keys
        if name == 'p' or code == ord('p'):
            self.paused = not self.paused
            return True
        elif name == 'r' or code == ord('r'):
            self.reset_game()
            return True
        elif name == 'h' or code == ord('h'):
            if hasattr(self, 'parent') and self.parent and hasattr(self.parent, 'show_help'):
                self.parent.show_help()
            return True

        if not self.game_over and not self.won and not self.paused:
            direction = None
            if name in ('left', 'right', 'up', 'down'):
                direction = name
            elif code in (276,):  # left
                direction = 'left'
            elif code in (275,):  # right
                direction = 'right'
            elif code in (273,):  # up
                direction = 'up'
            elif code in (274,):  # down
                direction = 'down'

            if direction == 'left':
                self.moving_left = True
                self.pacman_target_direction = 'left'
                self.pacman_direction = 'left'
                return True
            if direction == 'right':
                self.moving_right = True
                self.pacman_target_direction = 'right'
                self.pacman_direction = 'right'
                return True
            if direction == 'up':
                self.moving_up = True
                self.pacman_target_direction = 'up'
                self.pacman_direction = 'up'
                return True
            if direction == 'down':
                self.moving_down = True
                self.pacman_target_direction = 'down'
                self.pacman_direction = 'down'
                return True
        return True

    def on_key_up(self, keyboard, keycode):
        # accept numeric or name keycodes
        code = None
        name = None
        try:
            code = int(keycode[0])
        except Exception:
            code = None
        try:
            name = keycode[1]
        except Exception:
            name = None

        direction = None
        if name in ('left', 'right', 'up', 'down'):
            direction = name
        elif code in (276,):
            direction = 'left'
        elif code in (275,):
            direction = 'right'
        elif code in (273,):
            direction = 'up'
        elif code in (274,):
            direction = 'down'

        if direction == 'left':
            self.moving_left = False
        elif direction == 'right':
            self.moving_right = False
        elif direction == 'up':
            self.moving_up = False
        elif direction == 'down':
            self.moving_down = False
        return True

    def rect_collide(self, rect1, rect2):
        return not (rect1[0] + rect1[2] < rect2[0] or
                    rect1[0] > rect2[0] + rect2[2] or
                    rect1[1] + rect1[3] < rect2[1] or
                    rect1[1] > rect2[1] + rect2[3])

    def grid_to_pos(self, col, row):
        x = self.maze_offset_x + (col + 0.5) * self.tile_size
        y = self.maze_offset_y + (row + 0.5) * self.tile_size
        return x, y

    def is_walkable_cell(self, col, row):
        if col < 0 or col >= self.maze_cols or row < 0 or row >= self.maze_rows:
            return False
        map_row = self.maze_rows - 1 - row
        if MAZE_MAP[map_row][col] == '#':
            return False
        x, y = self.grid_to_pos(col, row)
        rect = (x - self.pacman_collision_radius, y - self.pacman_collision_radius,
                self.pacman_collision_radius * 2, self.pacman_collision_radius * 2)
        for wall in self.walls:
            if self.rect_collide(rect, wall):
                return False
        return True

    def find_open_tile(self, start_col, start_row):
        if self.is_walkable_cell(start_col, start_row):
            return start_col, start_row

        for radius in range(1, max(self.maze_cols, self.maze_rows)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    col = start_col + dx
                    row = start_row + dy
                    if self.is_walkable_cell(col, row):
                        return col, row
        return start_col, start_row

    def set_spawn_positions(self):
        pac_col = self.maze_cols - 5
        pac_row = self.maze_rows // 2
        pac_col, pac_row = self.find_open_tile(pac_col, pac_row)
        self.pacman_x, self.pacman_y = self.grid_to_pos(pac_col, pac_row)

    def check_wall_collision(self, new_x, new_y):
        pacman_rect = (new_x - self.pacman_collision_radius,
                       new_y - self.pacman_collision_radius,
                       self.pacman_collision_radius * 2,
                       self.pacman_collision_radius * 2)

        for wall in self.walls:
            if self.rect_collide(pacman_rect, wall):
                return True
        return False

    def check_pellet_collision(self):
        ate_small = False
        ate_big = False
        for pellet in self.pellets[:]:
            distance = simple_distance(self.pacman_x, self.pacman_y, pellet.x, pellet.y)

            if distance < self.pacman_radius + pellet.size:
                self.score += 10 if pellet.size <= 5 else 50
                self.pellets.remove(pellet)
                if pellet.size <= 5:
                    ate_small = True
                else:
                    ate_big = True

                if len(self.pellets) == 0:
                    self.won = True
                break

        if ate_small or ate_big:
            self.last_eat_time = time.time()
            if ate_big:
                # Enter frenzy mode: ghosts become frightened and edible
                self.frenzy_until = time.time() + self.frenzy_duration
                if hasattr(self, 'ghosts'):
                    for g in self.ghosts:
                        try:
                            g.set_frightened(self.frenzy_until)
                        except Exception:
                            pass
                self.audio.play_one_shot("frenzy")
            else:
                self.audio.play_one_shot("eating")

    def check_ghost_collision(self):
        pacman_rect = (self.pacman_x - self.pacman_radius,
                       self.pacman_y - self.pacman_radius,
                       self.pacman_radius * 2,
                       self.pacman_radius * 2)

        for ghost in self.ghosts:
            half = ghost.size / 2
            ghost_rect = (ghost.x - half, ghost.y - half, ghost.size, ghost.size)
            if self.rect_collide(pacman_rect, ghost_rect):
                if getattr(ghost, 'frightened', False):
                    # eat the ghost during frenzy
                    self.score += 200
                    try:
                        ghost.reset()
                        ghost.frightened = False
                    except Exception:
                        pass
                else:
                    if not self.game_over:
                        self.game_over = True
                        try:
                            self.show_game_over_popup()
                        except Exception:
                            pass
                break

    def move_pacman(self):
        old_x, old_y = self.pacman_x, self.pacman_y

        if self.pacman_target_direction != self.pacman_direction:
            # Improved turning: allow turns when near tile center to avoid clipping
            col = int((self.pacman_x - self.maze_offset_x) / self.tile_size)
            row = int((self.pacman_y - self.maze_offset_y) / self.tile_size)
            center_x, center_y = self.grid_to_pos(col, row)
            dist_to_center = simple_distance(self.pacman_x, self.pacman_y, center_x, center_y)

            if dist_to_center <= max(1.5, self.pacman_speed * 1.5):
                # check if the adjacent target cell is walkable; if so snap to center and turn
                tcol, trow = col, row
                if self.pacman_target_direction == 'left':
                    tcol -= 1
                elif self.pacman_target_direction == 'right':
                    tcol += 1
                elif self.pacman_target_direction == 'up':
                    trow += 1
                elif self.pacman_target_direction == 'down':
                    trow -= 1

                if self.is_walkable_cell(tcol, trow):
                    # snap to tile center for a clean turn
                    self.pacman_x, self.pacman_y = center_x, center_y
                    self.pacman_direction = self.pacman_target_direction
            else:
                # fallback: keep original behavior (allow immediate turn if next step is free)
                test_x, test_y = self.pacman_x, self.pacman_y

                if self.pacman_target_direction == 'left':
                    test_x -= self.pacman_speed
                elif self.pacman_target_direction == 'right':
                    test_x += self.pacman_speed
                elif self.pacman_target_direction == 'up':
                    test_y += self.pacman_speed
                elif self.pacman_target_direction == 'down':
                    test_y -= self.pacman_speed

                if not self.check_wall_collision(test_x, test_y):
                    self.pacman_direction = self.pacman_target_direction

        new_x, new_y = self.pacman_x, self.pacman_y
        wants_move = any([self.moving_left, self.moving_right, self.moving_up, self.moving_down])
        if wants_move:
            if self.pacman_direction == 'left':
                new_x -= self.pacman_speed
            elif self.pacman_direction == 'right':
                new_x += self.pacman_speed
            elif self.pacman_direction == 'up':
                new_y += self.pacman_speed
            elif self.pacman_direction == 'down':
                new_y -= self.pacman_speed

        if not self.check_wall_collision(new_x, new_y):
            self.pacman_x = new_x
            self.pacman_y = new_y

        bx, by, bw, bh = self.maze_bounds
        self.pacman_x = max(bx + self.pacman_radius, min(self.pacman_x, bx + bw - self.pacman_radius))
        self.pacman_y = max(by + self.pacman_radius, min(self.pacman_y, by + bh - self.pacman_radius))



    def update(self, dt):
        if self.intro_locked and hasattr(self, 'audio') and not self.audio.opening_active:
            self.intro_locked = False
            self.start_banner_until = time.time() + 1.2

        if not self.intro_locked and not self.game_over and not self.won and not self.paused:
            if self.mouth_opening:
                self.pacman_mouth_angle += 8
                if self.pacman_mouth_angle >= 60:
                    self.mouth_opening = False
            else:
                self.pacman_mouth_angle -= 8
                if self.pacman_mouth_angle <= 5:
                    self.mouth_opening = True

            self.move_pacman()

            self.check_pellet_collision()

            for ghost in self.ghosts:
                # pass the game instance so ghosts can use maze/grid helpers
                try:
                    ghost.update(self, dt)
                except Exception:
                    # fallback to old signature if needed
                    ghost.update(self.pacman_x, self.pacman_y, self.walls, dt)

            self.check_ghost_collision()

        if hasattr(self, 'audio'):
            self.audio.update(self)

        self.redraw_canvas()

    def show_game_over_popup(self):
        if getattr(self, '_game_over_popup_shown', False):
            return
        self._game_over_popup_shown = True
        content = kivy.uix.boxlayout.BoxLayout(orientation='vertical', spacing=10, padding=10)
        label = kivy.uix.label.Label(text='GAME OVER!', color=(1, 0, 0, 1), font_size='20sp')
        restart_btn = kivy.uix.button.Button(text='Restart', size_hint=(1, 0.3), background_color=(0.8, 0.2, 0.2, 1))
        content.add_widget(label)
        content.add_widget(restart_btn)
        popup = kivy.uix.popup.Popup(title='GAME OVER', content=content, size_hint=(0.4, 0.25), auto_dismiss=True)
        def on_restart(inst):
            try:
                popup.dismiss()
            except Exception:
                pass
            try:
                self.reset_game()
            except Exception:
                pass
        restart_btn.bind(on_press=on_restart)
        self._game_over_popup = popup
        popup.open()

    def reset_game(self):
        self.score = 0
        self.game_over = False
        self.won = False
        self.paused = False
        self.pacman_direction = 'right'
        self.pacman_target_direction = 'right'

        self.moving_left = False
        self.moving_right = False
        self.moving_up = False
        self.moving_down = False

        self.pellets.clear()
        self.create_pellets()
        self.set_spawn_positions()

        for ghost in self.ghosts:
            ghost.reset()

        if hasattr(self, 'audio'):
            self.audio.play_opening()
            self.intro_locked = self.audio.opening_active
            self.start_banner_until = 0.0

        self.redraw_canvas()

    def redraw_canvas(self, *args):
        try:
            self.canvas.clear()

            with self.canvas:
                kivy.graphics.Color(0.05, 0.05, 0.1, 1)
                kivy.graphics.Rectangle(pos=self.pos, size=self.size)

                wall_glow = 0.2
                for wall in self.walls:
                    x, y, w, h = wall
                    radius = [self.tile_size * 0.25]
                    kivy.graphics.Color(0.15, 0.3, 0.8, 0.35)
                    kivy.graphics.RoundedRectangle(
                        pos=(x - wall_glow, y - wall_glow),
                        size=(w + wall_glow * 2, h + wall_glow * 2),
                        radius=radius
                    )
                    kivy.graphics.Color(0.2, 0.45, 1, 1)
                    kivy.graphics.RoundedRectangle(
                        pos=(x, y),
                        size=(w, h),
                        radius=radius
                    )

                for pellet in self.pellets:
                    if pellet.size > 5:
                        kivy.graphics.Color(1, 1, 1, 0.4)
                        glow_size = pellet.size * 2.2
                        kivy.graphics.Ellipse(pos=(pellet.x - glow_size / 2,
                                                   pellet.y - glow_size / 2),
                                              size=(glow_size, glow_size))
                    kivy.graphics.Color(*pellet.color)
                    kivy.graphics.Ellipse(pos=(pellet.x - pellet.size / 2,
                                               pellet.y - pellet.size / 2),
                                          size=(pellet.size, pellet.size))

                if hasattr(self, 'ghosts'):
                    for ghost in self.ghosts:
                        body_width = ghost.size
                        body_height = ghost.size * 0.9
                        x = ghost.x - body_width / 2
                        y = ghost.y - body_height / 2

                        kivy.graphics.Color(*ghost.color)
                        kivy.graphics.Ellipse(pos=(x, y + body_height * 0.2),
                                              size=(body_width, body_height * 0.8))
                        kivy.graphics.Rectangle(pos=(x, y),
                                                size=(body_width, body_height * 0.55))

                        for i in range(3):
                            scallop_x = x + i * (body_width / 3)
                            kivy.graphics.Ellipse(pos=(scallop_x, y - body_width * 0.05),
                                                  size=(body_width / 3, body_width / 3))

                        eye_w = body_width * 0.22
                        eye_h = body_height * 0.3
                        eye_y = y + body_height * 0.35
                        left_eye_x = x + body_width * 0.2
                        right_eye_x = x + body_width * 0.58

                        kivy.graphics.Color(1, 1, 1, 1)
                        kivy.graphics.Ellipse(pos=(left_eye_x, eye_y),
                                              size=(eye_w, eye_h))
                        kivy.graphics.Ellipse(pos=(right_eye_x, eye_y),
                                              size=(eye_w, eye_h))

                        if hasattr(self, 'pacman_x') and hasattr(self, 'pacman_y'):
                            dx = (self.pacman_x - ghost.x) / (self.tile_size * 2)
                            dy = (self.pacman_y - ghost.y) / (self.tile_size * 2)
                            dx = max(-2, min(2, dx))
                            dy = max(-2, min(2, dy))

                            kivy.graphics.Color(0.1, 0.1, 0.2, 1)
                            pupil_w = eye_w * 0.45
                            pupil_h = eye_h * 0.6
                            kivy.graphics.Ellipse(pos=(left_eye_x + dx, eye_y + dy),
                                                  size=(pupil_w, pupil_h))
                            kivy.graphics.Ellipse(pos=(right_eye_x + dx, eye_y + dy),
                                                  size=(pupil_w, pupil_h))

                if hasattr(self, 'pacman_x') and hasattr(self, 'pacman_y') and hasattr(self, 'pacman_radius'):
                    if not self.game_over and not self.won:
                        kivy.graphics.Color(1, 0.9, 0.1, 1)

                        if self.pacman_direction == 'right':
                            start_angle = self.pacman_mouth_angle
                            end_angle = 360 - self.pacman_mouth_angle
                        elif self.pacman_direction == 'left':
                            start_angle = 180 + self.pacman_mouth_angle
                            end_angle = 540 - self.pacman_mouth_angle
                        elif self.pacman_direction == 'up':
                            start_angle = 90 + self.pacman_mouth_angle
                            end_angle = 450 - self.pacman_mouth_angle
                        else:
                            start_angle = 270 + self.pacman_mouth_angle
                            end_angle = 630 - self.pacman_mouth_angle

                        kivy.graphics.Ellipse(pos=(self.pacman_x - self.pacman_radius,
                                                   self.pacman_y - self.pacman_radius),
                                              size=(self.pacman_radius * 2, self.pacman_radius * 2),
                                              angle_start=start_angle,
                                              angle_end=end_angle)

                        kivy.graphics.Color(0.1, 0.1, 0.2, 1)
                        eye_offset = self.pacman_radius * 0.35
                        if self.pacman_direction == 'right':
                            eye_x = self.pacman_x + eye_offset
                            eye_y = self.pacman_y + eye_offset
                        elif self.pacman_direction == 'left':
                            eye_x = self.pacman_x - eye_offset
                            eye_y = self.pacman_y + eye_offset
                        elif self.pacman_direction == 'up':
                            eye_x = self.pacman_x - eye_offset * 0.2
                            eye_y = self.pacman_y + eye_offset
                        else:
                            eye_x = self.pacman_x - eye_offset * 0.2
                            eye_y = self.pacman_y - eye_offset

                        eye_size = self.pacman_radius * 0.25
                        kivy.graphics.Ellipse(pos=(eye_x - eye_size / 2,
                                                   eye_y - eye_size / 2),
                                              size=(eye_size, eye_size))
                    else:
                        if self.game_over:
                            kivy.graphics.Color(1, 0, 0, 1)
                        else:
                            kivy.graphics.Color(0, 1, 0, 1)
                        kivy.graphics.Ellipse(pos=(self.pacman_x - self.pacman_radius,
                                                   self.pacman_y - self.pacman_radius),
                                              size=(self.pacman_radius * 2, self.pacman_radius * 2))
        except Exception as e:
            pass


class GameUI(kivy.uix.boxlayout.BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'

        top_bar = kivy.uix.boxlayout.BoxLayout(size_hint=(1, 0.1))

        self.score_label = kivy.uix.label.Label(text='Score: 0',
                                                size_hint=(0.2, 1),
                                                color=(1, 1, 1, 1),
                                                font_size='16sp')

        title_label = kivy.uix.label.Label(text='PAC-MAN',
                                           size_hint=(0.25, 1),
                                           color=(1, 1, 0, 1),
                                           bold=True,
                                           font_size='18sp')

        self.difficulty_spinner = kivy.uix.spinner.Spinner(
            text='Medium',
            values=('Easy', 'Medium', 'Hard'),
            size_hint=(0.2, 0.8),
            pos_hint={'center_y': 0.5},
            background_color=(0.3, 0.6, 0.9, 1),
            color=(1, 1, 1, 1)
        )
        self.difficulty_spinner.bind(text=self.on_difficulty_change)

        button_layout = kivy.uix.boxlayout.BoxLayout(size_hint=(0.35, 1), spacing=3)

        self.help_button = kivy.uix.button.Button(text='Help (H)',
                                                  on_press=self.show_help,
                                                  background_color=(0.2, 0.6, 0.8, 1),
                                                  font_size='12sp')

        self.pause_button = kivy.uix.button.Button(text='Pause (P)',
                                                   on_press=self.toggle_pause,
                                                   background_color=(0.5, 0.5, 0.5, 1),
                                                   font_size='12sp')

        self.restart_button = kivy.uix.button.Button(text='Restart (R)',
                                                     on_press=self.restart_game,
                                                     background_color=(0.5, 0, 0, 1),
                                                     font_size='12sp')

        button_layout.add_widget(self.help_button)
        button_layout.add_widget(self.pause_button)
        button_layout.add_widget(self.restart_button)

        top_bar.add_widget(self.score_label)
        top_bar.add_widget(title_label)
        top_bar.add_widget(self.difficulty_spinner)
        top_bar.add_widget(button_layout)

        self.game = PacmanGame(difficulty='medium')

        self.status_label = kivy.uix.label.Label(
            text='Press H for instructions | Difficulty: Medium',
            size_hint=(0.88, 0.05),
            color=(0, 1, 0, 1),
            font_size='12sp'
        )

        # bottom bar with status and exit button (exit appears bottom-right)
        bottom_bar = kivy.uix.boxlayout.BoxLayout(size_hint=(1, 0.05), orientation='horizontal')
        bottom_bar.add_widget(self.status_label)
        logout_btn = kivy.uix.button.Button(text='Logout', size_hint=(0.12, 1), background_color=(0.8, 0.1, 0.1, 1))
        logout_btn.bind(on_press=self.logout)
        bottom_bar.add_widget(logout_btn)

        self.add_widget(top_bar)
        self.add_widget(self.game)
        self.add_widget(bottom_bar)

        kivy.clock.Clock.schedule_interval(self.update_ui, 1 / 30.0)

        kivy.clock.Clock.schedule_once(lambda dt: self.show_welcome_message(), 0.5)

    def logout(self, instance):
        # attempt to restore the login screen (parent is LoginScreen)
        parent = getattr(self, 'parent', None)
        try:
            from kivy.app import App
            if parent and parent.__class__.__name__ == 'LoginScreen':
                try:
                    parent.clear_widgets()
                    # re-initialize the login screen in place
                    parent.__init__()
                    return
                except Exception:
                    pass
            # fallback: replace app root
            app = App.get_running_app()
            new_login = LoginScreen()
            try:
                # clear existing root and set new root
                if hasattr(app, 'root') and app.root:
                    app.root.clear_widgets()
                app.root = new_login
            except Exception:
                try:
                    app.stop()
                except Exception:
                    import sys
                    sys.exit(0)
        except Exception:
            pass

    def exit_app(self, instance):
        app = kivy.app.App.get_running_app()
        try:
            app.stop()
        except Exception:
            import sys
            sys.exit(0)

    def on_difficulty_change(self, spinner, text):
        difficulty = text.lower()
        self.restart_with_difficulty(difficulty)
        self.status_label.text = f'Press H for instructions | Difficulty: {text}'

    def restart_with_difficulty(self, difficulty):
        if hasattr(self, 'game'):
            self.game.destroy()
        self.remove_widget(self.game)

        self.game = PacmanGame(difficulty=difficulty)

        self.add_widget(self.game, index=1)

        self.pause_button.text = 'Pause (P)'

    def show_welcome_message(self):
        content = kivy.uix.boxlayout.BoxLayout(orientation='vertical', spacing=10, padding=10)

        current_diff = self.difficulty_spinner.text
        welcome_text = f"""
🎮 WELCOME TO PAC-MAN! 🎮

QUICK GUIDE:
• Use ARROW KEYS to move
• Eat all YELLOW dots to win
• Avoid the GHOSTS at all costs!
• Big orange dots = 50 points

Current Difficulty: {current_diff}
• Easy: Slower ghosts, more pellets
• Medium: Balanced challenge
• Hard: Faster ghosts, complex maze

Press H for detailed instructions
        """

        label = kivy.uix.label.Label(text=welcome_text,
                                     color=(1, 1, 0, 1),
                                     halign='center',
                                     font_size='14sp')

        ok_button = kivy.uix.button.Button(text="LET'S PLAY!",
                                           size_hint=(1, 0.3),
                                           background_color=(0, 0.8, 0, 1))

        content.add_widget(label)
        content.add_widget(ok_button)

        popup = kivy.uix.popup.Popup(title='QUICK START GUIDE',
                                     content=content,
                                     size_hint=(0.8, 0.6),
                                     auto_dismiss=True)

        ok_button.bind(on_press=popup.dismiss)
        popup.open()

    def show_help(self, instance):
        content = kivy.uix.boxlayout.BoxLayout(orientation='vertical', spacing=10, padding=10)


        instructions = """
╔════════════════════════════════════╗
║         HOW TO PLAY PAC-MAN        ║
╚════════════════════════════════════╝

🎯 OBJECTIVE:
   • Eat all YELLOW pellets to win!
   • Avoid the GHOSTS at all costs!
   • Big ORANGE pellets = 50 points

🎮 CONTROLS:
   ← ↑ → ↓    : Move Pac-Man
   [P]        : Pause/Resume game
   [R]        : Restart game
   [H]        : Show this help screen

📊 DIFFICULTY LEVELS:

   🟢 EASY:
   • 2 Ghosts (slower, less aggressive)
   • More pellets and power-ups
   • Pac-Man moves faster
   • Simple maze layout

   🟡 MEDIUM:
   • 3 Ghosts (balanced speed)
   • Standard pellet count
   • Moderate maze complexity

   🔴 HARD:
   • 4 Ghosts (faster, more aggressive)
   • Fewer pellets (harder to win)
   • Complex maze with obstacles
   • Pac-Man moves slower

💰 SCORING:
   • Small pellets: 10 points
   • Large pellets: 50 points

💡 TIPS:
   • Change difficulty anytime using dropdown
   • Plan your route to avoid corners
   • Watch ghost movement patterns
   • Higher difficulty = more challenge!

Press ESC or click outside to close
        """

        instruction_label = kivy.uix.label.Label(text=instructions,
                                                 color=(1, 1, 1, 1),
                                                 halign='left',
                                                 valign='top',
                                                 font_size='12sp',
                                                 text_size=(400, None))

        content.add_widget(instruction_label)


        popup = kivy.uix.popup.Popup(title='🎮 PAC-MAN INSTRUCTIONS 🎮',
                                     content=content,
                                     size_hint=(0.9, 0.9),
                                     background_color=(0.1, 0.1, 0.1, 1))

        popup.open()

    def toggle_pause(self, instance):
        if hasattr(self, 'game'):
            self.game.paused = not self.game.paused
            if self.game.paused:
                self.pause_button.text = 'Resume (P)'
                self.status_label.text = '⏸ PAUSED - Press P to resume'
                self.status_label.color = (1, 1, 0, 1)
            else:
                self.pause_button.text = 'Pause (P)'
                diff_text = self.difficulty_spinner.text
                self.status_label.text = f'▶ Use arrow keys to move! | Difficulty: {diff_text}'
                self.status_label.color = (0, 1, 0, 1)

    def restart_game(self, instance):
        if hasattr(self, 'game'):
            self.game.reset_game()
            self.pause_button.text = 'Pause (P)'
            diff_text = self.difficulty_spinner.text
            self.status_label.text = f'🔄 Game restarted! | Difficulty: {diff_text}'
            self.status_label.color = (0, 1, 0, 1)

    def update_ui(self, dt):
        if hasattr(self, 'game') and hasattr(self.game, 'score'):
            self.score_label.text = f'Score: {self.game.score}'
            diff_text = self.difficulty_spinner.text

            if self.game.game_over:
                self.status_label.text = f'💀 GAME OVER! Press R to restart | Difficulty: {diff_text}'
                self.status_label.color = (1, 0, 0, 1)
            elif self.game.won:
                self.status_label.text = f'🏆 YOU WIN! Press R to play again | Difficulty: {diff_text}'
                self.status_label.color = (0, 1, 0, 1)
            elif self.game.paused:
                self.status_label.text = '⏸ PAUSED - Press P to resume'
                self.status_label.color = (1, 1, 0, 1)
            elif getattr(self.game, 'intro_locked', False):
                self.status_label.text = 'Ready!'
                self.status_label.color = (1, 1, 0, 1)
            elif time.time() < getattr(self.game, 'start_banner_until', 0.0):
                self.status_label.text = 'Start!'
                self.status_label.color = (0, 1, 0, 1)
            else:
                direction = self.game.pacman_direction.capitalize()
                moving = any([self.game.moving_left, self.game.moving_right,
                              self.game.moving_up, self.game.moving_down])


                diff_indicator = "🟢" if diff_text == "Easy" else "🟡" if diff_text == "Medium" else "🔴"

                if moving:
                    self.status_label.text = f'➡ Moving {direction} | Pellets: {len(self.game.pellets)} | {diff_indicator} {diff_text}'
                else:
                    self.status_label.text = f'⏹ Standing by | Pellets: {len(self.game.pellets)} | {diff_indicator} {diff_text}'
                self.status_label.color = (0, 1, 0, 1)


class LoginScreen(kivy.uix.floatlayout.FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.users_file = os.path.join(os.path.dirname(__file__), 'users.json')
        self.users = self.load_users()

        # glassy centered panel
        self.panel = kivy.uix.boxlayout.BoxLayout(orientation='vertical', size_hint=(0.5, 0.5),
                                                  pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=12,
                                                  padding=20)

        with self.panel.canvas.before:
            kivy.graphics.Color(1, 1, 1, 0.06)
            self._bg_rect = kivy.graphics.RoundedRectangle(pos=self.panel.pos, size=self.panel.size, radius=[12])
            kivy.graphics.Color(1, 1, 1, 0.12)
            self._border = kivy.graphics.RoundedRectangle(pos=(self.panel.pos[0]-1, self.panel.pos[1]-1), size=(self.panel.size[0]+2, self.panel.size[1]+2), radius=[12])

        self.panel.bind(pos=self._update_panel_bg, size=self._update_panel_bg)

        title = kivy.uix.label.Label(text='Welcome — PAC-MAN', size_hint=(1, 0.15), color=(1, 0.9, 0.1, 1), font_size='20sp')

        # user picker: spinner dropdown to pick existing user or choose 'New user'
        try:
            user_list = sorted(self.users.keys())
        except Exception:
            user_list = []
        values = ['New user'] + user_list if user_list else ['New user']
        self.user_spinner = kivy.uix.spinner.Spinner(text='New user', values=values, size_hint=(1, 0.12))
        self.user_spinner.bind(text=self.on_user_select)

        self.username = kivy.uix.textinput.TextInput(hint_text='Username', multiline=False, size_hint=(1, 0.12))
        self.password = kivy.uix.textinput.TextInput(hint_text='Password', password=True, multiline=False, size_hint=(1, 0.12))

        btn_box = kivy.uix.boxlayout.BoxLayout(size_hint=(1, 0.2), spacing=8)
        login_btn = kivy.uix.button.Button(text='Login', background_color=(0.2, 0.8, 0.2, 1))
        reg_btn = kivy.uix.button.Button(text='Register', background_color=(0.2, 0.4, 0.8, 1))
        exit_btn = kivy.uix.button.Button(text='Exit', background_color=(0.8, 0.1, 0.1, 1))
        btn_box.add_widget(login_btn)
        btn_box.add_widget(reg_btn)
        btn_box.add_widget(exit_btn)

        self.message = kivy.uix.label.Label(text='', size_hint=(1, 0.12), color=(1, 0.6, 0.2, 1))

        self.panel.add_widget(title)
        self.panel.add_widget(self.user_spinner)
        self.panel.add_widget(self.username)
        self.panel.add_widget(self.password)
        self.panel.add_widget(btn_box)
        self.panel.add_widget(self.message)

        self.add_widget(self.panel)

        login_btn.bind(on_press=self.attempt_login)
        reg_btn.bind(on_press=self.attempt_register)
        exit_btn.bind(on_press=self.exit_app)

    def _update_panel_bg(self, *args):
        try:
            self._bg_rect.pos = self.panel.pos
            self._bg_rect.size = self.panel.size
            self._border.pos = (self.panel.pos[0]-1, self.panel.pos[1]-1)
            self._border.size = (self.panel.size[0]+2, self.panel.size[1]+2)
        except Exception:
            pass

    def load_users(self):
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_users(self):
        try:
            with open(self.users_file, 'w') as f:
                json.dump(self.users, f)
        except Exception:
            pass

    def hash_pw(self, pw):
        return hashlib.sha256(pw.encode('utf-8')).hexdigest()

    def on_user_select(self, spinner, text):
        # When a username is chosen from the dropdown, fill the username field
        try:
            if not text or text == 'New user' or text == 'Select user':
                self.username.text = ''
                # focus username so user can type a new name
                try:
                    self.username.focus = True
                except Exception:
                    pass
            else:
                self.username.text = text
                try:
                    self.password.focus = True
                except Exception:
                    pass
        except Exception:
            pass

    def attempt_register(self, instance):
        u = (self.username.text or '').strip()
        p = (self.password.text or '')
        if not u or not p:
            self.message.text = 'Enter username and password.'
            return
        if u in self.users:
            self.message.text = 'User exists — choose a different name.'
            return
        self.users[u] = self.hash_pw(p)
        self.save_users()
        # update spinner values so new user appears in dropdown
        try:
            vals = ['New user'] + sorted(self.users.keys())
            self.user_spinner.values = vals
            self.user_spinner.text = u
        except Exception:
            pass
        self.message.text = 'Registered. You can now login.'

    def attempt_login(self, instance):
        u = (self.username.text or '').strip()
        p = (self.password.text or '')
        if not u or not p:
            self.message.text = 'Enter username and password.'
            return
        h = self.hash_pw(p)
        if self.users.get(u) == h:
            self.message.text = 'Login successful — starting game.'
            self.start_game()
        else:
            self.message.text = 'Invalid credentials.'

    def start_game(self):
        # remove login visuals (clear canvas) and add the GameUI
        try:
            self.canvas.clear()
        except Exception:
            pass
        self.clear_widgets()
        game_ui = GameUI()
        # keep reference for cleanup
        self.game = game_ui
        self.add_widget(game_ui)

    def exit_app(self, instance):
        app = kivy.app.App.get_running_app()
        try:
            app.stop()
        except Exception:
            import sys
            sys.exit(0)


class PacmanApp(kivy.app.App):
    def build(self):
        self.title = 'Pac-Man with Difficulty Levels - Press H for Help!'
        return LoginScreen()

    def on_stop(self):
        if hasattr(self, 'root') and hasattr(self.root, 'game'):
            self.root.game.destroy()


if __name__ == '__main__':
    PacmanApp().run()
