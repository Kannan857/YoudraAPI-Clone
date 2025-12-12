from enum import Enum


class Level(Enum):
    ROOT = 0
    BRANCH = 1
    LEAF = 999
class EntityType(Enum):
    MONTH = 1
    WEEK = 2
    DAY = 3
    ACTIVITY = 999
    MILESTONE = 1000
    TASK = 1001
class PlanStatus(Enum):
    TO_BE_STARTED = 0
    IN_PROGRESS = 1
    COMPLETE = 100
    APPROVED_BY_USER = 99
    NOT_APPLICABLE = -1
    NOT_APPROVED_BY_USER = -2

class TaskStatus(Enum):
    IN_PROGRESS = 1
    NOT_STARTED = 0
    COMPLETE  = 100
    