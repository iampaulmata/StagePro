import time

from PySide6.QtCore import Qt


def exit_combo_active(pressed_keys: set[int]) -> bool:
    pg_pair = (Qt.Key_PageUp in pressed_keys) and (Qt.Key_PageDown in pressed_keys)
    lr_pair = (Qt.Key_Left in pressed_keys) and (Qt.Key_Right in pressed_keys)
    return pg_pair or lr_pair


def start_or_stop_exit_timer(exit_timer, exit_hold_ms: int, pressed_keys: set[int]) -> None:
    if exit_combo_active(pressed_keys):
        if not exit_timer.isActive():
            exit_timer.start(exit_hold_ms)
    else:
        if exit_timer.isActive():
            exit_timer.stop()


def exit_if_still_held(pressed_keys: set[int], close_callback) -> None:
    if exit_combo_active(pressed_keys):
        close_callback()


def maybe_handle_onstage_toggle_combo(
    key: int,
    combo_latched: bool,
    last_pedal_down: dict[int, int],
    combo_window_ms: int,
    toggle_mode_callback,
) -> bool:
    """Detect a quick 'both footswitch buttons' press."""
    if key not in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Left, Qt.Key_Right):
        return False

    # Don't retrigger until both keys are released.
    if combo_latched:
        return False

    now_ms = int(time.monotonic() * 1000)
    last_pedal_down[key] = now_ms

    if key in (Qt.Key_PageUp, Qt.Key_PageDown):
        other = Qt.Key_PageDown if key == Qt.Key_PageUp else Qt.Key_PageUp
    else:
        other = Qt.Key_Right if key == Qt.Key_Left else Qt.Key_Left

    other_ts = last_pedal_down.get(other)
    if other_ts is None:
        return False

    if abs(now_ms - other_ts) <= combo_window_ms:
        toggle_mode_callback()
        return True

    return False
