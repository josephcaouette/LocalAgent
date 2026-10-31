"""Pong game with pygame rendering and a headless logic test mode."""

import sys


class Pong:
    """Pygame-independent Pong game logic."""

    WIN_SCORE = 5
    BALL_RADIUS = 5
    PADDLE_WIDTH = 15
    PADDLE_HEIGHT = 100
    PADDLE_SPEED = 5
    MAX_BALL_SPEED = 14.0
    SPEED_INCREASE = 1.1

    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height

        self.ball_pos = [width // 2, height // 2]
        self.ball_speed = [2.0, 2.0]

        self.left_paddle_pos = [20, height // 2]
        self.right_paddle_pos = [width - 20, height // 2]

        self.left_score = 0
        self.right_score = 0
        self.winner = None

    def reset(self):
        """Reset the full game state."""
        self.left_score = 0
        self.right_score = 0
        self.winner = None
        self.left_paddle_pos = [20, self.height // 2]
        self.right_paddle_pos = [self.width - 20, self.height // 2]
        self._reset_ball(1)

    def _reset_ball(self, direction=1):
        """Reset ball position and speed after a point."""
        self.ball_pos = [self.width // 2, self.height // 2]
        self.ball_speed = [2.0 * direction, 2.0]

    def _clamp_paddle_y(self, paddle):
        """Keep a paddle fully inside the playfield."""
        min_y = self.PADDLE_HEIGHT / 2
        max_y = self.height - self.PADDLE_HEIGHT / 2
        paddle[1] = max(min_y, min(max_y, paddle[1]))

    def _cap_ball_speed(self):
        """Limit ball speed so the game remains playable."""
        dx, dy = self.ball_speed
        speed = (dx * dx + dy * dy) ** 0.5
        if speed > self.MAX_BALL_SPEED:
            scale = self.MAX_BALL_SPEED / speed
            self.ball_speed = [dx * scale, dy * scale]

    def move_player(self, player_input=0):
        """Move the left paddle.

        player_input:
            -1 = up
             0 = no movement
             1 = down
        """
        if self.winner is not None:
            return

        self.left_paddle_pos[1] += player_input * self.PADDLE_SPEED
        self._clamp_paddle_y(self.left_paddle_pos)

    def move_ai(self):
        """Move the right paddle toward the ball."""
        if self.winner is not None:
            return

        target_y = self.ball_pos[1]
        current_y = self.right_paddle_pos[1]

        if current_y < target_y:
            self.right_paddle_pos[1] = min(target_y, current_y + self.PADDLE_SPEED)
        elif current_y > target_y:
            self.right_paddle_pos[1] = max(target_y, current_y - self.PADDLE_SPEED)

        self._clamp_paddle_y(self.right_paddle_pos)

    def _bounce_off_walls(self):
        """Bounce the ball off the top and bottom walls."""
        if self.ball_pos[1] - self.BALL_RADIUS <= 0:
            self.ball_pos[1] = self.BALL_RADIUS
            self.ball_speed[1] = abs(self.ball_speed[1])
        elif self.ball_pos[1] + self.BALL_RADIUS >= self.height:
            self.ball_pos[1] = self.height - self.BALL_RADIUS
            self.ball_speed[1] = -abs(self.ball_speed[1])

    def _collides_with_left_paddle(self):
        """Return True when the ball overlaps the left paddle while moving left."""
        if self.ball_speed[0] >= 0:
            return False

        paddle_x, paddle_y = self.left_paddle_pos
        ball_x, ball_y = self.ball_pos

        if ball_x + self.BALL_RADIUS < paddle_x - self.PADDLE_WIDTH / 2:
            return False
        if ball_x - self.BALL_RADIUS > paddle_x + self.PADDLE_WIDTH / 2:
            return False
        if ball_y < paddle_y - self.PADDLE_HEIGHT / 2 - self.BALL_RADIUS:
            return False
        if ball_y > paddle_y + self.PADDLE_HEIGHT / 2 + self.BALL_RADIUS:
            return False

        return True

    def _collides_with_right_paddle(self):
        """Return True when the ball overlaps the right paddle while moving right."""
        if self.ball_speed[0] <= 0:
            return False

        paddle_x, paddle_y = self.right_paddle_pos
        ball_x, ball_y = self.ball_pos

        if ball_x - self.BALL_RADIUS > paddle_x + self.PADDLE_WIDTH / 2:
            return False
        if ball_x + self.BALL_RADIUS < paddle_x - self.PADDLE_WIDTH / 2:
            return False
        if ball_y < paddle_y - self.PADDLE_HEIGHT / 2 - self.BALL_RADIUS:
            return False
        if ball_y > paddle_y + self.PADDLE_HEIGHT / 2 + self.BALL_RADIUS:
            return False

        return True

    def move_ball(self):
        """Advance the ball and handle wall/paddle collisions."""
        if self.winner is not None:
            return

        self.ball_pos[0] += self.ball_speed[0]
        self.ball_pos[1] += self.ball_speed[1]

        self._bounce_off_walls()

        if self._collides_with_left_paddle():
            paddle_x, _ = self.left_paddle_pos
            self.ball_pos[0] = paddle_x + self.PADDLE_WIDTH / 2 + self.BALL_RADIUS
            self.ball_speed[0] = abs(self.ball_speed[0]) * self.SPEED_INCREASE
            self._cap_ball_speed()

        elif self._collides_with_right_paddle():
            paddle_x, _ = self.right_paddle_pos
            self.ball_pos[0] = paddle_x - self.PADDLE_WIDTH / 2 - self.BALL_RADIUS
            self.ball_speed[0] = -abs(self.ball_speed[0]) * self.SPEED_INCREASE
            self._cap_ball_speed()

        if self.ball_pos[0] + self.BALL_RADIUS < 0:
            self.right_score += 1
            self._after_score(1)
        elif self.ball_pos[0] - self.BALL_RADIUS > self.width:
            self.left_score += 1
            self._after_score(-1)

    def _after_score(self, next_direction):
        """Check for a winner and reset the ball if the game continues."""
        if self.left_score >= self.WIN_SCORE:
            self.winner = "left"
            return
        if self.right_score >= self.WIN_SCORE:
            self.winner = "right"
            return

        self._reset_ball(next_direction)

    def update(self, player_input=0):
        """Run one full frame of game logic."""
        if self.winner is not None:
            return

        self.move_player(player_input)
        self.move_ai()
        self.move_ball()


def run_test():
    """Run exactly 100 headless logic frames and print the required result."""
    game = Pong()

    for _ in range(100):
        game.update(0)

    # Internal sanity checks. On failure, exit non-zero without extra stdout.
    if game.winner is not None:
        return 1

    if not (0 <= game.ball_pos[0] <= game.width):
        return 1
    if not (0 <= game.ball_pos[1] <= game.height):
        return 1
    if game.left_score < 0 or game.right_score < 0:
        return 1
    if game.left_score >= game.WIN_SCORE or game.right_score >= game.WIN_SCORE:
        return 1

    min_y = game.PADDLE_HEIGHT / 2
    max_y = game.height - game.PADDLE_HEIGHT / 2
    if not (min_y <= game.left_paddle_pos[1] <= max_y):
        return 1
    if not (min_y <= game.right_paddle_pos[1] <= max_y):
        return 1

    print("PASS: Logic verified")
    return 0


def run_gui():
    """Run the pygame-based interactive game."""
    try:
        import pygame
    except Exception as exc:
        print(f"pygame is required for the GUI: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        pygame.init()
        screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Pong")
    except Exception as exc:
        print(f"Could not initialize pygame display: {exc}", file=sys.stderr)
        sys.exit(1)

    clock = pygame.time.Clock()
    font_large = pygame.font.SysFont(None, 72)
    font_small = pygame.font.SysFont(None, 36)

    game = Pong(800, 600)
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r and game.winner is not None:
                    game.reset()

        player_input = 0
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            player_input -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            player_input += 1

        game.update(player_input)

        screen.fill((0, 0, 0))

        # Center line.
        for y in range(0, game.height, 20):
            pygame.draw.rect(screen, (80, 80, 80), (game.width // 2 - 2, y, 4, 10))

        # Ball.
        pygame.draw.circle(
            screen,
            (255, 255, 255),
            (game.ball_pos[0], game.ball_pos[1]),
            game.BALL_RADIUS,
        )

        # Left paddle.
        left_x, left_y = game.left_paddle_pos
        pygame.draw.rect(
            screen,
            (255, 255, 255),
            (
                left_x - game.PADDLE_WIDTH / 2,
                left_y - game.PADDLE_HEIGHT / 2,
                game.PADDLE_WIDTH,
                game.PADDLE_HEIGHT,
            ),
        )

        # Right paddle.
        right_x, right_y = game.right_paddle_pos
        pygame.draw.rect(
            screen,
            (255, 255, 255),
            (
                right_x - game.PADDLE_WIDTH / 2,
                right_y - game.PADDLE_HEIGHT / 2,
                game.PADDLE_WIDTH,
                game.PADDLE_HEIGHT,
            ),
        )

        # Score.
        score_text = font_large.render(
            f"{game.left_score}   {game.right_score}",
            True,
            (255, 255, 255),
        )
        score_rect = score_text.get_rect(midtop=(game.width // 2, 20))
        screen.blit(score_text, score_rect)

        if game.winner is not None:
            winner_text = "You win!" if game.winner == "left" else "AI wins"
            restart_text = "Press R to restart or ESC to exit"
            win_surf = font_large.render(winner_text, True, (255, 255, 255))
            restart_surf = font_small.render(restart_text, True, (200, 200, 200))

            win_rect = win_surf.get_rect(center=(game.width // 2, game.height // 2 - 30))
            restart_rect = restart_surf.get_rect(center=(game.width // 2, game.height // 2 + 30))
            screen.blit(win_surf, win_rect)
            screen.blit(restart_surf, restart_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(run_test())
    else:
        run_gui()
