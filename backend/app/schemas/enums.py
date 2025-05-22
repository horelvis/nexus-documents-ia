import enum

class IndexingStatus(enum.IntEnum):
    NOT_INDEXED = 0  # Default state, or if processing hasn't started for some reason
    INDEXED = 1
    INDEXING_ERROR = 2
    PROCESSING = 3   # Document is currently being processed
