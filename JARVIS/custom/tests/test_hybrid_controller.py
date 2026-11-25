"""Tests for Maya AI Hybrid Mode Controller."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.hybrid_controller import (
    HybridController,
    Controller,
    TaskStatus,
)


def test_initial_state():
    hc = HybridController(sleep_fn=lambda x: None)
    assert hc.current_controller() == Controller.NONE
    st = hc.status()
    assert st.controller == Controller.NONE
    assert st.ai_busy is False
    assert st.queued_tasks == 0
    assert st.conflicts == 0


def test_user_acquire():
    hc = HybridController(sleep_fn=lambda x: None)
    assert hc.acquire(Controller.USER) is True
    assert hc.is_controlled_by(Controller.USER) is True
    assert hc.current_controller() == Controller.USER


def test_ai_acquire_when_free():
    hc = HybridController(sleep_fn=lambda x: None)
    assert hc.acquire(Controller.AI) is True
    assert hc.is_controlled_by(Controller.AI) is True


def test_ai_cannot_acquire_when_user_holds():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.USER)
    assert hc.acquire(Controller.AI) is False
    assert hc.is_controlled_by(Controller.USER) is True


def test_user_takes_over_from_ai():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    tid = hc.queue_task("test task")
    # start running
    t = hc.next_task()
    assert t is not None and t.id == tid
    # user takeover cancels running task
    assert hc.acquire(Controller.USER) is True
    task = hc.get_task(tid)
    assert task.status == TaskStatus.CANCELLED
    assert hc.is_controlled_by(Controller.USER) is True


def test_release():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.USER)
    assert hc.release(Controller.USER) is True
    assert hc.current_controller() == Controller.NONE
    # release wrong controller fails
    hc.acquire(Controller.AI)
    assert hc.release(Controller.USER) is False


def test_takeover():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    assert hc.takeover(Controller.USER) is True
    assert hc.is_controlled_by(Controller.USER) is True


def test_queue_and_next_task():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    tid = hc.queue_task("do something")
    assert tid.startswith("t_")
    t = hc.next_task()
    assert t is not None
    assert t.description == "do something"
    assert t.status == TaskStatus.RUNNING
    # no second task while running
    assert hc.next_task() is None


def test_complete_task():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    tid = hc.queue_task("job")
    hc.next_task()
    assert hc.complete_task(tid, result="ok", ok=True) is True
    task = hc.get_task(tid)
    assert task.status == TaskStatus.DONE
    assert task.result == "ok"
    assert task.finished_at is not None
    assert hc.status().running_task is None


def test_fail_task():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    tid = hc.queue_task("job")
    hc.next_task()
    hc.complete_task(tid, result="boom", ok=False)
    task = hc.get_task(tid)
    assert task.status == TaskStatus.FAILED
    assert task.error == "boom"


def test_cancel_task():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    tid = hc.queue_task("job")
    assert hc.cancel_task(tid) is True
    task = hc.get_task(tid)
    assert task.status == TaskStatus.CANCELLED
    # cancel again fails
    assert hc.cancel_task(tid) is False


def test_cancel_all_ai():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    hc.queue_task("a")
    hc.queue_task("b")
    hc.next_task()
    n = hc.cancel_all_ai()
    assert n >= 1
    assert hc.status().queued_tasks == 0
    assert hc.status().running_task is None
    assert hc._ai_paused is True


def test_ai_cannot_act_when_user_controls():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.USER)
    assert hc.ai_can_act() is False


def test_ai_can_act_when_free_or_ai():
    hc = HybridController(sleep_fn=lambda x: None)
    assert hc.ai_can_act() is True
    hc.acquire(Controller.AI)
    assert hc.ai_can_act() is True


def test_conflict_counter():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.USER)
    hc.acquire(Controller.AI)  # conflict
    assert hc.status().conflicts == 1


def test_list_tasks():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    hc.queue_task("x")
    hc.queue_task("y")
    tasks = hc.list_tasks()
    assert len(tasks) == 2
    assert [t.description for t in tasks] == ["x", "y"]


def test_status_to_dict():
    hc = HybridController(sleep_fn=lambda x: None)
    d = hc.status().to_dict()
    assert "controller" in d
    assert "ai_busy" in d
    assert "queued_tasks" in d
    assert "conflicts" in d


def test_summary():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    hc.queue_task("z")
    s = hc.summary()
    assert "status" in s
    assert "tasks" in s
    assert len(s["tasks"]) == 1


def test_listener():
    hc = HybridController(sleep_fn=lambda x: None)
    events = []
    hc.on_status_change(lambda st: events.append(st))
    hc.acquire(Controller.USER)
    assert len(events) >= 1
    assert events[-1].controller == Controller.USER


def test_listener_exception_no_crash():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.on_status_change(lambda st: (_ for _ in ()).throw(ValueError("boom")))
    hc.acquire(Controller.USER)  # should not raise


def test_reset():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.USER)
    hc.queue_task("t")
    hc.reset()
    assert hc.current_controller() == Controller.NONE
    assert hc.status().queued_tasks == 0
    assert hc.status().conflicts == 0


def test_next_task_blocked_when_paused():
    hc = HybridController(sleep_fn=lambda x: None)
    hc.acquire(Controller.AI)
    hc.queue_task("job")
    hc.cancel_all_ai()  # pauses AI
    hc.acquire(Controller.AI)  # re-acquire? paused flag still true from cancel_all
    # paused blocks next_task even if controller is AI
    # reset paused by re-acquire? acquire(AI) sets paused False only when granting
    # Force paused state check:
    hc2 = HybridController(sleep_fn=lambda x: None)
    hc2.acquire(Controller.AI)
    hc2.queue_task("job2")
    hc2._ai_paused = True
    assert hc2.next_task() is None


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"✓ {t.__name__} passed")
    print(f"\nAll {len(tests)} hybrid controller tests passed!")
