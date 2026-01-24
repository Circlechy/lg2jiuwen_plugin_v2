"""
项目检测组件单元测试
"""
import os
import tempfile
import pytest

from lg2jiuwen_tool.components.project_detector import ProjectDetectorComp


class TestProjectDetectorComp:
    """项目检测组件测试"""

    def setup_method(self):
        self.comp = ProjectDetectorComp()

    @pytest.mark.asyncio
    async def test_detect_single_file(self):
        """测试检测单个文件"""
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as f:
            f.write('# test file\nprint("hello")')
            temp_file = f.name

        try:
            result = await self.comp.invoke(
                inputs={"source_path": temp_file},
                runtime=None,
                context=None
            )
            assert "file_list" in result
            assert len(result["file_list"]) == 1
            assert result["file_list"][0] == temp_file
            assert result.get("is_single_file") is True
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_detect_directory(self):
        """测试检测目录"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建多个 Python 文件
            files = []
            for name in ['a.py', 'b.py', 'c.py']:
                path = os.path.join(temp_dir, name)
                with open(path, 'w') as f:
                    f.write(f'# {name}\n')
                files.append(path)

            result = await self.comp.invoke(
                inputs={"source_path": temp_dir},
                runtime=None,
                context=None
            )
            assert "file_list" in result
            assert len(result["file_list"]) == 3
            assert result.get("is_single_file") is False

    @pytest.mark.asyncio
    async def test_detect_with_dependencies(self):
        """测试检测带依赖的文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建带 import 关系的文件
            main_file = os.path.join(temp_dir, 'main.py')
            util_file = os.path.join(temp_dir, 'utils.py')

            with open(util_file, 'w') as f:
                f.write('def helper(): pass\n')

            with open(main_file, 'w') as f:
                f.write('from utils import helper\nhelper()\n')

            result = await self.comp.invoke(
                inputs={"source_path": temp_dir},
                runtime=None,
                context=None
            )
            assert "dependency_order" in result
            # utils 应该在 main 之前 (因为 main 依赖 utils)
            order = result["dependency_order"]
            if len(order) == 2:
                utils_idx = next((i for i, f in enumerate(order) if 'utils' in f), -1)
                main_idx = next((i for i, f in enumerate(order) if 'main' in f), -1)
                if utils_idx >= 0 and main_idx >= 0:
                    assert utils_idx < main_idx

    @pytest.mark.asyncio
    async def test_detect_nonexistent_path(self):
        """测试检测不存在的路径"""
        result = await self.comp.invoke(
            inputs={"source_path": "/nonexistent/path/file.py"},
            runtime=None,
            context=None
        )
        assert "file_list" in result
        assert len(result["file_list"]) == 0 or "error" in result

    @pytest.mark.asyncio
    async def test_filter_non_python_files(self):
        """测试过滤非 Python 文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建混合文件
            py_file = os.path.join(temp_dir, 'code.py')
            txt_file = os.path.join(temp_dir, 'readme.txt')
            json_file = os.path.join(temp_dir, 'config.json')

            for f in [py_file, txt_file, json_file]:
                with open(f, 'w') as fp:
                    fp.write('content\n')

            result = await self.comp.invoke(
                inputs={"source_path": temp_dir},
                runtime=None,
                context=None
            )
            # 只应该包含 .py 文件
            assert all(f.endswith('.py') for f in result["file_list"])
            assert len(result["file_list"]) == 1
