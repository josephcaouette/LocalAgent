import sys
import argparse


class PongGame:
    """Lightweight Pong game logic."""

    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height
        self.left_paddle_y = height // 2
        self.right_paddle_y = height // 2
        self.ball_x = width // 2
        self.ball_y = height // 2
        self.ball_dx = 5
        self.ball_dy = 3
        self.paddle_height = 80
        self.paddle_width = 10
        self.left_score = 0
        self.right_score = 0

    def update(self):
        """Simulate one frame of game logic."""
        self.ball_x += self.ball_dx
        self.ball_y += self.ball_dy

        # Bounce off top and bottom
        if self.ball_y <= 0 or self.ball_y >= self.height:
            self.ball_dy *= -1

        # Bounce off left paddle
        if (self.ball_x <= self.paddle_width and
            self.left_paddle_y - self.paddle_height / 2 <= self.ball_y <= self.left_paddle_y + self.paddle_height / 2):
            self.ball_dx *= -1

        # Bounce off right paddle
        if (self.ball_x >= self.width - self.paddle_width and
            self.right_paddle_y - self.paddle_height / 2 <= self.ball_y <= self.right_paddle_y + self.paddle_height / 2):
            self.ball_dx *= -1

        # Score if ball goes off left or right
        if self.ball_x < 0:
            self.right_score += 1
            self.reset_ball()
        elif self.ball_x > self.width:
            self.left_score += 1
            self.reset_ball()

    def reset_ball(self):
        """Reset ball to center."""
        self.ball_x = self.width // 2
        self.ball_y = self.height // 2
        self.ball_dx = 5 if self.ball_dx >= 0 else -5
        self.ball_dy = 3 if self.ball_dy >= 0 else -3

    def move_paddle(self, side, dy):
        """Move a paddle up or down."""
        if side == 'left':
            self.left_paddle_y += dy
        else:
            self.right_paddle_y += dy

        # Clamp to screen
        min_y = self.paddle_height / 2
        max_y = self.height - self.paddle_height / 2
        if side == 'left':
            self.left_paddle_y = max(min_y, min(max_y, self.left_paddle_y))
        else:
            self.right_paddle_y = max(min_y, min(max_y, self.right_paddle_y))


def run_test():
    """Run automated test mode without GUI."""
    game = PongGame()

    # Simulate 10 frames
    for i in range(10):
        game.update()

    # Verify game state is valid
    assert 0 <= game.ball_x <= game.width, f"Ball x out of bounds: {game.ball_x}"
    assert 0 <= game.ball_y <= game.height, f"Ball y out of bounds: {game.ball_y}"
    assert game.left_score >= 0, "Left score should be non-negative"
    assert game.right_score >= 0, "Right score should be non-negative"

    # Test paddle movement
    game.move_paddle('left', 50)
    game.move_paddle('right', -50)

    # Verify paddle positions are clamped
    min_y = game.paddle_height / 2
    max_y = game.height - game.paddle_height / 2
    assert min_y <= game.left_paddle_y <= max_y, f"Left paddle out of bounds: {game.left_paddle_y}"
    assert min_y <= game.right_paddle_y <= max_y, f"Right paddle out of bounds: {game.right_paddle_y}"

    print("Pong test passed")


def run_game():
    """Run the interactive Pong game using turtle."""
    import turtle

    game = PongGame()

    screen = turtle.Screen()
    screen.title("Pong")
    screen.setup(game.width, game.height)
    screen.bgcolor("black")

    # Create paddles
    left_paddle = turtle.Turtle()
    left_paddle.shape("square")
    left_paddle.color("white")
    left_paddle.penup()
    left_paddle.shapesize(stretch_wide=0.5, stretch_len=4)
    left_paddle.goto(-game.width / 2 + 20, 0)

    right_paddle = turtle.Turtle()
    right_paddle.shape("square")
    right_paddle.color("white")
    right_paddle.penup()
    right_paddle.shapesize(stretch_wide=0.5, stretch_len=4)
    right_paddle.goto(game.width / 2 - 20, 0)

    # Create ball
    ball = turtle.Turtle()
    ball.shape("circle")
    ball.color("white")
    ball.penup()
    ball.goto(0, 0)

    # Score display
    score_left = turtle.Turtle()
    score_left.color("white")
    score_left.penup()
    score_left.hideturtle()
    score_left.goto(-50, 250)
    score_left.write("0", align="center", font=("Courier", 40, "normal"))

    score_right = turtle.Turtle()
    score_right.color("white")
    score_right.penup()
    score_right.hideturtle()
    score_right.goto(50, 250)
    score_right.write("0", align="center", font=("Courier", 40, "normal"))

    def move_left_up():
        game.move_paddle('left', 20)

    def move_left_down():
        game.move_paddle('left', -20)

    def move_right_up():
        game.move_paddle('right', 20)

    def move_right_down():
        game.move_paddle('right', -20)

    screen.listen()
    screen.onkey(move_left_up, "w")
    screen.onkey(move_left_down, "s")
    screen.onkey(move_right_up, "Up")
    screen.onkey(move_right_down, "Down")

    def game_loop():
        game.update()

        # Update ball position
        ball.goto(game.ball_x - game.width / 2, game.ball_y - game.height / 2)

        # Update paddle positions
        left_paddle.goto(-game.width / 2 + 20, game.left_paddle_y - game.height / 2)
        right_paddle.goto(game.width / 2 - 20, game.right_paddle_y - game.height / 2)

        # Update scores
        score_left.clear()
        score_left.write(str(game.left_score), align="center", font=("Courier", 40, "normal"))
        score_right.clear()
        score_right.write(str(game.right_score), align="center", font=("Courier", 40, "normal"))

        screen.ontimer(game_loop, 50)

    game_loop()
    screen.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Pong game")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    args = parser.parse_args()

    if args.test:
        run_test()
        sys.exit(0)
    else:
        run_game()


if __name__ == "__main__":
    main()
