from typing import Dict, Optional

from derisk._private.pydantic import BaseModel


class ExtConfigHolder(BaseModel):
    ext_config: Optional[Dict] = None
