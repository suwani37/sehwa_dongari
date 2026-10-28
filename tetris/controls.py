"""Physical key state and frame-stable horizontal DAS/ARR."""

class HorizontalRepeat:
    def __init__(self):
        self.reset()

    def reset(self):
        self.direction = 0
        self.das_elapsed = 0.0
        self.arr_elapsed = 0.0
        self.charged = False
        self.freeze_frames = 0

    def after_hard_drop(self):
        # Retain both charge and repeat phase; suppress only the current update.
        self.freeze_frames = 1

    def update(self, elapsed, direction, state, preferences):
        if self.freeze_frames:
            self.freeze_frames -= 1
            return
        if direction != self.direction:
            self.direction = direction
            self.das_elapsed = self.arr_elapsed = 0.0
            self.charged = False
            if direction and state.active is not None:
                state.move(direction, 0)
            return
        if not direction:
            return
        das = preferences.das_ms / 1000.0
        arr = preferences.arr_ms / 1000.0
        if not self.charged:
            self.das_elapsed += elapsed
            if self.das_elapsed + 1e-9 < das:
                return
            self.charged = True
            self.arr_elapsed = max(0.0, self.das_elapsed - das)
            if state.active is not None:
                state.move(direction, 0)
        else:
            self.arr_elapsed += elapsed
        if state.active is None:
            # Charge through line-clear delay, without building up movement debt.
            self.arr_elapsed = 0.0
            return
        if arr <= 0:
            while state.move(direction, 0):
                pass
            self.arr_elapsed = 0.0
        else:
            while self.arr_elapsed + 1e-9 >= arr:
                self.arr_elapsed = max(0.0, self.arr_elapsed - arr)
                if not state.move(direction, 0):
                    self.arr_elapsed = 0.0
                    break


class HeldKeys:
    def __init__(self):
        self.order = []

    def press(self, key):
        if key in self.order:
            return False
        self.order.append(key)
        return True

    def release(self, key):
        if key in self.order:
            self.order.remove(key)

    def clear(self):
        self.order.clear()

    def active(self, action, preferences):
        return any(preferences.matches(action, key) for key in self.order)

    def direction(self, preferences):
        for key in reversed(self.order):
            if preferences.matches("left", key):
                return -1
            if preferences.matches("right", key):
                return 1
        return 0
