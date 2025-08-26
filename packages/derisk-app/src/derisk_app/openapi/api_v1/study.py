import json

from derisk_app.openapi.api_view_model import ConversationVo

if __name__ == "__main__":
    ss = """
    {
	"user_input": {
		"role": "user",
		"content": [{
			"type": "image_url",
			"image_url": {
				"url": "derisk-fs://distributed/derisk_app_file/d2b08e6e-4dd9-4a9f-a2bf-68b60974f25e?user_name=001&conv_uid=04044188-8197-11f0-9219-a62ccd5aa23e",
				"file_name": "profile.test.svg"
			}
		}, {
			"type": "text",
			"text": "分析下"
		}]
	},
	"team_mode": "auto_plan",
	"app_config_code": "2817c20f06974593939b13d6ae4504c4",
	"conv_uid": "04044188-8197-11f0-9219-a62ccd5aa23e",
	"ext_info": {
		"vis_render": "derisk_vis_window2",
		"incremental": true
	},
	"app_code": "flamegraph_analysis",
	"chat_in_params": [{
		"param_type": "resource",
		"param_value": "{\"is_oss\":true,\"file_path\":\"derisk-fs://distributed/derisk_app_file/d2b08e6e-4dd9-4a9f-a2bf-68b60974f25e?user_name=001&conv_uid=04044188-8197-11f0-9219-a62ccd5aa23e\",\"file_name\":\"profile.test.svg\",\"file_learning\":false,\"bucket\":\"derisk_app_file\"}",
		"sub_type": "common_file"
	}]
}
    """

    s2 = "{\"is_oss\":true,\"file_path\":\"derisk-fs://distributed/derisk_app_file/d2b08e6e-4dd9-4a9f-a2bf-68b60974f25e?user_name=001&conv_uid=04044188-8197-11f0-9219-a62ccd5aa23e\",\"file_name\":\"profile.test.svg\",\"file_learning\":false,\"bucket\":\"derisk_app_file\"}"
    try:
        # data2 = json.loads(s2)
        # print(f"test:{data2}")

        data = json.loads(ss)
        model = ConversationVo.model_validate(data)
        print(f"test:{model}")
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
    except Exception as e:
        print(f"Other error: {e}")





