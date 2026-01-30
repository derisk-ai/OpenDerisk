from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, TypedDict, Union, IO, Dict


class FileType(Enum):
    """
    Enum representing the type of filesystem object.
    """

    FILE = "file"
    """
    Filesystem object is a file.
    """
    DIR = "dir"
    """
    Filesystem object is a directory.
    """



@dataclass
class WriteInfo:
    """
    Sandbox filesystem object information.
    """

    name: str
    """
    Name of the filesystem object.
    """
    type: Optional[FileType]
    """
    Type of the filesystem object.
    """
    path: str
    """
    Path to the filesystem object.
    """
    def to_dict(self):
        return asdict(self)


@dataclass
class EntryInfo(WriteInfo):
    """
    Extended sandbox filesystem object information.
    """

    size: int
    """
    Size of the filesystem object in bytes.
    """
    mode: int
    """
    File mode and permission bits.
    """
    permissions: str
    """
    String representation of file permissions (e.g. 'rwxr-xr-x').
    """
    owner: str
    """
    Owner of the filesystem object.
    """
    group: str
    """
    Group owner of the filesystem object.
    """
    modified_time: datetime
    """
    Last modification time of the filesystem object.
    """
    symlink_target: Optional[str] = None
    """
    Target of the symlink if the filesystem object is a symlink.
    If the filesystem object is not a symlink, this field is None.
    """

    def to_dict(self):
        return asdict(self)

class WriteEntry(TypedDict):
    """
    Contains path and data of the file to be written to the filesystem.
    """

    path: str
    data: Union[str, bytes, IO]


@dataclass
class OSSFile:
    object_name: str
    object_url: Optional[str]  = None
    status: Optional[str] = None
    temp_url: Optional[str] = None
    expiration: Optional[int] = None
    url: Optional[str] = None


    def to_dict(self):
        return asdict(self)

@dataclass
class FileInfo:
    """
    Contains path and data of the file to be written to the filesystem.
    """

    path: str
    content: Optional[str] = None
    name: Optional[str] = None
    old_content: Optional[str] = None
    oss_info: Optional[OSSFile] = None
    last_modify: Optional[datetime] = None
    last_editor: Optional[str] = None

    def to_dict(self):
        return asdict(self)



@dataclass
class TaskResult:
    start: int
    end: int
    status: str
    detail:  Dict
    def to_dict(self):
        return asdict(self)