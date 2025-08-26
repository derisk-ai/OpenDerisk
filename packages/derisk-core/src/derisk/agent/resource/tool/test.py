import importlib


def instantiate_class(module_name, class_name, *args, **kwargs):
    # 动态导入模块
    module = importlib.import_module(module_name)

    # 获取类对象
    cls = getattr(module, class_name)

    # 实例化类并传递参数
    instance = cls(*args, **kwargs)

    return instance


def call_class_method(module_name, class_name, method_name, init_args=(), init_kwargs=None, method_args=(),
                      method_kwargs=None):
    init_kwargs = init_kwargs or {}
    method_kwargs = method_kwargs or {}

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    instance = cls(*init_args, **init_kwargs)
    method = getattr(instance, method_name)
    return method(*method_args, **method_kwargs)


if __name__ == '__main__':
    print(call_class_method("local.template", "LocalTime", "get_time", init_kwargs={'time': '2025'}))
