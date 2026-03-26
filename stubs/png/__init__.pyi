from typing import Any, BinaryIO, Dict, List

class Image:
    def write(self, outfile: BinaryIO, packed: bool = False) -> None: ...
    @property
    def info(self) -> Dict[str, Any]: ...

def from_array(rows: List[List[int]], mode: str) -> Image: ...

class Writer:
    def __init__(
        self,
        width: int = ...,
        height: int = ...,
        greyscale: bool = False,
        alpha: bool = False,
        bitdepth: int = 8,
        palette: Any = None,
        compression: int | None = None,
        interlace: bool = False,
        gamma: float | None = None,
        compression_level: int | None = None,
    ) -> None: ...
    def write(
        self,
        outfile: BinaryIO,
        rows: List[List[int]],
    ) -> None: ...
