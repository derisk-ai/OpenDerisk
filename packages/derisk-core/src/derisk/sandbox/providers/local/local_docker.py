import docker
import os


def run_in_docker_sandbox(code, timeout=5):
    try:
        # 尝试显式指定 macOS 和 Linux 的通用连接方式
        client = docker.DockerClient(base_url='unix://var/run/docker.sock')
    except docker.errors.DockerException:
        # 回退到环境自动配置
        client = docker.from_env()

    # 创建临时目录存放代码
    os.makedirs("tmp_sandbox", exist_ok=True)
    script_path = "tmp_sandbox/script.py"
    with open(script_path, "w") as f:
        f.write(code)

    try:
        container = client.containers.run(
            "python:slim",
            command=f"timeout {timeout} python /sandbox/script.py",
            volumes={os.path.abspath("tmp_sandbox"): {"bind": "/sandbox", "mode": "ro"}},
            working_dir="/sandbox",
            stderr=True,
            stdout=True,
            remove=True,
            mem_limit="100m",
        )
        return container.decode('utf-8')
    except docker.errors.ContainerError as e:
        return f"Container Error: {e.stderr.decode('utf-8')}"
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)



if __name__ == "__main__":

    # 测试执行
    code = """
    print("Hello from sandbox!")
    import os
    print(os.listdir('/'))  # 显示容器内根目录
    """
    print(run_in_docker_sandbox(code))
