import json
import math
import os
import random
import sys

import pygame

# Initialize Pygame
pygame.init()

# --- DISPLAY SETTINGS ---
WIDTH, HEIGHT = 1000, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Timing Clash")
clock = pygame.time.Clock()

# --- SAVE SYSTEM ---
SAVE_FILE = "timing_clash_save.json"

def load_save():
    """Loads the player's highest unlocked level from save file."""
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
                data = json.load(f)
                return max(1, data.get("highest_unlocked_level", 1))
        except Exception:
            return 1
    return 1

def save_progress(highest_level):
    """Saves the player's highest unlocked level to disk."""
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump({"highest_unlocked_level": highest_level}, f)
    except Exception:
        pass

# --- GLOBAL GAME SETTINGS (TOGGLES) ---
SETTINGS = {
    "screen_shake": True,
    "particles": True,
    "show_fps": False,
    "hardcore_penalties": False,
}
SETTING_KEYS = list(SETTINGS.keys())
SETTING_LABELS = {
    "screen_shake": "Screen Shake Effect",
    "particles": "Particle FX",
    "show_fps": "FPS Counter",
    "hardcore_penalties": "Hardcore Penalties (2s Freeze)",
}

# --- HELPER FUNCTION ---
def load_and_scale(file_path, target_size):
    """Loads an image, converts it with alpha, and scales it to fit."""
    try:
        img = pygame.image.load(file_path).convert_alpha()
        return pygame.transform.scale(img, target_size)
    except (pygame.error, FileNotFoundError):
        return None


# --- ASSET CONFIGURATION & MANAGEMENT ---
ASSET_INFO = {
    "p1_bar": {"dim": (50, 400), "res": (50, 400), "file": "bar.png"},
    "p1_target": {"dim": (50, 80), "res": (50, 80), "file": "target.png"},
    "p1_cursor": {"dim": (80, 10), "res": (80, 10), "file": "cursor.png"},
    "p2_bar": {"dim": (50, 400), "res": (50, 400), "file": "bar.png"},
    "p2_target": {"dim": (50, 80), "res": (50, 80), "file": "target.png"},
    "p2_cursor": {"dim": (80, 10), "res": (80, 10), "file": "cursor2.png"},
}
EDITABLE_KEYS = list(ASSET_INFO.keys())

CUSTOM_ASSETS = {
    name: load_and_scale(info["file"], info["dim"]) 
    for name, info in ASSET_INFO.items()
}
CUSTOM_ASSETS["background"] = None

# --- DEFAULT COLORS ---
BG_COLOR = (25, 25, 35)
MENU_BG_COLOR = (15, 15, 20)
EDITOR_BG_COLOR = (20, 20, 30)
P1_COLOR = (100, 200, 255)
P2_COLOR = (255, 100, 100)
TARGET_COLOR = (100, 255, 100)
CURSOR_COLOR = (255, 255, 255)
TEXT_COLOR = (240, 240, 240)
FADED_TEXT_COLOR = (45, 45, 55)

# --- FONTS ---
font_giant = pygame.font.Font(None, 400)
font_large = pygame.font.Font(None, 80)
font_medium = pygame.font.Font(None, 36)
font_small = pygame.font.Font(None, 28)
font_tiny = pygame.font.Font(None, 22)


# --- BALANCED PROCEDURAL LEVEL GENERATOR ---
def generate_career_level(level_num):
    """Generates balanced, fair levels that start easy and never become impossible."""
    # Target score grows gradually and caps at a reasonable maximum
    target_score = 3 + min(level_num * 2 - 2, 25)
    
    # Cursor speed starts slow (200 px/sec) and caps at a humanly playable top speed (580 px/sec)
    base_speed = min(580, 200 + (level_num - 1) * 22)
    
    # Target box height starts generous (120 px) and floors at a hittable size (35 px)
    target_height = max(35, 120 - (level_num - 1) * 5)
    
    # Time limit provides ample time (~2.5 seconds per required point + buffer)
    time_limit = max(10.0, target_score * 2.5 + 4.0)

    descriptors = ["Beginnings", "Focus", "Precision", "Rhythm", "Tempo", "Speed", "Mastery", "Overdrive"]
    rng = random.Random(level_num * 9999)
    title = f"Level {level_num}: {rng.choice(descriptors)}"

    return {
        "level": level_num,
        "title": title,
        "target_score": target_score,
        "time_limit": time_limit,
        "cursor_speed": base_speed,
        "target_height": target_height,
    }


# --- PARTICLE SYSTEM ---
class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.vx = random.uniform(-250, 250)
        self.vy = random.uniform(-250, 250)
        self.lifetime = random.uniform(0.2, 0.5)
        self.color = color
        self.size = random.randint(4, 8)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.lifetime -= dt


class PlayerBar:
    def __init__(self, x, y, width, height, color, prefix, cursor_speed=350, target_height=80):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = color
        self.prefix = prefix
        self.score = 0
        self.streak = 0

        self.cursor_y = y
        self.cursor_speed = cursor_speed
        self.cursor_dir = 1

        self.target_height = target_height
        self.target_y = 0
        self.randomize_target()

        self.penalty_timer = 0
        self.particles = []
        self.shake_time = 0
        self.shake_offset = (0, 0)

    def randomize_target(self):
        self.target_y = random.randint(
            self.rect.top, self.rect.bottom - self.target_height
        )

    def update(self, dt):
        if SETTINGS["screen_shake"] and self.shake_time > 0:
            self.shake_time -= dt
            intensity = 8
            self.shake_offset = (
                random.randint(-intensity, intensity),
                random.randint(-intensity, intensity),
            )
        else:
            self.shake_offset = (0, 0)

        for p in self.particles[:]:
            p.update(dt)
            if p.lifetime <= 0:
                self.particles.remove(p)

        if self.penalty_timer > 0:
            self.penalty_timer -= dt
            return

        self.cursor_y += self.cursor_speed * self.cursor_dir * dt

        if self.cursor_y <= self.rect.top:
            self.cursor_y = self.rect.top
            self.cursor_dir = 1
        elif self.cursor_y >= self.rect.bottom:
            self.cursor_y = self.rect.bottom
            self.cursor_dir = -1

    def attempt_score(self):
        if self.penalty_timer > 0:
            return False

        if self.target_y <= self.cursor_y <= self.target_y + self.target_height:
            self.score += 1
            self.streak += 1
            self.cursor_speed += 20  # Slight speedup per successful hit

            if SETTINGS["particles"]:
                center_x = self.rect.centerx
                center_y = self.target_y + (self.target_height // 2)
                for _ in range(30):
                    self.particles.append(Particle(center_x, center_y, self.color))

            if self.streak >= 3 and self.streak % 3 == 0:
                self.shake_time = 0.2

            self.randomize_target()
            return True
        else:
            self.score -= 1
            if self.score < 0:
                self.score = 0

            self.streak = 0
            self.penalty_timer = 2.0 if SETTINGS["hardcore_penalties"] else 1.0
            self.shake_time = 0.3
            return False

    def draw(self, surface):
        dx, dy = self.shake_offset
        draw_rect = self.rect.move(dx, dy)

        # Draw Bar Background
        if CUSTOM_ASSETS[f"{self.prefix}_bar"]:
            surface.blit(CUSTOM_ASSETS[f"{self.prefix}_bar"], draw_rect)
        else:
            pygame.draw.rect(surface, (40, 40, 50), draw_rect)
            pygame.draw.rect(surface, self.color, draw_rect, 3)

        # Draw Target
        target_rect = pygame.Rect(
            draw_rect.x, self.target_y + dy, draw_rect.width, self.target_height
        )
        if CUSTOM_ASSETS[f"{self.prefix}_target"]:
            surface.blit(CUSTOM_ASSETS[f"{self.prefix}_target"], target_rect)
        else:
            pygame.draw.rect(surface, TARGET_COLOR, target_rect)

        # Draw Particles
        if SETTINGS["particles"]:
            for p in self.particles:
                pygame.draw.rect(surface, p.color, (p.x + dx, p.y + dy, p.size, p.size))

        # Draw Cursor
        cursor_rect = pygame.Rect(
            draw_rect.x - 15, self.cursor_y + dy - 5, draw_rect.width + 30, 10
        )
        if CUSTOM_ASSETS[f"{self.prefix}_cursor"]:
            surface.blit(CUSTOM_ASSETS[f"{self.prefix}_cursor"], cursor_rect)
            if self.penalty_timer > 0:
                red_overlay = pygame.Surface(cursor_rect.size, pygame.SRCALPHA)
                red_overlay.fill((255, 50, 50, 160))
                surface.blit(red_overlay, cursor_rect)
        else:
            color = (255, 50, 50) if self.penalty_timer > 0 else CURSOR_COLOR
            pygame.draw.rect(surface, color, cursor_rect)


def draw_text(surface, text, font, color, x, y, center=True):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(img, rect)


def draw_checkerboard(surface, rect, cell_size=10):
    for y in range(rect.top, rect.bottom, cell_size):
        for x in range(rect.left, rect.right, cell_size):
            color = (180, 180, 180) if ((x // cell_size) + (y // cell_size)) % 2 == 0 else (120, 120, 120)
            pygame.draw.rect(surface, color, (x, y, cell_size, cell_size))


def main():
    state = "MENU"
    mode = 1  # 1 = Career Mode, 2 = Tug-of-War (2P)

    # --- CAREER SAVE DATA & LEVEL SELECT VARIABLES ---
    highest_unlocked_level = load_save()
    career_level = highest_unlocked_level
    selected_level_cursor = highest_unlocked_level

    current_level_data = generate_career_level(career_level)
    game_duration = current_level_data["time_limit"]
    time_left = game_duration
    
    # Tug-of-war variables
    tug_balance = 0
    tug_winner = None

    # Tournament variables
    tournament_mode = False
    p1_wins = 0
    p2_wins = 0
    round_number = 1

    # Settings Menu Navigation
    selected_setting_idx = 0

    bar_width, bar_height = 50, 400
    y_pos = 120
    p1 = PlayerBar(200, y_pos, bar_width, bar_height, P1_COLOR, "p1")
    p2 = PlayerBar(WIDTH - 250, y_pos, bar_width, bar_height, P2_COLOR, "p2")

    # --- DRAWING STUDIO VARIABLES ---
    current_asset_idx = 0
    
    editor_canvases = {}
    for asset, info in ASSET_INFO.items():
        w, h = info["res"]
        editor_canvases[asset] = pygame.Surface((w, h), pygame.SRCALPHA)
        editor_canvases[asset].fill((0, 0, 0, 0))
    
    editor_colors = [
        (255, 255, 255, 255), (255, 50, 50, 255), (50, 255, 50, 255), 
        (50, 50, 255, 255), (255, 255, 50, 255), (0, 255, 255, 255), 
        (255, 100, 200, 255), (150, 75, 0, 255), (0, 0, 0, 255), (0, 0, 0, 0)
    ]
    current_color_idx = 0
    brush_size = 4

    def reset_round():
        nonlocal time_left, p1, p2, tug_balance, tug_winner, game_duration, current_level_data
        if mode == 1:
            current_level_data = generate_career_level(career_level)
            game_duration = current_level_data["time_limit"]
            p1_x = WIDTH // 2 - bar_width // 2
            p1 = PlayerBar(
                p1_x, y_pos, bar_width, bar_height, P1_COLOR, "p1", 
                cursor_speed=current_level_data["cursor_speed"], 
                target_height=current_level_data["target_height"]
            )
        else:
            game_duration = 30.0
            p1 = PlayerBar(200, y_pos, bar_width, bar_height, P1_COLOR, "p1")
            p2 = PlayerBar(WIDTH - 250, y_pos, bar_width, bar_height, P2_COLOR, "p2")

        time_left = game_duration
        tug_balance = 0
        tug_winner = None

    def reset_full_game(selected_mode):
        nonlocal mode, p1_wins, p2_wins, round_number
        mode = selected_mode
        p1_wins = 0
        p2_wins = 0
        round_number = 1
        reset_round()

    while True:
        dt = clock.tick(60) / 1000.0
        mx, my = pygame.mouse.get_pos()
        mb = pygame.mouse.get_pressed()

        active_asset = EDITABLE_KEYS[current_asset_idx]
        native_w, native_h = ASSET_INFO[active_asset]["res"]
        
        max_preview_w, max_preview_h = 450, 350
        scale_factor = min(max_preview_w / native_w, max_preview_h / native_h)
        preview_w = int(native_w * scale_factor)
        preview_h = int(native_h * scale_factor)
        canvas_x = WIDTH // 2 - preview_w // 2
        canvas_y = HEIGHT // 2 - preview_h // 2 + 20

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if state == "MENU":
                    if event.key == pygame.K_1:
                        selected_level_cursor = highest_unlocked_level
                        state = "LEVEL_SELECT"
                    elif event.key == pygame.K_2:
                        reset_full_game(2)
                        state = "GAME"
                    elif event.key == pygame.K_3:
                        state = "CONTROLS"
                    elif event.key in [pygame.K_4, pygame.K_s]:
                        state = "SETTINGS"
                    elif event.key == pygame.K_5:
                        state = "EDITOR"
                    elif event.key == pygame.K_t:
                        tournament_mode = not tournament_mode
                    elif event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

                elif state == "LEVEL_SELECT":
                    if event.key in [pygame.K_ESCAPE, pygame.K_BACKSPACE]:
                        state = "MENU"
                    elif event.key == pygame.K_LEFT:
                        selected_level_cursor = max(1, selected_level_cursor - 1)
                    elif event.key == pygame.K_RIGHT:
                        selected_level_cursor = min(highest_unlocked_level, selected_level_cursor + 1)
                    elif event.key == pygame.K_UP:
                        selected_level_cursor = max(1, selected_level_cursor - 5)
                    elif event.key == pygame.K_DOWN:
                        selected_level_cursor = min(highest_unlocked_level, selected_level_cursor + 5)
                    elif event.key in [pygame.K_SPACE, pygame.K_RETURN]:
                        career_level = selected_level_cursor
                        reset_full_game(1)
                        state = "GAME"

                elif state == "SETTINGS":
                    if event.key in [pygame.K_ESCAPE, pygame.K_BACKSPACE]:
                        state = "MENU"
                    elif event.key == pygame.K_UP:
                        selected_setting_idx = (selected_setting_idx - 1) % len(SETTING_KEYS)
                    elif event.key == pygame.K_DOWN:
                        selected_setting_idx = (selected_setting_idx + 1) % len(SETTING_KEYS)
                    elif event.key in [pygame.K_SPACE, pygame.K_RETURN]:
                        key = SETTING_KEYS[selected_setting_idx]
                        SETTINGS[key] = not SETTINGS[key]

                elif state == "CONTROLS":
                    if event.key in [pygame.K_ESCAPE, pygame.K_SPACE]:
                        state = "MENU"

                elif state == "EDITOR":
                    if event.key == pygame.K_ESCAPE:
                        state = "MENU"
                    elif event.key == pygame.K_UP:
                        current_asset_idx = (current_asset_idx - 1) % len(EDITABLE_KEYS)
                    elif event.key == pygame.K_DOWN:
                        current_asset_idx = (current_asset_idx + 1) % len(EDITABLE_KEYS)
                    elif event.key == pygame.K_LEFT:
                        brush_size = max(1, brush_size - 1)
                    elif event.key == pygame.K_RIGHT:
                        brush_size = min(20, brush_size + 1)
                    elif event.key == pygame.K_c:
                        editor_canvases[active_asset].fill((0, 0, 0, 0))
                    elif event.key == pygame.K_d:
                        file_name = ASSET_INFO[active_asset]["file"]
                        target_dim = ASSET_INFO[active_asset]["dim"]
                        loaded = load_and_scale(file_name, target_dim)
                        if loaded:
                            editor_canvases[active_asset] = pygame.transform.scale(loaded, (native_w, native_h))
                        else:
                            editor_canvases[active_asset].fill((0, 0, 0, 0))
                    elif event.key == pygame.K_s:
                        target_w, target_h = ASSET_INFO[active_asset]["dim"]
                        CUSTOM_ASSETS[active_asset] = pygame.transform.scale(editor_canvases[active_asset], (target_w, target_h))

                elif state == "GAME":
                    if event.key == pygame.K_a:
                        if p1.attempt_score() and mode == 2:
                            power = 1 + (p1.streak // 3)
                            tug_balance -= power
                    if event.key == pygame.K_l and mode == 2:
                        if p2.attempt_score():
                            power = 1 + (p2.streak // 3)
                            tug_balance += power

                elif state in ["LEVEL_CLEAR", "ROUND_OVER", "GAMEOVER", "TOURNAMENT_OVER"]:
                    if event.key == pygame.K_SPACE:
                        if state == "LEVEL_CLEAR":
                            career_level += 1
                            if career_level > highest_unlocked_level:
                                highest_unlocked_level = career_level
                                save_progress(highest_unlocked_level)
                            reset_round()
                            state = "GAME"
                        elif state == "ROUND_OVER":
                            round_number += 1
                            reset_round()
                            state = "GAME"
                        else:
                            reset_full_game(mode)
                            state = "GAME"
                    elif event.key == pygame.K_ESCAPE:
                        state = "MENU"

            if state == "EDITOR" and event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    for i, color in enumerate(editor_colors):
                        px, py = 50 + (i % 2) * 45, 160 + (i // 2) * 40
                        if px <= mx <= px + 35 and py <= my <= py + 35:
                            current_color_idx = i

        # Drawing Logic in Editor
        if state == "EDITOR" and mb[0]:
            if canvas_x <= mx < canvas_x + preview_w and canvas_y <= my < canvas_y + preview_h:
                local_x = int((mx - canvas_x) / scale_factor)
                local_y = int((my - canvas_y) / scale_factor)
                
                selected_col = editor_colors[current_color_idx]
                if selected_col[3] == 0:
                    target_surf = editor_canvases[active_asset]
                    rect_to_clear = pygame.Rect(local_x - brush_size*2, local_y - brush_size*2, brush_size*4, brush_size*4)
                    sub = target_surf.subsurface(rect_to_clear.clip(target_surf.get_rect()))
                    sub.fill((0, 0, 0, 0))
                else:
                    pygame.draw.circle(editor_canvases[active_asset], selected_col, (local_x, local_y), brush_size)

        # --- DRAWING ROUTINES ---
        if state == "MENU":
            screen.fill(MENU_BG_COLOR)
            
            # Indicators
            t_color = TARGET_COLOR if tournament_mode else (150, 150, 150)
            t_status = "ON" if tournament_mode else "OFF"
            draw_text(screen, f"[T] Tournament: {t_status}", font_small, t_color, 20, 20, center=False)
            draw_text(screen, f"Saved Level: {highest_unlocked_level}", font_small, (200, 200, 200), WIDTH - 160, 20, center=False)

            # Main Title
            draw_text(screen, "TIMING CLASH", font_large, TEXT_COLOR, WIDTH // 2, HEIGHT // 3 - 30)
            
            # Menu Items
            draw_text(screen, "[1]  Career Mode (Level Select)", font_medium, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 - 10)
            draw_text(screen, "[2]  Tug-of-War (2P)", font_medium, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 + 35)
            draw_text(screen, "[3]  Controls", font_medium, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 + 80)
            draw_text(screen, "[4]  Settings", font_medium, (255, 220, 100), WIDTH // 2, HEIGHT // 2 + 125)
            draw_text(screen, "[5]  Art Studio", font_medium, (100, 220, 255), WIDTH // 2, HEIGHT // 2 + 170)

        elif state == "LEVEL_SELECT":
            screen.fill(MENU_BG_COLOR)
            draw_text(screen, "CAREER LEVEL SELECT", font_large, TEXT_COLOR, WIDTH // 2, 70)
            draw_text(screen, f"Highest Level Unlocked: {highest_unlocked_level}", font_small, TARGET_COLOR, WIDTH // 2, 115)

            # Level Grid Display (up to max unlocked + 2 locked previews)
            total_display = max(10, ((highest_unlocked_level + 4) // 5) * 5)
            grid_cols = 5
            box_w, box_h = 110, 80
            start_x = WIDTH // 2 - (grid_cols * box_w + (grid_cols - 1) * 20) // 2
            start_y = 160

            for i in range(1, total_display + 1):
                col = (i - 1) % grid_cols
                row = (i - 1) // grid_cols
                bx = start_x + col * (box_w + 20)
                by = start_y + row * (box_h + 15)

                is_unlocked = i <= highest_unlocked_level
                is_selected = i == selected_level_cursor

                # Card Colors
                if is_selected and is_unlocked:
                    border_color = (255, 255, 255)
                    bg_col = (50, 100, 150)
                elif is_unlocked:
                    border_color = (100, 100, 120)
                    bg_col = (30, 30, 40)
                else:
                    border_color = (50, 50, 60)
                    bg_col = (20, 20, 25)

                pygame.draw.rect(screen, bg_col, (bx, by, box_w, box_h), border_radius=8)
                pygame.draw.rect(screen, border_color, (bx, by, box_w, box_h), 3 if is_selected else 1, border_radius=8)

                if is_unlocked:
                    draw_text(screen, f"Lvl {i}", font_medium, TEXT_COLOR, bx + box_w // 2, by + 30)
                    lvl_info = generate_career_level(i)
                    draw_text(screen, f"{lvl_info['target_score']} pts", font_tiny, (180, 180, 180), bx + box_w // 2, by + 58)
                else:
                    draw_text(screen, "LOCKED", font_tiny, (100, 100, 110), bx + box_w // 2, by + box_h // 2)

            # Display selected level info preview
            preview_data = generate_career_level(selected_level_cursor)
            preview_txt = f"Selected: Level {selected_level_cursor}  |  Target: {preview_data['target_score']} pts  |  Time: {int(preview_data['time_limit'])}s  |  Speed: {preview_data['cursor_speed']}px/s"
            draw_text(screen, preview_txt, font_small, (255, 220, 100), WIDTH // 2, HEIGHT - 100)

            draw_text(screen, "ARROWS: Navigate  |  SPACE/ENTER: Play Level  |  ESC: Main Menu", font_tiny, (150, 150, 150), WIDTH // 2, HEIGHT - 50)

        elif state == "SETTINGS":
            screen.fill(MENU_BG_COLOR)
            draw_text(screen, "GAME SETTINGS", font_large, TEXT_COLOR, WIDTH // 2, 80)

            start_y = 200
            for i, key in enumerate(SETTING_KEYS):
                label = SETTING_LABELS[key]
                val = SETTINGS[key]
                
                is_selected = (i == selected_setting_idx)
                color = (255, 255, 255) if is_selected else (140, 140, 150)
                val_text = "[ ON ]" if val else "[ OFF ]"
                val_color = TARGET_COLOR if val else (255, 80, 80)

                prefix = "> " if is_selected else "  "
                draw_text(screen, f"{prefix}{label}", font_medium, color, WIDTH // 2 - 100, start_y + i * 50, center=False)
                draw_text(screen, val_text, font_medium, val_color, WIDTH // 2 + 200, start_y + i * 50, center=False)

            draw_text(screen, "UP/DOWN: Navigate | SPACE/ENTER: Toggle | ESC: Back", font_small, (150, 150, 150), WIDTH // 2, HEIGHT - 80)

        elif state == "CONTROLS":
            screen.fill(MENU_BG_COLOR)
            draw_text(screen, "CONTROLS", font_large, TEXT_COLOR, WIDTH // 2, 100)
            draw_text(screen, "Player 1 Key: [ A ]", font_medium, P1_COLOR, WIDTH // 2, 220)
            draw_text(screen, "Player 2 Key: [ L ]", font_medium, P2_COLOR, WIDTH // 2, 280)
            draw_text(screen, "Wait for the moving line to enter the green box, then press your key!", font_small, TEXT_COLOR, WIDTH // 2, 380)
            draw_text(screen, "Press ESC or SPACE to return", font_small, (150, 150, 150), WIDTH // 2, 520)

        elif state == "EDITOR":
            screen.fill(EDITOR_BG_COLOR)
            
            draw_text(screen, "CUSTOM ART STUDIO", font_medium, TEXT_COLOR, WIDTH // 2, 30)
            draw_text(screen, f"Native Sprite Resolution: {native_w}x{native_h}px", font_tiny, FADED_TEXT_COLOR, WIDTH // 2, 60)
            
            pygame.draw.rect(screen, (30, 30, 40), (30, 100, 110, 440), border_radius=10)
            draw_text(screen, "Palette", font_small, TEXT_COLOR, 85, 125)
            for i, color in enumerate(editor_colors):
                px, py = 50 + (i % 2) * 45, 160 + (i // 2) * 40
                if color[3] == 0:
                    draw_checkerboard(screen, pygame.Rect(px, py, 35, 35), 5)
                    draw_text(screen, "Erase", font_tiny, (150, 150, 150), px + 17, py + 42)
                else:
                    pygame.draw.rect(screen, color, (px, py, 35, 35), border_radius=4)
                
                if i == current_color_idx:
                    pygame.draw.rect(screen, (255, 255, 255), (px - 2, py - 2, 39, 39), 2, border_radius=6)

            draw_text(screen, f"Brush Size: {brush_size}", font_tiny, TEXT_COLOR, 85, 390)
            draw_text(screen, "(Left/Right keys)", font_tiny, (150, 150, 150), 85, 410)

            pygame.draw.rect(screen, (30, 30, 40), (WIDTH - 290, 100, 260, 440), border_radius=10)
            draw_text(screen, "Editing Asset:", font_small, TEXT_COLOR, WIDTH - 160, 130)
            draw_text(screen, f"< {active_asset} >", font_small, P1_COLOR if "p1" in active_asset else P2_COLOR, WIDTH - 160, 170)
            draw_text(screen, "(Use UP/DOWN to swap)", font_tiny, (150, 150, 150), WIDTH - 160, 200)
            
            draw_text(screen, "[ S ] - Save Art to Game", font_small, TARGET_COLOR, WIDTH - 160, 260)
            draw_text(screen, "[ C ] - Clear Canvas", font_small, (255, 150, 100), WIDTH - 160, 310)
            draw_text(screen, "[ D ] - Reset to Default", font_small, (150, 200, 255), WIDTH - 160, 360)
            draw_text(screen, "[ ESC ] - Return to Menu", font_small, TEXT_COLOR, WIDTH - 160, 460)

            canvas_rect = pygame.Rect(canvas_x, canvas_y, preview_w, preview_h)
            pygame.draw.rect(screen, (15, 15, 20), canvas_rect.inflate(20, 20), border_radius=8)
            draw_checkerboard(screen, canvas_rect, cell_size=10)
            
            scaled_preview = pygame.transform.scale(editor_canvases[active_asset], (preview_w, preview_h))
            screen.blit(scaled_preview, canvas_rect.topleft)
            pygame.draw.rect(screen, (100, 100, 120), canvas_rect, 2)

        elif state == "GAME":
            time_left -= dt
            
            round_ended = False
            if mode == 1:
                if p1.score >= current_level_data["target_score"]:
                    state = "LEVEL_CLEAR"
                    if career_level + 1 > highest_unlocked_level:
                        highest_unlocked_level = career_level + 1
                        save_progress(highest_unlocked_level)
                elif time_left <= 0:
                    time_left = 0
                    state = "GAMEOVER"
            else:
                if tug_balance <= -12:
                    tug_winner = "P1 POWER KO WIN!"
                    round_ended = True
                elif tug_balance >= 12:
                    tug_winner = "P2 POWER KO WIN!"
                    round_ended = True
                
                if time_left <= 0 and not round_ended:
                    time_left = 0
                    round_ended = True

                if round_ended:
                    if tournament_mode:
                        round_win = None
                        if tug_winner:
                            round_win = "p1" if "P1" in tug_winner else "p2"
                        else:
                            if tug_balance < 0: round_win = "p1"
                            elif tug_balance > 0: round_win = "p2"
                        
                        if round_win == "p1": p1_wins += 1
                        elif round_win == "p2": p2_wins += 1

                        if p1_wins >= 2 or p2_wins >= 2:
                            state = "TOURNAMENT_OVER"
                        else:
                            state = "ROUND_OVER"
                    else:
                        state = "GAMEOVER"

            if state == "GAME":
                p1.update(dt)
                if mode == 2:
                    p2.update(dt)

            if CUSTOM_ASSETS["background"]:
                screen.blit(CUSTOM_ASSETS["background"], (0, 0))
            else:
                screen.fill(BG_COLOR)

            if tournament_mode and mode == 2:
                draw_text(screen, f"ROUND {round_number}  |  P1 WINS: {p1_wins}   P2 WINS: {p2_wins}", font_small, (200, 200, 100), WIDTH // 2, 20)

            if mode == 1:
                draw_text(screen, current_level_data["title"], font_medium, (255, 200, 100), WIDTH // 2, 30)
                draw_text(screen, f"Target: {p1.score} / {current_level_data['target_score']}", font_small, TEXT_COLOR, WIDTH // 2, 60)
                draw_text(screen, str(p1.score), font_giant, FADED_TEXT_COLOR, (WIDTH // 2 - 220) + p1.shake_offset[0], (HEIGHT // 2 + 50) + p1.shake_offset[1])
            else:
                meter_width = 460
                meter_height = 45
                meter_x = WIDTH // 2 - meter_width // 2
                meter_y = HEIGHT // 2 - 20
                
                pygame.draw.rect(screen, (30, 30, 40), (meter_x, meter_y, meter_width, meter_height), border_radius=6)
                pygame.draw.rect(screen, (80, 80, 100), (meter_x, meter_y, meter_width, meter_height), 2, border_radius=6)
                
                pygame.draw.line(screen, (200, 200, 200), (WIDTH // 2, meter_y - 8), (WIDTH // 2, meter_y + meter_height + 8), 3)
                
                indicator_x = (WIDTH // 2) + int(tug_balance * (meter_width / 26))
                ind_color = TEXT_COLOR
                if tug_balance < 0: ind_color = P1_COLOR
                elif tug_balance > 0: ind_color = P2_COLOR
                    
                pygame.draw.rect(screen, ind_color, (indicator_x - 8, meter_y - 6, 16, meter_height + 12), border_radius=4)
                draw_text(screen, "TUG OF WAR BATTLE", font_medium, FADED_TEXT_COLOR, WIDTH // 2, meter_y - 45)
                
            timer_color = (255, 50, 50) if time_left < 3 else TEXT_COLOR
            timer_y = 90 if mode == 1 else (80 if tournament_mode else 60)
            draw_text(screen, f"{math.ceil(time_left)}s", font_large, timer_color, WIDTH // 2, timer_y)

            p1.draw(screen)
            if mode == 2:
                p2.draw(screen)

            if SETTINGS["show_fps"]:
                fps_text = f"FPS: {int(clock.get_fps())}"
                draw_text(screen, fps_text, font_tiny, (100, 255, 100), WIDTH - 50, 20)

        elif state in ["LEVEL_CLEAR", "GAMEOVER", "ROUND_OVER", "TOURNAMENT_OVER"]:
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(15)
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, 0))

            if state == "LEVEL_CLEAR":
                draw_text(screen, "LEVEL COMPLETED!", font_large, TARGET_COLOR, WIDTH // 2, HEIGHT // 3)
                draw_text(screen, f"Cleared {current_level_data['title']}", font_medium, TEXT_COLOR, WIDTH // 2, HEIGHT // 2)
                draw_text(screen, f"Level {career_level + 1} Unlocked!", font_small, (255, 220, 100), WIDTH // 2, HEIGHT // 2 + 50)
                nav_text = "Press SPACE to Proceed to Next Level  |  ESC for Menu"

            elif state == "TOURNAMENT_OVER":
                title_text = "TOURNAMENT CHAMPION!"
                if p1_wins > p2_wins:
                    winner_txt = "PLAYER 1 WINS THE TOURNAMENT!"
                    w_color = P1_COLOR
                else:
                    winner_txt = "PLAYER 2 WINS THE TOURNAMENT!"
                    w_color = P2_COLOR
                
                draw_text(screen, title_text, font_large, (255, 215, 0), WIDTH // 2, HEIGHT // 3)
                draw_text(screen, winner_txt, font_medium, w_color, WIDTH // 2, HEIGHT // 2)
                draw_text(screen, f"Final Score: {p1_wins} - {p2_wins}", font_medium, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 + 60)
                nav_text = "Press SPACE to Play Again  |  ESC for Menu"

            else:
                title_text = "ROUND OVER!" if state == "ROUND_OVER" else "LEVEL FAILED!" if mode == 1 else "MATCH OVER!"
                draw_text(screen, title_text, font_large, TEXT_COLOR, WIDTH // 2, HEIGHT // 3)

                if mode == 1:
                    draw_text(screen, f"Attempted: Level {career_level}", font_medium, P1_COLOR, WIDTH // 2, HEIGHT // 2)
                    draw_text(screen, f"Score: {p1.score} / {current_level_data['target_score']}", font_small, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 + 50)
                else:
                    if tug_winner:
                        result_text = tug_winner
                        res_color = P1_COLOR if "P1" in tug_winner else P2_COLOR
                    else:
                        if tug_balance < 0:
                            result_text = "Player 1 Wins on Balance!"
                            res_color = P1_COLOR
                        elif tug_balance > 0:
                            result_text = "Player 2 Wins on Balance!"
                            res_color = P2_COLOR
                        else:
                            result_text = "It's a Complete Tie!"
                            res_color = TEXT_COLOR

                    draw_text(screen, result_text, font_medium, res_color, WIDTH // 2, HEIGHT // 2)
                    draw_text(screen, f"Final Tug Balance: {tug_balance}", font_small, TEXT_COLOR, WIDTH // 2, HEIGHT // 2 + 60)

                nav_text = "Press SPACE for Next Round" if state == "ROUND_OVER" else "Press SPACE to Retry  |  ESC for Menu"
            
            draw_text(screen, nav_text, font_small, (150, 150, 150), WIDTH // 2, HEIGHT - 100)

        pygame.display.flip()

if __name__ == "__main__":
    main()