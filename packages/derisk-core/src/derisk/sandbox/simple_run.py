import asyncio
import datetime
import json
import os
import posixpath
import time

from derisk.configs.model_config import DATA_DIR
from derisk.sandbox.base import SandboxBase, DEFAULT_WORK_DIR
from derisk.sandbox.client.file.types import FileInfo
from derisk.sandbox.client.shell.type.shell_command_result import ShellCommandResult


async def main():
    print(f"create begin:{datetime.datetime.now()}")
    # template = "b0f63efd-6068-4fd6-a495-bcec99a36e73"
    template = "c589607d-7c7a-442c-bb20-a74ac62f273b"
    # template = "9c85374e-1564-4313-be9f-3432f576b19e"

    # Use DATA_DIR/skill for local development
    skill_dir = os.path.join(DATA_DIR, "skill")

    from derisk_ext.sandbox.xic.xic_client import XICSandbox

    xic_client: SandboxBase = await XICSandbox.create(
        user_id="184089",
        agent="sregpt",
        template=template,
        work_dir=DEFAULT_WORK_DIR,
        skill_dir=skill_dir,
    )

    file_dir = f"{xic_client.work_dir}/chat/test123"
    derisk_skill_dir = f"{xic_client.work_dir}/skills/derisk-knowledge"

    # resp: ShellCommandResult = await xic_client.shell.exec_command(command=f"npm install axios")
    # print("打开文件夹:" + json.dumps(resp.to_dict(), ensure_ascii=False))

    # resp1: ShellCommandResult = await xic_client.shell.exec_command(command=f" agent-browser --version")
    # resp1: ShellCommandResult = await xic_client.shell.exec_command(command=f"cd /home/ubuntu && export PATH='/home/ubuntu/.npm-global/bin:$PATH' && agent-browser --version")
    resp1: ShellCommandResult = await xic_client.shell.exec_command(
        command=f"export PATH='/usr/bin:/home/ubuntu/.npm-global/bin:$PATH' && agent-browser --version"
    )
    # resp1: ShellCommandResult = await xic_client.shell.exec_command(command=f"source ~/.bashrc && echo $PATH && which agent-browser && agent-browser --version")

    # resp1: ShellCommandResult = await xic_client.shell.exec_command(command="export PATH='/home/ubuntu/.npm-global/bin:$PATH' && agent-browser snapshot")
    # resp1: ShellCommandResult = await xic_client.shell.exec_command(command=f"cd {DEFAULT_WORK_DIR} && cat .derisk")
    print("打开文件夹:" + json.dumps(resp1.to_dict(), ensure_ascii=False))

    # resp2: ShellCommandResult = await xic_client.shell.exec_command(command="""python3 -c 'print("Hello World")'""")
    # print("打开文件夹:" + json.dumps(resp2.to_dict(), ensure_ascii=False))

    # resp: ShellCommandResult = await xic_client.shell.exec_command( command=f"git clone {git_url}")
    ## 创建路径
    # resp: ShellCommandResult = await xic_client.shell.exec_command( command=f"mkdir {file_dir}")
    # print("创建文件夹:"+json.dumps(resp.to_dict(), ensure_ascii=False))
    # ## 新增文件
    # file_path = f"{file_dir}/test_xic.txt"
    # file_info = await xic_client.file.create(path=file_path, user="tuyang.yhj")
    # #
    # ## 写内容
    # write_resp = await xic_client.file.write(file_path, data="测试xic的文件写和转存oss！\n ----\n 你好！", overwrite=True)
    # print("写结果:" + json.dumps(write_resp.to_dict(), ensure_ascii=False))
    # print(write_resp.content)
    # #
    # ##上传到xic的oss
    # xic_oss = await xic_client.file.upload_to_oss(file_path)
    # print("写xic oss结果:" + json.dumps(write_resp.to_dict(), ensure_ascii=False))
    # print(write_resp.content)
    #
    # ## 下载到sandbox本地
    #
    # ## 从sandbo 读结果
    # read_resp = await xic_client.file.read(file_path)
    # print("读结果:" + json.dumps(read_resp.to_dict(), ensure_ascii=False))
    # print(read_resp.content)

    # ## 写入文件内容
    # write_resp = await xic_client.file.write(file_path, data="测试xic的文件写和转存oss！\n ----\n 你好！", overwrite=True, save_oss=True)
    # print("文件写入:" + json.dumps(write_resp.to_dict(), ensure_ascii=False))
    # ## 输出文件的oss 预览地址
    # print("文件地址:" + write_resp.oss_info.temp_url)

    # chat_session_id = "chat_test_123"
    # conversation_id = "11231414"
    # conversation_dir = posixpath.join(xic_client.work_dir, f'{conversation_id}/999')
    # chat_file_path = posixpath.join(conversation_dir, "ai-sre2.txt")
    # ## 写入对话文件
    # write_resp = await xic_client.file.write_chat_file(chat_session_id,
    #                                                    file_name='ai-sre.txt',
    #                                                    data="这是一个对话数据测试文件内容！\n ----\n 你好！",
    #                                                    overwrite=True)
    # print("文件写入:" + json.dumps(write_resp.to_dict(), ensure_ascii=False))
    #
    # ## 释放沙箱
    # print(f"释放沙箱环境!{xic_client.sandbox_id}")
    # await asyncio.sleep(5)
    # await xic_client.kill(template="9c85374e-1564-4313-be9f-3432f576b19e")
    #
    # ## 恢复沙箱
    # re_sandbox = await XICSandbox.recovery(user_id="184089", agent="derisk", chat_session=chat_session_id,
    #                                                   template="9c85374e-1564-4313-be9f-3432f576b19e")
    #
    # ## 查看恢复文件
    # resp:FileInfo = await re_sandbox.file.read(path=f"{xic_client.work_dir}/chat/{chat_session_id}/ai-sre.txt")
    # print(f"对话文件：{json.dumps(resp.to_dict(), ensure_ascii=False)}")

    ## 释放沙箱
    print(f"释放沙箱环境!{xic_client.sandbox_id}")
    await asyncio.sleep(5)
    await xic_client.kill(template=template)

    ## 恢复沙箱a
    # re_sandbox = await XICSandbox.recovery(user_id="184089", agent="derisk",
    #                                                   conversation_id=conversation_id,
    #                                                   template="9c85374e-1564-4313-be9f-3432f576b19e")

    # ## 查看恢复文件
    # resp:FileInfo = await re_sandbox.file.read(path=chat_file_path)
    # print(f"对话文件：{json.dumps(resp.to_dict(), ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
