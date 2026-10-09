"""Output adapters: present application events in the selected mode.

Both adapters implement ``EventConsumer``; exactly one is registered with the
``EventPublisher`` per run. They
never decode protocols or touch transport state.
"""
