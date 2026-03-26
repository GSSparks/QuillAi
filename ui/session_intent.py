from ui.intent_tracker import IntentTracker

_tracker: IntentTracker = None


def get_tracker() -> IntentTracker:
    global _tracker
    if _tracker is None:
        _tracker = IntentTracker()
    return _tracker


def init_tracker(memory_manager):
    global _tracker
    _tracker = IntentTracker(memory_manager=memory_manager)
    return _tracker