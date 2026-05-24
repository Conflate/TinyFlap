from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from array import array
import math
from pathlib import Path
import random
import sys

import pygame


BASE_DIR = Path(__file__).parent
APP_NAME = "Tiny Flap"
DATA_DIR = Path.home() / ".tiny_flap"
HIGH_SCORE_FILE = DATA_DIR / "high_score.txt"

WINDOW_WIDTH = 288
WINDOW_HEIGHT = 512
FPS = 60

BIRD_START_X = 58
BIRD_START_Y = 220
BIRD_SIZE = (34, 24)
BIRD_COLLISION_INSET = 4

GRAVITY = 0.42
JUMP_STRENGTH = 7.7
MAX_FALL_SPEED = 9.5

PIPE_WIDTH = 54
PIPE_HEIGHT = 320
PIPE_GAP = 140
PIPE_SPACING = 170
PIPE_SPEED_START = 2.7
PIPE_SPEED_STEP = 0.035
PIPE_SPEED_MAX = 4.4
PIPE_MARGIN = 72

GROUND_HEIGHT = 64
SKY_COLOR = (112, 197, 206)
WHITE = (255, 255, 255)
BLACK = (23, 24, 28)
DARK_GREEN = (73, 98, 46)
GREEN = (93, 188, 70)
LIGHT_GREEN = (139, 222, 104)
YELLOW = (248, 207, 76)
ORANGE = (232, 139, 54)
RED = (214, 74, 63)
BROWN = (221, 190, 116)
SAND = (236, 217, 146)
SKY_TOP = (91, 184, 218)
SKY_BOTTOM = (159, 224, 218)
HILL_BACK = (124, 198, 134)
HILL_FRONT = (90, 174, 103)
PANEL_FILL = (248, 240, 204)
PANEL_EDGE = (87, 66, 47)

SAMPLE_RATE = 44100
VOLUME = 0.22
SCORE_POP_FRAMES = 16
CRASH_SHAKE_FRAMES = 18
CRASH_FLASH_FRAMES = 12


class GameState(Enum):
    HOME = auto()
    PLAYING = auto()
    GAME_OVER = auto()
    PAUSED = auto()


@dataclass
class Pipe:
    x: float
    gap_center: int
    gap_size: int = PIPE_GAP
    scored: bool = False

    @property
    def top_rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(self.x),
            0,
            PIPE_WIDTH,
            self.gap_center - self.gap_size // 2,
        )

    @property
    def bottom_rect(self) -> pygame.Rect:
        bottom_y = self.gap_center + self.gap_size // 2
        return pygame.Rect(
            int(self.x),
            bottom_y,
            PIPE_WIDTH,
            WINDOW_HEIGHT - GROUND_HEIGHT - bottom_y,
        )

    @property
    def passed_x(self) -> float:
        return self.x + PIPE_WIDTH

    def move(self, speed: float) -> None:
        self.x -= speed

    def is_offscreen(self) -> bool:
        return self.passed_x < 0


class Bird:
    def __init__(self, images: list[pygame.Surface]) -> None:
        self.images = images
        self.image = images[0]
        self.reset()

    def reset(self) -> None:
        self.x = BIRD_START_X
        self.y = BIRD_START_Y
        self.velocity = 0.0
        self.rotation = 0
        self.frame = 0
        self.frame_time = 0
        self.image = self.images[0]

    @property
    def rect(self) -> pygame.Rect:
        return self.image.get_rect(topleft=(int(self.x), int(self.y)))

    @property
    def collision_rect(self) -> pygame.Rect:
        return self.rect.inflate(-BIRD_COLLISION_INSET * 2, -BIRD_COLLISION_INSET * 2)

    def flap(self) -> None:
        self.velocity = -JUMP_STRENGTH
        self.frame = 0
        self.frame_time = 0

    def update(self) -> None:
        self.velocity = min(self.velocity + GRAVITY, MAX_FALL_SPEED)
        self.y += self.velocity
        self.rotation = max(-70, min(25, int(-self.velocity * 4)))
        self.animate()

    def idle(self, frame_count: int) -> None:
        self.y = BIRD_START_Y + math.sin(frame_count * 0.07) * 5
        self.rotation = int(math.sin(frame_count * 0.05) * 5)
        self.animate()

    def animate(self) -> None:
        self.frame_time += 1
        if self.frame_time >= 5:
            self.frame_time = 0
            self.frame = (self.frame + 1) % len(self.images)
        self.image = self.images[self.frame]

    def draw(self, surface: pygame.Surface) -> None:
        shadow_rect = pygame.Rect(int(self.x) + 5, int(self.y) + 17, BIRD_SIZE[0] - 6, 8)
        pygame.draw.ellipse(surface, (65, 112, 116), shadow_rect)
        rotated = pygame.transform.rotate(self.image, self.rotation)
        rotated_rect = rotated.get_rect(center=self.rect.center)
        surface.blit(rotated, rotated_rect)


class Game:
    def __init__(self) -> None:
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 256)
        pygame.init()
        pygame.display.set_caption(APP_NAME)
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.canvas = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT)).convert()
        self.clock = pygame.time.Clock()
        self.has_custom_background = (BASE_DIR / "background.png").exists()
        self.assets = self.load_assets()
        self.assets["top_pipe"] = pygame.transform.flip(self.assets["pipe"], False, True)
        self.sounds = self.load_sounds()
        self.font_large = pygame.font.Font(None, 42)
        self.font_medium = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 20)
        self.bird = Bird(self.assets["bird_frames"])
        self.pipes: list[Pipe] = []
        self.score = 0
        self.best_score = self.load_best_score()
        self.speed = PIPE_SPEED_START
        self.state = GameState.HOME
        self.ground_offset = 0.0
        self.frame_count = 0
        self.score_pop_timer = 0
        self.shake_timer = 0
        self.flash_timer = 0
        self.clouds = [
            {"x": 26.0, "y": 74, "scale": 0.85, "speed": 0.18},
            {"x": 156.0, "y": 48, "scale": 1.05, "speed": 0.13},
            {"x": 236.0, "y": 123, "scale": 0.72, "speed": 0.21},
        ]

    def load_assets(self) -> dict[str, pygame.Surface]:
        has_custom_bird = (BASE_DIR / "bird.png").exists()
        bird_image = self.load_image(
            "bird.png",
            BIRD_SIZE,
            self.create_bird_surface(0),
            alpha=True,
        )
        return {
            "background": self.load_image(
                "background.png",
                (WINDOW_WIDTH, WINDOW_HEIGHT),
                self.create_background(),
                alpha=False,
            ),
            "bird_frames": self.create_bird_frames(bird_image, has_custom_bird),
            "pipe": self.load_image(
                "pipe.png",
                (PIPE_WIDTH, PIPE_HEIGHT),
                self.create_pipe_surface(),
                alpha=True,
            ),
        }

    def load_image(
        self,
        filename: str,
        size: tuple[int, int],
        fallback: pygame.Surface,
        *,
        alpha: bool,
    ) -> pygame.Surface:
        path = BASE_DIR / filename
        try:
            image = pygame.image.load(path)
            image = image.convert_alpha() if alpha else image.convert()
            return pygame.transform.smoothscale(image, size)
        except (FileNotFoundError, pygame.error):
            return fallback

    def create_background(self) -> pygame.Surface:
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT)).convert()
        for y in range(WINDOW_HEIGHT):
            blend = y / WINDOW_HEIGHT
            color = tuple(
                int(SKY_TOP[index] * (1 - blend) + SKY_BOTTOM[index] * blend)
                for index in range(3)
            )
            pygame.draw.line(surface, color, (0, y), (WINDOW_WIDTH, y))

        ground_top = WINDOW_HEIGHT - GROUND_HEIGHT
        for x in range(-80, WINDOW_WIDTH + 120, 86):
            pygame.draw.circle(surface, HILL_BACK, (x, ground_top + 28), 74)
        for x in range(-50, WINDOW_WIDTH + 120, 72):
            pygame.draw.circle(surface, HILL_FRONT, (x, ground_top + 42), 58)

        return surface

    def create_bird_frames(
        self,
        base_image: pygame.Surface,
        has_custom_bird: bool,
    ) -> list[pygame.Surface]:
        if has_custom_bird:
            return [base_image]
        return [
            self.create_bird_surface(-5),
            self.create_bird_surface(0),
            self.create_bird_surface(5),
            self.create_bird_surface(0),
        ]

    def create_bird_surface(self, wing_offset: int) -> pygame.Surface:
        surface = pygame.Surface(BIRD_SIZE, pygame.SRCALPHA)
        pygame.draw.ellipse(surface, (184, 145, 42, 85), (1, 7, 28, 18))
        pygame.draw.ellipse(surface, YELLOW, (2, 3, 27, 18))
        pygame.draw.ellipse(surface, (255, 229, 107), (7, 5, 15, 8))
        pygame.draw.ellipse(surface, ORANGE, (7, 11 + wing_offset, 17, 10))
        pygame.draw.arc(surface, BLACK, (7, 11 + wing_offset, 17, 10), 0.1, 3.0, 2)
        pygame.draw.polygon(surface, RED, [(27, 9), (34, 12), (27, 15)])
        pygame.draw.line(surface, BLACK, (28, 12), (33, 12), 1)
        pygame.draw.circle(surface, WHITE, (23, 8), 5)
        pygame.draw.circle(surface, BLACK, (25, 8), 2)
        pygame.draw.arc(surface, BLACK, (2, 4, 26, 17), 0.2, 5.5, 2)
        return surface.convert_alpha()

    def create_pipe_surface(self) -> pygame.Surface:
        surface = pygame.Surface((PIPE_WIDTH, PIPE_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(surface, (46, 122, 52, 90), (9, 26, PIPE_WIDTH - 4, PIPE_HEIGHT - 26))
        pygame.draw.rect(surface, GREEN, (6, 25, PIPE_WIDTH - 12, PIPE_HEIGHT - 25))
        pygame.draw.rect(surface, LIGHT_GREEN, (11, 30, 10, PIPE_HEIGHT - 35))
        pygame.draw.rect(surface, (76, 163, 61), (PIPE_WIDTH - 17, 29, 7, PIPE_HEIGHT - 36))
        pygame.draw.rect(surface, DARK_GREEN, (6, 25, PIPE_WIDTH - 12, PIPE_HEIGHT - 25), 3)
        pygame.draw.rect(surface, (111, 207, 82), (0, 0, PIPE_WIDTH, 31), border_radius=4)
        pygame.draw.rect(surface, LIGHT_GREEN, (8, 5, 12, 20), border_radius=3)
        pygame.draw.rect(surface, (74, 164, 61), (PIPE_WIDTH - 15, 5, 8, 21), border_radius=2)
        pygame.draw.rect(surface, DARK_GREEN, (0, 0, PIPE_WIDTH, 31), 3, border_radius=4)
        return surface.convert_alpha()

    def load_sounds(self) -> dict[str, pygame.mixer.Sound | None]:
        if pygame.mixer.get_init() is None:
            return {"flap": None, "score": None, "crash": None}

        try:
            return {
                "flap": self.create_tone(520, 0.055),
                "score": self.create_tone(820, 0.08),
                "crash": self.create_tone(120, 0.16),
            }
        except pygame.error:
            return {"flap": None, "score": None, "crash": None}

    def create_tone(self, frequency: int, duration: float) -> pygame.mixer.Sound:
        samples = int(SAMPLE_RATE * duration)
        wave = array("h")
        for sample in range(samples):
            fade = 1 - sample / samples
            value = int(
                32767
                * VOLUME
                * fade
                * math.sin(2 * math.pi * frequency * sample / SAMPLE_RATE)
            )
            wave.append(value)
        return pygame.mixer.Sound(buffer=wave.tobytes())

    def play_sound(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def load_best_score(self) -> int:
        try:
            return int(HIGH_SCORE_FILE.read_text(encoding="utf-8").strip() or "0")
        except (FileNotFoundError, ValueError):
            return 0

    def save_best_score(self) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        HIGH_SCORE_FILE.write_text(str(self.best_score), encoding="utf-8")

    def reset_round(self) -> None:
        self.bird.reset()
        self.pipes.clear()
        self.score = 0
        self.speed = PIPE_SPEED_START
        self.add_pipe(WINDOW_WIDTH + 70)

    def start_game(self) -> None:
        self.reset_round()
        self.bird.flap()
        self.play_sound("flap")
        self.state = GameState.PLAYING

    def end_game(self) -> None:
        if self.score > self.best_score:
            self.best_score = self.score
            self.save_best_score()
        self.play_sound("crash")
        self.shake_timer = CRASH_SHAKE_FRAMES
        self.flash_timer = CRASH_FLASH_FRAMES
        self.state = GameState.GAME_OVER

    def add_pipe(self, x: float | None = None) -> None:
        last_center = self.pipes[-1].gap_center if self.pipes else WINDOW_HEIGHT // 2
        min_center = PIPE_MARGIN
        max_center = WINDOW_HEIGHT - GROUND_HEIGHT - PIPE_MARGIN
        drift = random.randint(-85, 85)
        gap_center = max(min_center, min(max_center, last_center + drift))
        pipe_x = x if x is not None else self.pipes[-1].x + PIPE_SPACING
        self.pipes.append(Pipe(pipe_x, gap_center))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if event.type != pygame.KEYDOWN and event.type != pygame.MOUSEBUTTONDOWN:
            return

        key = event.key if event.type == pygame.KEYDOWN else None

        if key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit()

        if key == pygame.K_p and self.state in {GameState.PLAYING, GameState.PAUSED}:
            self.state = GameState.PAUSED if self.state == GameState.PLAYING else GameState.PLAYING
            return

        wants_flap = event.type == pygame.MOUSEBUTTONDOWN or key == pygame.K_SPACE
        if not wants_flap:
            return

        if self.state in {GameState.HOME, GameState.GAME_OVER}:
            self.start_game()
        elif self.state == GameState.PLAYING:
            self.bird.flap()
            self.play_sound("flap")

    def update(self) -> None:
        self.frame_count += 1
        self.ground_offset = (self.ground_offset + self.speed) % 18
        self.score_pop_timer = max(0, self.score_pop_timer - 1)
        self.shake_timer = max(0, self.shake_timer - 1)
        self.flash_timer = max(0, self.flash_timer - 1)

        if self.state == GameState.HOME:
            self.bird.idle(self.frame_count)

        if self.state != GameState.PLAYING:
            return

        self.bird.update()

        for pipe in self.pipes:
            pipe.move(self.speed)

        self.pipes = [pipe for pipe in self.pipes if not pipe.is_offscreen()]
        if not self.pipes or self.pipes[-1].x <= WINDOW_WIDTH - PIPE_SPACING:
            self.add_pipe()

        self.update_score()

        if self.check_collision():
            self.end_game()

    def update_score(self) -> None:
        for pipe in self.pipes:
            if not pipe.scored and pipe.passed_x < self.bird.x:
                pipe.scored = True
                self.score += 1
                self.score_pop_timer = SCORE_POP_FRAMES
                self.play_sound("score")
                self.speed = min(PIPE_SPEED_MAX, PIPE_SPEED_START + self.score * PIPE_SPEED_STEP)

    def check_collision(self) -> bool:
        bird_rect = self.bird.collision_rect
        if bird_rect.top <= 0 or bird_rect.bottom >= WINDOW_HEIGHT - GROUND_HEIGHT:
            return True

        for pipe in self.pipes:
            if bird_rect.colliderect(pipe.top_rect) or bird_rect.colliderect(pipe.bottom_rect):
                return True

        return False

    def draw(self) -> None:
        self.draw_background()
        self.draw_pipes()
        self.bird.draw(self.canvas)
        self.draw_ground()
        self.draw_hud()
        self.draw_flash()

        self.screen.fill(BLACK)
        self.screen.blit(self.canvas, self.shake_offset())
        pygame.display.flip()

    def draw_background(self) -> None:
        self.canvas.blit(self.assets["background"], (0, 0))
        if self.has_custom_background:
            return

        self.draw_hills()
        for cloud in self.clouds:
            x = (cloud["x"] - self.frame_count * cloud["speed"]) % (WINDOW_WIDTH + 90) - 45
            self.draw_cloud(int(x), cloud["y"], cloud["scale"])

    def draw_hills(self) -> None:
        ground_top = WINDOW_HEIGHT - GROUND_HEIGHT
        back_offset = -int((self.frame_count * 0.18) % 86)
        front_offset = -int((self.frame_count * 0.34) % 72)

        for x in range(back_offset - 86, WINDOW_WIDTH + 120, 86):
            pygame.draw.circle(self.canvas, HILL_BACK, (x, ground_top + 30), 74)
            pygame.draw.circle(self.canvas, (147, 216, 143), (x - 22, ground_top + 5), 18)
        for x in range(front_offset - 72, WINDOW_WIDTH + 120, 72):
            pygame.draw.circle(self.canvas, HILL_FRONT, (x, ground_top + 46), 58)

    def draw_cloud(self, x: int, y: int, scale: float) -> None:
        width = int(54 * scale)
        height = int(20 * scale)
        color = (255, 255, 255)
        shade = (227, 246, 242)
        pygame.draw.ellipse(self.canvas, shade, (x + 2, y + 4, width, height))
        pygame.draw.ellipse(self.canvas, color, (x, y + 5, width, height))
        pygame.draw.ellipse(
            self.canvas,
            color,
            (x + int(12 * scale), y - int(3 * scale), width // 2, height + 4),
        )
        pygame.draw.ellipse(
            self.canvas,
            color,
            (x + int(28 * scale), y + int(1 * scale), width // 2, height),
        )

    def draw_pipes(self) -> None:
        pipe_image = self.assets["pipe"]
        top_pipe = self.assets["top_pipe"]

        for pipe in self.pipes:
            top_y = pipe.top_rect.bottom - PIPE_HEIGHT
            shadow_x = int(pipe.x) + 5
            pygame.draw.rect(
                self.canvas,
                (42, 103, 57, 80),
                (shadow_x, 0, PIPE_WIDTH, pipe.top_rect.height),
            )
            pygame.draw.rect(
                self.canvas,
                (42, 103, 57, 80),
                (shadow_x, pipe.bottom_rect.top, PIPE_WIDTH, pipe.bottom_rect.height),
            )
            self.canvas.blit(top_pipe, (int(pipe.x), top_y))
            self.canvas.blit(pipe_image, (int(pipe.x), pipe.bottom_rect.top))

    def draw_ground(self) -> None:
        ground_top = WINDOW_HEIGHT - GROUND_HEIGHT
        pygame.draw.rect(self.canvas, SAND, (0, ground_top, WINDOW_WIDTH, GROUND_HEIGHT))
        pygame.draw.rect(self.canvas, (112, 185, 82), (0, ground_top - 6, WINDOW_WIDTH, 8))
        pygame.draw.rect(self.canvas, BROWN, (0, ground_top, WINDOW_WIDTH, 8))
        start_x = -int(self.ground_offset)
        for x in range(start_x, WINDOW_WIDTH + 18, 18):
            pygame.draw.rect(self.canvas, (212, 195, 119), (x, ground_top + 18, 9, 5))
            pygame.draw.line(
                self.canvas,
                (173, 143, 84),
                (x + 3, ground_top + 40),
                (x + 12, ground_top + 40),
                1,
            )

    def draw_hud(self) -> None:
        self.draw_score()

        if self.state == GameState.HOME:
            self.draw_text(APP_NAME, self.font_large, BLACK, (WINDOW_WIDTH // 2, 150))
            self.draw_text(
                "Space or click to start",
                self.font_medium,
                BLACK,
                (WINDOW_WIDTH // 2, 205),
            )
            self.draw_text("P pauses   Esc quits", self.font_small, BLACK, (WINDOW_WIDTH // 2, 238))
        elif self.state == GameState.GAME_OVER:
            self.draw_panel(
                "Game Over",
                f"Score {self.score}   Best {self.best_score}",
                "Space or click to retry",
            )
        elif self.state == GameState.PAUSED:
            self.draw_panel("Paused", f"Score {self.score}", "Press P to resume")

    def draw_panel(self, title: str, subtitle: str, prompt: str) -> None:
        panel = pygame.Rect(24, 156, WINDOW_WIDTH - 48, 138)
        shadow = panel.move(3, 4)
        pygame.draw.rect(self.canvas, (80, 74, 65, 110), shadow, border_radius=8)
        pygame.draw.rect(self.canvas, PANEL_FILL, panel, border_radius=8)
        pygame.draw.rect(self.canvas, PANEL_EDGE, panel, 3, border_radius=8)
        self.draw_text(title, self.font_large, BLACK, (WINDOW_WIDTH // 2, panel.y + 35))
        self.draw_text(subtitle, self.font_medium, BLACK, (WINDOW_WIDTH // 2, panel.y + 76))
        self.draw_text(prompt, self.font_small, BLACK, (WINDOW_WIDTH // 2, panel.y + 110))

    def draw_score(self) -> None:
        text_surface = self.font_large.render(str(self.score), True, WHITE)
        if self.score_pop_timer:
            scale = 1 + 0.28 * self.score_pop_timer / SCORE_POP_FRAMES
            size = (
                int(text_surface.get_width() * scale),
                int(text_surface.get_height() * scale),
            )
            text_surface = pygame.transform.smoothscale(text_surface, size)

        text_rect = text_surface.get_rect(center=(WINDOW_WIDTH // 2, 44))
        shadow_surface = self.font_large.render(str(self.score), True, BLACK)
        if self.score_pop_timer:
            shadow_surface = pygame.transform.smoothscale(shadow_surface, text_surface.get_size())
        shadow_rect = shadow_surface.get_rect(center=(WINDOW_WIDTH // 2 + 2, 46))
        self.canvas.blit(shadow_surface, shadow_rect)
        self.canvas.blit(text_surface, text_rect)

    def draw_flash(self) -> None:
        if self.flash_timer == 0:
            return
        alpha = int(110 * self.flash_timer / CRASH_FLASH_FRAMES)
        flash = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 255, 255, alpha))
        self.canvas.blit(flash, (0, 0))

    def shake_offset(self) -> tuple[int, int]:
        if self.shake_timer == 0:
            return (0, 0)
        strength = max(1, int(4 * self.shake_timer / CRASH_SHAKE_FRAMES))
        return (random.randint(-strength, strength), random.randint(-strength, strength))

    def draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        center: tuple[int, int],
        *,
        shadow: bool = False,
    ) -> None:
        if shadow:
            shadow_surface = font.render(text, True, BLACK)
            shadow_rect = shadow_surface.get_rect(center=(center[0] + 2, center[1] + 2))
            self.canvas.blit(shadow_surface, shadow_rect)

        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=center)
        self.canvas.blit(text_surface, text_rect)

    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                self.handle_event(event)

            self.update()
            self.draw()
            self.clock.tick(FPS)


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
