"""Controllers: application behavior applied to decoded results.

Controllers receive structured results (never raw frames or payload bytes),
update ``ApplicationState`` and publish application events. They never decode,
reassemble, render or serialize, and they never import route configuration.
"""
