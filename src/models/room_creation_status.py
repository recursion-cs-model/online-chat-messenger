from enum import Enum


class RoomCreationStatus(Enum):
    REQUEST = 0
    ACKNOWLEDGE = 1
    COMPLETE = 2
