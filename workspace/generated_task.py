import sys
import time
import random
import os

# Ensure the working directory is set to /workspace/
WORKSPACE_DIR = '/workspace/'
if not os.path.exists(WORKSPACE_DIR):
    print(f"Warning: {WORKSPACE_DIR} does not exist. Using current working directory.")
    WORKSPACE_DIR = os.getcwd()

# Screen dimensions
WIDTH, HEIGHT = 80, 20

# Paddle dimensions
PADDLE_HEIGHT = 5

# Ball dimensions
BALL_SIZE = 1

# Paddle positions
player_paddle_y = HEIGHT // 2 - PADDLE_HEIGHT // 2
opponent_paddle_y = HEIGHT // 2 - PADDLE_HEIGHT // 2

# Ball position and velocity
ball_x = WIDTH // 2
ball_y = HEIGHT // 2
ball_velocity_x = 1 if random.random() > 0.5 else -1
ball_velocity_y = 1 if random.random() > 0.5 else -1

# Score
player_score, opponent_score = 0, 0

def draw_everything():
    os.system('cls' if os.name == 'nt' else 'clear')
    screen = [[' ' for _ in range(WIDTH)] for _ in range(HEIGHT)]
    
    # Draw paddles
    for i in range(PADDLE_HEIGHT):
        screen[player_paddle_y + i][0] = '|'
        screen[opponent_paddle_y + i][WIDTH - 1] = '|'
    
    # Draw ball
    screen[ball_y][ball_x] = 'O'
    
    # Draw scores
    screen[0][WIDTH // 2 - 2] = str(player_score)
    screen[0][WIDTH // 2 + 2] = str(opponent_score)
    
    # Print screen
    for row in screen:
        print(''.join(row))

def reset_ball():
    global ball_x, ball_y, ball_velocity_x
    ball_x = WIDTH // 2
    ball_y = HEIGHT // 2
    ball_velocity_x *= -1

def get_keys():
    # Simulate key presses for demonstration purposes
    # In a real scenario, you would capture actual keyboard input
    import select
    import sys
    import tty
    import termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if rlist:
            return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ''

while True:
    try:
        draw_everything()
        time.sleep(0.1)
        
        # Get keys pressed
        keys = get_keys().strip().lower()
        if 'w' in keys and player_paddle_y > 0:
            player_paddle_y -= 1
        if 's' in keys and player_paddle_y < HEIGHT - PADDLE_HEIGHT:
            player_paddle_y += 1
        
        # Opponent AI
        if opponent_paddle_y + PADDLE_HEIGHT // 2 < ball_y:
            opponent_paddle_y += 1
        if opponent_paddle_y + PADDLE_HEIGHT // 2 > ball_y:
            opponent_paddle_y -= 1
        
        # Ball movement
        ball_x += ball_velocity_x
        ball_y += ball_velocity_y
        
        # Ball collision with top and bottom
        if ball_y <= 0 or ball_y >= HEIGHT - 1:
            ball_velocity_y *= -1
        
        # Ball collision with paddles
        if ball_x == 1 and player_paddle_y <= ball_y < player_paddle_y + PADDLE_HEIGHT:
            ball_velocity_x *= -1
        if ball_x == WIDTH - 2 and opponent_paddle_y <= ball_y < opponent_paddle_y + PADDLE_HEIGHT:
            ball_velocity_x *= -1
        
        # Ball out of bounds
        if ball_x <= 0:
            opponent_score += 1
            reset_ball()
        if ball_x >= WIDTH - 1:
            player_score += 1
            reset_ball()
    
    except KeyboardInterrupt:
        print("\nGame Over!")
        print(f"Final Score: Player {player_score} - {opponent_score} Opponent")
        break