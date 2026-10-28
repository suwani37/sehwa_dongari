"""Battle rules and AI decisions, without launching a game window or EXE."""
import random
import unittest
import pygame

from tetris import settings
from tetris.ai import AIController, placement_search
from tetris.attacks import LockEvent, attack_lines, combo_bonus
from tetris.battle import BattleMatch, GarbagePacket
from tetris.board import Board
from tetris.game import Game
from tetris.piece import Piece
from tetris.preferences import PlayerSettings
from tetris.renderer import Renderer
from tetris.state import GameState


def finish_search(search):
    while True:
        try:
            next(search)
        except StopIteration as done:
            return done.value


def fake_lock(match, index, event):
    state = match.sides[index].state
    state.active = None
    state.awaiting_spawn = True
    state.lock_events.append(event)


class AttackTests(unittest.TestCase):
    def test_confirmed_base_damage(self):
        for spin, amounts in (("none",(0,0,1,2,4)),("mini",(0,1,2)),("full",(0,2,4,6))):
            for lines,expected in enumerate(amounts):
                self.assertEqual(attack_lines(LockEvent(lines,spin),1),expected)
        self.assertEqual(attack_lines(LockEvent(2,"full",False,True),5),6)
        self.assertEqual(attack_lines(LockEvent(1,"none",False,True),1),0)

    def test_confirmed_combo_boundaries_and_perfect_clear_override(self):
        for count,expected in ((0,0),(1,0),(2,0),(3,1),(5,1),(6,2),(9,2),(10,3),(99,3)):
            self.assertEqual(combo_bonus(count),expected)
        for lines in (1,2,3,4):
            self.assertEqual(attack_lines(LockEvent(lines,"none",True,True),99),10)
        self.assertEqual(attack_lines(LockEvent(0,"full",False,True),99),0)

    def test_combo_advances_on_clears_and_resets_on_no_clear(self):
        match = BattleMatch(seed=1)
        expected = (0,0,1,1,1,2,2,2,2,3,3)
        for index,damage in enumerate(expected,1):
            before = match.sides[1].pending
            match.player.lock_events.append(LockEvent(1))
            match.resolve_locks()
            self.assertEqual(match.sides[0].combo,index)
            self.assertEqual(match.sides[1].pending-before,damage)
        match.player.lock_events.append(LockEvent(0,"mini"))
        match.resolve_locks()
        self.assertEqual(match.sides[0].combo,0)

    def test_own_queue_is_cancelled_before_sending(self):
        match = BattleMatch(seed=1)
        side = match.sides[0]
        side.incoming.extend((GarbagePacket(3,2,5),GarbagePacket(2,7,5)))
        match.player.lock_events.append(LockEvent(4))
        match.resolve_locks()
        self.assertEqual((side.pending,match.sides[1].pending),(1,0))
        self.assertEqual(side.incoming[0].hole,7)
        match.player.lock_events.append(LockEvent(4,back_to_back=True))
        match.resolve_locks()
        self.assertEqual((side.pending,match.sides[1].pending),(0,4))

    def test_simultaneous_attacks_cancel_without_order_advantage(self):
        for swapped in (False,True):
            match = BattleMatch(seed=1)
            events = (LockEvent(4),LockEvent(2,"full")) if not swapped else (LockEvent(2,"full"),LockEvent(4))
            for side,event in zip(match.sides,events):
                side.state.lock_events.append(event)
            match.resolve_locks()
            self.assertEqual([side.pending for side in match.sides],[0,0])
        match = BattleMatch(seed=1)
        match.player.lock_events.append(LockEvent(4))
        match.ai.lock_events.append(LockEvent(3))
        match.resolve_locks()
        self.assertEqual([side.pending for side in match.sides],[0,2])


class GarbageTests(unittest.TestCase):
    def test_one_second_warning_and_maximum_four_rows(self):
        match = BattleMatch(seed=2)
        match.enqueue(0,10)
        hole = match.sides[0].incoming[0].hole
        match.time = .999
        fake_lock(match,0,LockEvent(0))
        match.resolve_locks()
        self.assertEqual(match.sides[0].received,0)
        for time,received,pending in ((1,4,6),(2,8,2),(3,10,0)):
            match.time = time
            fake_lock(match,0,LockEvent(0))
            match.resolve_locks()
            self.assertEqual(match.sides[0].received,received)
            self.assertEqual(match.sides[0].pending,pending)
        for row in match.player.board.grid[-10:]:
            self.assertEqual([x for x,v in enumerate(row) if v is None],[hole])

    def test_each_packet_changes_hole_and_clear_blocks_rise(self):
        match = BattleMatch(seed=3)
        match.enqueue(0,3)
        match.enqueue(0,2)
        first,second = match.sides[0].incoming
        self.assertNotEqual(first.hole,second.hole)
        match.time = 2
        fake_lock(match,0,LockEvent(1))
        match.resolve_locks()
        self.assertEqual((match.sides[0].pending,match.sides[0].received),(5,0))

    def test_garbage_is_applied_before_spawn_and_can_top_out(self):
        match = BattleMatch(seed=4)
        match.player.next_queue[0] = "T"
        match.player.board.grid[5][4] = "J"
        match.player.active = Piece("O",8,20)
        match.sides[0].incoming.append(GarbagePacket(4,9,0))
        match.player.hard_drop()
        self.assertIsNone(match.player.active)
        self.assertTrue(match.player.awaiting_spawn)
        match.resolve_locks()
        self.assertTrue(match.player.game_over)
        self.assertEqual(match.winner,"ai")

    def test_overflow_and_draw(self):
        board = Board(10,22)
        board.grid[0][0] = "J"
        self.assertTrue(board.add_garbage(1,9))
        self.assertEqual(len(board.grid),22)
        self.assertFalse(Board(10,22).add_garbage(4,9))
        for losses,expected in (((True,False),"ai"),((False,True),"player"),((True,True),"draw")):
            match = BattleMatch(seed=5)
            match.player.game_over, match.ai.game_over = losses
            match.resolve_locks()
            self.assertTrue(match.finished)
            self.assertEqual(match.winner,expected)

    def test_real_clear_emits_damage_only_after_animation(self):
        match = BattleMatch(seed=6)
        match.player.active = Piece("I",6,20)
        match.player.board.grid[-1][:6] = ["J"]*6
        match.player.hard_drop()
        match.tick(.1)
        self.assertEqual(match.sides[1].pending,0)
        match.tick(.1)
        self.assertEqual(match.sides[1].pending,10)
        self.assertAlmostEqual(match.sides[1].incoming[0].ready_at,1.2)
        self.assertIsNotNone(match.player.active)

    def test_real_back_to_back_tetris_generates_four_then_five(self):
        match = BattleMatch(seed=11)
        for expected in (4,9):
            match.player.board.grid[8][0] = "J"
            for row in match.player.board.grid[-4:]:
                row[:9] = ["J"]*9
            match.player.active = Piece("I",7,18,1)
            match.player.hard_drop()
            match.tick(.2)
            self.assertEqual(match.sides[1].pending,expected)

    def test_real_t_spin_double_generates_four(self):
        match = BattleMatch(seed=12)
        piece = Piece("T",4,18,2)
        occupied = set(piece.cells())
        for y in (19,20):
            for x in range(10):
                if (x,y) not in occupied:
                    match.player.board.grid[y][x] = "J"
        match.player.board.grid[18][4] = "J"
        match.player.active = piece
        match.player.last_rotation = True
        match.player.last_kick_index = 0
        match.player.hard_drop()
        match.tick(.2)
        self.assertEqual(match.player.last_clear_type,"T-SPIN DOUBLE")
        self.assertEqual(match.sides[1].pending,4)

    def test_pause_freezes_clock_garbage_and_ai(self):
        match = BattleMatch(seed=7)
        match.enqueue(0,4)
        match.set_paused(True)
        match.tick(60)
        self.assertEqual(match.time,0)
        self.assertEqual(match.controller.age,0)
        self.assertEqual(match.sides[0].pending,4)
        self.assertTrue(match.player.paused and match.ai.paused)
        match.set_paused(False)
        match.tick(.1)
        self.assertAlmostEqual(match.time,.1)

    def test_same_seed_gives_independent_equal_piece_sequences(self):
        match = BattleMatch(seed=8)
        self.assertEqual(match.player.active.kind,match.ai.active.kind)
        self.assertEqual(list(match.player.next_queue),list(match.ai.next_queue))
        for _ in range(15):
            self.assertEqual(match.player.next_queue[0],match.ai.next_queue[0])
            match.player._spawn_next()
            match.ai._spawn_next()


class AIAndFlowTests(unittest.TestCase):
    def test_plans_are_legal_reachable_and_grounded(self):
        state = GameState(mode="battle")
        state.active = Piece("T",3,1)
        for x in (0,1,2,7,8,9):
            state.board.grid[-1][x] = "G"
        plans = finish_search(placement_search(state.board,state.active))
        self.assertTrue(plans)
        for plan in plans:
            replay = GameState(mode="battle")
            replay.board.grid = [row[:] for row in state.board.grid]
            replay.active = state.active
            for action in plan.actions:
                if action in ("left","right"):
                    self.assertTrue(replay.move(-1 if action == "left" else 1,0))
                elif action == "down":
                    self.assertTrue(replay.step_down())
                else:
                    self.assertTrue(replay.rotate(1 if action == "cw" else -1))
            self.assertEqual(replay.active,plan.piece)
            self.assertTrue(replay.is_grounded())
            self.assertTrue(replay.board.can_place(plan.piece))

    def test_ai_search_work_is_bounded_per_update(self):
        state = GameState(mode="battle")
        controller = AIController("hard",random.Random(1))
        visited = []
        def work():
            while True:
                visited.append(1)
                yield None
        controller.serial = state.spawn_serial
        controller.age = controller.interval
        controller.search = work()
        controller.start = state.active
        controller.node_budget = 7
        controller.time_budget = 10
        controller.update(1/60,state)
        self.assertEqual(len(visited),7)

    def test_ai_places_several_pieces_without_teleporting(self):
        state = GameState(mode="battle")
        controller = AIController("hard",random.Random(1))
        initial = state.spawn_serial
        for _ in range(420):
            controller.update(1/60,state)
            state.tick(1/60)
        self.assertGreaterEqual(state.spawn_serial-initial,3)
        self.assertFalse(state.game_over)

    def test_mode_difficulty_pause_and_retry_routing(self):
        game = Game(PlayerSettings())
        game.open("modes")
        game.selected = 3
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN))
        self.assertEqual(game.view,"difficulty")
        game.selected = 2
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN))
        self.assertEqual((game.view,game.state.mode,game.difficulty),("game","battle","hard"))
        match = game.battle
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE))
        self.assertEqual(game.view,"pause")
        self.assertTrue(match.paused)
        game.selected = 1
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN))
        game.tick(50)
        self.assertEqual(match.time,0)
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE))
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE))
        match.ai.game_over = True
        game.tick(1/60)
        self.assertEqual((game.view,match.winner),("result","player"))
        for key in (pygame.K_r,pygame.K_SPACE,pygame.K_RETURN,pygame.K_ESCAPE,pygame.K_DOWN):
            game.handle_event(pygame.event.Event(pygame.KEYDOWN,key=key))
            self.assertEqual(game.view,"result")
            self.assertIs(game.battle,match)
            self.assertEqual(game.selected,0)
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,
                                            pos=Renderer.pause_button_rect(0).center))
        self.assertEqual(game.view,"game")
        self.assertIsNot(game.battle,match)
        self.assertEqual(game.battle.difficulty,"hard")

    def test_battle_and_result_surfaces_fit_both_languages(self):
        pygame.font.init()
        try:
            surface = pygame.Surface((settings.WINDOW_WIDTH,settings.WINDOW_HEIGHT))
            for language in ("en","ko"):
                prefs = PlayerSettings(language=language)
                renderer = Renderer(surface,prefs)
                match = BattleMatch(prefs,seed=9)
                match.player.hold()
                match.enqueue(0,12)
                match.enqueue(1,3)
                match.player.last_clear_type = "T-SPIN MINI DOUBLE"
                match.player.last_clear_perfect = True
                match.player.clear_notice_timer = 2
                match.player.board.add_garbage(2,5)
                renderer.draw_modes(3)
                renderer.draw_difficulty(2)
                renderer.draw_battle(match)
                renderer.draw_pause(match.player,battle=match)
                match.winner = "player"
                renderer.draw_result(match.player,battle=match)
                for index in (0,1):
                    self.assertTrue(surface.get_rect().contains(renderer.battle_board_rect(index)))
                self.assertGreater(renderer.battle_board_rect(1).left,
                                   renderer.battle_board_rect(0).right)
        finally:
            pygame.font.quit()


if __name__ == "__main__":
    unittest.main()
