import json
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from pydantic import BaseModel

from derisk_client.schema import BaseAssetModel


class ToolParameterModel(BaseModel):
    """Tool Parameter Model"""
    param_name: str
    param_type: str
    param_description: str = None
    is_required: bool


class ToolModel(BaseAssetModel):
    """Tool Model"""
    tool_id: str
    tool_name: str
    tool_description: str = None
    sub_tool_name: Optional[str] = None
    sub_tool_description: Optional[str] = None
    tool_type: str = None
    tool_parameters: Optional[List[ToolParameterModel]] = None
    creator: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            tool_id=d["tool_id"],
            tool_name=d["name"],
            tool_type=d["type"],
            asset_type="tool",
            tags=[d.get("tag") if d.get("tag") else "其他"],
            sub_tool_name=d.get("sub_name", None),
            tool_description=d.get("description", ""),
            creator=d.get("owner", None),
            sub_tool_description=d.get("sub_description", None),
        )


class ToolClient:
    """
    A client for interacting with the Alipay Tool Base API.
    """

    def __init__(self,
                 nex_client_id: Optional[str] = None,
                 nex_token: Optional[str] = None,
                 deriskcore_prod_base_url: str = "",
                 ):
        self.nex_client_id = nex_client_id
        self.nex_token = nex_token
        self.deriskcore_prod_base_url = deriskcore_prod_base_url
        self.tool_detail_query_url = f"{self.deriskcore_prod_base_url}/api/v1/tool_detail/query_all"

    def get_tool_list(self) -> List[ToolModel]:
        """
        Get tool list.
        """

        response = requests.get(url=self.tool_detail_query_url)
        if response.status_code == 200:
            result = response.json()
            data, res = result.get('data', []), []
            for item in data:
                tool_model = ToolModel.from_dict(item)
                create_dt_object = datetime.strptime(item.get(
                        'gmt_create'), "%Y-%m-%dT%H:%M:%S")
                tool_model.create_time = create_dt_object.strftime("%Y-%m-%d %H:%M:%S")
                update_dt_object = datetime.strptime(item.get(
                    'gmt_modified'), "%Y-%m-%dT%H:%M:%S")
                tool_model.update_time = update_dt_object.strftime("%Y-%m-%d %H:%M:%S")
                tool_schema = json.loads(item.get('input_schema', None))
                parameters_data = tool_schema['properties']
                if tool_model.tool_name=="测试6":
                    continue
                param_name = ""
                param_type = ""
                param_description = ""
                is_required = False
                tool_parameters = []
                for param_name, param_details in parameters_data.items():
                    param_type = param_details.get('type',
                                                   'unknown')
                    param_description = param_details.get(
                        'description')
                    is_required = param_details.get('required',
                                                    False)
                    tool_parameters.append(ToolParameterModel(
                        param_name=param_name,
                        param_type=param_type,
                        param_description=param_description or "",
                        is_required=is_required
                    ))
                # tool_model.tool_schema = tool_schema
                tool_model.tool_parameters = tool_parameters
                res.append(tool_model)
            return res
        else:
            raise ValueError(f"获取工具列表失败！{response.text}")

    def get_tool_by_id(self, tool_id: str) -> ToolModel:
        """
        Get tool by id.
        """
        tool_detail_query = {
            'tool_id': tool_id
        }
        response = requests.post(self.tool_detail_query_url, json=tool_detail_query)
        if response.status_code == 200:
            result = response.json()
            data = result.get('data', {})
            return ToolModel.from_dict(data)
        else:
            raise ValueError(f"获取工具失败！{response.text}")


if __name__ == "__main__":
    tool_client = ToolClient()
    tool_list = tool_client.get_tool_list()
    print(tool_list)
