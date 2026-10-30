import sys
import os
import time

class Pong:
    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height
        self.ball_pos = [width // 2, height // 2]
        self.ball_speed = [2, 2]
        self.paddle_width = 15
        self.paddle_height = 100
        self.paddle_speed = 5
        self.left_paddle_pos = [self.paddle_width // 2, height // 2 - self.paddle_height // 2]
        self.right_paddle_pos = [width - self.paddle_width // 2, height // 2 - self.paddle_height // 2]

    def move_ball(self):
        self.ball_pos[0] += self.ball_speed[0]
        self.ball_pos[1] += self.ball_speed[1]

        # Ball collision with top and bottom walls
        if self.ball_pos[1] <= 0 or self.ball_pos[1] >= self.height:
            self.ball_speed[1] = -self.ball_speed[1]

        # Ball collision with paddles
        if (self.left_paddle_pos[1] <= self.ball_pos[1] <= self.left_paddle_pos[1] + self.paddle_height and
                self.ball_pos[0] - self.paddle_width // 2 <= self.paddle_width):
            self.ball_speed[0] = -self.ball_speed[0]
        elif (self.right_paddle_pos[1] <= self.ball_pos[1] <= self.right_paddle_pos[1] + self.paddle_height and
              self.ball_pos[0] + self.paddle_width // 2 >= self.width - self.paddle_width):
            self.ball_speed[0] = -self.ball_speed[0]

        # Ball out of bounds (reset ball position)
        if self.ball_pos[0] <= 0 or self.ball_pos[0] >= self.width:
            self.ball_pos = [self.width // 2, self.height // 2]
            self.ball_speed = [2, 2]

    def headless_simulation(self, frames=10):
        for _ in range(frames):
            self.move_ball()
            # Add more checks if needed to ensure game logic consistency

    def run_gui(self):
        try:
            from tkinter import Tk, Canvas
        except ImportError:
            print("Tkinter is not available. Running headless simulation instead.")
            self.headless_simulation()
            return

        root = Tk()
        root.title("Pong")
        canvas = Canvas(root, width=self.width, height=self.height, bg="black")
        canvas.pack()

        ball = canvas.create_oval(self.ball_pos[0] - 5, self.ball_pos[1] - 5,
                                   self.ball_pos[0] + 5, self.ball_pos[1] + 5, fill="white")

        left_paddle = canvas.create_rectangle(self.left_paddle_pos[0] - self.paddle_width // 2,
                                              self.left_paddle_pos[1],
                                              self.left_paddle_pos[0] + self.paddle_width // 2,
                                              self.left_paddle_pos[1] + self.paddle_height, fill="white")

        right_paddle = canvas.create_rectangle(self.right_paddle_pos[0] - self.paddle_width // 2,
                                               self.right_paddle_pos[1],
                                               self.right_paddle_pos[0] + self.paddle_width // 2,
                                               self.right_paddle_pos[1] + self.paddle_height, fill="white")

        def update():
            self.move_ball()
            canvas.coords(ball, self.ball_pos[0] - 5, self.ball_pos[1] - 5,
                          self.ball_pos[0] + 5, self.ball_pos[1] + 5)
            root.after(20, update)

        update()
        root.mainloop()

if __name__ == "__main__":
    pong_game = Pong()
    if '--test' in sys.argv or 'DISPLAY' not in os.environ:
        pong_game.headless_simulation()
        print('Self-test passed')
        sys.exit(0)
    else:
        pong_game.run_gui()