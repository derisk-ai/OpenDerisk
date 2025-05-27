from derisk.util.singleton import Singleton
from derisk.util.tracer import root_tracer
from derisk_app.scene.base_chat import BaseChat


class ChatFactory(metaclass=Singleton):
    @staticmethod
    def get_implementation(chat_mode, system_app, **kwargs):
        # Lazy loading
        from derisk_app.scene.chat_dashboard.chat import ChatDashboard  # noqa: F401
        from derisk_app.scene.chat_dashboard.prompt import prompt  # noqa: F401
        from derisk_app.scene.chat_data.chat_excel.excel_analyze.chat import (  # noqa: F401
            ChatExcel,
        )
        from derisk_app.scene.chat_data.chat_excel.excel_analyze.prompt import (  # noqa: F401,F811
            prompt,
        )
        from derisk_app.scene.chat_data.chat_excel.excel_learning.prompt import (  # noqa: F401, F811
            prompt,
        )
        from derisk_app.scene.chat_db.auto_execute.chat import (  # noqa: F401
            ChatWithDbAutoExecute,
        )
        from derisk_app.scene.chat_db.auto_execute.prompt import (  # noqa: F401,F811
            prompt,
        )
        from derisk_app.scene.chat_db.professional_qa.chat import (  # noqa: F401
            ChatWithDbQA,
        )
        from derisk_app.scene.chat_db.professional_qa.prompt import (  # noqa: F401, F811
            prompt,
        )
        from derisk_app.scene.chat_knowledge.refine_summary.chat import (  # noqa: F401
            ExtractRefineSummary,
        )
        from derisk_app.scene.chat_knowledge.refine_summary.prompt import (  # noqa: F401,F811
            prompt,
        )
        from derisk_app.scene.chat_knowledge.v1.chat import ChatKnowledge  # noqa: F401
        from derisk_app.scene.chat_knowledge.v1.prompt import prompt  # noqa: F401,F811
        from derisk_app.scene.chat_normal.chat import ChatNormal  # noqa: F401
        from derisk_app.scene.chat_normal.prompt import prompt  # noqa: F401,F811

        chat_classes = BaseChat.__subclasses__()
        implementation = None
        for cls in chat_classes:
            if cls.chat_scene == chat_mode:
                metadata = {"cls": str(cls)}
                with root_tracer.start_span(
                    "get_implementation_of_chat", metadata=metadata
                ):
                    implementation = cls(**kwargs, system_app=system_app)
        if implementation is None:
            raise Exception(f"Invalid implementation name:{chat_mode}")
        return implementation
